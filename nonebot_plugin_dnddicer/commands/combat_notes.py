"""战斗记录（``.战斗记录``，2026-10-24 新增）。

``$战斗记录$`` 在 BUFF 表之前作为可维护的临时状态列表：

- ``.战斗记录``：按序号列出；
- ``.战斗记录 +文本``：追加一条，文本含 ``;`` 时拆成多条；
- ``.战斗记录 -序号``：按 1 起序号删除，多个用 ``/`` 或 ``;`` 分隔；
- ``.战斗记录 清``：清空全部。

沿用卡面限制（最多 20 条、每条 ≤60 字、不含 ``$``）；命令直接改
``character.combat_notes`` 后保存整卡，不触碰其他段。
"""

from __future__ import annotations

import re
from typing import List, Tuple

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ..character.constants import COMBAT_NOTE_MAX_COUNT, COMBAT_NOTE_MAX_LEN
from ..character.models import DNDCharacter
from ..data.characters import get_character, save_character
from . import base, text

_HELP = (
    ".战斗记录 [清|+文本|-序号]\n"
    "  无参数：按序号列出战斗记录\n"
    "  添加：+祝福术(专注,3轮)，; 分隔多条\n"
    "  删除：-2 或 -1/3（序号从 1 起）\n"
    "  上限 20 条，每条 60 字"
)
combat_notes_matcher = base.on_dnd_command(
    "战斗记录", _HELP, doc="guide/character-card"
)

#: 全角数字 → 半角（序号输入容错）
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def _format_items(notes: List[str]) -> str:
    """按序号展示战斗记录（清单 / 添加反馈共用）。"""
    return "\n".join(
        text.TXT_COMBAT_NOTE_ITEM.format(index=index, text=note)
        for index, note in enumerate(notes, start=1)
    )


async def _add_notes(
    matcher, character: DNDCharacter, body: str
) -> None:
    """追加一条或多条战斗记录（整条命令原子）。"""
    items = [item.strip() for item in re.split(r"[;；]", body) if item.strip()]
    if not items:
        await matcher.finish(text.TXT_COMBAT_NOTE_USAGE)
    for item in items:
        if "$" in item:
            await matcher.finish(
                text.TXT_COMBAT_NOTE_DOLLAR.format(text=item)
            )
        if len(item) > COMBAT_NOTE_MAX_LEN:
            await matcher.finish(
                text.TXT_COMBAT_NOTE_TOO_LONG.format(
                    max=COMBAT_NOTE_MAX_LEN, text=item
                )
            )
    total = len(character.combat_notes) + len(items)
    if total > COMBAT_NOTE_MAX_COUNT:
        await matcher.finish(
            text.TXT_COMBAT_NOTE_TOO_MANY.format(
                max=COMBAT_NOTE_MAX_COUNT,
                cur=len(character.combat_notes),
                add=len(items),
            )
        )
    character.combat_notes.extend(items)
    await save_character(character)
    await matcher.finish(
        text.TXT_COMBAT_NOTE_ADD.format(
            count=len(items),
            items="；".join(items),
            total=len(character.combat_notes),
        )
    )


def _parse_indexes(body: str) -> Tuple[List[int], List[str]]:
    """解析删除序号 → (合法序号, 无法解析的原文片段)。"""
    indexes: List[int] = []
    invalid: List[str] = []
    for token in (part.strip() for part in re.split(r"[/;；]", body)):
        if not token:
            continue
        normalized = token.translate(_FULLWIDTH_DIGITS)
        if not normalized.isdigit():
            invalid.append(token)
            continue
        number = int(normalized)
        if number not in indexes:
            indexes.append(number)
    return indexes, invalid


@combat_notes_matcher.handle()
async def handle_combat_notes(event: MessageEvent) -> None:
    """处理 .战斗记录：查看 / 添加 / 删除 / 清空。"""
    if not isinstance(event, GroupMessageEvent):
        await combat_notes_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await combat_notes_matcher.finish(text.TXT_CHAR_MISS)

    if not rest:
        if not character.combat_notes:
            await combat_notes_matcher.finish(text.TXT_COMBAT_NOTE_EMPTY)
        await combat_notes_matcher.finish(
            text.TXT_COMBAT_NOTE_LIST.format(
                count=len(character.combat_notes),
                items=_format_items(character.combat_notes),
            )
        )

    if rest in ("清", "清空"):
        if not character.combat_notes:
            await combat_notes_matcher.finish(text.TXT_COMBAT_NOTE_CLR_EMPTY)
        count = len(character.combat_notes)
        character.combat_notes = []
        await save_character(character)
        await combat_notes_matcher.finish(
            text.TXT_COMBAT_NOTE_CLR.format(count=count)
        )

    if rest.startswith(("+", "＋")):
        await _add_notes(combat_notes_matcher, character, rest[1:].strip())

    if rest.startswith(("-", "－")):
        body = rest[1:].strip()
        indexes, invalid = _parse_indexes(body)
        if not indexes and not invalid:
            await combat_notes_matcher.finish(text.TXT_COMBAT_NOTE_USAGE)
        total = len(character.combat_notes)
        valid = [index for index in indexes if 1 <= index <= total]
        invalid.extend(str(index) for index in indexes if not 1 <= index <= total)
        if not valid:
            await combat_notes_matcher.finish(
                text.TXT_COMBAT_NOTE_DEL_NONE.format(
                    invalid="/".join(invalid)
                )
            )
        # 从大到小删除，避免序号位移；回报按原序号顺序
        deleted = [
            character.combat_notes[index - 1]
            for index in sorted(valid)
        ]
        for index in sorted(valid, reverse=True):
            del character.combat_notes[index - 1]
        await save_character(character)
        if invalid:
            await combat_notes_matcher.finish(
                text.TXT_COMBAT_NOTE_DEL_PARTIAL.format(
                    items="；".join(deleted), invalid="/".join(invalid)
                )
            )
        await combat_notes_matcher.finish(
            text.TXT_COMBAT_NOTE_DEL.format(items="；".join(deleted))
        )

    await combat_notes_matcher.finish(text.TXT_COMBAT_NOTE_USAGE)
