"""DND5e 角色卡命令：``.角色卡`` 系列 + ``.状态`` + 检定类点命令。

命令面（2026-10-23 卡库化）：
- ``.角色卡 [卡名]`` / ``.角色卡 @玩家|角色名``：查看；私聊按卡名选，卡库
  仅一张时可省略卡名；群聊只看本群绑定卡；
- ``.角色卡新建 <卡名> <完整卡内容>``：新建；群聊成功后自动绑定本群；
- ``.角色卡修改 [卡名] <段条目…>``：只覆盖提到的段，空段表示清空；
- ``.角色卡改名 / 列表 / 绑定 / 解绑 / 清除``：卡库管理；
- ``.角色卡记录`` 已退役，不再单独处理（按普通未匹配走默认错误）。

检定类点命令（非固定命令名，按消息模式触发）：
``.[次数#][属性/技能/先攻]检定[优势/劣势][±加值]``
``.[次数#][属性]豁免[优势/劣势][±加值]``

@ 提及目标（群聊）：
- ``.角色卡 @玩家`` / ``.角色卡 角色名``：查看他人**在本群绑定**的卡；
- ``.状态 @玩家``：查看他人在本群绑定卡的 HP 与生命骰摘要；
- 检定点右侧 @ 目标：用目标角色的属性/熟练/加值代掷。
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher
from nonebot.plugin import on_message
from nonebot.rule import Rule

from ..character.constants import (
    ABILITY_LIST,
    CHECK_ITEM_LIST,
    SAVING_LIST,
    SKILL_SYNONYM_DICT,
)
from ..character.services import (
    AbilityService,
    CharacterService,
    gen_template_char,
    parse_template_to_dict,
)
from ..config import get_config
from ..data import portraits
from ..data.characters import (
    CardError,
    bind_card,
    create_card,
    delete_card,
    get_bound_card,
    get_card_by_name,
    get_character,
    list_bound_groups,
    list_cards_by_owner,
    rename_card,
    save_card,
    unbind_card,
)
from ..platform import onebot_v11
from . import base, card_helpers, text

_HELP = (
    ".角色卡 [卡名] / .角色卡 @玩家\n"
    "  群聊看本群绑定卡；私聊看本人卡（多张需带卡名）\n"
    "  新建：.角色卡新建 <卡名> <完整卡内容>（群聊自动绑定）\n"
    "  修改：.角色卡修改 [卡名] <段条目>（空段表示清空）\n"
    "  改名/列表/绑定/解绑/清除等卡库管理见帮助文档"
)
char_matcher = base.on_dnd_command("角色卡", _HELP, doc="guide/character-card")

_HELP_STATE = (
    ".状态 [@玩家|卡名]\n"
    "  查看 HP 与生命骰摘要\n"
    "  私聊多张卡需带卡名；@玩家 需在群聊"
)
state_matcher = base.on_dnd_command("状态", _HELP_STATE, doc="guide/hp")


def _gen_template_feedback() -> str:
    """.角色卡模板 输出：示例卡 + 段落使用提示。

    提示为纯说明文字，禁含 $ 字符——建卡内容按 $ 分段，说明会污染
    「复制模板再新建」的解析。
    """
    tips = (
        "\n\n——提示（建卡时请仅复制上方模板段并修改）——\n"
        "建卡：.角色卡新建 <卡名> <完整卡内容>（卡名最多 20 字，不能包含空格、美元符号、@）\n"
        "改卡：.角色卡修改 <卡名> <段条目>（只覆盖提到的段；段名后留空表示清空）\n"
        "群聊新建会自动绑定本群；私聊建卡后用 .角色卡绑定 <卡名> <群号> 绑定\n"
        "属性段六个数值依次对应: 力量/敏捷/体质/智力/感知/魅力\n"
        "熟练段 = 技能/豁免/先攻条目（2*为专精），可加护甲/武器/工具/语言分组\n"
        "属性调整值、豁免与技能加值由骰娘按等级与熟练自动计算，无需另填\n"
        "额外加值段键 = 六属性/技能/豁免条目/豁免（作用于全部豁免）\n"
        "额外加值取值 = 可选 优势/劣势 ±掷骰表达式, 如: 隐匿:优势+2\n"
        "武器段格式 = 名称+命中加值,伤害表达式+类型[,备注]（多项用 / 分隔）\n"
        "限定资源段格式 = 名称:当前/上限恢复方式[|说明]（短休/长休/两者/手动，可加 +N 或 满）\n"
        "法术段格式 = 施法属性:属性; 豁免DC:15; 法术攻击:+8; 法术名:环阶[*][|时间=…,距离=…,专注=是,仪式=否,材料=是,备注=…]\n"
        "法术位段格式 = 环阶:当前/上限（契约魔法写 契约3:2/2），多项用 ; 分隔\n"
        "战斗段格式 = AC:18; 速度:30（先攻、被动察觉由骰娘按属性、熟练与额外加值自动计算，不需要写）\n"
        "进度段格式 = 经验:6500; 激励:有（下一级经验由骰娘按等级计算）\n"
        "专长 / 种族特性段多项用 / 分隔，可写 名称:说明；职业特性写 等级|名称:说明\n"
        "物品段格式 = 名称x数量，多项用 ; 分隔；魔法物品段格式 = 名称|标签|说明（说明用 // 分段）\n"
        "钱币段格式 = CP:0; SP:8; EP:0; GP:18; PP:0\n"
        "背景段为固定键:值（5e 另有理想/羁绊/缺点），多项用 ; 分隔；故事段可多行/多段（最多 1000 字，换行不计）；战斗记录段每项用 ; 分隔"
    )
    return gen_template_char().get_char_info() + tips


def _reserved_names() -> Tuple[str, ...]:
    return tuple(base.get_registered_commands())


def _is_group(event: MessageEvent) -> bool:
    return isinstance(event, GroupMessageEvent)


def _owner(event: MessageEvent) -> str:
    return str(event.user_id)


# =========================================================================
# 检定类点命令（模式匹配，非固定命令名）
# =========================================================================

#: 消息体模式：([1-9]#)? 条目 (检定|豁免) 剩余(优劣势/加值)
_CHECK_PATTERN = re.compile(r"^([1-9]#)?(.+?)(检定|豁免)(.*)$")


def _resolve_check_name(entry: str, kind: str) -> Optional[str]:
    """把消息中的条目段解析为正式检定条目名。"""
    if kind == "检定":
        name = SKILL_SYNONYM_DICT.get(entry, entry)
        return name if name in CHECK_ITEM_LIST else None
    if entry in ABILITY_LIST:
        return f"{entry}{kind}"
    return None


def parse_check_body(body: str) -> Optional[Tuple[int, str, str]]:
    """解析检定命令体 → (次数, 条目全名, 加值修正串)；无效返回 None。"""
    m = _CHECK_PATTERN.match(body)
    if not m:
        return None
    time_part, entry_part, kind, tail = m.groups()
    times = int(time_part[:-1]) if time_part else 1
    entry = entry_part.strip()
    if not entry:
        return None
    name = _resolve_check_name(entry, kind)
    if name is None:
        return None
    return times, name, tail.strip()


def _check_command_rule() -> Rule:
    async def _checker(event: MessageEvent) -> bool:
        text_body = event.get_plaintext().strip()
        if not text_body:
            return False
        starts = base.get_command_starts()
        matched_start = next((s for s in starts if text_body.startswith(s)), None)
        if matched_start is None:
            return False
        body = text_body[len(matched_start):]
        fixed_name, fixed_rest = base.match_command_name(body)
        if fixed_name is not None:
            if not (fixed_name == "先攻" and fixed_rest.lstrip().startswith("检定")):
                return False
        return parse_check_body(body) is not None

    return Rule(_checker) & base.group_service_rule()


def _make_check_matcher() -> Matcher:
    priority = get_config().dnddicer_command_priority
    return on_message(_check_command_rule(), priority=priority, block=True)


check_matcher = _make_check_matcher()


# =========================================================================
# 子命令处理
# =========================================================================


async def _handle_new(event: MessageEvent, args: str) -> None:
    """``.角色卡新建 <卡名> <完整卡内容>``。"""
    card_name, content = card_helpers.split_name_content(args)
    if not card_name or not content:
        await char_matcher.finish(text.TXT_CHAR_NEW_USAGE)
    owner = _owner(event)
    is_group = _is_group(event)
    created_in = str(event.group_id) if is_group else "private"
    try:
        new_char = CharacterService.parse_full(
            content, created_in, owner, _reserved_names()
        )
        card_id = await create_card(owner, card_name, created_in, new_char)
    except (AssertionError, CardError) as exc:
        await char_matcher.finish(str(exc))

    if not is_group:
        await char_matcher.finish(text.TXT_CHAR_NEW_PRIVATE.format(name=card_name))

    old_bound = await get_bound_card(event.group_id, owner)  # type: ignore[attr-defined]
    try:
        await bind_card(event.group_id, owner, card_id)  # type: ignore[attr-defined]
    except CardError as exc:
        await char_matcher.finish(
            text.TXT_CHAR_BIND_FAILED_CREATED.format(
                name=card_name, error=str(exc)
            )
        )
    if old_bound is not None and old_bound[0] != card_id:
        await char_matcher.finish(
            text.TXT_CHAR_NEW_GROUP_REPLACED.format(
                name=card_name, old=old_bound[1]
            )
        )
    await char_matcher.finish(text.TXT_CHAR_NEW_GROUP.format(name=card_name))


async def _handle_modify(event: MessageEvent, args: str) -> None:
    """``.角色卡修改 [卡名] <段条目…>``。"""
    name_arg, content = card_helpers.split_optional_card(args)
    if not content:
        await char_matcher.finish(text.TXT_CHAR_MODIFY_USAGE)
    owner = _owner(event)
    if _is_group(event):
        card_id, card_name, existing = await card_helpers.resolve_group_bound(
            event.group_id, owner, char_matcher  # type: ignore[attr-defined]
        )
        if name_arg and name_arg.casefold() != card_name.casefold():
            await char_matcher.finish(
                text.TXT_CHAR_MODIFY_GROUP_MISMATCH.format(name=card_name)
            )
    elif name_arg:
        card_id, card_name, existing = await card_helpers.resolve_private_manage(
            owner, name_arg, char_matcher
        )
    else:
        card_id, card_name, existing = await card_helpers.resolve_private_current(
            owner, "", char_matcher
        )

    try:
        data = parse_template_to_dict(content, keep_empty=True)
        merged = CharacterService.merge_segments(
            existing, data, _reserved_names()
        )
        await save_card(card_id, merged)
    except (AssertionError, CardError) as exc:
        await char_matcher.finish(str(exc))
    await char_matcher.finish(text.TXT_CHAR_MODIFY_OK.format(name=card_name))


async def _handle_rename(event: MessageEvent, args: str) -> None:
    """``.角色卡改名 <旧名> <新名>``。"""
    parts = args.split()
    if len(parts) != 2:
        await char_matcher.finish(text.TXT_CHAR_RENAME_USAGE)
    old_name, new_name = parts
    owner = _owner(event)
    if _is_group(event):
        card_id, bound_name, _character = await card_helpers.resolve_group_bound(
            event.group_id, owner, char_matcher  # type: ignore[attr-defined]
        )
        if old_name.casefold() != bound_name.casefold():
            await char_matcher.finish(
                text.TXT_CHAR_MODIFY_GROUP_MISMATCH.format(name=bound_name)
            )
    else:
        found = await get_card_by_name(owner, old_name)
        if found is None:
            await char_matcher.finish(
                text.TXT_CHAR_NAME_MISS.format(name=old_name)
            )
        card_id, _character = found
    try:
        renamed = await rename_card(card_id, new_name)
    except CardError as exc:
        await char_matcher.finish(str(exc))
    await char_matcher.finish(
        text.TXT_CHAR_RENAME_OK.format(old=old_name, new=renamed)
    )


async def _handle_list(event: MessageEvent) -> None:
    """``.角色卡列表``。"""
    owner = _owner(event)
    cards = await list_cards_by_owner(owner)
    if not cards:
        await char_matcher.finish(text.TXT_CHAR_LIST_EMPTY)
    current_group = event.group_id if _is_group(event) else None  # type: ignore[attr-defined]
    body = await card_helpers.format_card_list(cards, current_group)
    await char_matcher.finish(text.TXT_CHAR_LIST_TITLE + "\n" + body)


async def _handle_bind(
    bot: Bot, event: MessageEvent, args: str
) -> None:
    """``.角色卡绑定 <卡名>``（群聊） / ``.角色卡绑定 <卡名> <群号>``（私聊）。"""
    owner = _owner(event)
    if _is_group(event):
        parts = args.split()
        if len(parts) != 1:
            await char_matcher.finish(text.TXT_CHAR_BIND_USAGE_GROUP)
        card_id, card_name, _character = await card_helpers.resolve_private_manage(
            owner, parts[0], char_matcher
        )
        group_id = event.group_id  # type: ignore[attr-defined]
        old_bound = await get_bound_card(group_id, owner)
        try:
            await bind_card(group_id, owner, card_id)
        except CardError as exc:
            await char_matcher.finish(str(exc))
        if old_bound is not None and old_bound[0] != card_id:
            await char_matcher.finish(
                text.TXT_CHAR_BIND_REPLACED.format(
                    name=card_name, group=group_id, old=old_bound[1]
                )
            )
        await char_matcher.finish(
            text.TXT_CHAR_BIND_OK.format(name=card_name, group=group_id)
        )

    parts = args.split()
    if len(parts) != 2:
        await char_matcher.finish(text.TXT_CHAR_BIND_USAGE_PRIVATE)
    name, group_str = parts
    group_id = card_helpers.parse_group_id(group_str)
    if group_id is None:
        await char_matcher.finish(text.TXT_CHAR_BIND_USAGE_PRIVATE)
    card_id, card_name, _character = await card_helpers.resolve_private_manage(
        owner, name, char_matcher
    )
    group_ids = await card_helpers.bot_group_ids(bot)
    if group_ids is not None and str(group_id) not in group_ids:
        await char_matcher.finish(
            text.TXT_CHAR_BIND_GROUP_MISSING.format(group=group_id)
        )
    old_bound = await get_bound_card(group_id, owner)
    try:
        await bind_card(group_id, owner, card_id)
    except CardError as exc:
        await char_matcher.finish(str(exc))
    suffix = "" if group_ids is not None else text.TXT_CHAR_BIND_GROUP_UNKNOWN
    hint = text.TXT_CHAR_BIND_PRIVATE_HINT
    if old_bound is not None and old_bound[0] != card_id:
        await char_matcher.finish(
            text.TXT_CHAR_BIND_REPLACED.format(
                name=card_name, group=group_id, old=old_bound[1]
            )
            + hint
            + suffix
        )
    await char_matcher.finish(
        text.TXT_CHAR_BIND_OK.format(name=card_name, group=group_id)
        + hint
        + suffix
    )


async def _handle_unbind(event: MessageEvent, args: str) -> None:
    """``.角色卡解绑``（群聊） / ``.角色卡解绑 <群号>``（私聊）。"""
    owner = _owner(event)
    if _is_group(event):
        if args:
            await char_matcher.finish(text.TXT_CHAR_UNBIND_USAGE_GROUP)
        previous = await unbind_card(event.group_id, owner)  # type: ignore[attr-defined]
        if previous:
            await char_matcher.finish(text.TXT_CHAR_UNBIND_OK)
        await char_matcher.finish(text.TXT_CHAR_UNBIND_NONE)

    group_id = card_helpers.parse_group_id(args)
    if group_id is None:
        await char_matcher.finish(text.TXT_CHAR_UNBIND_USAGE)
    previous = await unbind_card(group_id, owner)
    if previous:
        await char_matcher.finish(
            text.TXT_CHAR_UNBIND_PRIVATE_OK.format(group=group_id)
        )
    await char_matcher.finish(text.TXT_CHAR_UNBIND_PRIVATE_NONE)


async def _handle_delete(event: MessageEvent, args: str) -> None:
    """``.角色卡清除 <卡名> [确认]``。"""
    parts = args.split()
    if not parts:
        await char_matcher.finish(text.TXT_CHAR_DELETE_USAGE)
    name = parts[0]
    confirm = len(parts) >= 2 and parts[1] in ("确认", "确认删除", "confirm")
    if len(parts) > 2 or (len(parts) == 2 and not confirm):
        await char_matcher.finish(text.TXT_CHAR_DELETE_USAGE)
    owner = _owner(event)
    found = await get_card_by_name(owner, name)
    if found is None:
        await char_matcher.finish(text.TXT_CHAR_NAME_MISS.format(name=name))
    card_id, character = found
    groups = await list_bound_groups(card_id)
    if groups:
        await char_matcher.finish(
            text.TXT_CHAR_DELETE_BOUND.format(
                name=name, groups="、".join(groups)
            )
        )
    if not confirm:
        await char_matcher.finish(
            text.TXT_CHAR_DELETE_CONFIRM.format(name=name)
        )
    await portraits.delete_portrait(character.portrait)
    try:
        await delete_card(card_id)
    except CardError as exc:
        await char_matcher.finish(str(exc))
    await char_matcher.finish(text.TXT_CHAR_DELETE_OK.format(name=name))


async def _handle_view(bot: Bot, event: MessageEvent, rest: str) -> None:
    """``.角色卡`` 查看。"""
    owner = _owner(event)
    if not _is_group(event):
        if rest.startswith("@"):
            await char_matcher.finish(text.TXT_CHAR_PRIVATE_TARGET_UNSUPPORTED)
        _card_id, _card_name, character = await card_helpers.resolve_private_current(
            owner, rest, char_matcher
        )
        await char_matcher.finish(character.get_char_info())

    if not rest:
        _card_id, _card_name, character = await card_helpers.resolve_group_bound(
            event.group_id, owner, char_matcher  # type: ignore[attr-defined]
        )
        await char_matcher.finish(character.get_char_info())

    # 群聊查看他人：.角色卡 @玩家 / .角色卡 角色名
    # 注：函数内导入——避免 commands 包的模块导入顺序被改变。
    from .hp import search_target

    source_key, target_id = await search_target(
        rest, event.group_id  # type: ignore[attr-defined]
    )
    if source_key == "at_miss":
        await char_matcher.finish(
            onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
        )
    if source_key == "pc_hp":
        # 只有无卡 HP 记录的玩家：角色卡相关命令仍按「未绑定」处理
        if onebot_v11.parse_mention_token(rest) is not None:
            await char_matcher.finish(
                onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
            )
        await char_matcher.finish(
            text.TXT_CHAR_TARGET_MISS.format(name=rest)
        )
    if source_key == "multiple":
        await char_matcher.finish(
            text.TXT_HP_INFO_MULTI.format(name_list=target_id.split("/"))
        )
    if source_key == "npc":
        await char_matcher.finish(
            text.TXT_CHAR_NPC_NO_CARD.format(name=target_id)
        )
    if source_key == "pc":
        target_char = await get_character(event.group_id, target_id)  # type: ignore[attr-defined]
        if target_char is None:
            await char_matcher.finish(
                onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
            )
        name = await base.resolve_display_name(
            bot, event, target_id, char_name=target_char.name
        )
        await char_matcher.finish(
            text.TXT_CHAR_TARGET_TITLE.format(name=name)
            + "\n"
            + target_char.get_char_info()
        )
    await char_matcher.finish(text.TXT_CHAR_TARGET_MISS.format(name=rest))


# =========================================================================
# 处理器
# =========================================================================


@char_matcher.handle()
async def handle_character(bot: Bot, event: MessageEvent) -> None:
    """处理 .角色卡 系列子命令。"""
    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    parts = rest.split(maxsplit=1)
    head = parts[0] if parts else ""
    tail = parts[1].strip() if len(parts) > 1 else ""

    if head == "新建":
        await _handle_new(event, tail)
        return
    if head == "修改":
        await _handle_modify(event, tail)
        return
    if head == "改名":
        await _handle_rename(event, tail)
        return
    if head == "列表":
        await _handle_list(event)
        return
    if head == "绑定":
        await _handle_bind(bot, event, tail)
        return
    if head == "解绑":
        await _handle_unbind(event, tail)
        return
    if head == "清除":
        await _handle_delete(event, tail)
        return
    if head == "模板":
        await char_matcher.finish(_gen_template_feedback())

    await _handle_view(bot, event, rest)


@state_matcher.handle()
async def handle_state(bot: Bot, event: MessageEvent) -> None:
    """处理 .状态（群聊 @/名称看他人，私聊按卡名看本人）。"""
    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    owner = _owner(event)
    name = ""
    if not _is_group(event):
        if rest.startswith("@"):
            await state_matcher.finish(text.TXT_CHAR_PRIVATE_TARGET_UNSUPPORTED)
        _card_id, card_name, character = await card_helpers.resolve_private_current(
            owner, rest, state_matcher
        )
        name = card_name
    elif rest:
        from .hp import search_target

        source_key, target_id = await search_target(
            rest, event.group_id  # type: ignore[attr-defined]
        )
        if source_key == "at_miss":
            await state_matcher.finish(
                onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
            )
        if source_key == "pc_hp":
            # 只有无卡 HP 记录的玩家：.状态 仍以角色卡为准
            if onebot_v11.parse_mention_token(rest) is not None:
                await state_matcher.finish(
                    onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
                )
            await state_matcher.finish(
                text.TXT_CHAR_TARGET_MISS.format(name=rest)
            )
        if source_key == "multiple":
            await state_matcher.finish(
                text.TXT_HP_INFO_MULTI.format(name_list=target_id.split("/"))
            )
        if source_key == "npc":
            await state_matcher.finish(
                text.TXT_CHAR_NPC_NO_CARD.format(name=target_id)
            )
        if source_key != "pc":
            await state_matcher.finish(
                text.TXT_CHAR_TARGET_MISS.format(name=rest)
            )
        character = await get_character(event.group_id, target_id)  # type: ignore[attr-defined]
        if character is None:
            await state_matcher.finish(
                onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
            )
        name = await base.resolve_display_name(
            bot, event, target_id, char_name=character.name
        )
    else:
        character = await get_character(event.group_id, event.user_id)  # type: ignore[attr-defined]
        if character is None:
            await state_matcher.finish(text.TXT_CHAR_MISS)

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
    """处理检定/豁免点命令（rule 已确保命中且参数可解析）。"""
    if not isinstance(event, GroupMessageEvent):
        await check_matcher.finish(text.TXT_GROUP_ONLY)

    text_body = onebot_v11.strip_leading_mentions(
        onebot_v11.rebuild_text_with_mentions(event)
    ).strip()
    start = next(
        (s for s in base.get_command_starts() if text_body.startswith(s)), None
    )
    if start is None:
        return
    parsed = parse_check_body(text_body[len(start):])
    if parsed is None:
        return
    times, check_name, mod_str = parsed

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

    advantage = 0
    if mod_str.startswith("优势"):
        advantage = 1
        mod_str = mod_str[2:]
    elif mod_str.startswith("劣势"):
        advantage = -1
        mod_str = mod_str[2:]

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
    if check_name in SAVING_LIST:
        display_item = check_name
    else:
        display_item = f"{check_name}检定"
    display_check = display_item if times == 1 else f"{times}次{display_item}"
    if check_name != "先攻":
        state = text.get_roll_state_text(roll_results)
        if state:
            results[-1] = text.join_roll_state_text(results[-1], state, own_line=True)
    feedback = text.TXT_CHECK_RESULT.format(
        name=name,
        check=display_check,
        hint=hint,
        result="\n".join(results),
    )
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
