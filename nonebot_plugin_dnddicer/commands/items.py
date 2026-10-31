"""背包物品（``.物品``，2026-11-01 新增）。

- ``.物品``：按序号列出 ``$物品$``；
- ``.物品 名称+`` / ``名称+3``：增加 1 个 / 3 个，没有时新建；
- ``.物品 名称-3``：扣减 3 个，扣到 0 时移除；
- ``.物品 名称-``：扣减 1 个，扣到 0 时移除。

名称精确优先，未命中再按子串匹配；多候选列清单不猜。数量不足整条拒绝。
命令只改 ``character.items`` 后保存整卡，不触碰其他段。
"""

from __future__ import annotations

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ..character.items import (
    ItemAmbiguous,
    ItemDuplicate,
    ItemInsufficient,
    ItemLimit,
    ItemNotFound,
    apply_item_operation,
    format_item_candidates,
    format_item_list,
    parse_item_operation,
)
from ..data.characters import get_character, save_character
from . import base, text

_HELP = (
    ".物品 [名称+数量|名称-数量|名称-]\n"
    "  无参数：按序号列出背包物品\n"
    "  增加：治疗药水+3；只写 + 表示加 1 个\n"
    "  减少：箭矢-3 扣 3 个；只写 - 表示扣 1 个，扣到 0 自动移除\n"
    "  名称支持模糊匹配，数量不足会整条拒绝"
)
items_matcher = base.on_dnd_command(
    "物品", _HELP, doc="guide/character-card"
)


def _format_list(items) -> str:
    """按序号展示物品清单。"""
    return "\n".join(
        text.TXT_ITEM_LIST_ITEM.format(index=index, text=item)
        for index, item in enumerate(items, start=1)
    )


@items_matcher.handle()
async def handle_items(event: MessageEvent) -> None:
    """处理 .物品：查看 / 增加 / 扣减。"""
    if not isinstance(event, GroupMessageEvent):
        await items_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await items_matcher.finish(text.TXT_CHAR_MISS)

    if not rest:
        if not character.items:
            await items_matcher.finish(text.TXT_ITEM_EMPTY)
        await items_matcher.finish(
            text.TXT_ITEM_LIST.format(
                count=len(character.items),
                items=_format_list(format_item_list(character.items)),
            )
        )

    try:
        operation = parse_item_operation(rest)
    except AssertionError as exc:
        await items_matcher.finish(str(exc))

    try:
        change = apply_item_operation(character.items, operation)
    except ItemDuplicate as exc:
        await items_matcher.finish(text.TXT_ITEM_DUPLICATE.format(name=exc.name))
    except ItemAmbiguous as exc:
        await items_matcher.finish(
            text.TXT_ITEM_AMBIGUOUS.format(
                name=exc.name,
                candidates=format_item_candidates(exc.candidates),
            )
        )
    except ItemNotFound as exc:
        await items_matcher.finish(
            text.TXT_ITEM_NOT_FOUND.format(name=exc.name)
        )
    except ItemInsufficient as exc:
        await items_matcher.finish(
            text.TXT_ITEM_INSUFFICIENT.format(
                name=exc.name,
                current=exc.current,
                requested=exc.requested,
            )
        )
    except ItemLimit as exc:
        if exc.kind == "count":
            await items_matcher.finish(
                text.TXT_ITEM_MAX_COUNT.format(max=exc.limit)
            )
        await items_matcher.finish(
            text.TXT_ITEM_MAX_QUANTITY.format(name=exc.name, max=exc.limit)
        )

    character.items = list(change.items)
    await save_character(character)

    if change.kind == "add_new":
        await items_matcher.finish(
            text.TXT_ITEM_ADD_NEW.format(
                name=change.name, quantity=change.new_quantity
            )
        )
    if change.kind == "remove_zero":
        await items_matcher.finish(
            text.TXT_ITEM_REMOVE_ZERO.format(
                name=change.name, old=change.old_quantity
            )
        )
    await items_matcher.finish(
        text.TXT_ITEM_CHANGE.format(
            name=change.name,
            old=change.old_quantity,
            new=change.new_quantity,
        )
    )
