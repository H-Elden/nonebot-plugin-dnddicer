"""``$半熟练$`` 规则：解析、取整、范围与检定联动的单测。"""

import pytest

from nonebot_plugin_dnddicer.character.models import DNDCharacter
from nonebot_plugin_dnddicer.character.services import (
    AbilityService,
    CharacterService,
    parse_half_prof,
)
from nonebot_plugin_dnddicer.engine.roll.karma_runtime import (
    reset_runtime,
    set_runtime,
)
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_BASE = "$姓名$ 测试\n$等级$ 5\n$属性$ 10/14/10/10/14/10\n"


def _parse(extra: str) -> DNDCharacter:
    return CharacterService.parse(_BASE + extra, "g", "u")


def test_parse_half_prof_valid_and_sorted():
    """多条用半角分号分隔；规则按固定顺序回写。"""
    rules = parse_half_prof("力敏体:向上; 全部:向下")
    assert [(rule.scope, rule.rounding) for rule in rules] == [
        ("全部", "向下"),
        ("力敏体", "向上"),
    ]


@pytest.mark.parametrize(
    "text, match",
    [
        ("全部", "不完整"),
        ("全部:随便", "取整方式无效"),
        ("身体:向下", "范围无效"),
        ("全部:向下; 全部:向下", "重复"),
        ("全部:向下:向上", "不完整"),
    ],
)
def test_parse_half_prof_invalid(text, match):
    with pytest.raises(AssertionError, match=match):
        parse_half_prof(text)


def test_2014_joat_down_all_ability_checks():
    """2014 万事通：全部属性检定、向下取整；豁免不吃半熟练。"""
    char = _parse("$半熟练$ 全部:向下")
    info = char.ability_info
    assert info.get_half_prof_bonus("先攻") == 1
    assert info.get_check_display("先攻") == "+3"  # 敏捷 +2 + 半熟练 1
    assert info.get_check_display("运动") == "+1"  # 力量 +0 + 1
    assert info.get_check_display("察觉") == "+3"  # 感知 +2 + 1
    assert info.get_check_display("智力") == "+1"  # 纯属性检定
    assert info.get_half_prof_bonus("敏捷豁免") == 0
    assert info.get_check_display("敏捷豁免") == "+2"


def test_2014_remarkable_athlete_up_physical_only():
    """2014 运动健将：力量/敏捷/体质检定、向上取整。"""
    char = _parse("$半熟练$ 力敏体:向上")
    info = char.ability_info
    assert info.get_half_prof_bonus("先攻") == 2
    assert info.get_check_display("先攻") == "+4"  # 敏捷 +2 + 2
    assert info.get_check_display("运动") == "+2"  # 力量 +0 + 2
    assert info.get_check_display("察觉") == "+2"  # 感知 +2，不吃半熟练
    assert info.get_check_display("智力") == "+0"  # 智力 +0，不吃半熟练
    assert info.get_half_prof_bonus("力量豁免") == 0


def test_2024_joat_skills_only_excludes_initiative_and_raw_checks():
    """2024 万事通：只到正式技能，不含先攻与纯属性检定。"""
    char = _parse("$半熟练$ 技能:向下")
    info = char.ability_info
    assert info.get_half_prof_bonus("先攻") == 0
    assert info.get_check_display("先攻") == "+2"
    assert info.get_check_display("运动") == "+1"
    assert info.get_check_display("察觉") == "+3"
    assert info.get_check_display("智力") == "+0"
    assert info.get_half_prof_bonus("敏捷豁免") == 0


def test_full_proficiency_and_expertise_disable_half():
    """已有熟练/专精时半熟练不叠加。"""
    char = _parse("$熟练$ 先攻; 运动; 察觉; 2*隐匿\n$半熟练$ 全部:向下")
    info = char.ability_info
    assert info.get_half_prof_bonus("先攻") == 0
    assert info.get_check_display("先攻") == "+5"  # 敏捷 +2 + 熟练 3
    assert info.get_half_prof_bonus("运动") == 0
    assert info.get_check_display("运动") == "+3"
    assert info.get_half_prof_bonus("隐匿") == 0
    assert info.get_check_display("隐匿") == "+8"  # 敏捷 +2 + 3*2


def test_multiple_rules_take_highest_half_bonus():
    """诗人/勇士兼职：重叠时取较高的半熟练。"""
    char = _parse("$半熟练$ 全部:向下; 力敏体:向上")
    info = char.ability_info
    assert info.get_half_prof_bonus("先攻") == 2
    assert info.get_check_display("先攻") == "+4"
    assert info.get_half_prof_bonus("运动") == 2
    assert info.get_check_display("运动") == "+2"
    assert info.get_half_prof_bonus("察觉") == 1
    assert info.get_check_display("察觉") == "+3"


def test_rounding_changes_with_proficiency_bonus():
    """13 级熟练 +5：向下 +2，向上 +3。"""
    down = CharacterService.parse(
        "$姓名$ 测试\n$等级$ 13\n$属性$ 10/14/10/10/14/10\n$半熟练$ 全部:向下",
        "g",
        "u",
    )
    up = CharacterService.parse(
        "$姓名$ 测试\n$等级$ 13\n$属性$ 10/14/10/10/14/10\n$半熟练$ 力敏体:向上",
        "g",
        "u",
    )
    assert down.ability_info.get_half_prof_bonus("先攻") == 2
    assert up.ability_info.get_half_prof_bonus("先攻") == 3


def test_passive_perception_includes_half():
    """被动察觉走同一套检定加值：技能半熟练会计入。"""
    joat = _parse("$半熟练$ 技能:向下")
    assert joat.ability_info.get_passive_score("察觉") == "13"  # 10 + 2 + 1
    athlete = _parse("$半熟练$ 力敏体:向上")
    assert athlete.ability_info.get_passive_score("察觉") == "12"  # 感知 +2，无半熟练
    proficient = _parse("$熟练$ 察觉\n$半熟练$ 技能:向下")
    assert proficient.ability_info.get_passive_score("察觉") == "15"  # 10 + 2 + 3


def test_perform_check_hint_and_roll_include_half():
    """检定过程说明与掷骰表达式都要带半熟练。"""
    char = _parse("$半熟练$ 全部:向下")
    token = set_runtime(SequenceRuntime([10]))
    try:
        hint, result, value, _ = AbilityService.perform_check(
            char.ability_info, "先攻", 0, ""
        )
    finally:
        reset_runtime(token)
    assert "半熟练加值:1" in hint
    assert "敏捷调整值:2" in hint
    assert value == 13
    assert "+1" in result


def test_half_prof_round_trip_and_merge_segments():
    """卡文本回写顺序稳定，分段修改时半熟练不丢。"""
    char = _parse(
        "$熟练$ 运动\n$半熟练$ 力敏体:向上; 全部:向下\n$额外加值$ 运动:+1"
    )
    text = char.get_char_info()
    assert text.index("$熟练$") < text.index("$半熟练$") < text.index("$额外加值$")
    assert "$半熟练$ 全部:向下; 力敏体:向上" in text

    merged = CharacterService.merge_segments(char, {"$姓名$": "改名"})
    assert merged.name == "改名"
    assert [(rule.scope, rule.rounding) for rule in merged.ability_info.half_prof_rules] == [
        ("全部", "向下"),
        ("力敏体", "向上"),
    ]
    assert "$半熟练$ 全部:向下; 力敏体:向上" in merged.get_char_info()


def test_old_card_without_half_prof_is_unchanged():
    """旧卡没有 ``$半熟练$`` 时字段为空，回写不新增空行。"""
    char = _parse("")
    assert char.ability_info.half_prof_rules == []
    assert "$半熟练$" not in char.get_char_info()
