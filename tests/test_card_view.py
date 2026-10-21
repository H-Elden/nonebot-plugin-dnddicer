"""角色卡图视图（``card_view``）的单测，纯函数、不需要渲染依赖。

覆盖单页版式的数据整理规则：页眉核心数值、六属性卡（豁免/技能/专精合并）、
HP 与死亡豁免状态、武器五列、法术位网格与契约位、法术分组、物品/背景/熟练，
以及低配卡的空段处理。模板结构见 ``test_render_templates.py``。
"""

from __future__ import annotations

import pytest

from nonebot_plugin_dnddicer.character.card_view import build_card_view
from nonebot_plugin_dnddicer.character.constants import (
    ABILITY_LIST,
    CHECK_ITEM_INDEX_DICT,
)
from nonebot_plugin_dnddicer.character.models import DNDCharacter
from nonebot_plugin_dnddicer.character.services import (
    CharacterService,
    gen_template_char,
)

_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-portrait-bytes"


def _empty(name: str = "空卡") -> DNDCharacter:
    """只有姓名的一张卡（其余全空）。"""
    return DNDCharacter(group_id="g", user_id="u", name=name, is_init=True)


def test_header_and_core_stats() -> None:
    """页眉：姓名、副标题、核心数值、熟练按等级计算、HP 五格。"""
    view = build_card_view(gen_template_char())
    assert view.name == "张三"
    assert view.subtitle == "高等精灵 · 法师（塑能师） · 5 级"
    assert {stat.label: stat.value for stat in view.core_stats} == {
        "AC": "15",
        "先攻": "+2",
        "速度": "30",
        "被动察觉": "13",
        "熟练": "+3",
    }
    assert view.hp == "29/37"
    assert view.hp_state == ""
    assert view.temp_hp == "5"
    assert view.hit_dice == "5/5 D6"
    assert (view.death_success, view.death_failure, view.death_state) == (0, 0, "")
    assert (view.xp, view.xp_next, view.inspiration) == ("6,500", "14,000", True)


def test_ability_blocks_merge_saves_and_skills() -> None:
    """六属性卡：值/调整、豁免、技能与专精标记来自三处数据。"""
    view = build_card_view(gen_template_char())
    assert [ability.name for ability in view.abilities] == ABILITY_LIST

    strength = view.abilities[0]
    assert (strength.score, strength.mod) == ("8", "-1")
    assert strength.save is not None
    assert (strength.save.value, strength.save.proficient) == ("+1", False)

    intelligence = view.abilities[3]
    assert (intelligence.score, intelligence.mod) == ("18", "+4")
    assert (intelligence.save.value, intelligence.save.proficient) == ("+9", True)

    skills = {skill.name: skill for ability in view.abilities for skill in ability.skills}
    assert "先攻" not in skills  # 先攻在页眉核心数值里，不重复进技能行
    assert skills["奥秘"].expertise is True
    assert skills["奥秘"].value == "+10"
    assert skills["历史"].proficient is True
    assert skills["运动"].proficient is False
    # 技能顺序沿用技能表顺序（敏捷组：体操、巧手、隐匿）
    assert [skill.name for skill in view.abilities[1].skills] == ["体操", "巧手", "隐匿"]


def test_ability_fallback_to_raw_scores() -> None:
    """没有 ``$属性值$`` 时退回 ``$属性$`` 原始值，调整值显示 ``—``。"""
    char = CharacterService.parse(
        "$姓名$ 小鹿\n$等级$ 1\n$属性$ 9/15/15/15/12/9", "g", "u"
    )
    view = build_card_view(char)
    assert [ability.score for ability in view.abilities] == ["9", "15", "15", "15", "12", "9"]
    assert all(ability.mod == "—" for ability in view.abilities)
    assert all(ability.save is None for ability in view.abilities)
    assert all(ability.skills == () for ability in view.abilities)


def test_expertise_comes_from_star_or_prof_scale() -> None:
    """专精既可由 ``$技能$`` 尾部 ``*`` 表示，也可由 ``$熟练$`` 的 ``2*`` 表示。"""
    char = _empty()
    char.skills = {"隐匿": "+8*", "巧手": "+5"}
    char.ability_info.check_prof[CHECK_ITEM_INDEX_DICT["巧手"]] = 2
    view = build_card_view(char)
    skills = {skill.name: skill for skill in view.abilities[1].skills}
    assert skills["隐匿"].value == "+8"
    assert skills["隐匿"].expertise is True
    assert skills["巧手"].expertise is True
    assert skills["巧手"].proficient is True


def test_save_line_shown_when_only_proficient() -> None:
    """没有豁免值但有熟练时仍画一行，值显示 ``—``。"""
    char = _empty()
    char.ability_info.is_init = True
    char.ability_info.check_prof[CHECK_ITEM_INDEX_DICT["力量豁免"]] = 1
    view = build_card_view(char)
    save = view.abilities[0].save
    assert save is not None
    assert (save.value, save.proficient) == ("—", True)


def test_hp_states_and_death_saves() -> None:
    """HP 状态后缀与死亡豁免文字（濒死 / 稳定 / 已死亡）。"""
    char = _empty()
    char.hp_info.initialize(0, 20, 0, 8, 3, 3)
    view = build_card_view(char)
    assert (view.hp, view.hp_state) == ("0/20", "濒死")
    assert view.death_state == ""

    char.hp_info.add_death_failure(2)
    view = build_card_view(char)
    assert view.death_failure == 2

    char.hp_info.add_death_success(3)
    view = build_card_view(char)
    assert (view.hp_state, view.death_state) == ("稳定", "伤势稳定")

    char.hp_info.add_death_failure(3)
    view = build_card_view(char)
    assert (view.hp_state, view.death_state) == ("已死亡", "已死亡")


def test_temp_hp_and_hit_dice() -> None:
    char = _empty()
    char.hp_info.initialize(10, 20, 5, 8, 3, 3)
    view = build_card_view(char)
    assert view.temp_hp == "5"
    assert view.hit_dice == "3/3 D8"


def test_weapons_five_columns() -> None:
    view = build_card_view(gen_template_char())
    assert [weapon.name for weapon in view.weapons] == ["火焰箭", "匕首", "法杖", "轻弩"]
    assert (view.weapons[0].hit, view.weapons[0].damage, view.weapons[0].damage_type) == (
        "+7",
        "2d10",
        "火焰",
    )
    assert view.weapons[0].note == "法术攻击 · 120尺"
    assert view.weapons[1].hit == "+5"
    assert view.weapons[1].damage == "1d4+2"
    assert view.weapons[1].damage_type == "穿刺"
    assert view.weapons[1].note == "灵巧 · 轻型"


def test_slots_grid_and_pact() -> None:
    char = _empty()
    char.spell_slots.slots_cur = [4, 3, 2, 0, 0, 0, 0, 0, 0]
    char.spell_slots.slots_max = [4, 3, 2, 0, 0, 0, 0, 0, 0]
    view = build_card_view(char)
    assert view.has_slots is True
    assert view.slot_rows[0][0].value == "4/4"
    assert view.slot_rows[0][0].total == 4
    assert view.slot_rows[1][0].empty is True
    assert view.slot_rows[1][0].value == "—"
    assert view.pact_slot is None

    char.spell_slots.pact_level = 3
    char.spell_slots.pact_cur = 2
    char.spell_slots.pact_max = 2
    view = build_card_view(char)
    assert view.pact_slot is not None
    assert view.pact_slot.label == "契约3环"
    assert view.pact_slot.value == "2/2"


def test_slot_pips_cap() -> None:
    """单级法术位超过 9 个时不画方块，只显示数字。"""
    char = _empty()
    char.spell_slots.slots_cur[0] = 3
    char.spell_slots.slots_max[0] = 12
    view = build_card_view(char)
    slot = view.slot_rows[0][0]
    assert slot.value == "3/12"
    assert (slot.filled, slot.total) == (0, 0)


def test_spells_grouped_by_level() -> None:
    view = build_card_view(gen_template_char())
    assert [group.label for group in view.spell_groups] == ["戏法", "1 环", "2 环", "3 环"]
    assert [spell.name for spell in view.spell_groups[0].spells] == ["火焰箭"]
    assert view.spell_groups[1].spells[0].prepared is True
    assert view.spell_groups[3].spells[1].prepared is False
    fireball = view.spell_groups[3].spells[0]
    assert (fireball.time, fireball.range, fireball.material) == ("1动作", "150尺", True)
    assert fireball.note == "8d6 火焰 / 敏捷"
    spells = {spell.name: spell for group in view.spell_groups for spell in group.spells}
    assert spells["侦测魔法"].concentration is True
    assert spells["侦测魔法"].ritual is True
    assert spells["云雾术"].material is True


def test_items_proficiencies_background() -> None:
    view = build_card_view(gen_template_char())
    assert "法术书 [装备]" in view.items
    assert "治疗药水 ×2" in view.items
    assert "绳索50尺" in view.items
    assert view.proficiencies[0] == "武器：匕首、法杖、轻弩"
    assert view.background_rows[0].cells[0] == ("背景", "贤者")
    assert len(view.background_rows) == 5  # 9 项 → 5 行，末行只有一格


def test_background_rows_pairing() -> None:
    char = _empty()
    char.background = {"背景": "士兵", "阵营": "守序善良", "年龄": "32"}
    view = build_card_view(char)
    assert len(view.background_rows) == 2
    assert view.background_rows[0].cells == (("背景", "士兵"), ("阵营", "守序善良"))
    assert view.background_rows[1].cells == (("年龄", "32"),)


def test_empty_card_has_no_panels() -> None:
    view = build_card_view(_empty())
    assert [stat.label for stat in view.core_stats] == ["AC", "先攻", "速度", "被动察觉"]
    assert all(stat.value == "—" for stat in view.core_stats)
    assert view.subtitle == "未记录身份"
    assert view.hp == "—" and view.temp_hp == "—" and view.hit_dice == "—"
    assert all(ability.score == "—" for ability in view.abilities)
    assert view.weapons == () and view.items == () and view.combat_notes == ()
    assert view.feats == () and view.traits == () and view.class_features == ()
    assert view.background_rows == () and view.proficiencies == ()
    assert view.has_slots is False
    assert all(slot.empty for row in view.slot_rows for slot in row)
    assert view.spell_groups == ()


def test_card_face_extensions_are_wired() -> None:
    """批②字段：经验、激励、钱币、故事、法术详情与说明文本。"""
    view = build_card_view(gen_template_char())
    assert (view.xp, view.xp_next, view.inspiration) == ("6,500", "14,000", True)
    assert [coin.label for coin in view.coins] == ["CP", "SP", "EP", "GP", "PP"]
    assert [coin.value for coin in view.coins] == ["0", "8", "0", "18", "0"]
    assert view.story.startswith("张三出身")
    assert any(spell.note for group in view.spell_groups for spell in group.spells)
    assert view.feats[0].text == "专注豁免具有优势；可借机施法"
    assert view.traits[0].text.startswith("60 尺内微光")
    assert view.class_features[0].text.startswith("短休时回复")
    assert (view.spell_dc, view.spell_attack) == ("15", "+7")


def test_coins_fill_missing_denominations() -> None:
    """只记录一种币值时，卡面仍按五种币值补齐（缺省 0）。"""
    char = _empty()
    char.coins = {"GP": 18}
    view = build_card_view(char)
    assert [coin.label for coin in view.coins] == ["CP", "SP", "EP", "GP", "PP"]
    assert [coin.value for coin in view.coins] == ["0", "0", "0", "18", "0"]


def test_progress_without_next_level() -> None:
    char = _empty()
    char.progress = {"经验": "500", "激励": "无"}
    view = build_card_view(char)
    assert (view.xp, view.xp_next, view.inspiration) == ("500", "", False)


def test_portrait_data_uri() -> None:
    view = build_card_view(_empty("张三"), _PNG, "image/png")
    assert view.has_portrait is True
    assert view.portrait_data_uri.startswith("data:image/png;base64,")
    assert view.portrait_initial == "张"

    plain = build_card_view(_empty("张三"))
    assert plain.has_portrait is False
    assert plain.portrait_data_uri == ""
