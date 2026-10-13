"""角色卡规则版本（5e / 5r）与死亡豁免模型层单测（不依赖 nonebug）。

覆盖：
- ``character/rules.py`` 的版本归一、默认回落与群级读取（读的是真实群配置
  数据层，仅 monkeypatch 掉数据读写本身，不碰网络）；
- ``HPInfo`` 的死亡豁免字段与计数语义（成功/失败/稳定/死亡/复活）；
- ``HPService`` 的伤害联动（进入濒死、濒死中受击、重击 +2、即死）与
  ``roll_death_save`` 的出目判定（自然 20 / 自然 1 / ≥10 / ≤9）。
"""

import pytest

from nonebot_plugin_dnddicer.character import rules
from nonebot_plugin_dnddicer.character.models import HPInfo
from nonebot_plugin_dnddicer.character.services import HPService
from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime


def _hp(cur: int = 20, hp_max: int = 30) -> HPInfo:
    """构造一张已初始化生命值的 HPInfo。"""
    info = HPInfo()
    info.initialize(hp_cur=cur, hp_max=hp_max, hp_temp=0, hp_dice_type=8,
                    hp_dice_num=3, hp_dice_max=3)
    return info


def _roll(seq):
    return set_runtime(SequenceRuntime(seq))


# =========================================================================
# 规则版本归一与群级读取
# =========================================================================


@pytest.mark.parametrize("raw, expected", [
    ("2024", "2024"), ("5r", "2024"), ("5R", "2024"), (" 5r ", "2024"),
    ("5.5e", "2024"), ("2024版", "2024"), ("5e2024", "2024"),
    ("2014", "2014"), ("5e", "2014"), ("5E", "2014"), ("2014版", "2014"),
    ("5e2014", "2014"),
    ("", None), ("6e", None), ("2025", None), (None, None),
])
def test_normalize_rules_version(raw, expected):
    """各种写法归一到 2014 / 2024；无法识别的返回 None。"""
    assert rules.normalize_rules_version(raw) == expected


def test_default_rules_version():
    """配置项默认值为 2024（5r）。"""
    assert rules.default_rules_version() == "2024"


@pytest.mark.asyncio
async def test_group_level_rules_version(monkeypatch):
    """群级设置优先；未设置或脏值回落默认。"""
    store = {"group_level": "2014", "group_dirty": "6e", "group_empty": None}

    async def fake_get_group_config(group_id):
        return {rules.RULES_VERSION_FIELD: store.get(str(group_id))}

    monkeypatch.setattr(rules, "get_group_config", fake_get_group_config)

    version, is_group_level = await rules.read_rules_version("group_level")
    assert (version, is_group_level) == ("2014", True)
    assert await rules.rules_version("group_level") == "2014"

    version, is_group_level = await rules.read_rules_version("group_dirty")
    assert (version, is_group_level) == ("2024", False)

    version, is_group_level = await rules.read_rules_version("group_empty")
    assert (version, is_group_level) == ("2024", False)


# =========================================================================
# HPInfo 死亡豁免状态
# =========================================================================


def test_hp_info_initializes_without_death_state():
    """新卡初始化后死亡豁免状态干净；旧存档缺字段按默认值读入。"""
    info = _hp()
    assert (info.ds_success, info.ds_failure) == (0, 0)
    assert not info.is_stable and not info.is_dead
    assert info.get_death_info() == ""
    legacy = HPInfo(**{"is_init": True, "hp_cur": 0, "hp_max": 10, "is_alive": False})
    assert (legacy.ds_success, legacy.ds_failure) == (0, 0)
    assert legacy.is_dying()  # 旧存档「0 HP 昏迷」直接视为濒死


def test_is_dying_follows_hp_value():
    """濒死以 HP ≤ 0 判定（损失记录模式的负 HP 也算），不看 is_alive 标记。"""
    record = HPInfo()
    record.initialize(hp_cur=0, hp_max=0)
    assert record.is_dying()  # 未设上限、HP 为 0 的「损失记录」初始态
    record.hp_cur = -5
    assert record.is_dying()
    record.hp_cur = 3
    assert not record.is_dying()


def test_death_success_three_times_makes_stable():
    """成功累计 3 次 → 稳定并清零计数。"""
    info = _hp(cur=0)
    info.is_alive = False
    assert info.add_death_success() is False
    assert info.add_death_success() is False
    assert info.add_death_success() is True
    assert info.is_stable
    assert (info.ds_success, info.ds_failure) == (0, 0)
    assert info.get_death_info() == "伤势稳定"
    assert not info.is_dying()


def test_death_failure_three_times_dies():
    """失败累计 3 次 → 死亡并解除稳定。"""
    info = _hp(cur=0)
    info.is_alive = False
    info.add_death_failure()
    info.add_death_failure()
    assert info.add_death_failure() is True
    assert info.is_dead and not info.is_stable
    assert info.get_death_info() == "已死亡"
    # 已死亡后不再累加
    assert info.add_death_failure() is False
    assert info.ds_failure == 3


def test_clear_death_state_revive_flag():
    """clear_death_state 默认连死亡标记一起清，revive=False 只清计数。"""
    info = _hp(cur=0)
    info.is_alive = False
    info.add_death_failure(3)
    assert info.is_dead
    info.clear_death_state(revive=False)
    assert info.is_dead and not info.is_stable
    info.clear_death_state()
    assert not info.is_dead


def test_heal_clears_death_state_but_not_dead():
    """治疗回正清除濒死状态；已死亡的卡不被治疗复活。"""
    info = _hp(cur=0)
    info.is_alive = False
    info.add_death_failure(2)
    info.add_death_success(1)
    info.heal(5)
    assert info.hp_cur == 5 and info.is_alive
    assert (info.ds_success, info.ds_failure, info.is_stable) == (0, 0, False)

    dead = _hp(cur=0)
    dead.is_alive = False
    dead.add_death_failure(3)
    dead.heal(10)
    assert dead.hp_cur == 0 and dead.is_dead


# =========================================================================
# 伤害联动
# =========================================================================


def test_damage_to_zero_enters_dying():
    """HP 归 0 → 返回「本次进入濒死」，计数清零。"""
    info = _hp(cur=10)
    was_unconscious = not info.is_alive
    info.take_damage(10)
    transition, text_out = HPService.apply_death_save_on_damage(
        info, 10, was_unconscious=was_unconscious
    )
    assert transition == HPService.DEATH_TRANSITION_ENTERED and text_out == ""
    assert (info.ds_success, info.ds_failure) == (0, 0)
    assert info.is_dying()


def test_damage_while_dying_records_failure():
    """濒死中再受伤 → 失败 +1；重击 +2。"""
    info = _hp(cur=10)
    was_unconscious = not info.is_alive
    info.take_damage(10)
    HPService.apply_death_save_on_damage(info, 10, was_unconscious=was_unconscious)

    was_unconscious = not info.is_alive
    info.take_damage(3)
    transition, message = HPService.apply_death_save_on_damage(
        info, 3, was_unconscious=was_unconscious
    )
    assert transition == HPService.DEATH_TRANSITION_DAMAGE
    assert "失败+1" in message and info.ds_failure == 1

    was_unconscious = not info.is_alive
    info.take_damage(3)
    transition, message = HPService.apply_death_save_on_damage(
        info, 3, critical=True, was_unconscious=was_unconscious
    )
    assert transition == HPService.DEATH_TRANSITION_DEATH
    assert info.ds_failure == 3 and info.is_dead
    assert "死亡" in message


def test_damage_while_stable_restarts_death_save():
    """稳定中受伤 → 解除稳定、重新开始死亡豁免（不累加旧计数）。"""
    info = _hp(cur=10)
    was_unconscious = not info.is_alive
    info.take_damage(10)
    HPService.apply_death_save_on_damage(info, 10, was_unconscious=was_unconscious)
    info.add_death_failure(2)
    info.add_death_success(3)
    assert info.is_stable

    was_unconscious = not info.is_alive
    info.take_damage(4)
    transition, message = HPService.apply_death_save_on_damage(
        info, 4, was_unconscious=was_unconscious
    )
    # 稳定中受击：昏迷状态未变，故按「重新开始」而非「进入濒死」播报
    assert transition == HPService.DEATH_TRANSITION_RESTART and message == ""
    assert not info.is_stable and info.is_dying()
    assert (info.ds_success, info.ds_failure) == (0, 0)


def test_damage_over_hp_max_is_instant_death():
    """单次伤害 ≥ HP 上限 → 直接死亡（不看计数）。"""
    info = _hp(cur=30, hp_max=30)
    was_unconscious = not info.is_alive
    info.take_damage(30)
    transition, message = HPService.apply_death_save_on_damage(
        info, 30, was_unconscious=was_unconscious
    )
    assert transition == HPService.DEATH_TRANSITION_DEATH and info.is_dead
    assert "死亡" in message
    assert info.get_info().endswith("已死亡")


def test_damage_without_hp_max_skips_instant_death():
    """未设 HP 上限（损失记录模式）不做即死判定，负数夹到 0 并记失败。"""
    info = HPInfo()
    info.initialize(hp_cur=0, hp_max=0)  # 记录模式：0 HP、无法看出昏迷标记
    was_unconscious = info.is_dying()
    info.take_damage(7)  # 记录模式：0 - 7 = -7
    assert info.hp_cur == -7
    transition, _message = HPService.apply_death_save_on_damage(
        info, 7, was_unconscious=was_unconscious
    )
    assert transition == HPService.DEATH_TRANSITION_DAMAGE
    assert info.hp_cur == 0 and info.ds_failure == 1
    assert not info.is_dead  # 上限未知，绝不因「伤害 ≥ 上限」误杀


def test_dead_character_takes_no_further_failure():
    """已死亡者再受伤不叠加失败（复活由 .死亡豁免 重置 裁决）。"""
    info = _hp(cur=10)
    info.take_damage(10)
    info.add_death_failure(3)
    assert info.is_dead
    info.take_damage(5)
    transition, message = HPService.apply_death_save_on_damage(
        info, 5, was_unconscious=True
    )
    assert transition == HPService.DEATH_TRANSITION_NONE and message == ""
    assert info.ds_failure == 3


# =========================================================================
# .死亡豁免 掷骰结算
# =========================================================================


def test_roll_death_save_success_and_failure():
    """出目 ≥10 记成功、≤9 记失败（与属性无关）。"""
    info = _hp(cur=0)
    info.is_alive = False
    token = _roll([10])
    try:
        _res, message, value, nat20, nat1 = HPService.roll_death_save(info)
    finally:
        reset_runtime(token)
    assert value == 10 and not nat20 and not nat1
    assert info.ds_success == 1 and "成功" in message

    token = _roll([9])
    try:
        _res, message, _value, _n20, _n1 = HPService.roll_death_save(info)
    finally:
        reset_runtime(token)
    assert info.ds_failure == 1 and "失败" in message


def test_roll_death_save_natural_20_revives():
    """自然 20 → 回复 1 点 HP、清空死亡豁免状态。"""
    info = _hp(cur=0)
    info.is_alive = False
    info.add_death_failure(2)
    token = _roll([20])
    try:
        _res, message, _value, nat20, _nat1 = HPService.roll_death_save(info)
    finally:
        reset_runtime(token)
    assert nat20 and info.hp_cur == 1 and info.is_alive
    assert (info.ds_success, info.ds_failure) == (0, 0)
    assert "自然20" in message


def test_roll_death_save_natural_1_counts_twice():
    """自然 1 → 失败 +2。"""
    info = _hp(cur=0)
    info.is_alive = False
    token = _roll([1])
    try:
        _res, message, _value, _nat20, nat1 = HPService.roll_death_save(info)
    finally:
        reset_runtime(token)
    assert nat1 and info.ds_failure == 2 and not info.is_dead
    assert "失败 +2" in message


def test_roll_death_save_third_failure_dies():
    """失败累计 3 次 → 死亡。"""
    info = _hp(cur=0)
    info.is_alive = False
    for expected_failure in (1, 2, 3):
        token = _roll([5])
        try:
            _res, message, _value, _n20, _n1 = HPService.roll_death_save(info)
        finally:
            reset_runtime(token)
        assert info.ds_failure == expected_failure
    assert info.is_dead and "死亡" in message


def test_roll_death_save_advantage_and_bonus():
    """优势取高、房规 ±加值只影响出目判定。"""
    info = _hp(cur=0)
    info.is_alive = False
    token = _roll([7, 3])
    try:
        _res, _message, value, _n20, _n1 = HPService.roll_death_save(info, 1)
    finally:
        reset_runtime(token)
    assert value == 7 and info.ds_failure == 1

    token = _roll([8])
    try:
        _res, _message, value, _n20, _n1 = HPService.roll_death_save(info, 0, "+3")
    finally:
        reset_runtime(token)
    assert value == 11 and info.ds_success == 1

    with pytest.raises(AssertionError):
        HPService.roll_death_save(info, 0, "abc")
