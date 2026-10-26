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
    assert view.name == "伊瑟兰·晨星"
    assert view.subtitle == "高等精灵 · 法师（塑能师） · 5 级"
    assert {stat.label: stat.value for stat in view.core_stats} == {
        "AC": "16",
        "先攻": "+2",
        "速度": "30",
        "被动察觉": "13",
        "熟练": "+3",
    }
    assert view.hp == "37/37"
    assert view.hp_state == ""
    assert view.temp_hp == "—"
    assert view.hit_dice == "5/5 D6"
    assert (view.death_success, view.death_failure, view.death_state) == (0, 0, "")
    assert (view.xp, view.xp_next, view.inspiration) == ("6,500", "14,000", True)


def test_ability_blocks_merge_saves_and_skills() -> None:
    """六属性卡：值/调整、豁免、技能与专精标记全部按属性与熟练现算。"""
    view = build_card_view(gen_template_char())
    assert [ability.name for ability in view.abilities] == ABILITY_LIST

    strength = view.abilities[0]
    assert (strength.score, strength.mod) == ("8", "-1")
    assert strength.save is not None
    # 防护斗篷：全部豁免 +1
    assert (strength.save.value, strength.save.proficient) == ("+0", False)

    intelligence = view.abilities[3]
    assert (intelligence.score, intelligence.mod) == ("18", "+4")
    assert (intelligence.save.value, intelligence.save.proficient) == ("+8", True)

    skills = {skill.name: skill for ability in view.abilities for skill in ability.skills}
    assert "先攻" not in skills  # 先攻在页眉核心数值里，不重复进技能行
    assert skills["调查"].expertise is True
    assert skills["调查"].value == "+10"
    assert skills["奥秘"].proficient is True
    assert skills["奥秘"].value == "+7"
    assert skills["历史"].proficient is True
    assert skills["历史"].value == "+7"
    assert skills["运动"].proficient is False
    assert skills["运动"].value == "-1"
    # 技能顺序沿用技能表顺序（敏捷组：体操、巧手、隐匿）
    assert [skill.name for skill in view.abilities[1].skills] == ["体操", "巧手", "隐匿"]
    # 18 项技能全部画出（先攻除外）
    assert len(skills) == 18


def test_ability_values_are_computed_without_manual_fields() -> None:
    """没有手填展示值时，属性调整、豁免与技能仍按属性/等级/熟练算出来。"""
    char = CharacterService.parse(
        "$姓名$ 小鹿\n$等级$ 1\n$属性$ 9/15/15/15/12/9", "g", "u"
    )
    view = build_card_view(char)
    assert [ability.score for ability in view.abilities] == ["9", "15", "15", "15", "12", "9"]
    assert [ability.mod for ability in view.abilities] == ["-1", "+2", "+2", "+2", "+1", "-1"]
    # 1 级熟练加值 +2；未熟练时豁免只是属性调整值
    assert view.abilities[0].save.value == "-1"
    assert view.abilities[1].save.value == "+2"
    skills = {skill.name: skill for ability in view.abilities for skill in ability.skills}
    assert skills["运动"].value == "-1"
    assert skills["体操"].value == "+2"
    assert all(not skill.proficient for skill in skills.values())


def test_expertise_comes_from_prof_scale() -> None:
    """专精只看 ``$熟练$`` 的 ``2*``；熟练框与专精星随之变化。"""
    char = _empty()
    char.ability_info.is_init = True
    char.ability_info.level = 5
    char.ability_info.ability = [10, 10, 10, 10, 10, 10]
    char.ability_info.check_prof[CHECK_ITEM_INDEX_DICT["隐匿"]] = 2
    char.ability_info.check_prof[CHECK_ITEM_INDEX_DICT["巧手"]] = 1
    view = build_card_view(char)
    skills = {skill.name: skill for skill in view.abilities[1].skills}
    assert skills["隐匿"].value == "+6"
    assert skills["隐匿"].expertise is True
    assert skills["巧手"].value == "+3"
    assert skills["巧手"].proficient is True
    assert skills["巧手"].expertise is False


def test_all_saves_show_with_computed_values() -> None:
    """初始化后六项豁免全部画出，值按属性调整值现算。"""
    char = _empty()
    char.ability_info.is_init = True
    char.ability_info.level = 5
    char.ability_info.ability = [10, 12, 14, 16, 18, 20]
    char.ability_info.check_prof[CHECK_ITEM_INDEX_DICT["力量豁免"]] = 1
    view = build_card_view(char)
    saves = [ability.save for ability in view.abilities]
    assert all(save is not None for save in saves)
    assert [save.value for save in saves] == ["+3", "+1", "+2", "+3", "+4", "+5"]
    assert [save.proficient for save in saves] == [True, False, False, False, False, False]


def test_extra_bonus_participates_in_display() -> None:
    """额外加值进展示值：常数求和、骰子项原样附后、优劣势不改数值。"""
    char = CharacterService.parse(
        "$等级$ 5\n$属性$ 16/10/10/10/10/10\n"
        "$熟练$ 运动\n"
        "$额外加值$ 豁免:+2/运动:+1d4/隐匿:优势",
        "g",
        "u",
    )
    view = build_card_view(char)
    strength = view.abilities[0]
    assert strength.save.value == "+5"  # 力量 +3 + 全局豁免 +2
    skills = {skill.name: skill for ability in view.abilities for skill in ability.skills}
    assert skills["运动"].value == "+6+1d4"  # 力量 +3 + 熟练 +3 + 骰子
    assert skills["隐匿"].value == "+0"  # 优势不改变加值


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
    assert [weapon.name for weapon in view.weapons] == [
        "火焰箭", "冷冻射线", "匕首", "长棍",
    ]
    assert (view.weapons[0].hit, view.weapons[0].damage, view.weapons[0].damage_type) == (
        "+8",
        "2d10",
        "火焰",
    )
    assert view.weapons[0].note == "法术攻击 · 120尺"
    assert (view.weapons[1].hit, view.weapons[1].damage) == ("+8", "2d8")
    assert view.weapons[1].damage_type == "寒冷"
    assert view.weapons[1].note == "法术攻击 · 60尺 · 速度-10"
    assert view.weapons[2].hit == "+5"
    assert view.weapons[2].damage == "1d4+2"
    assert view.weapons[2].damage_type == "穿刺"
    assert view.weapons[2].note == "灵巧 · 轻型"
    assert (view.weapons[3].hit, view.weapons[3].damage) == ("+2", "1d6-1")


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
    assert [spell.name for spell in view.spell_groups[0].spells] == [
        "火焰箭", "冷冻射线", "法师之手", "次级幻象", "魔法伎俩", "光亮术", "心灵之楔",
    ]
    assert all(spell.is_cantrip for spell in view.spell_groups[0].spells)
    assert view.spell_groups[1].spells[0].prepared is True
    assert view.spell_groups[3].spells[1].prepared is True
    fireball = view.spell_groups[3].spells[0]
    assert (fireball.time, fireball.range, fireball.material) == ("1动作", "150尺", True)
    assert fireball.note == "20尺半径 / 8d6 火焰 / 敏捷"
    spells = {spell.name: spell for group in view.spell_groups for spell in group.spells}
    assert spells["侦测魔法"].concentration is True
    assert spells["侦测魔法"].ritual is True
    assert spells["蛛网术"].material is True


def test_items_proficiencies_background() -> None:
    view = build_card_view(gen_template_char())
    assert "法术书" in view.items
    assert "治疗药水" in view.items
    assert "长棍" in view.items
    assert all("[装备]" not in item for item in view.items)
    assert view.proficiencies[0] == "武器：简易武器"
    assert view.background_rows[0].cells[0] == ("背景", "智者")
    assert len(view.background_rows) == 4  # 5r 七项 → 4 行


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
    assert (
        view.feats == ()
        and view.race_traits == ()
        and view.class_traits == ()
        and view.resources == ()
        and view.magic_items == ()
    )
    assert view.background_rows == () and view.proficiencies == ()
    assert view.has_slots is False
    assert all(slot.empty for row in view.slot_rows for slot in row)
    assert view.spell_groups == ()


def test_card_face_extensions_are_wired() -> None:
    """批②字段：经验、激励、钱币、故事、法术详情与说明文本。"""
    view = build_card_view(gen_template_char())
    assert (view.xp, view.xp_next, view.inspiration) == ("6,500", "14,000", True)
    assert [coin.label for coin in view.coins] == ["CP", "SP", "EP", "GP", "PP"]
    assert [coin.value for coin in view.coins] == ["0", "0", "0", "13", "0"]
    assert view.story.startswith("伊瑟兰出身")
    assert len(view.story_lines) == 3
    assert view.story_lines[1].startswith("此后伊瑟兰离开书斋")
    assert any(spell.note for group in view.spell_groups for spell in group.spells)
    assert view.feats[0].text == "习得光亮术、心灵之楔与护盾术；护盾术可免法术位施展一次，长休恢复"
    assert view.race_traits[0].text.startswith("60 尺内微光")
    assert [(item.level, item.name) for item in view.class_traits][:3] == [
        (1, "仪式学家"),
        (1, "奥术回想"),
        (2, "学者"),
    ]
    assert view.class_traits[0].text.startswith("法术书中的仪式")
    assert view.resources[0].text.startswith("短休时恢复")
    assert view.resources[0].uses == "1/1 短休回满"
    assert view.resources[1].uses == "1/1 长休回满"
    assert view.magic_items[0].name == "战法师魔杖 +1"
    assert view.magic_items[0].tag.startswith("魔杖")
    assert view.magic_items[0].paragraphs[1].startswith("此外")
    assert view.magic_items[1].paragraphs == (
        "着装此斗篷期间，你的 AC 和豁免获得 +1 加值。",
    )
    assert (view.spell_dc, view.spell_attack) == ("15", "+8")


def test_coins_fill_missing_denominations() -> None:
    """只记录一种币值时，卡面仍按五种币值补齐（缺省 0）。"""
    char = _empty()
    char.coins = {"GP": 18}
    view = build_card_view(char)
    assert [coin.label for coin in view.coins] == ["CP", "SP", "EP", "GP", "PP"]
    assert [coin.value for coin in view.coins] == ["0", "0", "0", "18", "0"]


def test_initiative_and_next_xp_are_computed_not_read_from_card() -> None:
    """先攻、被动察觉与下一级经验按等级/属性/熟练现算，不读卡面旧值（2026-10-22）。"""
    from nonebot_plugin_dnddicer.character.constants import (
        CHECK_ITEM_INDEX_DICT,
        EXT_ITEM_INDEX_DICT,
    )

    char = gen_template_char()
    char.combat["先攻"] = "+99"
    char.combat["被动察觉"] = "99"
    char.progress = {"经验": "6500/99999", "激励": "有"}
    char.ability_info.check_prof[CHECK_ITEM_INDEX_DICT["先攻"]] = 1
    char.ability_info.check_ext[EXT_ITEM_INDEX_DICT["先攻"]] = "+1"
    view = build_card_view(char)
    stats = {stat.label: stat.value for stat in view.core_stats}
    # 敏捷 +2 + 熟练 +3 + 额外 +1 = +6（不读 $战斗$ 的 +99）
    assert stats["先攻"] == "+6"
    # 感知 11（+0）+ 察觉熟练 +3 = 13（不读 $战斗$ 的 +99）
    assert stats["被动察觉"] == "13"
    # 察觉有优势时，被动察觉 +5
    char.ability_info.check_adv[CHECK_ITEM_INDEX_DICT["察觉"]] = 1
    stats = {stat.label: stat.value for stat in build_card_view(char).core_stats}
    assert stats["被动察觉"] == "18"
    # 父属性（感知）优势同样作用于察觉
    char.ability_info.check_adv[CHECK_ITEM_INDEX_DICT["察觉"]] = 0
    char.ability_info.check_adv[EXT_ITEM_INDEX_DICT["感知"]] = 1
    stats = {stat.label: stat.value for stat in build_card_view(char).core_stats}
    assert stats["被动察觉"] == "18"
    # 5 级下一级经验 = 14000（不读卡面残留的 99999）
    assert (view.xp, view.xp_next) == ("6,500", "14,000")


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


def test_inspiration_three_states_and_version_label() -> None:
    """激励三态（未记录 / 无 / 有）与 2024 / 2014 两种称呼。"""
    character = _empty()
    view = build_card_view(character)
    assert view.inspiration is None
    assert view.inspiration_label == "英雄激励"

    character.progress = {"激励": "无"}
    view = build_card_view(character, version_2024=False)
    assert view.inspiration is False
    assert view.inspiration_label == "激励"

    character.progress = {"激励": "有"}
    view = build_card_view(character, version_2024=True)
    assert view.inspiration is True
    assert view.inspiration_label == "英雄激励"


def test_skill_half_proficiency_marker() -> None:
    """半熟练技能有独立标记，先攻按范围决定是否吃半熟练。"""
    skill_only = CharacterService.parse(
        "$姓名$ 半熟练\n$等级$ 5\n$属性$ 10/14/10/10/14/10\n$半熟练$ 技能:向下",
        "g",
        "u",
    )
    view = build_card_view(skill_only)
    skills = {skill.name: skill for ability in view.abilities for skill in ability.skills}
    assert skills["运动"].half is True
    assert skills["运动"].proficient is False
    assert skills["运动"].value == "+1"
    assert {stat.label: stat.value for stat in view.core_stats}["先攻"] == "+2"

    all_checks = CharacterService.parse(
        "$姓名$ 半熟练\n$等级$ 5\n$属性$ 10/14/10/10/14/10\n$半熟练$ 全部:向下",
        "g",
        "u",
    )
    all_view = build_card_view(all_checks)
    assert {stat.label: stat.value for stat in all_view.core_stats}["先攻"] == "+3"
