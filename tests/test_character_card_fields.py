"""完整角色卡面扩展段与分段录入。

覆盖种族特性、职业特性、限定资源、魔法物品、背景固定键与 ``$熟练$`` 扩展
分组：解析、校验、规范化回写、单段合并、多段整卡、未知段拒绝。
"""

from __future__ import annotations

import pytest

from nonebot_plugin_dnddicer.character.constants import EXT_ITEM_INDEX_DICT
from nonebot_plugin_dnddicer.character.services import (
    CharacterService,
    gen_template_char,
    normalize_class_name,
    parse_background,
    parse_class_features,
    parse_coins,
    parse_combat,
    parse_combat_notes,
    parse_feature_item,
    parse_feats,
    parse_items,
    parse_magic_items,
    parse_prof_entries,
    parse_progress,
    parse_race_traits,
    parse_spell_item,
    parse_spell_setting,
    parse_story,
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
        "$专长$", "$特性$", "$种族特性$", "$职业特性$", "$限定资源$",
        "$魔法物品$", "$物品$", "$战斗记录$", "$故事$", "$进度$", "$钱币$",
    ):
        assert key not in text
    assert "$姓名$ 伊丽莎白" in text
    assert "$属性$ 15/14/13/12/10/8" in text
    assert "$熟练$ 力量/2*隐匿/奥秘" in text
    assert "$额外加值$ 隐匿:优势+2" in text


def test_extra_advantage_only_roundtrip() -> None:
    """只有 优势/劣势、没有数值的额外加值也要原样回写（否则再记录会丢）。"""
    char = _parse(
        "$等级$ 5\n$属性$ 10/10/10/10/10/10\n"
        "$额外加值$ 隐匿:优势/游说:劣势/豁免:优势+2"
    )
    text = char.get_char_info()
    assert "$额外加值$ 隐匿:优势/游说:劣势/豁免:优势+2" in text
    again = _parse(text)
    assert again.get_char_info() == text
    assert again.ability_info.check_adv[EXT_ITEM_INDEX_DICT["隐匿"]] == 1
    assert again.ability_info.check_adv[EXT_ITEM_INDEX_DICT["游说"]] == -1
    assert again.ability_info.check_ext[EXT_ITEM_INDEX_DICT["豁免"]] == "+2"


def test_template_roundtrip() -> None:
    """完整模板可解析、可原样回写（卡文本 → 解析 → 卡文本）。"""
    text = gen_template_char().get_char_info()
    parsed = _parse(text)
    assert parsed.get_char_info() == text
    assert parsed.background["背景"] == "智者"
    assert "理想" not in parsed.background
    assert parsed.combat["AC"] == "16"
    assert parsed.feats == [
        "魔法学徒（法师）:习得光亮术、心灵之楔与护盾术；护盾术可免法术位施展一次，长休恢复",
        "属性值提升:智力 +1、感知 +1",
    ]
    assert parsed.race_traits == [
        "黑暗视觉:60 尺内微光视为明亮，黑暗视为微光",
        "妖精血统:进行避免或结束魅惑状态的豁免时具有优势",
        "敏锐感官:获得察觉熟练",
        "出神:无需睡眠，魔法无法使你入睡；4 小时即可完成长休并保持清醒",
        "高等精灵血系:习得魔法伎俩；3 级习得侦测魔法、5 级习得迷踪步，"
        "始终准备，各可免法术位施展一次，长休恢复",
    ]
    assert [(item.level, item.name) for item in parsed.class_traits] == [
        (1, "仪式学家"),
        (1, "奥术回想"),
        (2, "学者"),
        (3, "塑能学者"),
        (3, "强力戏法"),
        (5, "记忆法术"),
    ]
    assert [(item.name, item.tag) for item in parsed.magic_items] == [
        ("战法师魔杖 +1", "魔杖，非普通（需施法者同调）"),
        ("防护斗篷", "奇物，非普通（需同调）"),
    ]
    assert parsed.magic_items[0].get_paragraphs() == [
        "持握这根魔杖期间，你的法术攻击检定获得 +1 加值。",
        "此外，你在进行法术攻击检定时无视半身掩护。",
    ]
    assert parsed.items[0] == "法术书x1"
    assert all("[装备]" not in item for item in parsed.items)
    assert parsed.combat_notes == ["法师护甲(8小时)"]
    assert parsed.ability_info.prof_weapons == ["简易武器"]
    assert parsed.coins == {"CP": 0, "SP": 0, "EP": 0, "GP": 13, "PP": 0}
    assert parsed.progress == {"经验": "6500/14000", "激励": "有"}
    assert parsed.story.startswith("伊瑟兰出身于银月城的学者世家")
    assert parsed.story.count("\n") == 2
    assert (parsed.spell_dc, parsed.spell_attack) == ("15", "+8")
    assert parsed.weapons[2].note == "灵巧 · 轻型"
    assert parsed.ability_info.check_ext[EXT_ITEM_INDEX_DICT["豁免"]] == "+1"


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
    assert parse_race_traits("黑暗视觉 / 妖精血统:豁免优势") == [
        "黑暗视觉", "妖精血统:豁免优势"
    ]
    class_traits = parse_class_features(
        "1|仪式学家:仪式法术直接施展/3|塑能学者"
    )
    assert [item.get_info() for item in class_traits] == [
        "1|仪式学家:仪式法术直接施展", "3|塑能学者"
    ]
    items = parse_items("治疗药水x2; 长剑x1; 绳索50尺x1; 火把x3")
    assert items == ["治疗药水x2", "长剑x1", "绳索50尺x1", "火把x3"]
    bg = parse_background("背景:士兵; 阵营:守序善良; 理想:守护家园")
    assert bg == {"背景": "士兵", "阵营": "守序善良", "理想": "守护家园"}
    assert parse_combat_notes("祝福术(专注,3轮); 中毒") == [
        "祝福术(专注,3轮)", "中毒"
    ]
    with pytest.raises(AssertionError, match="物品名称过长"):
        parse_items("很长" * 20)
    with pytest.raises(AssertionError, match="背景条目重复"):
        parse_background("背景:士兵; 背景:贤者")
    with pytest.raises(AssertionError, match="背景键无效"):
        parse_background("自定义:值")
    with pytest.raises(AssertionError, match="战斗记录条目过长"):
        parse_combat_notes("很长" * 40)
    with pytest.raises(AssertionError, match="不再支持 \\[装备\\]"):
        parse_items("长剑[装备]")


def test_magic_items_parsing() -> None:
    items = parse_magic_items(
        "防护斗篷|奇物，非普通（需同调）|AC 和豁免 +1。//专注时仍生效; "
        "战法师魔杖 +1|魔杖，非普通"
    )
    assert items[0].get_paragraphs() == ["AC 和豁免 +1。", "专注时仍生效"]
    assert items[1].get_info() == "战法师魔杖 +1|魔杖，非普通"
    with pytest.raises(AssertionError, match="条目不完整"):
        parse_magic_items("防护斗篷|奇物|说明|多余")
    with pytest.raises(AssertionError, match="标签不能为空"):
        parse_magic_items("防护斗篷||说明")
    with pytest.raises(AssertionError, match="名称过长"):
        parse_magic_items("长" * 31 + "|奇物")
    with pytest.raises(AssertionError, match="最多 .* 段"):
        parse_magic_items("防护斗篷|奇物|" + "//".join(["段"] * 6))
    with pytest.raises(AssertionError, match="说明过长"):
        parse_magic_items("防护斗篷|奇物|" + "长" * 501)


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
        ("$物品$ 火把x3", lambda c: c.items == ["火把x3"]),
        (
            "$背景$ 背景:士兵; 阵营:守序善良",
            lambda c: c.background["背景"] == "士兵",
        ),
        ("$战斗记录$ 中毒", lambda c: c.combat_notes == ["中毒"]),
        ("$专长$ 幸运", lambda c: c.feats == ["幸运"]),
        ("$种族特性$ 黑暗视觉", lambda c: c.race_traits == ["黑暗视觉"]),
        (
            "$职业特性$ 3|塑能学者:说明",
            lambda c: c.class_traits[0].get_info() == "3|塑能学者:说明",
        ),
        (
            "$限定资源$ 奥术回想:1/1短休",
            lambda c: c.features[0].name == "奥术回想",
        ),
        (
            "$魔法物品$ 防护斗篷|奇物，非普通|AC +1",
            lambda c: c.magic_items[0].name == "防护斗篷",
        ),
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
    assert merged.ability_info.prof_weapons == ["简易武器"]


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
    assert replaced.race_traits == []
    assert replaced.class_traits == []
    assert replaced.magic_items == []


def test_single_segment_without_existing_fails() -> None:
    with pytest.raises(AssertionError, match="必须设定等级与属性"):
        _parse("$姓名$ 李四")


def test_custom_class_is_accepted() -> None:
    assert normalize_class_name("法师") == "法师"
    assert normalize_class_name("盗贼") == "游荡者"
    assert normalize_class_name("机关术师") == "机关术师"
    char = _parse(
        "$等级$ 5\n$属性$ 10/10/10/10/10/10\n"
        "$职业$ 机关术师\n$子职$ 铸甲师"
    )
    assert (char.char_class, char.subclass) == ("机关术师", "铸甲师")
    with pytest.raises(AssertionError, match="暂不支持兼职"):
        normalize_class_name("法师/战士")
    with pytest.raises(AssertionError, match="职业名称过长"):
        normalize_class_name("长" * 21)


# ── 钱币 / 进度 / 故事 / 武器备注 / 法术详情 / 说明文本 ──────────────


def test_coins_progress_story_parsing() -> None:
    assert parse_coins("cp:0; sp:8; GP:18") == {"CP": 0, "SP": 8, "GP": 18}
    assert parse_progress("经验:6500/14000; 激励:有") == {
        "经验": "6500/14000",
        "激励": "有",
    }
    assert parse_progress("经验:500; 激励:无") == {"经验": "500", "激励": "无"}
    assert parse_story("  一段故事  ") == "一段故事"
    assert parse_story("第一段\n第二段\n\n第三段") == "第一段\n第二段\n\n第三段"
    assert parse_story("长" * 1000) == "长" * 1000
    assert parse_story("长" * 500 + "\n" + "长" * 500).count("\n") == 1

    with pytest.raises(AssertionError, match="钱币条目重复"):
        parse_coins("GP:1; GP:2")
    with pytest.raises(AssertionError, match="钱币数值无效"):
        parse_coins("GP:很多")
    with pytest.raises(AssertionError, match="经验值写法无效"):
        parse_progress("经验:abc")
    with pytest.raises(AssertionError, match="激励只能写"):
        parse_progress("激励:也许")
    with pytest.raises(AssertionError, match="故事内容过长"):
        parse_story("长" * 1001)
    with pytest.raises(AssertionError, match="故事内容不能包含符号"):
        parse_story("故事里有 $姓名$")


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
        "施法属性:智力; 豁免DC:15; 法术攻击:+8; 火球术:3"
    )
    assert (ability, dc, attack) == ("智力", "15", "+8")
    assert spells[0].name == "火球术"
    with pytest.raises(AssertionError, match="豁免DC必须是"):
        parse_spell_setting("豁免DC:很高")
    with pytest.raises(AssertionError, match="法术攻击加值无效"):
        parse_spell_setting("法术攻击:很强")


def test_feature_and_feat_description() -> None:
    feature = parse_feature_item("奥术回想:1/1短休|短休时回复一个法术位")
    assert feature.text == "短休时回复一个法术位"
    assert feature.get_info() == "奥术回想:1/1短休|短休时回复一个法术位"
    with pytest.raises(AssertionError, match="限定资源说明过长"):
        parse_feature_item("奥术回想:1/1短休|" + "长" * 81)

    assert parse_feats("战法师:专注豁免具有优势/幸运") == [
        "战法师:专注豁免具有优势",
        "幸运",
    ]
    assert parse_race_traits("黑暗视觉:60 尺内微光视为明亮") == [
        "黑暗视觉:60 尺内微光视为明亮"
    ]
    with pytest.raises(AssertionError, match="专长说明过长"):
        parse_feats("战法师:" + "长" * 61)


def test_single_segment_merge_new_segments() -> None:
    base = gen_template_char("g", "u")
    assert _parse("$钱币$ GP:99", existing=base).coins == {"GP": 99}
    assert _parse("$故事$ 新故事", existing=base).story == "新故事"
    assert _parse(
        "$故事$ 第一段\n第二段", existing=base
    ).story == "第一段\n第二段"
    assert _parse("$进度$ 经验:1/2; 激励:无", existing=base).progress == {
        "经验": "1/2",
        "激励": "无",
    }


def test_legacy_segments_are_rejected() -> None:
    """旧段不再兼容：整卡与单段录入都直接报未知段。"""
    text = gen_template_char().get_char_info() + "\n$属性值$ 力量:8/-1\n"
    with pytest.raises(AssertionError, match="未知段: \\$属性值\\$"):
        _parse(text)
    base = gen_template_char("g", "u")
    for segment in ("$技能$ 运动:+5", "$豁免$ 力量:+5", "$特性$ 黑暗视觉", "$能力$ 奥术回想:1/1短休"):
        with pytest.raises(AssertionError, match="未知段"):
            _parse(segment, existing=base)
