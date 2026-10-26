"""角色卡库命令的共用解析与展示（私聊卡名选中、群内绑定卡）。"""

from __future__ import annotations

from typing import List, Optional, Set, Tuple

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher

from ..character.models import DNDCharacter
from ..data.characters import (
    find_cards_by_name,
    get_bound_card,
    get_card_by_name,
    get_character,
    list_bound_groups,
    list_cards_by_owner,
    list_characters_by_group,
)
from ..platform import onebot_v11
from . import base, text

CardRef = Tuple[str, str, DNDCharacter]


def split_name_content(args: str) -> Tuple[str, str]:
    """把 ``卡名 内容`` 拆成两段；内容可含空白与换行。"""
    arg_str = args.strip()
    if not arg_str:
        return "", ""
    parts = arg_str.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1].strip()


def split_optional_card(args: str) -> Tuple[Optional[str], str]:
    """解析 ``[卡名] <段条目>``；段条目以 ``$`` 开头时视为省略卡名。"""
    arg_str = args.strip()
    if not arg_str:
        return None, ""
    if arg_str.startswith("$"):
        return None, arg_str
    return split_name_content(arg_str)


def format_names(cards: List[CardRef]) -> str:
    return "、".join(name for _card_id, name, _character in cards)


async def resolve_private_view(
    owner: int | str, query: str, matcher: Matcher
) -> CardRef:
    """私聊查看：精确优先、其次子串；多候选列清单不猜。"""
    matches = await find_cards_by_name(owner, query)
    if not matches:
        await matcher.finish(text.TXT_CHAR_NAME_MISS.format(name=query))
    if len(matches) > 1:
        await matcher.finish(
            text.TXT_CHAR_NAME_MULTI.format(
                name=query, names=format_names(matches)
            )
        )
    return matches[0]


async def resolve_private_manage(
    owner: int | str, name: str, matcher: Matcher
) -> CardRef:
    """私聊管理命令：卡名精确匹配（大小写不敏感）。"""
    found = await get_card_by_name(owner, name)
    if found is None:
        await matcher.finish(text.TXT_CHAR_NAME_MISS.format(name=name))
    card_id, character = found
    return card_id, name, character


async def resolve_private_current(
    owner: int | str, query: str, matcher: Matcher
) -> CardRef:
    """私聊命令取卡：给了卡名按卡名，没给卡名时仅在卡库仅一张时可用。"""
    if query:
        return await resolve_private_view(owner, query, matcher)
    cards = await list_cards_by_owner(owner)
    if not cards:
        await matcher.finish(text.TXT_CHAR_NO_CARD_PRIVATE)
    if len(cards) > 1:
        await matcher.finish(text.TXT_CHAR_NEED_NAME.format(count=len(cards)))
    return cards[0]


async def resolve_group_bound(
    group_id: int | str, owner: int | str, matcher: Matcher
) -> CardRef:
    """群聊命令取卡：只认本群绑定的卡。"""
    bound = await get_bound_card(group_id, owner)
    if bound is None:
        await matcher.finish(text.TXT_CHAR_MISS)
    return bound


async def resolve_view_target(
    bot: Bot, event: MessageEvent, matcher: Matcher, query: str
) -> Tuple[DNDCharacter, str]:
    """解析查看类命令（``.角色卡`` / ``.立绘``）的目标，返回 (角色卡, 展示名)。

    - 私聊：按卡名看本人卡（卡库仅一张时可省略）；``@`` 一律提示不支持；
    - 群聊：无参数看本人本群绑定卡；给 ``@玩家`` / 角色名则看对方在本群绑定卡。

    条件不满足时已用 ``matcher.finish`` 回复并结束当前处理，调用方无需判空。
    展示名只在群聊看他人时非空（角色名优先的统一回退链）。
    """
    query = (query or "").strip()
    owner = str(event.user_id)
    if not isinstance(event, GroupMessageEvent):
        if query.startswith("@"):
            await matcher.finish(text.TXT_CHAR_PRIVATE_TARGET_UNSUPPORTED)
        if not query and not await list_cards_by_owner(owner):
            await matcher.finish(
                text.TXT_CHAR_VIEW_MISS_PRIVATE.format(
                    url=text.TXT_CARD_BUILDER_URL
                )
            )
        _card_id, _card_name, character = await resolve_private_current(
            owner, query, matcher
        )
        return character, ""

    if not query:
        bound = await get_bound_card(event.group_id, owner)
        if bound is None:
            if await list_cards_by_owner(owner):
                await matcher.finish(text.TXT_CHAR_VIEW_MISS_BOUND)
            await matcher.finish(
                text.TXT_CHAR_VIEW_MISS_GROUP.format(
                    url=text.TXT_CARD_BUILDER_URL
                )
            )
        _card_id, _card_name, character = bound
        return character, ""

    # 群聊查看他人：@玩家 / 角色名
    # 注：函数内导入——避免 commands 包的模块导入顺序被改变。
    from .hp import search_target

    source_key, target_id = await search_target(query, event.group_id)
    if source_key == "at_miss":
        await matcher.finish(
            onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
        )
    if source_key == "pc_hp":
        # 只有无卡 HP 记录的玩家：角色卡相关命令仍按「未绑定」处理
        if onebot_v11.parse_mention_token(query) is not None:
            await matcher.finish(
                onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
            )
        await matcher.finish(text.TXT_CHAR_TARGET_MISS.format(name=query))
    if source_key == "multiple":
        await matcher.finish(
            text.TXT_HP_INFO_MULTI.format(name_list=target_id.split("/"))
        )
    if source_key == "npc":
        await matcher.finish(text.TXT_CHAR_NPC_NO_CARD.format(name=target_id))
    if source_key == "pc":
        target_char = await get_character(event.group_id, target_id)
        if target_char is None:
            await matcher.finish(
                onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
            )
        name = await base.resolve_display_name(
            bot, event, target_id, char_name=target_char.name
        )
        return target_char, name
    await matcher.finish(text.TXT_CHAR_TARGET_MISS.format(name=query))


async def format_card_list(
    cards: List[CardRef], current_group: int | str | None = None
) -> str:
    """卡库清单：卡名、角色名、等级/职业、已绑定群与当前群标记。"""
    lines: List[str] = []
    for card_id, card_name, character in cards:
        level = character.ability_info.level if character.ability_info.is_init else 0
        class_part = character.char_class or ""
        item = text.TXT_CHAR_LIST_ITEM.format(
            name=card_name,
            character=character.name or "未命名",
            level=level,
            class_name=class_part,
        )
        groups = await list_bound_groups(card_id)
        if groups:
            item += text.TXT_CHAR_LIST_BOUND.format(groups="、".join(groups))
        if current_group is not None and str(current_group) in groups:
            item += text.TXT_CHAR_LIST_CURRENT
        lines.append(item)
    return "\n".join(lines)


def parse_group_id(value: str) -> Optional[int]:
    text_value = value.strip()
    if not text_value.isdigit():
        return None
    group_id = int(text_value)
    return group_id if group_id > 0 else None


async def find_group_characters(
    group_id: int | str, query: str
) -> List[DNDCharacter]:
    """按角色名匹配本群已绑定卡：精确优先，其次子串。

    与 ``.hp`` 等既有目标搜索同款两级口径（多候选原样返回，由调用方列清单、
    不猜）。空查询返回空列表。
    """
    lowered = (query or "").strip().lower()
    if not lowered:
        return []
    chars = await list_characters_by_group(group_id)
    exact = [
        char for char in chars
        if (char.name or "").strip().lower() == lowered
    ]
    if exact:
        return exact
    return [
        char for char in chars
        if lowered in (char.name or "").strip().lower()
    ]


async def bot_group_ids(bot: Bot) -> Optional[Set[str]]:
    """取骰娘所在群号集合；接口不可用时返回 None（由调用方降级处理）。"""
    try:
        groups = await bot.get_group_list()
    except Exception:  # noqa: BLE001 - 不同协议端能力不一致
        logger.warning("DNDDicer 获取群列表失败，跳过骰娘在群校验")
        return None
    result: Set[str] = set()
    for item in groups or []:
        if isinstance(item, dict):
            group_id = item.get("group_id")
        else:
            group_id = getattr(item, "group_id", None)
        if group_id is not None:
            result.add(str(group_id))
    return result
