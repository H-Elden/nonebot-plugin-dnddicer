"""钱币收支（``.钱币``，2026-10-24 新增）。

- ``.钱币``：查看 CP / SP / EP / GP / PP；
- ``.钱币 +20GP-5SP``：紧凑收支，大小写不敏感、可连续写多条，按书写顺序结算。

加法只加指定币种、不做汇率换算；减法先扣指定币种，不足时按「最接近的更高
币种优先」破开，更高币种不足再用更低币种按面值抵扣。整条命令原子：任一条
减法无法完成就整体拒绝，不产生部分扣款。结算规则见 ``character/coins.py``。
"""

from __future__ import annotations

from typing import Dict, List

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ..character.coins import (
    CoinInsufficient,
    CoinResult,
    apply_coin_operations,
    parse_coin_operations,
)
from ..character.constants import COIN_KEY_LIST
from ..data.characters import get_character, save_character
from . import base, text

_HELP = (
    ".钱币 [+20GP-5SP]\n"
    "  查看五种币值；紧凑收支可连续写多条\n"
    "  加法不换算；减法不足会自动破币并播报\n"
    "  示例：.钱币 +20GP-5SP ｜ .钱币 -1GP"
)
coins_matcher = base.on_dnd_command("钱币", _HELP, doc="guide/character-card")


def _format_changes(result: CoinResult) -> str:
    """最终变更行：只列数值发生变化的币种，按顺序显示旧 → 新。"""
    parts: List[str] = [
        text.TXT_COIN_CHANGE_ITEM.format(
            key=key,
            old=result.old_coins.get(key, 0),
            new=result.coins.get(key, 0),
        )
        for key in result.touched
        if result.old_coins.get(key, 0) != result.coins.get(key, 0)
    ]
    return "；".join(parts)


@coins_matcher.handle()
async def handle_coins(event: MessageEvent) -> None:
    """处理 .钱币：查看或按紧凑写法收支。"""
    if not isinstance(event, GroupMessageEvent):
        await coins_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await coins_matcher.finish(text.TXT_CHAR_MISS)

    if not rest:
        values: Dict[str, int] = {
            key: int(character.coins.get(key, 0) or 0)
            for key in COIN_KEY_LIST
        }
        await coins_matcher.finish(text.TXT_COIN_VIEW.format(**values))

    try:
        operations = parse_coin_operations(rest)
    except AssertionError as exc:
        await coins_matcher.finish(str(exc))

    try:
        result = apply_coin_operations(character.coins, operations)
    except CoinInsufficient as exc:
        await coins_matcher.finish(
            text.TXT_COIN_INSUFFICIENT.format(
                amount=exc.amount,
                unit=exc.unit,
                need=exc.need_cp,
                total=exc.total_cp,
            )
        )

    character.coins = result.coins
    await save_character(character)

    lines = [
        text.TXT_COIN_DONE.format(
            ops="，".join(operation.get_info() for operation in operations)
        )
    ]
    if result.details:
        lines.append("；".join(result.details))
    changes = _format_changes(result)
    if changes:
        lines.append(changes)
    await coins_matcher.finish("\n".join(lines))
