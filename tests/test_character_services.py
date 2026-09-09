"""角色卡/检定服务层单测（模板解析 + 确定性检定计算，不依赖 nonebug）。"""

import pytest

from nonebot_plugin_dnddicer.character.services import (
    AbilityService,
    CharacterService,
    gen_template_char,
    parse_template_to_dict,
)
from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_TEMPLATE = """$姓名$ 伊丽莎白
$等级$ 5
$生命值$ 20/30(5)
$生命骰$ 3/4 D8
$属性$ 15/14/13/12/10/8
$熟练$ 力量/2*隐匿/奥秘
$额外加值$ 隐匿:优势+2/游说:-2"""


def _roll(seq: SequenceRuntime):
    token = set_runtime(seq)
    try:
        return token
    except Exception:  # pragma: no cover
        reset_runtime(token)
        raise


def test_parse_template_to_dict():
    data = parse_template_to_dict(_TEMPLATE)
    assert data["$姓名$"] == "伊丽莎白"
    assert data["$等级$"] == "5"
    assert data["$属性$"] == "15/14/13/12/10/8"
    assert data["$熟练$"] == "力量/2*隐匿/奥秘"


def test_parse_character():
    char = CharacterService.parse(_TEMPLATE, "g1", "u1")
    assert char.is_init
    assert char.name == "伊丽莎白"
    assert char.group_id == "g1" and char.user_id == "u1"
    ai = char.ability_info
    assert ai.level == 5
    assert ai.ability == [15, 14, 13, 12, 10, 8]
    # 熟练加值 = 2 + (5-1)//4 = 3
    assert ai.get_prof_bonus() == 3
    # 力量熟练(1)、隐匿 2*、奥秘 1；攻击默认全部不熟练（8.4 #8）
    from nonebot_plugin_dnddicer.character.constants import CHECK_ITEM_INDEX_DICT

    assert ai.check_prof[CHECK_ITEM_INDEX_DICT["力量"]] == 1
    assert ai.check_prof[CHECK_ITEM_INDEX_DICT["隐匿"]] == 2
    assert ai.check_prof[CHECK_ITEM_INDEX_DICT["奥秘"]] == 1
    assert ai.check_prof[CHECK_ITEM_INDEX_DICT["力量攻击"]] == 0
    # hp
    assert char.hp_info.hp_cur == 20 and char.hp_info.hp_max == 30
    assert char.hp_info.hp_temp == 5
    assert char.hp_info.hp_dice_type == 8


def test_parse_character_attack_prof_explicit():
    """攻击熟练仅在 $熟练$ 显式声明时生效（8.4 #8）。"""
    char = CharacterService.parse(
        "$等级$ 5\n$属性$ 15/14/13/12/10/8\n$熟练$ 力量攻击", "g", "u"
    )
    from nonebot_plugin_dnddicer.character.constants import CHECK_ITEM_INDEX_DICT

    assert char.ability_info.check_prof[CHECK_ITEM_INDEX_DICT["力量攻击"]] == 1
    # 未声明的其他攻击保持不熟练
    assert char.ability_info.check_prof[CHECK_ITEM_INDEX_DICT["敏捷攻击"]] == 0


def test_parse_character_attack_prof_zero_disables():
    """0*力量攻击 显式关闭 → 不熟练（0* 语义保留）。"""
    char = CharacterService.parse(
        "$等级$ 5\n$属性$ 15/14/13/12/10/8\n$熟练$ 0*力量攻击", "g", "u"
    )
    from nonebot_plugin_dnddicer.character.constants import CHECK_ITEM_INDEX_DICT

    assert char.ability_info.check_prof[CHECK_ITEM_INDEX_DICT["力量攻击"]] == 0


def test_parse_character_missing_level_fails():
    with pytest.raises(AssertionError, match="必须设定等级与属性"):
        CharacterService.parse("$属性$ 15/14/13/12/10/8", "g", "u")


def test_parse_character_invalid_prof_fails():
    with pytest.raises(AssertionError, match="无效的检定条目"):
        CharacterService.parse("$等级$ 1\n$属性$ 15/14/13/12/10/8\n$熟练$ 不存在技能", "g", "u")


def test_perform_check_ability_with_sequence():
    """力量检定：15 → 调整 +2；掷骰序列 [10] → 10+2=12。"""
    char = CharacterService.parse(
        "$等级$ 1\n$属性$ 15/14/13/12/10/8", "g", "u"
    )
    token = set_runtime(SequenceRuntime([10]))
    try:
        hint, result, value = AbilityService.perform_check(char.ability_info, "力量", 0, "")
    finally:
        reset_runtime(token)
    assert "无熟练加值" in hint
    assert "力量调整值:2" in hint
    assert value == 12
    assert "1D20+2=[10]+2=12" in result


def test_perform_check_skill_with_proficiency():
    """隐匿（熟练系数 2、自带优势+2）：15 敏捷 → 调整 +2；掷 D20优势。"""
    char = CharacterService.parse(
        "$等级$ 5\n$属性$ 10/15/13/12/10/8\n$熟练$ 2*隐匿\n$额外加值$ 隐匿:优势+2",
        "g", "u",
    )
    token = set_runtime(SequenceRuntime([4, 18]))  # 优势两次掷骰，取高 18
    try:
        hint, result, value = AbilityService.perform_check(char.ability_info, "隐匿", 0, "")
    finally:
        reset_runtime(token)
    # 熟练加值 = 2 + (5-1)//4 = 3，双倍熟练（scale=2）提示按 DicePP 风格显示 3*2
    assert "熟练加值:3*2" in hint
    assert "敏捷调整值:2" in hint
    assert "额外加值:+2" in hint
    assert value == 18 + 6 + 2 + 2


def test_perform_check_synonym():
    """同义词：观察 → 察觉。"""
    char = CharacterService.parse(
        "$等级$ 1\n$属性$ 10/14/13/12/10/8", "g", "u"
    )
    token = set_runtime(SequenceRuntime([3]))
    try:
        hint, result, value = AbilityService.perform_check(char.ability_info, "观察", 0, "")
    finally:
        reset_runtime(token)
    assert "感知调整值:0" in hint
    assert value == 3


def test_perform_check_invalid_item():
    char = CharacterService.parse(
        "$等级$ 1\n$属性$ 15/14/13/12/10/8", "g", "u"
    )
    with pytest.raises(AssertionError, match="无效, 可用检定条目"):
        AbilityService.perform_check(char.ability_info, "不存在", 0, "")


def test_template_char_is_recordable():
    """模板角色卡再次被解析应成功（可复制保存多卡的闭环）。"""
    template_char = gen_template_char()
    text = template_char.get_char_info()
    char = CharacterService.parse(text, "g2", "u2")
    assert char.is_init
    assert char.name == "张三"
