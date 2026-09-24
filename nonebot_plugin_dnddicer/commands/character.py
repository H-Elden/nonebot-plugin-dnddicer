"""DND5e 角色卡命令：``.角色卡`` / ``.状态`` / 检定类点命令。

命令面：
- ``.角色卡`` 查看 / ``.角色卡记录 <模板文本>`` / ``.角色卡清除`` / ``.角色卡模板``
  （不自动改群名片，避免依赖群管理权限）；
- ``.状态``：查看本角色 HP 与生命骰摘要；
- 检定类点命令（非固定命令名，按消息模式触发）：
  ``.[次数#][属性/技能/先攻]检定[优势/劣势][±加值]``
  ``.[次数#][属性]豁免[±加值]``
  ``.[次数#][属性]攻击[优势/劣势][±加值]``
  例：``.力量检定`` ``.2#运动检定+1`` ``.智力豁免+d4`` ``.3#敏捷攻击优势+d8`` ``.先攻检定``
  检定只掷出裸数值（d20+加值），不对 DC 判定——由玩家/DM 自行比较。

@ 提及目标（2026-09-22 新增）：
- ``.角色卡 @玩家`` / ``.角色卡 角色名``：查看**他人**整卡（输出加标题行）；
  查看对任何人开放（群内信息共享），而记录/清除仍仅限本人（写入目标恒为发送者）；
- ``.状态 @玩家``：查看他人 HP 与生命骰摘要（加角色名前缀）；
- 检定类点命令表达式**右侧**的 @ 为目标：``.力量豁免 @玩家`` ``.3#敏捷攻击优势+d8 @玩家``
  ——用目标角色的属性/熟练/加值代掷，``.先攻检定 @玩家`` 以该玩家为 owner 入先攻表。
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher
from nonebot.plugin import on_message
from nonebot.rule import Rule

from ..character.constants import (
    ABILITY_LIST,
    ATTACK_LIST,
    CHECK_ITEM_INDEX_DICT,
    CHECK_ITEM_LIST,
    SAVING_LIST,
    SKILL_SYNONYM_DICT,
)
from ..character.models import DNDCharacter
from ..character.services import AbilityService, CharacterService, gen_template_char
from ..config import get_config
from ..data.characters import delete_character, get_character, save_character
from ..platform import onebot_v11
from . import base, text

_HELP = (
    "DND5e 角色卡\n"
    "用法：.角色卡模板 / .角色卡记录 <模板内容> / .角色卡 / .角色卡清除\n"
    "查看他人：.角色卡 @玩家 或 .角色卡 角色名（任何人可查看；记录/清除仅限本人）\n"
    "自定义武器写在卡上（$武器$ 段，或用 .设置武器 维护）：.刺剑攻击 / .刺剑伤害 直接调用；\n"
    "职业段（$职业$）供偷袭骰自动计算（游荡者）。\n"
    "每人在每个群中拥有一张角色卡；.角色卡 查看当前卡（$…$ 文本可直接复制再次记录以保存多张）。"
)
char_matcher = base.on_dnd_command("角色卡", _HELP)

_HELP_STATE = (
    "查看本角色当前 HP 与生命骰状态。\n"
    ".状态 @玩家 -> 查看该玩家的状态（需该玩家已在本群建卡）"
)
state_matcher = base.on_dnd_command("状态", _HELP_STATE)


def _gen_template_feedback() -> str:
    """.角色卡模板 输出：示例卡 + 段落使用提示。

    提示为纯说明文字，禁含 $ 字符——记录解析按 $ 分段，说明会污染
    「复制模板再记录」的解析。
    """
    tips = (
        "\n\n——提示（记录时请仅复制上方模板段并修改）——\n"
        "属性段六个数值依次对应: 力量/敏捷/体质/智力/感知/魅力\n"
        "额外加值段键 = 六属性/技能/豁免/攻击条目, 另有作用于全部的全局键: 豁免 与 攻击\n"
        "额外加值取值 = 可选 优势/劣势 前缀 + ±掷骰表达式, 如: 隐匿:优势+2\n"
        "职业段填 12 职业名之一（如 游荡者），游荡者的偷袭后缀会按等级自动附加偷袭骰\n"
        "武器段格式 = 名称+命中加值,伤害表达式+类型（多项用 / 分隔），如 短剑+4,1d4+2穿刺"
    )
    return gen_template_char().get_char_info() + tips


# =========================================================================
# 检定类点命令（模式匹配，非固定命令名）
# =========================================================================

#: 消息体模式：([1-9]#)? 条目 (检定|豁免|攻击) 剩余(优劣势/加值)
_CHECK_PATTERN = re.compile(r"^([1-9]#)?(.+?)(检定|豁免|攻击)(.*)$")


def _resolve_check_name(entry: str, kind: str) -> Optional[str]:
    """把消息中的条目段解析为正式检定条目名。

    - kind=检定：entry 可为属性/技能/先攻（含同义词）；
    - kind=豁免/攻击：entry 为属性名，拼出 力量豁免 等全名。
    """
    if kind == "检定":
        name = SKILL_SYNONYM_DICT.get(entry, entry)
        return name if name in CHECK_ITEM_LIST else None
    full = f"{entry}{kind}"
    # 豁免/攻击条目输入仅接受属性名（同义表不含豁免，宽容处理常见全名输入）
    if entry in ABILITY_LIST:
        return full
    return None


def parse_check_body(body: str) -> Optional[Tuple[int, str, str]]:
    """解析检定命令体 → (次数, 条目全名, 加值修正串)；无效返回 None。

    以 检定/豁免/攻击 之一切分条目与修正，支持 ``N#`` 次数前缀；
    修正串可带 优势/劣势 前缀再跟 ±表达式。
    """
    m = _CHECK_PATTERN.match(body)
    if not m:
        return None
    time_part, entry_part, kind, tail = m.groups()
    times = int(time_part[:-1]) if time_part else 1

    entry = entry_part.strip()
    # 条目为空白（如 ".检定"）不触发
    if not entry:
        return None
    name = _resolve_check_name(entry, kind)
    if name is None:
        return None

    mod = tail.strip()
    # 优劣势从修正串中拆出：kind 检定/攻击允许；豁免同样支持
    return times, name, mod


def _check_command_rule() -> Rule:
    async def _checker(event: MessageEvent) -> bool:
        text = event.get_plaintext().strip()
        if not text:
            return False
        # 必须以本插件起始符开头，且非已注册固定命令
        starts = base.get_command_starts()
        matched_start = next((s for s in starts if text.startswith(s)), None)
        if matched_start is None:
            return False
        body = text[len(matched_start):]
        fixed_name, fixed_rest = base.match_command_name(body)
        if fixed_name is not None:
            # .先攻检定 属于检定点命令而非 .先攻 列表命令
            if not (fixed_name == "先攻" and fixed_rest.lstrip().startswith("检定")):
                return False
        return parse_check_body(body) is not None

    # 群聊服务门禁（与固定命令一致：未开启服务的群不响应，见 base.group_service_rule）
    return Rule(_checker) & base.group_service_rule()


def _make_check_matcher() -> Matcher:
    priority = get_config().dnddicer_command_priority
    return on_message(_check_command_rule(), priority=priority, block=True)


check_matcher = _make_check_matcher()


# =========================================================================
# 处理器
# =========================================================================


@char_matcher.handle()
async def handle_character(bot: Bot, event: MessageEvent) -> None:
    """处理 .角色卡 系列子命令。"""
    if not isinstance(event, GroupMessageEvent):
        await char_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    character: Optional[DNDCharacter] = await get_character(event.group_id, event.user_id)

    if not rest:
        # 查看
        if character is None or not character.is_init:
            await char_matcher.finish(text.TXT_CHAR_MISS)
        await char_matcher.finish(character.get_char_info())

    if rest.startswith("记录"):
        content = rest[2:].strip()
        try:
            new_char = CharacterService.parse(
                content,
                str(event.group_id),
                str(event.user_id),
                reserved_names=tuple(base.get_registered_commands()),
            )
        except AssertionError as exc:
            await char_matcher.finish(str(exc))
        await save_character(new_char)
        # 注：不自动改群名片为角色名（避免依赖群管理权限）
        await char_matcher.finish(text.TXT_CHAR_SET)

    if rest.startswith("清除"):
        await delete_character(event.group_id, event.user_id)
        await char_matcher.finish(text.TXT_CHAR_DEL)

    if rest.startswith("模板"):
        await char_matcher.finish(_gen_template_feedback())

    # 查看他人角色卡：.角色卡 @玩家 / .角色卡 角色名（@ 直连；名称复用 .hp 的
    # 三层搜索，见 hp.search_target）。查看对任何人开放（群内信息共享），
    # 记录/清除/模板 仍在上面按发送者处理（写入目标恒为本人）。
    # 注：函数内导入——避免 commands 包的模块导入顺序被改变（.帮助 列表顺序
    # 由 commands/__init__.py 的导入次序决定）。
    from .hp import search_target

    source_key, target_id = await search_target(rest, event.group_id)
    if source_key == "at_miss":
        await char_matcher.finish(
            onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
        )
    if source_key == "multiple":
        await char_matcher.finish(
            text.TXT_HP_INFO_MULTI.format(name_list=target_id.split("/"))
        )
    if source_key == "npc":
        await char_matcher.finish(text.TXT_CHAR_NPC_NO_CARD.format(name=target_id))
    if source_key == "pc":
        target_char = await get_character(event.group_id, target_id)
        name = await base.resolve_display_name(
            bot, event, target_id,
            char_name=target_char.name if target_char else "",
        )
        await char_matcher.finish(
            text.TXT_CHAR_TARGET_TITLE.format(name=name)
            + "\n"
            + (target_char.get_char_info() if target_char else "")
        )

    await char_matcher.finish(text.TXT_CHAR_TARGET_MISS.format(name=rest))


@state_matcher.handle()
async def handle_state(bot: Bot, event: MessageEvent) -> None:
    """处理 .状态（.状态 @玩家 查看他人）。"""
    if not isinstance(event, GroupMessageEvent):
        await state_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    target_qq = onebot_v11.parse_mention_token(rest) if rest else None
    if target_qq is not None:
        character = await get_character(event.group_id, target_qq)
        if character is None or not character.is_init:
            await state_matcher.finish(
                onebot_v11.at_reply(target_qq, text.TXT_MENTION_NO_CHAR)
            )
        name = await base.resolve_display_name(
            bot, event, target_qq, char_name=character.name
        )
    else:
        character = await get_character(event.group_id, event.user_id)
        if character is None or not character.is_init:
            await state_matcher.finish(text.TXT_CHAR_MISS)
        name = ""
    feedback = character.hp_info.get_info()
    if character.hp_info.hp_dice_type != 0:
        feedback += (
            f"\n生命骰:{character.hp_info.hp_dice_num}"
            f"/{character.hp_info.hp_dice_max} D{character.hp_info.hp_dice_type}"
        )
    if name:
        feedback = text.TXT_STATE_TARGET.format(name=name, info=feedback)
    await state_matcher.finish(feedback)


@check_matcher.handle()
async def handle_check(bot: Bot, event: MessageEvent) -> None:
    """处理检定/豁免/攻击点命令（rule 已确保命中且参数可解析）。"""
    if not isinstance(event, GroupMessageEvent):
        await check_matcher.finish(text.TXT_GROUP_ONLY)

    # 用带标记文本解析：@ 目标保留在修正串中（规则层仍基于纯文本，见 _check_command_rule）
    text_body = onebot_v11.strip_leading_mentions(
        onebot_v11.rebuild_text_with_mentions(event)
    ).strip()
    start = next(
        (s for s in base.get_command_starts() if text_body.startswith(s)), None
    )
    if start is None:  # 理论不可达（rule 已过滤），防御性兜底
        return
    parsed = parse_check_body(text_body[len(start):])
    if parsed is None:  # 理论不可达（rule 已过滤），防御性兜底
        return
    times, check_name, mod_str = parsed

    # 表达式右侧的 @ 目标（.力量豁免 @玩家 / .2#敏捷攻击优势 @玩家）
    target_qq, mod_str = base.split_target_mention(mod_str)
    if target_qq is not None:
        character = await get_character(event.group_id, target_qq)
        if character is None or not character.is_init:
            await check_matcher.finish(
                onebot_v11.at_reply(target_qq, text.TXT_MENTION_NO_CHAR)
            )
    else:
        character = await get_character(event.group_id, event.user_id)
        if character is None or not character.is_init:
            await check_matcher.finish(text.TXT_CHAR_MISS)

    # 解析临时优劣势（修正串开头的 优势/劣势）
    advantage = 0
    if mod_str.startswith("优势"):
        advantage = 1
        mod_str = mod_str[2:]
    elif mod_str.startswith("劣势"):
        advantage = -1
        mod_str = mod_str[2:]

    # 先攻检定只掷一次；先攻表联动在 initiative 模块落地后接入（TODO）
    if check_name == "先攻":
        times = 1

    try:
        hint = ""
        results: list[str] = []
        values: list[int] = []
        roll_results = []
        for _ in range(times):
            hint, result_str, result_val, roll_result = AbilityService.perform_check(
                character.ability_info, check_name, advantage, mod_str
            )
            results.append(result_str)
            values.append(result_val)
            roll_results.append(roll_result)
    except AssertionError as exc:
        await check_matcher.finish(str(exc))

    if target_qq is not None:
        name = await base.resolve_display_name(
            bot, event, target_qq, char_name=character.name
        )
    else:
        name = await base.resolve_display_name(bot, event, char_name=character.name)
    # 展示名：攻击/豁免用原名（敏捷攻击/敏捷豁免），属性/技能/先攻追加「检定」
    if check_name in ATTACK_LIST or check_name in SAVING_LIST:
        display_item = check_name
    else:
        display_item = f"{check_name}检定"
    display_check = display_item if times == 1 else f"{times}次{display_item}"
    # d20 大成功/大失败播报：与 .r 同文案同聚合（唯一 d20 出目 20/1 判定见
    # text._d20_crit_counts）；先攻检定除外——先攻掷骰没有大成功/大失败一说
    if check_name != "先攻":
        state = text.get_roll_state_text(roll_results)
        if state:
            results[-1] = f"{results[-1]} {state}"
    feedback = text.TXT_CHECK_RESULT.format(
        name=name,
        check=display_check,
        hint=hint,
        result="\n".join(results),
    )
    # .先攻检定：掷出后自动加入先攻列表（掷骰过程行被替换为入表反馈，
    # 便于群内直读先攻结果）；@ 目标以该玩家为 owner 入表（与 .ri @玩家 同源逻辑）
    if check_name == "先攻" and values:
        from .initiative import add_initiative_entities

        owner_id = target_qq if target_qq is not None else str(event.user_id)
        init_feedback = await add_initiative_entities(
            {name: (values[0], results[0])},
            owner_id,
            event.group_id,
        )
        if results[0] in feedback:
            feedback = feedback.replace(results[0], init_feedback)
        else:
            feedback += f"\n{init_feedback}"
    await check_matcher.finish(feedback)
