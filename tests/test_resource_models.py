"""能力 / 法术 / 法术位模型与解析单测（2026-10-20 批②，不依赖 nonebug）。

覆盖：``$限定资源$`` 四档恢复语法与数量校验、``$法术$`` 施法属性与准备标记、
``$法术位$`` 各环与契约魔法，以及模板往返与旧卡兼容。
"""

import pytest

from nonebot_plugin_dnddicer.character.constants import (
    FEATURE_MAX_COUNT,
    SPELL_MAX_COUNT,
)
from nonebot_plugin_dnddicer.character.models import (
    CharacterFeature,
    DNDCharacter,
    SpellEntry,
    SpellSlots,
)
from nonebot_plugin_dnddicer.character.services import (
    CharacterService,
    gen_template_char,
    match_features,
    match_spells,
    normalize_feature_recover,
    parse_feature_item,
    parse_feature_list,
    parse_spell_item,
    parse_spell_setting,
    parse_spell_slot_entries,
    parse_spell_slots,
)


# =========================================================================
# $限定资源$
# =========================================================================


def test_feature_item_full_syntax():
    """四档恢复 + 恢复量 + 满：解析与回写一致。"""
    feature = parse_feature_item("引导神力:2/2短休+1,长休满")
    assert feature.name == "引导神力"
    assert feature.uses_cur == 2 and feature.uses_max == 2
    assert feature.recover == "短休+1,长休"
    assert feature.get_info() == "引导神力:2/2短休+1,长休"
    assert feature.get_recover_display() == "短休+1，长休回满"


def test_feature_recover_defaults_to_full():
    """不带后缀 = 回满；``手动`` 不带恢复量。"""
    assert parse_feature_item("圣疗:25/25长休").recover == "长休"
    assert parse_feature_item("充能:1/1手动").recover == "手动"
    assert parse_feature_item("狂暴:3/3两者").recover == "两者"


def test_feature_recover_display_explicit_full():
    """回满显式写成「回满」；``+N`` 与 ``手动`` 原样展示。"""
    assert parse_feature_item("圣疗:25/25长休").get_recover_display() == "长休回满"
    assert parse_feature_item("圣疗:25/25短休").get_recover_display() == "短休回满"
    assert (
        parse_feature_item("圣疗:25/25短休+1,长休").get_recover_display()
        == "短休+1，长休回满"
    )
    assert (
        parse_feature_item("狂暴:3/3两者").get_recover_display()
        == "短休回满，长休回满"
    )
    assert parse_feature_item("充能:1/1手动").get_recover_display() == "手动"


def test_feature_recover_normalized_order():
    """恢复档按固定顺序输出（长休写在短休前面也会被排好）。"""
    assert normalize_feature_recover("长休,短休+1") == "短休+1,长休"
    feature = parse_feature_item("引导神力：2/2长休+2，短休")
    assert feature.recover == "短休,长休+2"


def test_feature_list_semicolon_both_widths():
    """半角 / 全角分号都接受；多条解析。"""
    features = parse_feature_list("奥术回想:1/1短休；圣疗:25/25长休")
    assert [feature.name for feature in features] == ["奥术回想", "圣疗"]


@pytest.mark.parametrize(
    "item, message",
    [
        ("引导神力2/2短休", "限定资源条目不完整"),
        ("引导神力:2/2", "限定资源恢复方式不能为空"),
        ("引导神力:2/2短休+0", "恢复量必须大于 0"),
        ("引导神力:2/2短休+", "限定资源恢复量无效"),
        ("引导神力:2/2两者,短休", "「两者」已含短休与长休"),
        ("引导神力:2/2短休,短休", "限定资源恢复方式重复"),
        ("引导神力:2/2手动+1", "「手动」不能带恢复量"),
        ("引导神力:3/2短休", "当前次数不能超过上限"),
        ("引导神力:2/0短休", "限定资源上限必须大于 0"),
        ("引导/神力:2/2短休", "不能包含符号「/」"),
        ("引导神力-:2/2短休", "不能包含符号「-」"),
        ("攻击神力:2/2短休", "不能包含「攻击」字样"),
    ],
)
def test_feature_item_errors(item: str, message: str):
    """写法与取值范围错误都给出面向用户的提示。"""
    with pytest.raises(AssertionError, match=message):
        parse_feature_item(item)


def test_feature_list_limits_and_duplicates():
    items = "; ".join(
        f"限定资源{i}:1/1长休" for i in range(FEATURE_MAX_COUNT + 1)
    )
    with pytest.raises(AssertionError, match="限定资源数量最多"):
        parse_feature_list(items)
    with pytest.raises(AssertionError, match="限定资源名称重复"):
        parse_feature_list("奥术回想:1/1短休; 奥术回想:1/1长休")


def test_feature_old_card_defaults():
    """旧卡没有 $限定资源$ 段：字段按默认空列表读入。"""
    char = DNDCharacter.model_validate(
        {"group_id": "g", "user_id": "u", "name": "旧卡"}
    )
    assert char.features == []
    assert char.spells == []
    assert char.spell_slots.is_empty()
    assert char.spellcasting_ability == ""


# =========================================================================
# $法术$
# =========================================================================


def test_spell_setting_with_ability_and_prepared():
    """施法属性 + 准备标记 + 戏法。"""
    ability, spells, dc, attack = parse_spell_setting(
        "施法属性：魅力; 火球术:3*; 闪电束:3; 火焰箭:0"
    )
    assert ability == "魅力"
    assert (dc, attack) == ("", "")
    assert [spell.name for spell in spells] == ["火球术", "闪电束", "火焰箭"]
    assert spells[0].prepared and spells[0].level == 3
    assert not spells[1].prepared
    assert spells[2].level == 0
    assert spells[2].get_level_label() == "戏法"
    assert spells[0].get_info() == "火球术:3*"


def test_spell_setting_without_ability():
    ability, spells, dc, attack = parse_spell_setting("魔法飞弹:1*")
    assert (ability, dc, attack) == ("", "", "")
    assert spells[0].prepared


@pytest.mark.parametrize(
    "item, message",
    [
        ("火球术", "法术条目不完整"),
        ("火球术:十", "法术环阶无效"),
        ("火球术:10", "法术环阶无效"),
        ("火球术:3**", "法术环阶无效"),
        (":3", "法术名称不能为空"),
    ],
)
def test_spell_item_errors(item: str, message: str):
    with pytest.raises(AssertionError, match=message):
        parse_spell_item(item)


def test_spell_setting_errors():
    with pytest.raises(AssertionError, match="施法属性无效"):
        parse_spell_setting("施法属性:运气; 火球术:3")
    with pytest.raises(AssertionError, match="施法属性只能写一条"):
        parse_spell_setting("施法属性:智力; 施法属性:感知")
    with pytest.raises(AssertionError, match="法术名称重复"):
        parse_spell_setting("火球术:3; 火球术:4")
    too_many = "; ".join(f"法术{i}:1" for i in range(SPELL_MAX_COUNT + 1))
    with pytest.raises(AssertionError, match="法术数量最多"):
        parse_spell_setting(too_many)


def test_spell_name_forbidden_chars():
    with pytest.raises(AssertionError, match="不能包含符号「\\*」"):
        parse_spell_item("火球*术:3")


def test_spell_entry_labels():
    assert SpellEntry(name="火球术", level=3).get_level_label() == "3环"
    assert SpellEntry(name="火焰箭", level=0, prepared=True).get_info() == "火焰箭:0*"


# =========================================================================
# $法术位$
# =========================================================================


def test_spell_slots_parse_and_render():
    slots = parse_spell_slots("1:4/4; 2:3/3; 3:2/2; 契约3:2/2")
    assert slots.slots_cur[:3] == [4, 3, 2]
    assert slots.slots_max[:3] == [4, 3, 2]
    assert (slots.pact_level, slots.pact_cur, slots.pact_max) == (3, 2, 2)
    assert slots.get_char_info() == "$法术位$ 1:4/4; 2:3/3; 3:2/2; 契约3:2/2"


def test_spell_slots_set_omitted_max():
    """命令写法 ``1:4`` = 当前与上限都设为 4。"""
    entries = parse_spell_slot_entries(
        "1:4, 2:3, 契约3:2/2", allow_omitted_max=True
    )
    assert entries == [
        (False, 1, 4, 4),
        (False, 2, 3, 3),
        (True, 3, 2, 2),
    ]


@pytest.mark.parametrize(
    "content, message",
    [
        ("1:4", "法术位条目不完整"),
        ("0:1/1", "法术位环阶无效"),
        ("10:1/1", "法术位环阶无效"),
        ("1:5/4", "当前值不能超过上限"),
        ("1:100/100", "法术位数量无效"),
        ("1:4/4; 1:3/3", "法术位重复"),
        ("契约3:2/2; 契约3:1/1", "法术位重复"),
    ],
)
def test_spell_slots_errors(content: str, message: str):
    with pytest.raises(AssertionError, match=message):
        parse_spell_slots(content)


def test_spell_slots_empty_render():
    assert SpellSlots().get_char_info() == ""
    assert SpellSlots().is_empty()


# =========================================================================
# 模板与往返
# =========================================================================


def test_template_contains_new_segments_and_roundtrips():
    """模板覆盖限定资源/魔法物品/法术/法术位，且可再次解析回同一份记录。"""
    text = gen_template_char().get_char_info()
    assert "$限定资源$ 奥术回想:1/1短休|" in text
    assert "$魔法物品$ 战法师魔杖 +1|" in text
    assert "$法术$ 施法属性:智力; 豁免DC:15; 法术攻击:+8; 火焰箭:0|" in text
    assert "$法术位$ 1:4/4; 2:3/3; 3:2/2" in text

    char = CharacterService.parse(text, "g", "u")
    assert char.char_class == "法师"
    assert char.features[0].name == "奥术回想"
    assert char.features[0].text
    assert char.spellcasting_ability == "智力"
    assert (char.spell_dc, char.spell_attack) == ("15", "+8")
    by_name = {spell.name: spell for spell in char.spells}
    assert by_name["火球术"].prepared is True
    assert by_name["火球术"].cast_time == "1动作"
    assert by_name["火球术"].material is True
    assert char.spell_slots.get_char_info() == "$法术位$ 1:4/4; 2:3/3; 3:2/2"


def test_full_card_parse_with_new_segments():
    text = "\n".join([
        "$姓名$ 测试",
        "$等级$ 5",
        "$属性$ 10/10/10/10/10/10",
        "$限定资源$ 引导神力:2/2短休+1,长休; 圣疗:25/25长休",
        "$法术$ 施法属性:魅力; 制裁斩:1*; 治疗真言:1",
        "$法术位$ 1:2/2",
    ])
    char = CharacterService.parse(text, "g", "u")
    assert len(char.features) == 2
    assert char.spells[0].prepared and not char.spells[1].prepared
    assert char.spell_slots.slots_cur[0] == 2


# =========================================================================
# 名称匹配
# =========================================================================


def test_match_features_and_spells():
    features = [
        CharacterFeature(name="引导神力", uses_cur=2, uses_max=2, recover="短休"),
        CharacterFeature(name="引路神力", uses_cur=1, uses_max=1, recover="长休"),
    ]
    # 精确优先：卡上同时有「引导神力」与「引路神力」时命中前者
    assert match_features(features, "引导神力")[0].name == "引导神力"
    # 子串命中多项 → 交给调用方列候选
    assert len(match_features(features, "引")) == 2
    assert match_features(features, "不存在") == []

    spells = [
        SpellEntry(name="火球术", level=3),
        SpellEntry(name="火焰箭", level=0),
    ]
    assert match_spells(spells, "火球")[0].name == "火球术"
    assert len(match_spells(spells, "火")) == 2
