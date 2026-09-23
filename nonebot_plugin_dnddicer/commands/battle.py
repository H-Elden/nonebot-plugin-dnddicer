"""战斗轮命令：``.br`` / ``.回合`` / ``.轮次`` / ``.ed``。

战斗轮不是独立系统，而是**先攻表的"进行中状态机"**——复用
data/initiative.py 的 InitList（实体列表 + round/turn 指针），本模块只做
查看/跳转/推进与播报：

- ``.br`` / ``.战斗轮``：新建战斗轮（清空本群先攻表与指针，重新开局）；
- ``.回合`` / ``.轮次``（无参数）：查看当前轮/回合；
- ``.回合 +n / -n / =n / n``：回合前移/后移/直接跳转（溢出自动进位/退位）；
- ``.回合 名字``：按名字跳转（精确 → 模糊，无/多结果报错）；``.回合 @玩家``
  按归属定位该玩家的条目（改名/同名歧义不受影响，见 2026-09-22 的 @ 目标支持）；
- ``.轮次 n``：对轮次做查看/加减/跳转；
- ``.ed`` / ``.结束``：结束当前回合——播报 + 自动推进下一位；一轮走完自动
  进位播报；轮到绑定 QQ 的玩家时输出 @ 提醒。

名称显示为入表时快照（不做实时刷新）；BUFF 计时表不做。
"""

from __future__ import annotations

from typing import List, Optional

from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageEvent
from nonebot.matcher import Matcher

from ..data.initiative import clear_init_list, get_init_list, save_init_list
from ..initiative.models import InitList
from ..platform.onebot_v11 import at_reply, at_segment, parse_mention_token
from . import base, text
from .initiative import cleanup_temp_npc_health

_HELP_BR = (
    ".br 或 .战斗轮 开始新的战斗轮\n"
    ".init 或 .先攻 查阅当前先攻表\n"
    ".ri+<调整值> 投掷先攻\n"
    ".回合 或 .轮次 查看当前轮次与回合\n"
    ".轮次<数值> 设置轮次数值\n"
    ".回合<数值> 设置当前进行到的回合\n"
    ".ed 或 .结束 在自己回合中宣言回合结束"
)
_HELP_TURN = (
    "查看或修改当前回合：.回合 / .回合+1 / .回合-1 / .回合=2 / .回合 名字"
    " / .回合 @玩家\n"
    "名字精确优先再模糊；@玩家 按归属定位条目（改名不受影响）。"
    "回合越界会自动进位/退位轮次。"
)
_HELP_ROUND = (
    "查看或修改当前轮次：.轮次 / .轮次+1 / .轮次-1 / .轮次=3\n"
    "回合越界会自动进位/退位轮次。"
)
_HELP_ED = "结束当前回合，自动推进到下一位并播报；一轮走完自动进入下一轮。"

br_matcher = base.on_dnd_command("br", _HELP_BR, aliases=("battleroll", "战斗轮"))
turn_matcher = base.on_dnd_command("turn", _HELP_TURN, aliases=("回合",))
round_matcher = base.on_dnd_command("round", _HELP_ROUND, aliases=("轮次",))
ed_matcher = base.on_dnd_command("ed", _HELP_ED, aliases=("结束",))


async def _load_battle(event: GroupMessageEvent) -> InitList:
    """读取本群战斗状态；无先攻表/空表则回复并结束。"""
    init_data = await get_init_list(event.group_id)
    if init_data is None or not init_data.entities:
        await ed_matcher.finish(text.TXT_BR_NO_INIT)
    return init_data  # type: ignore[return-value]  # finish 已抛异常


def _clamp_round_target(
    init_data: InitList, target_round: int, target_turn: int
) -> "tuple[int, int]":
    """回合/轮次越界修正：溢出进位、退位回绕。"""
    turns_in_round = init_data.turns_in_round
    if turns_in_round > 0:
        if target_turn > turns_in_round:
            overflow = target_turn - 1
            target_round += overflow // turns_in_round
            target_turn = (overflow % turns_in_round) + 1
        elif target_turn < 1:
            deficit = 1 - target_turn
            round_back = (deficit + turns_in_round - 1) // turns_in_round
            target_round = max(1, target_round - round_back)
            target_turn = turns_in_round - ((deficit - 1) % turns_in_round)
    return target_round, target_turn


async def _finish_battle_lines(
    matcher: Matcher,
    rows: List[str],
    at_name: str = "",
    at_owner: str = "",
) -> None:
    """播报行收尾发送（行间换行）。

    at_owner 非空（下一行动者绑定 QQ）时，末行拆为「at 前缀文本 +
    @消息段 + at 后缀文本」组装消息（@ 用 onebot v11 MessageSegment.at，
    弃用原 CQ 码文本拼接）；前序行 + at 前缀合并为单个文本段。
    无 at 时按纯文本发送（与既有输出一致）。
    """
    if not at_owner:
        await matcher.finish("\n".join(rows))
        return
    head = "\n".join(rows)
    at_head = text.TXT_BR_TURN_NEW_WITH_AT_PREFIX.format(turn_name=at_name)
    msg = Message((head + "\n" if head else "") + at_head)
    msg += at_segment(at_owner)
    msg += text.TXT_BR_TURN_NEW_WITH_AT_SUFFIX
    await matcher.finish(msg)


def _parse_num_mod(arg_str: str) -> "tuple[Optional[int], str]":
    """解析回合/轮次的数值修改参数 → (修改量, 错误文案)。

    参数语义：``+n``/``++``/``+`` 增加，``-n`` 减少，``=n``/裸数字 直接设定。
    返回 (None, 错误文案) 表示非数字。
    """
    if arg_str.startswith("+") or arg_str.startswith("-"):
        if arg_str in ("++", "+", "--", "-"):
            return (1 if arg_str.startswith("+") else -1), ""
        if arg_str[1:].isdigit():
            value = int(arg_str[1:])
            return (value if arg_str.startswith("+") else -value), ""
        return None, text.TXT_BR_ERROR_NOT_NUMBER
    if arg_str.startswith("="):
        if arg_str[1:].isdigit():
            return int(arg_str[1:]), ""
        return None, text.TXT_BR_ERROR_NOT_NUMBER
    if arg_str.isdigit():
        return int(arg_str), ""
    return None, text.TXT_BR_ERROR_NOT_NUMBER


def _find_turn_target(intent: str, names: List[str]) -> "tuple[Optional[str], str]":
    """按名字找回合目标：精确（大小写不敏感）→ 模糊 substring。

    返回 (目标名, 错误文案)；错误文案非空时需直接回复。
    """
    exact = [n for n in names if n.lower() == intent.lower()]
    if len(exact) > 1:
        return None, text.TXT_BR_ERROR_TOO_MUCH_FOUND
    if len(exact) == 1:
        return exact[0], ""
    fuzzy = list(dict.fromkeys(n for n in names if intent.lower() in n.lower()))
    if len(fuzzy) == 0:
        return None, text.TXT_BR_ERROR_NOT_FOUND
    if len(fuzzy) > 1:
        return None, text.TXT_BR_ERROR_TOO_MUCH_FOUND
    return fuzzy[0], ""


async def _handle_turn_round(event: GroupMessageEvent, mode: str) -> None:
    """处理 .回合/.轮次（mode: "turn" / "round"）。"""
    arg_str = (base.get_command_rest_with_mentions(event) or "").strip()
    init_data = await _load_battle(event)
    if not init_data.entities:
        await turn_matcher.finish(text.TXT_BR_NO_INIT)

    entity_count = len(init_data.entities)
    turns_in_round = entity_count if entity_count else 1
    prev_round = init_data.round
    prev_turn = init_data.turn
    target_round = prev_round
    target_turn = prev_turn
    query_only = arg_str == ""

    if not query_only:
        # 数值修改（+n/-n/=n/裸数字）
        if arg_str[0] in "+-=" or arg_str.isdigit():
            mod_value, error = _parse_num_mod(arg_str)
            if error:
                await turn_matcher.finish(error)
            if mode == "turn":
                if arg_str.startswith("=") or arg_str.isdigit():
                    # 直接设定回合：=n 校验范围，裸数字由下方越界修正自动进位
                    if arg_str.startswith("=") and (
                        mod_value > turns_in_round or mod_value < 1
                    ):
                        await turn_matcher.finish(
                            text.TXT_BR_ERROR_TOO_BIG
                            if mod_value > turns_in_round
                            else text.TXT_BR_ERROR_TOO_SMALL
                        )
                    target_turn = mod_value
                else:
                    target_turn += mod_value
            else:  # round
                if arg_str.startswith("=") or arg_str.isdigit():
                    target_round = mod_value
                else:
                    target_round += mod_value
        else:
            # 名字跳转（精确 → 模糊）；@玩家 按归属定位条目（改名不受影响）
            name_list = [entity.name for entity in init_data.entities]
            target_qq = parse_mention_token(arg_str)
            if target_qq is not None:
                mention_entity = next(
                    (e for e in init_data.entities if e.owner == target_qq), None
                )
                if mention_entity is None:
                    await turn_matcher.finish(
                        at_reply(target_qq, text.TXT_MENTION_NOT_IN_INIT)
                    )
                target, error = mention_entity.name, ""
            else:
                target, error = _find_turn_target(arg_str, name_list)
            if error:
                await turn_matcher.finish(error)
            target_turn = name_list.index(target) + 1  # type: ignore[arg-type]

    # 越界修正（回合增减溢出自动进位/退位轮次）
    target_round, target_turn = _clamp_round_target(
        init_data, target_round, target_turn
    )
    if target_round < 1:
        target_round = 1

    entity = init_data.entities[target_turn - 1]
    display_name = entity.name

    if query_only:
        if (prev_round, prev_turn, init_data.turns_in_round) != (
            target_round, target_turn, turns_in_round
        ):
            init_data.round = target_round
            init_data.turn = target_turn
            init_data.turns_in_round = turns_in_round
            await save_init_list(init_data)
        await turn_matcher.finish(text.TXT_BR_ROUND.format(
            round=target_round, turn=target_turn, turn_name=display_name
        ))

    round_changed = target_round != prev_round
    turn_changed = prev_turn != target_turn

    # 实际推进/跳转 = 战斗已开始（与 .ed 一致）：此后增删实体按战斗中修正指针
    init_data.first_turn = False
    init_data.round = target_round
    init_data.turn = target_turn
    init_data.turns_in_round = turns_in_round
    await save_init_list(init_data)

    feedbacks: List[str] = []
    at_name = ""
    at_owner = ""
    if mode == "round":
        if round_changed:
            feedbacks.append(text.TXT_BR_ROUND_MOD.format(round=target_round))
        if round_changed or turn_changed:
            feedbacks.append(text.TXT_BR_ROUND_SHOW.format(
                turn_name=display_name
            ))
        else:
            feedbacks.append(text.TXT_BR_ROUND.format(
                round=target_round, turn=target_turn, turn_name=display_name
            ))
    else:  # mode == "turn"
        if round_changed:
            if target_round > prev_round:
                feedbacks.append(text.TXT_BR_ROUND_NEW.format(round=target_round))
            else:
                feedbacks.append(text.TXT_BR_ROUND_MOD.format(round=target_round))
        if round_changed or turn_changed:
            if entity.owner:
                at_name, at_owner = display_name, entity.owner
            else:
                feedbacks.append(text.TXT_BR_TURN_NEW.format(
                    turn_name=display_name
                ))
        else:
            feedbacks.append(text.TXT_BR_ROUND_SHOW.format(
                turn_name=display_name
            ))
    await _finish_battle_lines(turn_matcher, feedbacks, at_name, at_owner)


@br_matcher.handle()
async def handle_br(event: MessageEvent) -> None:
    """处理 .br：新建战斗轮（清空先攻表与指针，并清理 NPC 临时血量）。

    .br 与 .init clr 清空语义等价（仅播报不同），共用 NPC 临时血量清理。
    """
    if not isinstance(event, GroupMessageEvent):
        await br_matcher.finish(text.TXT_GROUP_ONLY)
    await cleanup_temp_npc_health(event.group_id)
    await clear_init_list(event.group_id)
    await br_matcher.finish(text.TXT_BR_NEW)


@turn_matcher.handle()
async def handle_turn(event: MessageEvent) -> None:
    """处理 .回合。"""
    if not isinstance(event, GroupMessageEvent):
        await turn_matcher.finish(text.TXT_GROUP_ONLY)
    await _handle_turn_round(event, "turn")


@round_matcher.handle()
async def handle_round(event: MessageEvent) -> None:
    """处理 .轮次。"""
    if not isinstance(event, GroupMessageEvent):
        await round_matcher.finish(text.TXT_GROUP_ONLY)
    await _handle_turn_round(event, "round")


@ed_matcher.handle()
async def handle_ed(event: MessageEvent) -> None:
    """处理 .ed：结束当前回合，自动推进并播报。"""
    if not isinstance(event, GroupMessageEvent):
        await ed_matcher.finish(text.TXT_GROUP_ONLY)
    init_data = await _load_battle(event)

    # 先把可能越界的存量状态归一
    round_no, turn = _clamp_round_target(init_data, init_data.round, init_data.turn)
    round_no = max(1, round_no)
    turns_in_round = len(init_data.entities)

    end_entity = init_data.entities[turn - 1]
    feedbacks: List[str] = [
        text.TXT_BR_TURN_END.format(
            round=round_no, turn=turn, turn_name=end_entity.name
        )
    ]
    # 推进到下一位；一轮走完自动进位
    turn += 1
    if turn > turns_in_round:
        turn -= turns_in_round
        round_no += 1
        feedbacks.append(text.TXT_BR_ROUND_NEW.format(round=round_no))
    next_entity = init_data.entities[turn - 1]
    at_name = ""
    at_owner = ""
    if next_entity.owner:
        at_name, at_owner = next_entity.name, next_entity.owner
    else:
        feedbacks.append(text.TXT_BR_TURN_NEW.format(turn_name=next_entity.name))

    init_data.round = round_no
    init_data.turn = turn
    init_data.turns_in_round = turns_in_round
    init_data.first_turn = False
    await save_init_list(init_data)
    await _finish_battle_lines(ed_matcher, feedbacks, at_name, at_owner)
