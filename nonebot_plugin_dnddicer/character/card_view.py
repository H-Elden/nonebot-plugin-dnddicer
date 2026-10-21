"""角色卡图片的展示视图（纯函数，无 IO）。

把 ``DNDCharacter`` 转成单页高密度卡面所需的页眉、六属性卡、面板与法术区：

- 只做展示整理，不按规则重算：AC / 先攻 / 豁免 / 技能等仍以卡面手填值为准
  （2026-10-21 卡图批次口径），唯一例外是熟练加值按等级公式计算（拍板④）；
- 空段不输出（低等级角色没有物品/法术时不画空面板）；
- 立绘字节在这里转 data URI，渲染过程不读文件、不发网络请求；
- 标记位用布尔值交给模板渲染（方块 / 星星 / 准备圆点），视图不拼 HTML。

2026-10-21 改版：按 ``doc/refs/card-v2`` 的单页高密度版式重写，旧两栏视图
（``vitals`` / 通用 ``rows``）全部移除。同日批②接上 ``$钱币$`` / ``$进度$`` /
``$故事$``、武器与法术详情、特性/专长/能力说明。
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from .constants import (
    ABILITY_LIST,
    BACKGROUND_KEY_LIST,
    CHECK_ITEM_INDEX_DICT,
    COIN_KEY_LIST,
    COMBAT_KEY_LIST,
    SKILL_LIST,
    SKILL_PARENT_DICT,
    SPELL_LEVEL_MAX,
)
from .models import DNDCharacter

#: 法术位格子里最多画几个方块（再多就只显示数字，避免撑破格子）
_SLOT_PIPS_MAX = 9

#: ``$物品$`` 条目的 ``名称x数量`` 形态
_ITEM_RE = re.compile(r"^(?P<name>.+?)(?:[xX×](?P<qty>\d+))?$")


@dataclass(frozen=True)
class CoreStat:
    """页眉核心数值（AC / 先攻 / 速度 / 被动察觉 / 熟练）。"""

    label: str
    value: str


@dataclass(frozen=True)
class SaveView:
    """一条豁免：值 + 是否熟练。"""

    label: str
    value: str
    proficient: bool


@dataclass(frozen=True)
class SkillView:
    """一条技能：值 + 熟练 / 专精标记。"""

    name: str
    value: str
    proficient: bool
    expertise: bool


@dataclass(frozen=True)
class AbilityView:
    """一张属性卡：值、调整值、豁免与技能列表。"""

    name: str
    score: str
    mod: str
    save: Optional[SaveView]
    skills: Tuple[SkillView, ...] = ()


@dataclass(frozen=True)
class WeaponView:
    """武器表一行（五列）。"""

    name: str
    hit: str
    damage: str
    damage_type: str
    note: str = ""


@dataclass(frozen=True)
class FeatureView:
    """特性 / 专长 / 能力一行：名称 + 次数 + 说明。"""

    name: str
    uses: str = ""
    text: str = ""


@dataclass(frozen=True)
class SpellView:
    """法术表一行（八列）。"""

    name: str
    prepared: bool
    time: str = ""
    range: str = ""
    concentration: bool = False
    ritual: bool = False
    material: bool = False
    note: str = ""


@dataclass(frozen=True)
class SpellGroupView:
    """一档法术（戏法或 1~9 环）。"""

    label: str
    spells: Tuple[SpellView, ...]


@dataclass(frozen=True)
class SlotView:
    """法术位格子：``3/4`` + 方块数；``空`` 表示该环没有法术位。"""

    label: str
    value: str
    filled: int = 0
    total: int = 0
    empty: bool = False


@dataclass(frozen=True)
class BackgroundRow:
    """背景与个性的一行（最多两个键值对）。"""

    cells: Tuple[Tuple[str, str], ...] = ()


@dataclass(frozen=True)
class CoinView:
    """钱币一列（数据补齐批次使用）。"""

    label: str
    value: str


@dataclass(frozen=True)
class CharacterCardView:
    """单页角色卡图模板的全部输入。"""

    name: str
    subtitle: str
    portrait_data_uri: str = ""
    portrait_initial: str = "?"
    has_portrait: bool = False
    core_stats: Tuple[CoreStat, ...] = ()
    xp: str = ""
    xp_next: str = ""
    hp: str = "—"
    hp_state: str = ""
    temp_hp: str = "—"
    hit_dice: str = "—"
    death_success: int = 0
    death_failure: int = 0
    death_state: str = ""
    inspiration: Optional[bool] = None
    abilities: Tuple[AbilityView, ...] = ()
    proficiencies: Tuple[str, ...] = ()
    combat_notes: Tuple[str, ...] = ()
    weapons: Tuple[WeaponView, ...] = ()
    traits: Tuple[FeatureView, ...] = ()
    feats: Tuple[FeatureView, ...] = ()
    class_features: Tuple[FeatureView, ...] = ()
    items: Tuple[str, ...] = ()
    coins: Tuple[CoinView, ...] = ()
    background_rows: Tuple[BackgroundRow, ...] = ()
    story: str = ""
    spellcasting: str = "—"
    spell_dc: str = ""
    spell_attack: str = ""
    slot_rows: Tuple[Tuple[SlotView, ...], ...] = ()
    pact_slot: Optional[SlotView] = None
    has_slots: bool = False
    spell_groups: Tuple[SpellGroupView, ...] = ()


def _subtitle(character: DNDCharacter) -> str:
    """副标题：种族 · 职业（子职）· N 级，缺项跳过。"""
    parts = []
    if character.race:
        parts.append(character.race)
    if character.char_class or character.subclass:
        class_text = character.char_class
        if character.subclass:
            class_text += f"（{character.subclass}）"
        parts.append(class_text)
    if character.ability_info.is_init and character.ability_info.level > 0:
        parts.append(f"{character.ability_info.level} 级")
    return " · ".join(parts) if parts else "未记录身份"


def _thousands(value: str) -> str:
    """数字加千位分隔（只在展示层加，卡面文本仍写原始数字）。"""
    text = value.strip()
    return f"{int(text):,}" if text.isdigit() else text


def _split_name_text(item: str) -> Tuple[str, str]:
    """把 ``名称:说明`` 拆成两段（没有冒号时说明为空）。"""
    name, _, text = item.replace("：", ":").partition(":")
    return name.strip(), text.strip()


def _progress(character: DNDCharacter) -> Tuple[str, str, Optional[bool]]:
    """``$进度$`` → (经验, 下一级, 英雄激励)；未记录时返回空串 / None。"""
    raw = character.progress.get("经验", "")
    xp = xp_next = ""
    if raw:
        current, _, following = raw.partition("/")
        xp = _thousands(current)
        xp_next = _thousands(following)
    flag = character.progress.get("激励", "")
    inspiration = None
    if flag:
        inspiration = flag == "有"
    return xp, xp_next, inspiration


def _coin_views(character: DNDCharacter) -> Tuple[CoinView, ...]:
    """``$钱币$`` → 固定五列的展示值（未写的币值按 0 显示）。"""
    if not character.coins:
        return ()
    return tuple(
        CoinView(label=key, value=str(character.coins.get(key, 0)))
        for key in COIN_KEY_LIST
    )


def _core_stats(character: DNDCharacter) -> Tuple[CoreStat, ...]:
    """页眉核心数值：``$战斗$`` 四项 + 按等级算出的熟练加值。

    宽度不写死：让每个格子按「标签 + 数值」的字符长度自适应（用户 2026-10-21
    明确要求不要五个等宽格子）。
    """
    stats = [
        CoreStat(label, character.combat.get(label) or "—")
        for label in COMBAT_KEY_LIST
    ]
    info = character.ability_info
    if info.is_init and info.level > 0:
        stats.append(CoreStat("熟练", f"+{info.get_prof_bonus()}"))
    return tuple(stats)


def _hp_cells(character: DNDCharacter) -> Tuple[str, str, str, str]:
    """HP 摘要 → (生命值, 状态后缀, 临时生命, 生命骰)。"""
    info = character.hp_info
    if not info.is_init:
        return "—", "", "—", "—"
    if info.hp_max > 0:
        hp = f"{info.hp_cur}/{info.hp_max}"
    else:
        hp = str(info.hp_cur)
    if info.is_dead:
        state = "已死亡"
    elif info.is_stable:
        state = "稳定"
    elif info.is_dying():
        state = "濒死"
    elif not info.is_alive:
        state = "昏迷"
    else:
        state = ""
    temp = str(info.hp_temp) if info.hp_temp > 0 else "—"
    if info.hp_dice_type > 0:
        dice = f"{info.hp_dice_num}/{info.hp_dice_max} D{info.hp_dice_type}"
    else:
        dice = "—"
    return hp, state, temp, dice


def _death_state(character: DNDCharacter) -> str:
    """死亡豁免行改用文字的情形：已死亡 / 伤势稳定。"""
    info = character.hp_info
    if not info.is_init:
        return ""
    if info.is_dead:
        return "已死亡"
    if info.is_stable:
        return "伤势稳定"
    return ""


def _skill_views(character: DNDCharacter, ability: str) -> Tuple[SkillView, ...]:
    """某属性下的技能（只画已填条目；先攻归页眉，不重复）。"""
    prof = character.ability_info.check_prof
    rows = []
    for skill in SKILL_LIST:
        if skill == "先攻" or SKILL_PARENT_DICT.get(skill) != ability:
            continue
        raw = character.skills.get(skill, "").strip()
        if not raw:
            continue
        expertise = raw.endswith(("*", "＊"))
        value = raw.rstrip("*＊").strip() if expertise else raw
        scale = prof[CHECK_ITEM_INDEX_DICT[skill]]
        expertise = expertise or scale >= 2
        proficient = expertise or scale >= 1
        rows.append(
            SkillView(
                name=skill,
                value=value,
                proficient=proficient,
                expertise=expertise,
            )
        )
    return tuple(rows)


def _save_view(character: DNDCharacter, ability: str) -> Optional[SaveView]:
    """某属性的豁免行：有值或有熟练才画。"""
    value = character.saves.get(ability, "").strip()
    scale = character.ability_info.check_prof[
        CHECK_ITEM_INDEX_DICT[f"{ability}豁免"]
    ]
    if not value and scale <= 0:
        return None
    return SaveView(label="豁免", value=value or "—", proficient=scale > 0)


def _ability_views(character: DNDCharacter) -> Tuple[AbilityView, ...]:
    """六张属性卡：``$属性值$`` 优先，缺失退回 ``$属性$`` 原始值。"""
    info = character.ability_info
    rows = []
    for index, name in enumerate(ABILITY_LIST):
        display = character.ability_display.get(name, "").strip()
        if display:
            score, _, mod = display.partition("/")
            score, mod = score.strip(), mod.strip()
        else:
            raw = info.ability[index] if info.is_init else 0
            score = str(raw) if raw else "—"
            mod = "—"
        rows.append(
            AbilityView(
                name=name,
                score=score or "—",
                mod=mod or "—",
                save=_save_view(character, name),
                skills=_skill_views(character, name),
            )
        )
    return tuple(rows)


def _weapon_views(character: DNDCharacter) -> Tuple[WeaponView, ...]:
    """武器五行：名称 / 命中 / 伤害 / 类型 / 备注。"""
    rows = []
    for weapon in character.weapons:
        hit = "—" if weapon.no_attack else (weapon.attack_bonus or "—")
        rows.append(
            WeaponView(
                name=weapon.name,
                hit=hit,
                damage=weapon.damage_expr or "—",
                damage_type=weapon.damage_type or "—",
                note=weapon.note,
            )
        )
    return tuple(rows)


def _class_features(character: DNDCharacter) -> Tuple[FeatureView, ...]:
    """有次数的能力：名称 + ``当前/上限 恢复档`` + 说明。"""
    rows = []
    for feature in character.features:
        uses = ""
        if feature.uses_max > 0:
            uses = f"{feature.uses_cur}/{feature.uses_max}"
            recover = feature.get_recover_display()
            if recover:
                uses += f" {recover}"
        rows.append(
            FeatureView(name=feature.name, uses=uses, text=feature.text)
        )
    return tuple(rows)


def _item_lines(character: DNDCharacter) -> Tuple[str, ...]:
    """背包条目：``名称``、``×N``（N>1）、``[装备]``。"""
    lines = []
    for raw in character.items:
        equipped = raw.endswith("[装备]")
        body = raw[: -len("[装备]")].strip() if equipped else raw.strip()
        matched = _ITEM_RE.match(body)
        if matched is None:
            text = body
        else:
            text = matched.group("name").strip()
            quantity = int(matched.group("qty") or "1")
            if quantity > 1:
                text += f" ×{quantity}"
        if equipped:
            text += " [装备]"
        lines.append(text)
    return tuple(lines)


def _background_rows(character: DNDCharacter) -> Tuple[BackgroundRow, ...]:
    """背景与个性：固定键序，两列一行；未列出的键按录入顺序追加。"""
    items = [
        (key, character.background[key])
        for key in BACKGROUND_KEY_LIST
        if character.background.get(key)
    ]
    items.extend(
        (key, value)
        for key, value in character.background.items()
        if key not in BACKGROUND_KEY_LIST and value
    )
    rows = [
        BackgroundRow(cells=tuple(items[index:index + 2]))
        for index in range(0, len(items), 2)
    ]
    return tuple(rows)


def _slot_view(is_pact: bool, level: int, cur: int, maximum: int) -> SlotView:
    """单个法术位格子；空环画 ``—``，方块数超过上限就不画。"""
    if is_pact:
        label = f"契约{level}环"
    else:
        label = f"{level}环"
    if maximum <= 0:
        return SlotView(label=label, value="—", empty=True)
    total = maximum if maximum <= _SLOT_PIPS_MAX else 0
    return SlotView(
        label=label,
        value=f"{cur}/{maximum}",
        filled=min(cur, total) if total else 0,
        total=total,
    )


def _slot_rows(
    character: DNDCharacter,
) -> Tuple[Tuple[Tuple[SlotView, ...], ...], Optional[SlotView], bool]:
    """法术位 3×3 网格、契约位单列一行、是否有任何法术位。"""
    slots = character.spell_slots
    cells = [
        _slot_view(False, level, slots.slots_cur[level - 1], slots.slots_max[level - 1])
        for level in range(1, SPELL_LEVEL_MAX + 1)
    ]
    rows = (tuple(cells[0:3]), tuple(cells[3:6]), tuple(cells[6:9]))
    pact = None
    if slots.pact_max > 0:
        pact = _slot_view(True, slots.pact_level, slots.pact_cur, slots.pact_max)
    has_slots = bool(pact) or any(not slot.empty for slot in cells)
    return rows, pact, has_slots


def _spell_groups(character: DNDCharacter) -> Tuple[SpellGroupView, ...]:
    """法术按环阶分组（戏法 / 1 环…），并带上卡面详情与备注。"""
    groups = []
    for level in range(0, SPELL_LEVEL_MAX + 1):
        spells = [spell for spell in character.spells if spell.level == level]
        if not spells:
            continue
        label = "戏法" if level == 0 else f"{level} 环"
        groups.append(
            SpellGroupView(
                label=label,
                spells=tuple(
                    SpellView(
                        name=spell.name,
                        prepared=spell.prepared,
                        time=spell.cast_time,
                        range=spell.range,
                        concentration=spell.concentration,
                        ritual=spell.ritual,
                        material=spell.material,
                        note=spell.note,
                    )
                    for spell in spells
                ),
            )
        )
    return tuple(groups)


def _named_features(items: Tuple[str, ...]) -> Tuple[FeatureView, ...]:
    """``$专长$`` / ``$特性$`` 的 ``名称:说明`` 条目拆成两段。"""
    rows = []
    for item in items:
        name, text = _split_name_text(item)
        rows.append(FeatureView(name=name or item, text=text))
    return tuple(rows)


def build_card_view(
    character: DNDCharacter,
    portrait: bytes = b"",
    portrait_mime: str = "",
) -> CharacterCardView:
    """把角色卡模型转成卡面视图；``portrait`` 为已校验的原始图片字节。"""
    portrait_uri = ""
    if portrait:
        mime = portrait_mime or "image/png"
        encoded = base64.b64encode(portrait).decode("ascii")
        portrait_uri = f"data:{mime};base64,{encoded}"
    name = character.name or "未命名"
    hp, hp_state, temp_hp, hit_dice = _hp_cells(character)
    slot_rows, pact_slot, has_slots = _slot_rows(character)
    xp, xp_next, inspiration = _progress(character)
    hp_info = character.hp_info
    return CharacterCardView(
        name=name,
        subtitle=_subtitle(character),
        portrait_data_uri=portrait_uri,
        portrait_initial=name[0] if name else "?",
        has_portrait=bool(portrait),
        core_stats=_core_stats(character),
        xp=xp,
        xp_next=xp_next,
        hp=hp,
        hp_state=hp_state,
        temp_hp=temp_hp,
        hit_dice=hit_dice,
        death_success=hp_info.ds_success if hp_info.is_init else 0,
        death_failure=hp_info.ds_failure if hp_info.is_init else 0,
        death_state=_death_state(character),
        inspiration=inspiration,
        abilities=_ability_views(character),
        proficiencies=tuple(
            f"{label}：{'、'.join(items)}"
            for label, items in character.ability_info.get_prof_groups()
        ),
        combat_notes=tuple(character.combat_notes),
        weapons=_weapon_views(character),
        traits=_named_features(character.traits),
        feats=_named_features(character.feats),
        class_features=_class_features(character),
        items=_item_lines(character),
        coins=_coin_views(character),
        background_rows=_background_rows(character),
        story=character.story,
        spellcasting=character.spellcasting_ability or "—",
        spell_dc=character.spell_dc,
        spell_attack=character.spell_attack,
        slot_rows=slot_rows,
        pact_slot=pact_slot,
        has_slots=has_slots,
        spell_groups=_spell_groups(character),
    )
