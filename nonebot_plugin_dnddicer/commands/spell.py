"""法术清单与法术位命令：``.法术`` / ``.设置法术`` / ``.删除法术`` / ``.法术位``。

命令面（2026-10-20 批②新增）：

- ``.法术``：列出卡上法术、环阶与今日准备标记；
- ``.法术 准备 名称`` / ``.法术 取消 名称``：切换 ``*`` 准备标记（戏法无需准备）；
- ``.法术 提醒 [on|off]``：本群施法未准备提醒开关（默认开，按群持久）；
- ``.设置法术 名称:环阶[*]``：录入或覆盖（多项用 ``;`` 分隔，可写 ``施法属性:智力``）；
- ``.删除法术 名称``：删除（支持模糊匹配，多个用 ``/`` 分隔）；
- ``.法术位``（别名 ``.ss``）：查看；``set 1:4,2:3`` 设置；``1 -1`` / ``契约 -1``
  手动增减；``reset`` 恢复全部（长休口径）。

环阶一律来自卡面录入，不查速查索引、不发网络请求。名称匹配沿用「精确优先，
其次子串，多候选列清单不猜」的两级口径。
"""

from __future__ import annotations

import re
from typing import List, Optional

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ..character.constants import SPELL_LEVEL_MAX, SPELL_MAX_COUNT
from ..character.models import SpellEntry, SpellSlots
from ..character.services import (
    match_spells,
    parse_spell_setting,
    parse_spell_slot_entries,
    spell_slot_label,
)
from ..data import spell_settings
from ..data.characters import get_character, save_character
from . import base, text

_HELP_SPELL = (
    ".法术 [准备|取消 名称] [提醒 on|off]\n"
    "  列出法术、环阶与今日准备标记\n"
    "  准备/取消切换标记；戏法无需准备\n"
    "  录入用 .设置法术 名称:环阶"
)
spell_matcher = base.on_dnd_command("法术", _HELP_SPELL, doc="guide/resources")

_HELP_SET_SPELL = (
    ".设置法术 名称:环阶 （多项用 ; 分隔）\n"
    "  环阶 0 = 戏法；尾部 * 表示今日已准备\n"
    "  可写 施法属性:智力 记录施法属性\n"
    "  示例：.设置法术 火球术:3; 火焰箭:0"
)
set_spell_matcher = base.on_dnd_command(
    "设置法术", _HELP_SET_SPELL, doc="guide/resources"
)

_HELP_DEL_SPELL = (
    ".删除法术 名称 （多个用 / 分隔）\n"
    "  删除卡上法术，名称支持模糊匹配\n"
    "  未找到或名称不明确时逐项回报"
)
del_spell_matcher = base.on_dnd_command(
    "删除法术", _HELP_DEL_SPELL, doc="guide/resources"
)

_HELP_SPELL_SLOTS = (
    ".法术位 / .ss [set 环阶:当前/上限]\n"
    "  查看法术位；set 设置，如 1:4,2:3\n"
    "  环阶 ±N 手动增减；契约 指契约魔法\n"
    "  reset 恢复全部（长休口径）"
)
spell_slots_matcher = base.on_dnd_command(
    "法术位", _HELP_SPELL_SLOTS, aliases=("ss",), doc="guide/resources"
)

#: 法术位目标 + 增减：``1 -1`` / ``契约 +1``（N 缺省 1）
_SLOTS_ACTION_RE = re.compile(
    r"^(契约(?:魔法|位)?|\d+)\s*([+-])\s*(\d*)$"
)


def _format_spell_lines(spells: List[SpellEntry]) -> str:
    """法术清单的编号多行展示（清单 / 设置反馈共用）。"""
    lines: List[str] = []
    for index, spell in enumerate(spells, start=1):
        template = (
            text.TXT_SPELL_ITEM_PREPARED
            if spell.prepared
            else text.TXT_SPELL_ITEM
        )
        lines.append(
            template.format(
                index=index,
                name=spell.name,
                level=spell.get_level_label(),
            )
        )
    return "\n".join(lines)


def _format_slots_lines(slots: SpellSlots) -> str:
    """法术位清单：各环在前、契约魔法在后。"""
    lines: List[str] = []
    for level in range(1, SPELL_LEVEL_MAX + 1):
        index = level - 1
        if slots.slots_max[index] <= 0:
            continue
        lines.append(
            text.TXT_SLOTS_ITEM.format(
                level=level,
                cur=slots.slots_cur[index],
                max=slots.slots_max[index],
            )
        )
    if slots.pact_max > 0:
        lines.append(
            text.TXT_SLOTS_PACT_ITEM.format(
                level=slots.pact_level,
                cur=slots.pact_cur,
                max=slots.pact_max,
            )
        )
    return "\n".join(lines)


def _resolve_spell(
    spells: List[SpellEntry], name: str
) -> tuple[Optional[SpellEntry], List[SpellEntry]]:
    """精确优先 → 子串；返回 (唯一命中, 全部候选)。"""
    candidates = match_spells(spells, name)
    if len(candidates) == 1:
        return candidates[0], candidates
    return None, candidates


async def _finish_spell_not_found(name: str, candidates: List[SpellEntry]) -> None:
    """法术未找到 / 名称不明确的统一回复（终止当前命令）。"""
    if candidates:
        await spell_matcher.finish(
            text.TXT_SPELL_VAGUE.format(
                name=name,
                names="/".join(item.name for item in candidates),
            )
        )
    await spell_matcher.finish(text.TXT_SPELL_NOT_FOUND.format(name=name))


def _parse_reminder_switch(value: str) -> Optional[bool]:
    """提醒开关取值 → True/False；无法识别返回 None。"""
    lowered = value.strip().lower()
    if lowered in ("on", "开", "开启"):
        return True
    if lowered in ("off", "关", "关闭"):
        return False
    return None


@spell_matcher.handle()
async def handle_spell(event: MessageEvent) -> None:
    """处理 .法术：清单 / 准备切换 / 提醒开关。"""
    if not isinstance(event, GroupMessageEvent):
        await spell_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()

    # 提醒开关是群级设置，不要求发送者已有角色卡
    if rest.startswith("提醒"):
        value = rest[2:].strip()
        if not value:
            enabled = await spell_settings.is_reminder_enabled(event.group_id)
            await spell_matcher.finish(
                text.TXT_SPELL_REMIND_STATE_ON
                if enabled
                else text.TXT_SPELL_REMIND_STATE_OFF
            )
        switch = _parse_reminder_switch(value)
        if switch is None:
            await spell_matcher.finish(text.TXT_SPELL_REMIND_USAGE)
        await spell_settings.set_reminder_enabled(event.group_id, switch)
        await spell_matcher.finish(
            text.TXT_SPELL_REMIND_ON if switch else text.TXT_SPELL_REMIND_OFF
        )

    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await spell_matcher.finish(text.TXT_CHAR_MISS)

    if not rest:
        if not character.spells:
            await spell_matcher.finish(text.TXT_SPELL_LIST_EMPTY)
        ability_part = (
            text.TXT_SPELL_ABILITY_PART.format(
                ability=character.spellcasting_ability
            )
            if character.spellcasting_ability
            else ""
        )
        await spell_matcher.finish(
            text.TXT_SPELL_LIST.format(
                count=len(character.spells),
                ability=ability_part,
                items=_format_spell_lines(character.spells),
            )
        )

    for keyword, prepared in (("准备", True), ("取消", False)):
        if not rest.startswith(keyword):
            continue
        name = rest[len(keyword):].strip()
        if not name:
            await spell_matcher.finish(text.TXT_SPELL_USAGE)
        spell, candidates = _resolve_spell(character.spells, name)
        if spell is None:
            await _finish_spell_not_found(name, candidates)
        if spell.level == 0:
            await spell_matcher.finish(
                text.TXT_SPELL_PREPARE_CANTRIP.format(name=spell.name)
            )
        if spell.prepared == prepared:
            template = (
                text.TXT_SPELL_ALREADY_PREPARED
                if prepared
                else text.TXT_SPELL_ALREADY_UNPREPARED
            )
            await spell_matcher.finish(
                template.format(name=spell.name, level=spell.get_level_label())
            )
        spell.prepared = prepared
        await save_character(character)
        template = text.TXT_SPELL_PREPARED if prepared else text.TXT_SPELL_UNPREPARED
        await spell_matcher.finish(
            template.format(name=spell.name, level=spell.get_level_label())
        )

    await spell_matcher.finish(text.TXT_SPELL_USAGE)


@set_spell_matcher.handle()
async def handle_set_spell(event: MessageEvent) -> None:
    """处理 .设置法术：录入法术与施法属性（仅操作本人角色卡）。"""
    if not isinstance(event, GroupMessageEvent):
        await set_spell_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    if not rest:
        await set_spell_matcher.finish(text.TXT_SPELL_SET_USAGE)
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await set_spell_matcher.finish(text.TXT_CHAR_MISS)

    try:
        casting_ability, new_spells = parse_spell_setting(rest)
    except AssertionError as exc:
        await set_spell_matcher.finish(str(exc))

    if casting_ability:
        character.spellcasting_ability = casting_ability

    merged: List[SpellEntry] = list(character.spells)
    set_names: List[str] = []
    for spell in new_spells:
        existing = next(
            (
                item for item in merged
                if item.name.lower() == spell.name.lower()
            ),
            None,
        )
        if existing is not None:
            # 只改环阶；已准备标记不被普通设置抹掉（取消准备走 .法术 取消）
            existing.level = spell.level
            if spell.prepared:
                existing.prepared = True
        else:
            merged.append(spell)
        set_names.append(spell.name)
    if len(merged) > SPELL_MAX_COUNT:
        await set_spell_matcher.finish(f"法术数量最多 {SPELL_MAX_COUNT} 条")

    character.spells = merged
    await save_character(character)

    lines: List[str] = []
    if casting_ability:
        lines.append(
            text.TXT_SPELL_ABILITY_SET.format(ability=casting_ability)
        )
    if set_names:
        lines.append(
            text.TXT_SPELL_SET.format(
                names="/".join(set_names),
                count=len(merged),
                items=_format_spell_lines(merged),
            )
        )
    if not lines:  # 理论不可达（解析成功时至少有一项），防御性兜底
        lines.append(text.TXT_SPELL_SET_USAGE)
    await set_spell_matcher.finish("\n".join(lines))


@del_spell_matcher.handle()
async def handle_del_spell(event: MessageEvent) -> None:
    """处理 .删除法术（支持 / 与 ; 分隔多个；名称可只写一部分）。"""
    if not isinstance(event, GroupMessageEvent):
        await del_spell_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    if not rest:
        await del_spell_matcher.finish(text.TXT_SPELL_DEL_USAGE)
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await del_spell_matcher.finish(text.TXT_CHAR_MISS)

    names = [
        item.strip()
        for item in re.split(r"[/;；]", rest)
        if item.strip()
    ]
    remained: List[SpellEntry] = list(character.spells)
    deleted: List[str] = []
    missing: List[str] = []
    vague: List[str] = []
    for name in names:
        candidates = match_spells(remained, name)
        if not candidates:
            missing.append(name)
        elif len(candidates) > 1:
            vague.append(
                text.TXT_SPELL_DEL_VAGUE_ITEM.format(
                    name=name,
                    names="/".join(item.name for item in candidates),
                )
            )
        else:
            remained.remove(candidates[0])
            deleted.append(candidates[0].name)

    lines: List[str] = []
    if deleted:
        if missing:
            lines.append(
                text.TXT_SPELL_DEL_PARTIAL.format(
                    deleted="/".join(deleted), missing="/".join(missing)
                )
            )
        else:
            lines.append(text.TXT_SPELL_DEL.format(deleted="/".join(deleted)))
    elif missing:
        lines.append(text.TXT_SPELL_DEL_MISS.format(missing="/".join(missing)))
    if vague:
        lines.append(text.TXT_SPELL_DEL_VAGUE.format(items="；".join(vague)))
    if not lines:  # 理论不可达（names 非空时必有结论），防御性兜底
        lines.append(text.TXT_SPELL_DEL_MISS.format(missing="/".join(names)))

    if deleted:
        character.spells = remained
        await save_character(character)
    await del_spell_matcher.finish("\n".join(lines))


@spell_slots_matcher.handle()
async def handle_spell_slots(event: MessageEvent) -> None:
    """处理 .法术位 / .ss：查看 / set / ±N / reset。"""
    if not isinstance(event, GroupMessageEvent):
        await spell_slots_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await spell_slots_matcher.finish(text.TXT_CHAR_MISS)
    slots = character.spell_slots

    if not rest:
        if slots.is_empty():
            await spell_slots_matcher.finish(text.TXT_SLOTS_EMPTY)
        await spell_slots_matcher.finish(
            text.TXT_SLOTS_LIST.format(items=_format_slots_lines(slots))
        )

    if rest in ("reset", "重置", "恢复"):
        for index in range(SPELL_LEVEL_MAX):
            slots.slots_cur[index] = slots.slots_max[index]
        slots.pact_cur = slots.pact_max
        await save_character(character)
        if slots.is_empty():
            await spell_slots_matcher.finish(text.TXT_SLOTS_EMPTY)
        await spell_slots_matcher.finish(
            text.TXT_SLOTS_RESET.format(items=_format_slots_lines(slots))
        )

    lowered = rest.lower()
    if lowered.startswith("set") or rest.startswith("设置"):
        content = rest[3:].strip() if lowered.startswith("set") else rest[2:].strip()
        if not content:
            await spell_slots_matcher.finish(text.TXT_SLOTS_USAGE)
        try:
            entries = parse_spell_slot_entries(content, allow_omitted_max=True)
        except AssertionError as exc:
            await spell_slots_matcher.finish(str(exc))
        applied: List[str] = []
        for is_pact, level, cur, max_value in entries:
            label = spell_slot_label(is_pact, level)
            if is_pact:
                if max_value <= 0:
                    slots.pact_level = 0
                    slots.pact_cur = 0
                    slots.pact_max = 0
                else:
                    slots.pact_level = level
                    slots.pact_cur = cur
                    slots.pact_max = max_value
            else:
                slots.slots_cur[level - 1] = cur
                slots.slots_max[level - 1] = max_value
            applied.append(
                text.TXT_SLOTS_SET_NAME.format(
                    label=label, cur=cur, max=max_value
                )
            )
        await save_character(character)
        if slots.is_empty():
            await spell_slots_matcher.finish(
                text.TXT_SLOTS_SET.format(
                    names="、".join(applied), items="（无）"
                )
            )
        await spell_slots_matcher.finish(
            text.TXT_SLOTS_SET.format(
                names="、".join(applied),
                items=_format_slots_lines(slots),
            )
        )

    matched = _SLOTS_ACTION_RE.match(rest)
    if matched is None:
        await spell_slots_matcher.finish(text.TXT_SLOTS_USAGE)
    target, sign, amount_text = matched.groups()
    amount = int(amount_text) if amount_text else 1
    if amount < 1:
        await spell_slots_matcher.finish(text.TXT_SLOTS_AMOUNT_INVALID)

    is_pact = not target.isdigit()
    if is_pact:
        level = slots.pact_level
        if level <= 0 or slots.pact_max <= 0:
            await spell_slots_matcher.finish(
                text.TXT_SLOTS_NOT_RECORDED.format(
                    label="契约魔法法术位", hint="契约3:2/2"
                )
            )
        old, max_value = slots.pact_cur, slots.pact_max
        new = (
            max(0, old - amount)
            if sign == "-"
            else min(max_value, old + amount)
        )
        if new != old:
            slots.pact_cur = new
    else:
        level = int(target)
        if not 1 <= level <= SPELL_LEVEL_MAX:
            await spell_slots_matcher.finish(
                text.TXT_SLOTS_USAGE
            )
        if slots.slots_max[level - 1] <= 0:
            await spell_slots_matcher.finish(
                text.TXT_SLOTS_NOT_RECORDED.format(
                    label=f"{level}环法术位", hint=f"{level}:4/4"
                )
            )
        old = slots.slots_cur[level - 1]
        max_value = slots.slots_max[level - 1]
        new = (
            max(0, old - amount)
            if sign == "-"
            else min(max_value, old + amount)
        )
        if new != old:
            slots.slots_cur[level - 1] = new

    note = ""
    if sign == "-" and new == 0 and old > 0:
        note = text.TXT_SLOTS_MOD_EXHAUSTED
    elif sign == "+" and new == max_value and old < max_value:
        note = text.TXT_SLOTS_MOD_FULL
    if new != old:
        await save_character(character)
    await spell_slots_matcher.finish(
        text.TXT_SLOTS_MOD.format(
            label=spell_slot_label(is_pact, level),
            old=old,
            max=max_value,
            new=new,
            note=note,
        )
    )
