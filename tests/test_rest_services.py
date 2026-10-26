"""休息结算服务单测（2026-10-20 批③，不依赖 nonebug）。

覆盖：生命骰两版规则（2014 逐粒 + 体质、2024 骰点总和 + 枚数 × 体质）、
能力次数恢复档、契约/普通法术位恢复、施法未准备提醒判定与法术位消耗。
"""

import pytest

from nonebot_plugin_dnddicer.character.models import (
    CharacterFeature,
    HPInfo,
    SpellSlots,
)
from nonebot_plugin_dnddicer.character.services import HPService, RestService
from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime


def _roll(seq: SequenceRuntime):
    token = set_runtime(seq)
    try:
        return token
    except Exception:  # pragma: no cover
        reset_runtime(token)
        raise


def _hp(cur: int = 10, max_: int = 30, dice_type: int = 8, dice_num: int = 3, dice_max: int = 3):
    hp = HPInfo(is_init=True, hp_cur=cur, hp_max=max_, hp_dice_type=dice_type,
                hp_dice_num=dice_num, hp_dice_max=dice_max)
    return hp


# =========================================================================
# 生命骰：2014 / 2024 两版规则
# =========================================================================


def test_use_hp_dice_2014_single():
    """2014：单粒「骰值 + 体质调整值」。"""
    hp = _hp()
    token = _roll(SequenceRuntime([7]))
    try:
        ok, text = HPService.use_hp_dice_ex(hp, 1, 2)
    finally:
        reset_runtime(token)
    assert ok
    assert text == (
        "使用1颗D8生命骰, 体质调整值为2, 回复[7]+2=9点生命值\n"
        "HP:10/30 -> HP:19/30"
    )
    assert hp.hp_cur == 19 and hp.hp_dice_num == 2


def test_use_hp_dice_2014_multiple_clamps_each_die():
    """2014：多粒逐粒结算，每粒最低 0。"""
    hp = _hp()
    token = _roll(SequenceRuntime([1, 5]))
    try:
        _ok, text = HPService.use_hp_dice_ex(hp, 2, -3)
    finally:
        reset_runtime(token)
    # 1-3=-2 → 0；5-3=2
    assert "(([1]+-3)->0)" in text
    assert "([5]+-3)" in text
    assert text.endswith("=2点生命值\nHP:10/30 -> HP:12/30")
    assert hp.hp_cur == 12


def test_use_hp_dice_2024_single():
    """2024：骰点总和 + 枚数 × 体质调整值。"""
    hp = _hp()
    token = _roll(SequenceRuntime([7]))
    try:
        ok, text = HPService.use_hp_dice_ex(hp, 1, 2, version_2024=True)
    finally:
        reset_runtime(token)
    assert ok
    assert text == (
        "使用1颗D8生命骰, 体质调整值为2, 骰点1D8=[7]=7, "
        "调整1×2=+2, 回复9点生命值\n"
        "HP:10/30 -> HP:19/30"
    )


def test_use_hp_dice_2024_multiple_negative_con():
    """2024：3 颗骰点总和 8，3×(-1) = -3，回复 5。"""
    hp = _hp()
    token = _roll(SequenceRuntime([1, 5, 2]))
    try:
        _ok, text = HPService.use_hp_dice_ex(hp, 3, -1, version_2024=True)
    finally:
        reset_runtime(token)
    assert "骰点3D8=[1+5+2]=8, 调整3×-1=-3, 回复5点生命值" in text
    assert hp.hp_cur == 15 and hp.hp_dice_num == 0


def test_use_hp_dice_2024_heal_floor_zero():
    """2024：骰点 + 调整 ≤ 0 时治疗按 0（骰子仍消耗）。"""
    hp = _hp(dice_num=1, dice_max=1)
    token = _roll(SequenceRuntime([5]))
    try:
        _ok, text = HPService.use_hp_dice_ex(hp, 1, -10, version_2024=True)
    finally:
        reset_runtime(token)
    assert "回复0点生命值（最低为0）" in text
    assert hp.hp_cur == 10 and hp.hp_dice_num == 0


def test_use_hp_dice_errors():
    no_dice = _hp(dice_type=0, dice_num=0, dice_max=0)
    assert HPService.use_hp_dice_ex(no_dice, 1, 2) == (False, "尚未设置生命骰")
    hp = _hp(dice_num=1, dice_max=1)
    assert HPService.use_hp_dice_ex(hp, 2, 2) == (False, "生命骰数量不足, 还有1颗生命骰")
    assert HPService.use_hp_dice_ex(hp, 0, 2) == (False, "无效的生命骰数量(0)")


def test_use_hp_dice_old_interface_keeps_2014_output():
    """旧接口默认仍是 2014 版规则（既有调用方不需要改）。"""
    hp = _hp()
    token = _roll(SequenceRuntime([7]))
    try:
        text = HPService.use_hp_dice(hp, 1, 2)
    finally:
        reset_runtime(token)
    assert "回复[7]+2=9点生命值" in text


# =========================================================================
# 能力次数恢复
# =========================================================================


def _feature(name: str, cur: int, max_: int, recover: str) -> CharacterFeature:
    return CharacterFeature(name=name, uses_cur=cur, uses_max=max_, recover=recover)


def test_recover_features_short_and_long():
    features = [
        _feature("奥术回想", 0, 1, "短休"),
        _feature("引导神力", 1, 2, "短休+1,长休"),
        _feature("圣疗", 3, 25, "长休"),
        _feature("狂暴", 0, 3, "两者"),
        _feature("充能", 0, 1, "手动"),
    ]
    short_changes = RestService.recover_features(features, "短休")
    assert short_changes == [
        ("奥术回想", 0, 1, 1),
        ("引导神力", 1, 2, 2),
        ("狂暴", 0, 3, 3),
    ]
    long_changes = RestService.recover_features(features, "长休")
    assert long_changes == [("圣疗", 3, 25, 25)]
    assert features[-1].uses_cur == 0


def test_recover_features_no_change_when_full():
    features = [_feature("奥术回想", 1, 1, "短休")]
    assert RestService.recover_features(features, "短休") == []


def test_feature_recovery_amount_two_modes_with_amount():
    assert RestService.feature_recovery_amount("两者+1", "短休") == 1
    assert RestService.feature_recovery_amount("两者+1", "长休") == 1
    assert RestService.feature_recovery_amount("手动", "短休") is None


# =========================================================================
# 法术位恢复与消耗
# =========================================================================


def _slots() -> SpellSlots:
    return SpellSlots(
        slots_cur=[2, 1, 1, 0, 0, 0, 0, 0, 0],
        slots_max=[4, 3, 2, 0, 0, 0, 0, 0, 0],
        pact_level=3,
        pact_cur=1,
        pact_max=2,
    )


def test_restore_slots_short_only_pact():
    slots = _slots()
    changes = RestService.restore_slots(slots, "短休")
    assert changes == [("契约魔法（3环）", 1, 2, 2)]
    assert slots.pact_cur == 2
    # 普通法术位不动
    assert slots.slots_cur[:3] == [2, 1, 1]


def test_restore_slots_long_all():
    slots = _slots()
    changes = RestService.restore_slots(slots, "长休")
    assert ("1环", 2, 4, 4) in changes
    assert ("2环", 1, 3, 3) in changes
    assert ("3环", 1, 2, 2) in changes
    assert ("契约魔法（3环）", 1, 2, 2) in changes
    assert slots.slots_cur[:3] == [4, 3, 2]
    assert slots.pact_cur == 2


def test_consume_slot_prefers_normal_then_pact_upcast():
    slots = _slots()
    consumed = RestService.consume_spell_slot(slots, 3)
    assert consumed == (False, 3, 1, 2) and slots.slots_cur[2] == 0
    # 3 环普通位已用尽 → 契约位（3 环）兜底
    consumed = RestService.consume_spell_slot(slots, 3)
    assert consumed == (True, 3, 1, 2) and slots.pact_cur == 0
    # 契约位也没了
    assert RestService.consume_spell_slot(slots, 3) is None


def test_consume_slot_pact_upcast_lower_level():
    slots = SpellSlots(slots_max=[0] * 9, slots_cur=[0] * 9,
                       pact_level=3, pact_cur=1, pact_max=1)
    consumed = RestService.consume_spell_slot(slots, 1)
    assert consumed == (True, 3, 1, 1)


def test_consume_slot_no_pact_upcast_when_disallowed():
    slots = SpellSlots(slots_max=[0] * 9, slots_cur=[0] * 9,
                       pact_level=3, pact_cur=1, pact_max=1)
    assert RestService.consume_spell_slot(slots, 1, allow_pact_upcast=False) is None
    assert RestService.consume_spell_slot(slots, 3, allow_pact_upcast=False) is not None


def test_available_slots_summary():
    slots = _slots()
    assert RestService.available_slots_summary(slots) == (
        "1环 2/4、2环 1/3、3环 1/2、契约魔法（3环） 1/2"
    )
    assert RestService.available_slots_summary(SpellSlots()) == "无"


# =========================================================================
# 未准备提醒判定
# =========================================================================


@pytest.mark.parametrize(
    "version_2024, char_class, expected",
    [
        (True, "法师", True),
        (True, "魔契师", True),
        (True, "游荡者", False),
        (True, "", False),
        (False, "法师", True),
        (False, "牧师", True),
        (False, "吟游诗人", False),
        (False, "游侠", False),
        (False, "游荡者", False),
    ],
)
def test_should_remind_preparation(version_2024, char_class, expected):
    assert (
        RestService.should_remind_preparation(version_2024, char_class)
        is expected
    )
