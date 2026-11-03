"""法术清单与法术位命令：``.法术`` / ``.设置法术`` / ``.删除法术`` / ``.法术位``。

命令面（2026-10-20 批②新增）：

- ``.法术``：列出卡上法术、环阶与今日准备标记；
- ``.法术 准备 名称`` / ``.法术 取消 名称``：切换 ``*`` 准备标记（戏法无需准备）；
- ``.法术 提醒 [on|off]``：本群施法未准备提醒开关（默认开，按群持久）；
- ``.设置法术 名称:环阶[*]``：录入或覆盖（多项用 ``;`` 分隔，可写 ``施法属性:智力``）；
- ``.删除法术 名称``：删除（支持模糊匹配，多个用 ``/`` 分隔）；
- ``.法术位``（别名 ``.ss``）：查看；``set 1:4;2:3`` 设置；``1 -1`` / ``契约 -1``
  手动增减；``reset`` 恢复全部（长休规则）。

环阶一律来自卡面录入，不查速查索引、不发网络请求。名称匹配沿用「精确优先，
其次子串，多候选列清单不猜」的两级匹配。
"""

from __future__ import annotations

import re
from typing import List, NamedTuple, Optional, Tuple

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent

from ..character import rules as char_rules
from ..character import spell_combat
from ..character.constants import SPELL_LEVEL_MAX, SPELL_MAX_COUNT
from ..character.models import DNDCharacter, SpellDamagePart, SpellEntry, SpellSlots
from ..character.services import (
    RestService,
    match_spells,
    parse_spell_setting,
    parse_spell_slot_entries,
    spell_slot_label,
)
from ..data import spell_settings
from ..data.characters import get_character, save_character
from ..platform import onebot_v11
from . import base, card_helpers, text
from .weapon import WeaponDamageRoll, append_multi_damage_lines

_HELP_SPELL = (
    ".法术 [准备|取消 名称] [提醒 on|off]\n"
    "  列出法术、环阶与今日准备标记\n"
    "  准备/取消切换标记；戏法无需准备\n"
    "  录入用 .设置法术 名称:环阶"
)
spell_matcher = base.on_dnd_command("法术", _HELP_SPELL, doc="guide/resources")

_HELP_SET_SPELL = (
    ".设置法术 名称:环阶[*] （多项用 ; 分隔）\n"
    "  可写 施法属性:智力; 豁免DC:15; 法术攻击:+8\n"
    "  战斗字段：类型:攻击/豁免/自动/辅助/治疗/特殊\n"
    "  伤害:8d6火焰; 治疗:2d4+3; 多发:3; 升环:+1d6\n"
    "  豁免型写 豁免:敏捷; 成功:半伤/无伤；多段伤害用 + 连接\n"
    "  示例：.设置法术 火球术:3*|类型:豁免|豁免:敏捷|伤害:8d6火焰"
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
    ".法术位 / .ss [目标] [set 环阶:当前/上限]\n"
    "  查看法术位；目标写 @玩家 或角色名\n"
    "  set 设置，如 1:4;2:3；环阶 ±N 手动增减\n"
    "  契约 指契约魔法；reset 恢复全部（长休规则）"
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
        casting_ability, new_spells, spell_dc, spell_attack = parse_spell_setting(rest)
    except AssertionError as exc:
        await set_spell_matcher.finish(str(exc))

    lines: List[str] = []
    if casting_ability:
        character.spellcasting_ability = casting_ability
        lines.append(
            text.TXT_SPELL_ABILITY_SET.format(ability=casting_ability)
        )
    if spell_dc:
        character.spell_dc = spell_dc
        lines.append(text.TXT_SPELL_DC_SET.format(dc=spell_dc))
    if spell_attack:
        character.spell_attack = spell_attack
        lines.append(text.TXT_SPELL_ATTACK_SET.format(attack=spell_attack))

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
            # 只改环阶；已准备标记不被普通设置抹掉（取消准备走 .法术 取消）；
            # 卡面详情：写了 |详情 才整组覆盖，没写就保留原值（2026-10-21 批②）
            existing.level = spell.level
            if spell.prepared:
                existing.prepared = True
            if spell.get_detail_text():
                existing.cast_time = spell.cast_time
                existing.range = spell.range
                existing.concentration = spell.concentration
                existing.ritual = spell.ritual
                existing.material = spell.material
                existing.note = spell.note
                existing.kind = spell.kind
                existing.attack_bonus = spell.attack_bonus
                existing.save_ability = spell.save_ability
                existing.save_dc = spell.save_dc
                existing.save_success = spell.save_success
                existing.damage_parts = spell.damage_parts
                existing.heal_expr = spell.heal_expr
                existing.upcast = spell.upcast
                existing.effect = spell.effect
        else:
            merged.append(spell)
        set_names.append(spell.name)
    if len(merged) > SPELL_MAX_COUNT:
        await set_spell_matcher.finish(f"法术数量最多 {SPELL_MAX_COUNT} 条")

    character.spells = merged
    await save_character(character)

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


#: set / reset 等自身子语法（非数字开头，不得被当成角色名）
_SLOTS_SELF_KEYWORDS = (
    "set", "设置", "reset", "重置", "恢复", "契约", "契约魔法", "契约位",
)


async def _resolve_slots_target(
    bot: Bot, event: GroupMessageEvent, rest: str
) -> Tuple[Optional[DNDCharacter], str, str]:
    """拆出 ``.法术位`` 开头的目标 → (目标卡, 剩余参数, 展示名)。

    数字 / ``set`` / ``reset`` / ``契约`` 等自身子语法优先；只有非数字且
    能匹配到本群绑定卡的首段才当目标。匹配不到时按本人处理。
    """
    mentions = onebot_v11.iter_mentions(rest)
    if mentions:
        target_qq = mentions[0]
        character = await get_character(event.group_id, target_qq)
        if character is None or not character.is_init:
            await spell_slots_matcher.finish(
                onebot_v11.at_reply(target_qq, text.TXT_MENTION_NO_CHAR)
            )
        remaining = onebot_v11.strip_mentions(rest).strip()
        display = await base.resolve_display_name(
            bot, event, target_qq, char_name=character.name
        )
        return character, remaining, display

    if not rest:
        return None, rest, ""

    token, separator, tail = rest.partition(" ")
    lowered = token.lower()
    if not token or token[0].isdigit() or lowered in _SLOTS_SELF_KEYWORDS:
        return None, rest, ""
    if lowered.startswith("set") or lowered.startswith("契约"):
        return None, rest, ""

    matches = await card_helpers.find_group_characters(
        event.group_id, token
    )
    if len(matches) > 1:
        await spell_slots_matcher.finish(
            text.TXT_TARGET_CARD_MULTI.format(
                name=token,
                names="/".join(
                    char.name or char.user_id for char in matches
                ),
            )
        )
    if len(matches) == 1:
        display = await base.resolve_display_name(
            bot, event, matches[0].user_id, char_name=matches[0].name
        )
        return matches[0], tail.strip() if separator else "", display
    return None, rest, ""


@spell_slots_matcher.handle()
async def handle_spell_slots(bot: Bot, event: MessageEvent) -> None:
    """处理 .法术位 / .ss：查看 / set / ±N / reset（支持 @ 与角色名目标）。"""
    if not isinstance(event, GroupMessageEvent):
        await spell_slots_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    target, rest, target_name = await _resolve_slots_target(
        bot, event, rest
    )
    if target is None:
        character = await get_character(event.group_id, event.user_id)
        if character is None or not character.is_init:
            await spell_slots_matcher.finish(text.TXT_CHAR_MISS)
    else:
        character = target
    slots = character.spell_slots

    if not rest:
        if slots.is_empty():
            template = (
                text.TXT_SLOTS_EMPTY_TARGET
                if target is not None
                else text.TXT_SLOTS_EMPTY
            )
            await spell_slots_matcher.finish(
                template.format(name=target_name)
            )
        template = (
            text.TXT_SLOTS_LIST_TARGET
            if target is not None
            else text.TXT_SLOTS_LIST
        )
        await spell_slots_matcher.finish(
            template.format(
                name=target_name, items=_format_slots_lines(slots)
            )
        )

    if rest in ("reset", "重置", "恢复"):
        for index in range(SPELL_LEVEL_MAX):
            slots.slots_cur[index] = slots.slots_max[index]
        slots.pact_cur = slots.pact_max
        await save_character(character)
        if slots.is_empty():
            template = (
                text.TXT_SLOTS_EMPTY_TARGET
                if target is not None
                else text.TXT_SLOTS_EMPTY
            )
            await spell_slots_matcher.finish(
                template.format(name=target_name)
            )
        template = (
            text.TXT_SLOTS_RESET_TARGET
            if target is not None
            else text.TXT_SLOTS_RESET
        )
        await spell_slots_matcher.finish(
            template.format(
                name=target_name, items=_format_slots_lines(slots)
            )
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
        template = (
            text.TXT_SLOTS_SET_TARGET
            if target is not None
            else text.TXT_SLOTS_SET
        )
        if slots.is_empty():
            await spell_slots_matcher.finish(
                template.format(
                    name=target_name,
                    names="、".join(applied),
                    items="（无）",
                )
            )
        await spell_slots_matcher.finish(
            template.format(
                name=target_name,
                names="、".join(applied),
                items=_format_slots_lines(slots),
            )
        )

    matched = _SLOTS_ACTION_RE.match(rest)
    if matched is None:
        await spell_slots_matcher.finish(text.TXT_SLOTS_USAGE)
    level_target, sign, amount_text = matched.groups()
    amount = int(amount_text) if amount_text else 1
    if amount < 1:
        await spell_slots_matcher.finish(text.TXT_SLOTS_AMOUNT_INVALID)

    is_pact = not level_target.isdigit()
    if is_pact:
        level = slots.pact_level
        if level <= 0 or slots.pact_max <= 0:
            template = (
                text.TXT_SLOTS_NOT_RECORDED_TARGET
                if target is not None
                else text.TXT_SLOTS_NOT_RECORDED
            )
            await spell_slots_matcher.finish(
                template.format(
                    name=target_name,
                    label="契约魔法法术位",
                    hint="契约3:2/2",
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
        level = int(level_target)
        if not 1 <= level <= SPELL_LEVEL_MAX:
            await spell_slots_matcher.finish(
                text.TXT_SLOTS_USAGE
            )
        if slots.slots_max[level - 1] <= 0:
            template = (
                text.TXT_SLOTS_NOT_RECORDED_TARGET
                if target is not None
                else text.TXT_SLOTS_NOT_RECORDED
            )
            await spell_slots_matcher.finish(
                template.format(
                    name=target_name,
                    label=f"{level}环法术位",
                    hint=f"{level}:4/4",
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
    template = (
        text.TXT_SLOTS_MOD_TARGET
        if target is not None
        else text.TXT_SLOTS_MOD
    )
    await spell_slots_matcher.finish(
        template.format(
            name=target_name,
            label=spell_slot_label(is_pact, level),
            old=old,
            max=max_value,
            new=new,
            note=note,
        )
    )


# =========================================================================
# .施法 / .cast（2026-10-20 批③）
# =========================================================================

_HELP_CAST = (
    ".施法 法术名[N环|+N环] / 环阶（.cast）\n"
    "  环阶来自卡面；升环写 火球术4环 或 +1环\n"
    "  .施法 3 用一个 3 环位；戏法不耗位\n"
    "  攻击掷攻击、豁免/自动掷伤害、治疗掷治疗量\n"
    "  仪式施法不耗位；未准备照常施放，只附提醒\n"
    "  示例：.施法 火球术 ｜ .施法 魔法飞弹2 ｜ .施法 2"
)
cast_matcher = base.on_dnd_command(
    "施法", _HELP_CAST, aliases=("cast",), doc="guide/resources"
)

#: 全角数字与加号 → 半角（环阶写法容错）
_FULLWIDTH_CAST_MAP = str.maketrans("０１２３４５６７８９＋", "0123456789+")
#: 纯环阶写法（3 / 3环）
_CAST_LEVEL_ONLY_RE = re.compile(r"^(\d+)\s*环?$")
#: 尾部环阶修饰：法术名 + [+可选]数字 + 可选「环」
_CAST_TAIL_RE = re.compile(r"^(.*?)\s*([+]?)(\d+)\s*环?$")


def _find_exact_spell(spells: List[SpellEntry], name: str) -> Optional[SpellEntry]:
    """按名称精确查找法术（大小写不敏感；供给 `.施法` 的整串优先匹配）。"""
    lowered = name.lower()
    for spell in spells:
        if spell.name.lower() == lowered:
            return spell
    return None


def _parse_cast_modifier(
    arg: str,
) -> Tuple[str, Optional[Tuple[int, bool]]]:
    """把施法参数拆成 ``(法术名, (数值, 是否相对升环) 或 None)``。

    整串精确命中的判断由调用方先做（``火球术4`` 这类带数字的法术名不会被
    误拆）；本函数只处理「名称 + 尾部环阶修饰」，无修饰时返回 ``(arg, None)``。
    """
    matched = _CAST_TAIL_RE.match(arg)
    if matched is None:
        return arg, None
    name = matched.group(1).strip()
    if not name:
        # 纯环阶/只有 +数字 的形态由调用方另行处理
        return "", None
    return name, (int(matched.group(3)), matched.group(2) == "+")


def _split_cast_advantage(arg: str) -> Tuple[str, int]:
    """摘出施法参数末尾的 优势/劣势 → (剩余参数, 1/-1/0)。

    整串精确命中法术名由调用方先判断，避免把名为「优势」的法术误拆。
    """
    for word, value in (("优势", 1), ("劣势", -1)):
        if arg.endswith(word) and len(arg) > len(word):
            return arg[: -len(word)].strip(), value
    return arg, 0


async def _resolve_cast_spell(
    spells: List[SpellEntry], name: str
) -> Tuple[Optional[SpellEntry], List[SpellEntry]]:
    """施法用的法术名匹配（精确优先 → 子串；多候选由调用方列清单）。"""
    candidates = match_spells(spells, name)
    if len(candidates) == 1:
        return candidates[0], candidates
    return None, candidates


async def _finish_cast_no_slot(
    matcher, character: DNDCharacter, level: int
) -> None:
    """环位不足的统一回复（列出当前可用法术位）。"""
    summary = RestService.available_slots_summary(character.spell_slots)
    await matcher.finish(
        text.TXT_CAST_NO_SLOT.format(level=level, available=summary)
    )


class _CastCombat(NamedTuple):
    """施法前已校验好的战斗计划（避免扣位后才报配置错误）。"""

    kind: str
    attack_expression: str
    damage_parts: List[SpellDamagePart]
    upcast_note: str
    save_ability: str
    save_dc: str
    save_success: str
    effect: str
    shots: int = 1
    heal_expression: str = ""


def _build_cast_combat(
    character: DNDCharacter,
    spell: SpellEntry,
    cast_level: int,
    advantage: int,
) -> Optional[_CastCombat]:
    """按法术类型生成战斗计划；未配置类型返回 None。"""
    if not spell.kind:
        return None
    if spell.kind == "攻击":
        bonus = spell_combat.get_attack_bonus(character, spell)
        advantage_text = (
            "优势" if advantage > 0 else "劣势" if advantage < 0 else ""
        )
        parts, note = spell_combat.build_damage_parts(spell, cast_level)
        return _CastCombat(
            "攻击", f"D20{advantage_text}{bonus}", parts, note,
            "", "", "", spell.effect,
            spell_combat.resolve_spell_shots(spell, cast_level),
        )
    if spell.kind == "豁免":
        dc = spell_combat.get_save_dc(character, spell)
        parts, note = spell_combat.build_damage_parts(spell, cast_level)
        return _CastCombat(
            "豁免", "", parts, note,
            spell.save_ability, dc, spell.save_success or "半伤", spell.effect,
        )
    if spell.kind == "自动":
        parts, note = spell_combat.build_damage_parts(spell, cast_level)
        return _CastCombat(
            "自动", "", parts, note, "", "", "", spell.effect,
            spell_combat.resolve_spell_shots(spell, cast_level),
        )
    if spell.kind == "治疗":
        expr, note = spell_combat.build_heal_expression(spell, cast_level)
        return _CastCombat(
            "治疗", "", [], note, "", "", "", spell.effect, 1, expr
        )
    return _CastCombat(spell.kind, "", [], "", "", "", "", spell.effect)


def _append_spell_damage(
    lines: List[str],
    display_name: str,
    spell: SpellEntry,
    shot_rolls: List[List[spell_combat.SpellDamagePartRoll]],
    note: str,
    shots: int = 1,
) -> None:
    """把法术伤害逐发拼进回复；多发逐发显示，单发沿用单行模板。"""
    if not shot_rolls:
        return
    if shots > 1:
        all_rolls = [roll for shot in shot_rolls for roll in shot]
        total = sum(roll.total for roll in all_rolls)
        types = {roll.damage_type for roll in all_rolls if roll.damage_type}
        lines.append(
            text.TXT_SPELL_SHOT_DAMAGE_HEAD.format(
                name=display_name,
                spell=spell.name,
                total=total,
                type=next(iter(types)) if len(types) == 1 else "多类型" if types else "",
                shots=shots,
                note=note,
            )
        )
        for index, shot in enumerate(shot_rolls, start=1):
            lines.append(
                text.TXT_SPELL_SHOT_DAMAGE_ITEM.format(
                    no=index,
                    result=" + ".join(
                        roll.result.get_complete_result() for roll in shot
                    ),
                    type=shot[0].damage_type if len(shot) == 1 else "多类型",
                )
            )
        return

    rolls = shot_rolls[0]
    if not rolls:
        return
    total = sum(roll.total for roll in rolls)
    types = {roll.damage_type for roll in rolls if roll.damage_type}
    if len(rolls) == 1:
        roll = rolls[0]
        lines.append(
            text.TXT_SPELL_DAMAGE.format(
                name=display_name,
                spell=spell.name,
                total=roll.total,
                type=roll.damage_type,
                note=note,
                result=roll.result.get_complete_result(),
            )
        )
        return
    lines.append(
        text.TXT_SPELL_MULTI_DAMAGE_HEAD.format(
            name=display_name,
            spell=spell.name,
            total=total,
            type=next(iter(types)) if len(types) == 1 else "多类型",
            note=note,
        )
    )
    append_multi_damage_lines(
        lines,
        display_name,
        [
            WeaponDamageRoll(
                weapon=spell.name,
                damage_type=roll.damage_type,
                note="",
                result=roll.result,
                total=roll.total,
                no_dice=re.search(r"\d*[dD]\d+", roll.expr) is None,
            )
            for roll in rolls
        ],
    )


def _append_cast_combat(
    lines: List[str],
    combat: Optional[_CastCombat],
    spell: SpellEntry,
    display_name: str,
) -> None:
    """执行战斗计划并把结果追加到回复行。"""
    if combat is None:
        lines.append(text.TXT_CAST_NO_COMBAT.format(spell=spell.name))
        return

    if combat.kind == "治疗":
        result = spell_combat.roll_heal(combat.heal_expression)
        total = result.get_val()
        if re.fullmatch(r"\d+", combat.heal_expression):
            lines.append(
                text.TXT_SPELL_HEAL_FLAT.format(
                    name=display_name,
                    spell=spell.name,
                    total=total,
                    note=combat.upcast_note,
                )
            )
        else:
            lines.append(
                text.TXT_SPELL_HEAL.format(
                    name=display_name,
                    spell=spell.name,
                    total=total,
                    note=combat.upcast_note,
                    result=result.get_complete_result(),
                )
            )
        if combat.effect:
            lines.append(combat.effect)
        return

    if combat.kind == "攻击":
        if combat.shots > 1:
            lines.append(
                text.TXT_SPELL_MULTI_ATTACK_HEAD.format(
                    spell=spell.name, shots=combat.shots
                )
            )
            for index in range(1, combat.shots + 1):
                result = spell_combat.roll_expression(combat.attack_expression)
                lines.append(
                    text.TXT_SPELL_MULTI_ATTACK_ITEM.format(
                        no=index,
                        result=result.get_complete_result(),
                        marker=text.format_nat_shot_marker(result),
                    )
                )
        else:
            result = spell_combat.roll_expression(combat.attack_expression)
            lines.append(
                text.TXT_SPELL_ATTACK_LINE.format(
                    spell=spell.name, result=result.get_complete_result()
                )
            )
            nat_state = text.format_nat_attack_state([result], spell.name)
            if nat_state:
                lines.append(nat_state)
        if combat.effect:
            lines.append(combat.effect)
        if combat.upcast_note:
            lines.append(combat.upcast_note)
        if combat.damage_parts:
            lines.append(
                text.TXT_CAST_ATTACK_HINT_MULTI.format(
                    spell=spell.name, shots=combat.shots
                )
                if combat.shots > 1
                else text.TXT_CAST_ATTACK_HINT.format(spell=spell.name)
            )
        return

    if combat.damage_parts:
        if combat.kind == "豁免":
            lines.append(
                text.TXT_CAST_SAVE_HEAD.format(
                    ability=combat.save_ability,
                    dc=combat.save_dc,
                    success=combat.save_success,
                )
            )
            shot_rolls = [spell_combat.roll_damage_parts(combat.damage_parts)]
        else:
            shot_rolls = spell_combat.roll_damage_shots(
                combat.damage_parts, combat.shots
            )
        _append_spell_damage(
            lines, display_name, spell, shot_rolls,
            combat.upcast_note, combat.shots,
        )
        if combat.effect:
            lines.append(combat.effect)
        return

    if combat.effect:
        lines.append(combat.effect)
    if combat.upcast_note:
        lines.append(combat.upcast_note)


async def _cast_spell(
    matcher,
    event: GroupMessageEvent,
    character: DNDCharacter,
    display_name: str,
    spell: SpellEntry,
    cast_level: int,
    version_2024: bool,
    advantage: int = 0,
) -> None:
    """执行一次已确定法术与环阶的施法结算并回复。"""
    lines: List[str] = []

    # 战斗数据先校验，避免扣掉法术位后才报配置错误
    combat: Optional[_CastCombat] = None
    if spell.kind:
        try:
            combat = _build_cast_combat(
                character, spell, cast_level, advantage
            )
        except spell_combat.SpellCombatError as exc:
            await matcher.finish(str(exc))

    if spell.level == 0:
        lines.append(
            text.TXT_CAST_HEAD.format(
                name=display_name,
                spell=spell.name,
                level=spell.get_level_label(),
            )
        )
        lines.append(text.TXT_CAST_CANTRIP)
    else:
        consumed = RestService.consume_spell_slot(
            character.spell_slots, cast_level
        )
        if consumed is None:
            await _finish_cast_no_slot(matcher, character, cast_level)
        is_pact, actual_level, old, maximum = consumed
        lines.append(
            text.TXT_CAST_HEAD.format(
                name=display_name,
                spell=spell.name,
                # 契约位兜底时实际施法环阶以契约位为准（如 1 环法术用 3 环契约位）
                level=f"{actual_level}环",
            )
        )
        lines.append(
            text.TXT_CAST_SLOT.format(
                label=spell_slot_label(is_pact, actual_level),
                old=old,
                max=maximum,
                new=old - 1,
            )
        )
        await save_character(character)

    if advantage and spell.kind and spell.kind != "攻击":
        lines.append(text.TXT_SPELL_NOT_ATTACK.format(spell=spell.name))

    try:
        _append_cast_combat(lines, combat, spell, display_name)
    except spell_combat.SpellCombatError as exc:
        await matcher.finish(str(exc))

    # 未准备提醒固定在回复末尾（非戏法、成功消耗环位后才判定）
    if (
        spell.level > 0
        and not spell.prepared
        and RestService.should_remind_preparation(
            version_2024, character.char_class
        )
        and await spell_settings.is_reminder_enabled(event.group_id)
    ):
        lines.append(text.TXT_CAST_PREP_HINT.format(name=spell.name))

    await matcher.finish("\n".join(lines))


@cast_matcher.handle()
async def handle_cast(bot: Bot, event: MessageEvent) -> None:
    """处理 .施法：卡面环阶 / 绝对升环 / 相对升环 / 纯环阶。"""
    if not isinstance(event, GroupMessageEvent):
        await cast_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    if not rest:
        await cast_matcher.finish(text.TXT_CAST_USAGE)
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await cast_matcher.finish(text.TXT_CHAR_MISS)

    arg = rest.translate(_FULLWIDTH_CAST_MAP).strip()
    display_name = await base.resolve_display_name(
        bot, event, char_name=character.name
    )
    version_2024 = (
        await char_rules.rules_version(event.group_id)
    ) == char_rules.RULES_2024

    # ① 整串精确命中法术名（支持名称本身以数字结尾的卡面条目）
    exact = _find_exact_spell(character.spells, arg)
    advantage = 0
    if exact is None:
        # 末尾的 优势/劣势 只在整串不是法名时才摘除
        stripped, advantage = _split_cast_advantage(arg)
        if advantage:
            arg = stripped
            exact = _find_exact_spell(character.spells, arg)
    if exact is not None:
        await _cast_spell(
            cast_matcher, event, character, display_name,
            exact, exact.level, version_2024, advantage,
        )
        return

    # ② 纯环阶：.施法 3 / .施法 3环
    level_only = _CAST_LEVEL_ONLY_RE.fullmatch(arg)
    if level_only is not None:
        level = int(level_only.group(1))
        if not 1 <= level <= SPELL_LEVEL_MAX:
            await cast_matcher.finish(text.TXT_CAST_LEVEL_RANGE)
        consumed = RestService.consume_spell_slot(
            character.spell_slots, level, allow_pact_upcast=False
        )
        if consumed is None:
            await _finish_cast_no_slot(cast_matcher, character, level)
        is_pact, actual_level, old, maximum = consumed
        await save_character(character)
        template = (
            text.TXT_CAST_LEVEL_ONLY_PACT
            if is_pact
            else text.TXT_CAST_LEVEL_ONLY
        )
        await cast_matcher.finish(
            template.format(
                name=display_name,
                level=actual_level,
                old=old,
                max=maximum,
                new=old - 1,
            )
        )

    # ③ 法术名 + 可选环阶修饰（绝对 / 相对升环）
    spell_name, modifier = _parse_cast_modifier(arg)
    if not spell_name:
        await cast_matcher.finish(text.TXT_CAST_USAGE)
    spell, candidates = await _resolve_cast_spell(
        character.spells, spell_name
    )
    if spell is None:
        if candidates:
            await cast_matcher.finish(
                text.TXT_CAST_VAGUE.format(
                    name=spell_name,
                    names="/".join(item.name for item in candidates),
                )
            )
        await cast_matcher.finish(
            text.TXT_CAST_NOT_FOUND.format(name=spell_name)
        )

    cast_level = spell.level
    if modifier is not None:
        value, relative = modifier
        if spell.level == 0:
            # 戏法写 0 视作不升环；其余修饰一律拒绝
            if not relative and value == 0:
                modifier = None
            else:
                await cast_matcher.finish(
                    text.TXT_CAST_CANTRIP_UPCAST.format(name=spell.name)
                )
        if modifier is not None:
            if relative:
                if value < 1:
                    await cast_matcher.finish(text.TXT_CAST_UPCAST_ZERO)
                cast_level = spell.level + value
            else:
                cast_level = value
            if cast_level < spell.level:
                await cast_matcher.finish(
                    text.TXT_CAST_TOO_LOW.format(
                        name=spell.name, min=spell.level, level=cast_level
                    )
                )
            if not 1 <= cast_level <= SPELL_LEVEL_MAX:
                await cast_matcher.finish(text.TXT_CAST_LEVEL_RANGE)

    await _cast_spell(
        cast_matcher, event, character, display_name,
        spell, cast_level, version_2024, advantage,
    )
