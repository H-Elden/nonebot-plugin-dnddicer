"""完整角色卡面扩展段与分段录入（2026-10-21）。

覆盖九类完整卡面扩展段与 ``$熟练$`` 扩展分组：
解析、校验、规范化回写、单段合并、多段整卡、旧卡输出不变。
"""

from __future__ import annotations

import pytest

from nonebot_plugin_dnddicer.character.services import (
    CharacterService,
    gen_template_char,
    parse_background,
    parse_coins,
    parse_combat,
    parse_combat_notes,
    parse_feature_item,
    parse_feats,
    parse_items,
    parse_prof_entries,
    parse_progress,
    parse_saves,
    parse_skills,
    parse_spell_item,
    parse_spell_setting,
    parse_story,
    parse_traits,
    parse_weapon_item,
)


def _parse(text: str, existing=None):
    return CharacterService.parse(text, "g", "u", existing=existing)


_OLD_CARD = """$姓名$ 伊丽莎白
$种族$ 半精灵
$职业$ 游荡者
$等级$ 5
$生命值$ 20/30(5)
$生命骰$ 3/4 D8
$属性$ 15/14/13/12/10/8
$熟练$ 力量/2*隐匿/奥秘
$额外加值$ 隐匿:优势+2"""


def test_old_card_output_unchanged() -> None:
    """旧卡（不含新段）的输出不出现任何新段，旧段内容保持。"""
    char = _parse(_OLD_CARD)
    text = char.get_char_info()
    for key in (
        "$背景$", "$战斗$", "$属性值$", "$豁免$", "$技能$",
        "$专长$", "$特性$", "$物品$", "$战斗记录$",
        "$故事$", "$进度$", "$钱币$",
    ):
        assert key not in text
    assert "$姓名$ 伊丽莎白" in text
    assert "$属性$ 15/14/13/12/10/8" in text
    assert "$熟练$ 力量/2*隐匿/奥秘" in text
    assert "$额外加值$ 隐匿:优势+2" in text


def test_template_roundtrip() -> None:
    """完整模板可解析、可原样回写（卡文本 → 解析 → 卡文本）。"""
    text = gen_template_char().get_char_info()
    parsed = _parse(text)
    assert parsed.get_char_info() == text
    # 关键段都有内容
    assert parsed.background["背景"] == "贤者"
    assert parsed.combat["AC"] == "15"
    assert parsed.saves["智力"] == "+9"
    assert parsed.skills["奥秘"] == "+10*"
    assert parsed.feats == ["战法师:专注豁免具有优势；可借机施法"]
    assert parsed.traits == [
        "黑暗视觉（种族）:60 尺内微光视为明亮，黑暗视为微光",
        "妖精血统（种族）:对抗魅惑的豁免具有优势，魔法无法使你入睡",
        "出神（种族）:长休只需 4 小时，期间保持清醒",
    ]
    assert "法术书x1[装备]" in parsed.items
    assert parsed.combat_notes == ["法师护甲(8小时)", "专注:飞行术"]
    assert parsed.ability_info.prof_weapons == ["匕首", "法杖", "轻弩"]
    assert parsed.coins == {"CP": 0, "SP": 8, "EP": 0, "GP": 18, "PP": 0}
    assert parsed.progress == {"经验": "6500/14000", "激励": "有"}
    assert parsed.story.startswith("张三出身于银月城的学者世家")
    assert (parsed.spell_dc, parsed.spell_attack) == ("15", "+7")
    assert parsed.weapons[1].note == "灵巧 · 轻型"


def test_ability_display_requires_six() -> None:
    with pytest.raises(AssertionError, match="写全六项属性"):
        _parse(
            "$等级$ 1\n$属性$ 10/10/10/10/10/10\n"
            "$属性值$ 力量:10/+0"
        )
    with pytest.raises(AssertionError, match="调整值超出范围"):
        _parse(
            "$等级$ 1\n$属性$ 10/10/10/10/10/10\n"
            "$属性值$ 力量:10/+0; 敏捷:10/+0; 体质:10/+0; "
            "智力:10/+0; 感知:10/+0; 魅力:10/+11"
        )


def test_combat_validation() -> None:
    combat = parse_combat("AC:18; 先攻:+1; 速度:30尺; 被动察觉:13")
    assert combat == {"AC": "18", "先攻": "+1", "速度": "30尺", "被动察觉": "13"}
    assert parse_combat("ac:18") == {"AC": "18"}
    with pytest.raises(AssertionError, match="战斗条目不完整"):
        parse_combat("力量:18")
    with pytest.raises(AssertionError, match="AC必须是"):
        parse_combat("AC:很高")
    with pytest.raises(AssertionError, match="先攻加值无效"):
        parse_combat("先攻:优势")


def test_saves_and_skills_normalization() -> None:
    assert parse_saves("力量:+7; 体质豁免：+6") == {"力量": "+7", "体质": "+6"}
    with pytest.raises(AssertionError, match="豁免重复"):
        parse_saves("力量:+7; 力量豁免:+6")
    skills = parse_skills("观察:+5; 隐匿:+8*; 运动:＋3")
    assert skills == {"察觉": "+5", "隐匿": "+8*", "运动": "+3"}
    with pytest.raises(AssertionError, match="技能条目不完整"):
        parse_skills("力量:+5")


def test_prof_groups_and_check_entries() -> None:
    checks, groups = parse_prof_entries(
        "运动/2*隐匿/护甲:轻甲·中甲/武器:军用武器/语言:通用语·精灵语"
    )
    assert checks == ["运动", "2*隐匿"]
    assert groups == {
        "护甲": ["轻甲", "中甲"],
        "武器": ["军用武器"],
        "语言": ["通用语", "精灵语"],
    }
    with pytest.raises(AssertionError, match="不能为空"):
        parse_prof_entries("护甲:")
    with pytest.raises(AssertionError, match="条目重复"):
        parse_prof_entries("护甲:轻甲·轻甲")


def test_feats_traits_items_background_notes() -> None:
    assert parse_feats("巨武器大师/幸运") == ["巨武器大师", "幸运"]
    assert parse_traits("黑暗视觉（种族）/ 引导神力 (职业)") == [
        "黑暗视觉（种族）", "引导神力 (职业)"
    ]
    items = parse_items("治疗药水x2; 长剑[装备]; 绳索50尺x1; 火把x3[装备]")
    assert items == ["治疗药水x2", "长剑x1[装备]", "绳索50尺x1", "火把x3[装备]"]
    bg = parse_background("背景:士兵; 阵营:守序善良; 自定义:值")
    assert bg == {"背景": "士兵", "阵营": "守序善良", "自定义": "值"}
    assert parse_combat_notes("祝福术(专注,3轮); 中毒") == [
        "祝福术(专注,3轮)", "中毒"
    ]
    with pytest.raises(AssertionError, match="物品名称过长"):
        parse_items("很长" * 20)
    with pytest.raises(AssertionError, match="背景条目重复"):
        parse_background("背景:士兵; 背景:贤者")
    with pytest.raises(AssertionError, match="战斗记录条目过长"):
        parse_combat_notes("很长" * 40)


def test_content_rejects_dollar() -> None:
    with pytest.raises(AssertionError, match="不能包含符号"):
        parse_combat("AC:18; 备注:$x$")
    with pytest.raises(AssertionError, match="不能包含符号"):
        parse_feats("$幸运$")


@pytest.mark.parametrize(
    "segment, check",
    [
        ("$姓名$ 李四", lambda c: c.name == "李四"),
        ("$等级$ 6", lambda c: c.ability_info.level == 6),
        (
            "$战斗$ AC:17; 先攻:+3; 速度:30; 被动察觉:12",
            lambda c: c.combat["AC"] == "17",
        ),
        ("$技能$ 运动:+5; 隐匿:+8*", lambda c: c.skills == {
            "运动": "+5", "隐匿": "+8*"
        }),
        ("$物品$ 火把x3", lambda c: c.items == ["火把x3"]),
        (
            "$背景$ 背景:士兵; 阵营:守序善良",
            lambda c: c.background["背景"] == "士兵",
        ),
        ("$战斗记录$ 中毒", lambda c: c.combat_notes == ["中毒"]),
        ("$专长$ 幸运", lambda c: c.feats == ["幸运"]),
        ("$特性$ 黑暗视觉（种族）", lambda c: c.traits == ["黑暗视觉（种族）"]),
    ],
)
def test_single_segment_merge_keeps_others(segment: str, check) -> None:
    base = gen_template_char("g", "u")
    base.name = "张三"
    merged = _parse(segment, existing=base)
    assert check(merged)
    # 其余字段保留
    assert merged.ability_info.ability == base.ability_info.ability
    assert merged.weapons == base.weapons
    assert merged.spells == base.spells
    assert merged.ability_info.prof_weapons == ["匕首", "法杖", "轻弩"]


def test_single_segment_merge_preserves_portrait() -> None:
    base = gen_template_char("g", "u")
    base.portrait = "portraits/g_u.png"
    merged = _parse("$姓名$ 李四", existing=base)
    assert merged.portrait == "portraits/g_u.png"


def test_full_record_with_existing_preserves_portrait() -> None:
    base = gen_template_char("g", "u")
    base.portrait = "portraits/g_u.png"
    replaced = _parse(_OLD_CARD, existing=base)
    assert replaced.portrait == "portraits/g_u.png"


def test_multi_segment_full_replace_clears_omitted() -> None:
    base = gen_template_char("g", "u")
    replaced = _parse("$姓名$ 李四\n$等级$ 5\n$属性$ 10/10/10/10/10/10", existing=base)
    assert replaced.name == "李四"
    assert replaced.weapons == []
    assert replaced.spells == []
    assert replaced.background == {}
    assert replaced.combat == {}


def test_single_segment_without_existing_fails() -> None:
    with pytest.raises(AssertionError, match="必须设定等级与属性"):
        _parse("$姓名$ 李四")


# ── 批②：钱币 / 进度 / 故事 / 武器备注 / 法术详情 / 说明文本 ──────────


def test_coins_progress_story_parsing() -> None:
    assert parse_coins("cp:0; sp:8; GP:18") == {"CP": 0, "SP": 8, "GP": 18}
    assert parse_progress("经验:6500/14000; 激励:有") == {
        "经验": "6500/14000",
        "激励": "有",
    }
    assert parse_progress("经验:500; 激励:无") == {"经验": "500", "激励": "无"}
    assert parse_story("  一段故事  ") == "一段故事"

    with pytest.raises(AssertionError, match="钱币条目重复"):
        parse_coins("GP:1; GP:2")
    with pytest.raises(AssertionError, match="钱币数值无效"):
        parse_coins("GP:很多")
    with pytest.raises(AssertionError, match="经验值写法无效"):
        parse_progress("经验:abc")
    with pytest.raises(AssertionError, match="激励只能写"):
        parse_progress("激励:也许")
    with pytest.raises(AssertionError, match="故事内容过长"):
        parse_story("长" * 301)


def test_weapon_note_parsing() -> None:
    weapon = parse_weapon_item("匕首+5,1d4+2穿刺,灵巧·轻型")
    assert weapon.note == "灵巧·轻型"
    assert weapon.get_info() == "匕首+5,1d4+2穿刺,灵巧·轻型"
    assert parse_weapon_item("匕首+5,1d4+2穿刺").note == ""
    with pytest.raises(AssertionError, match="最多三段"):
        parse_weapon_item("匕首+5,1d4+2穿刺,a,b")
    with pytest.raises(AssertionError, match="备注过长"):
        parse_weapon_item("匕首+5,1d4+2穿刺," + "长" * 31)
    with pytest.raises(AssertionError, match="不能包含符号"):
        parse_weapon_item("匕首+5,1d4+2穿刺,灵巧/轻型")


def test_spell_details_parsing() -> None:
    spell = parse_spell_item(
        "火球术:3*|时间=1动作,距离=150尺,材料=是,备注=8d6 火焰 / 敏捷"
    )
    assert (spell.level, spell.prepared) == (3, True)
    assert (spell.cast_time, spell.range) == ("1动作", "150尺")
    assert spell.material is True
    assert spell.note == "8d6 火焰 / 敏捷"
    assert spell.get_info() == (
        "火球术:3*|时间=1动作,距离=150尺,材料=是,备注=8d6 火焰 / 敏捷"
    )
    with pytest.raises(AssertionError, match="法术详情重复"):
        parse_spell_item("火球术:3|时间=1动作,时间=1反应")
    with pytest.raises(AssertionError, match="只能写 是 或 否"):
        parse_spell_item("火球术:3|专注=也许")
    with pytest.raises(AssertionError, match="备注过长"):
        parse_spell_item("火球术:3|备注=" + "长" * 41)


def test_spell_setting_header_keys() -> None:
    ability, spells, dc, attack = parse_spell_setting(
        "施法属性:智力; 豁免DC:15; 法术攻击:+7; 火球术:3"
    )
    assert (ability, dc, attack) == ("智力", "15", "+7")
    assert spells[0].name == "火球术"
    with pytest.raises(AssertionError, match="豁免DC必须是"):
        parse_spell_setting("豁免DC:很高")
    with pytest.raises(AssertionError, match="法术攻击加值无效"):
        parse_spell_setting("法术攻击:很强")


def test_feature_and_feat_description() -> None:
    feature = parse_feature_item("奥术回想:1/1短休|短休时回复一个法术位")
    assert feature.text == "短休时回复一个法术位"
    assert feature.get_info() == "奥术回想:1/1短休|短休时回复一个法术位"
    with pytest.raises(AssertionError, match="能力说明过长"):
        parse_feature_item("奥术回想:1/1短休|" + "长" * 81)

    assert parse_feats("战法师:专注豁免具有优势/幸运") == [
        "战法师:专注豁免具有优势",
        "幸运",
    ]
    assert parse_traits("黑暗视觉（种族）:60 尺内微光视为明亮") == [
        "黑暗视觉（种族）:60 尺内微光视为明亮"
    ]
    with pytest.raises(AssertionError, match="专长说明过长"):
        parse_feats("战法师:" + "长" * 61)


def test_single_segment_merge_new_segments() -> None:
    base = gen_template_char("g", "u")
    assert _parse("$钱币$ GP:99", existing=base).coins == {"GP": 99}
    assert _parse("$故事$ 新故事", existing=base).story == "新故事"
    assert _parse("$进度$ 经验:1/2; 激励:无", existing=base).progress == {
        "经验": "1/2",
        "激励": "无",
    }
