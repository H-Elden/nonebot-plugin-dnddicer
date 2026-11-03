"""法术治疗字段与治疗骰测试（2026-11-03）。

覆盖：``治疗`` 字段解析与回写、治疗型校验、升环加骰与固定值、
``.施法`` 治疗型输出、``.X攻击`` / ``.X伤害`` 拒绝治疗型、
``.设置法术`` 覆盖治疗字段。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11
from nonebot_plugin_dnddicer.character.services import (
    parse_spell_item,
    split_spell_upcast,
)
from nonebot_plugin_dnddicer.character.spell_combat import (
    build_damage_parts,
    build_heal_expression,
)
from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_GROUP = 87654362

_CARD = "\n".join([
    "$姓名$ 布鲁姆",
    "$职业$ 牧师",
    "$等级$ 5",
    "$生命值$ 48/48",
    "$生命骰$ 5/5 D8",
    "$属性$ 14/8/16/8/18/11",
    "$武器$ 战锤+5|1d8+2钝击",
    "$法术$ 施法属性:感知; 豁免DC:15; 法术攻击:+7; "
    "治疗真言:1*|类型:治疗|治疗:2d4+4|升环:+2d4|"
    "时间:1附赠动作|距离:60尺; "
    "医疗术:6*|类型:治疗|治疗:70|升环:+10; "
    "群体治愈真言:3*|类型:治疗|治疗:2d4+4|升环:+1d4|效果:至多 6 个目标",
    "$法术位$ 1:4/4; 2:3/3; 3:2/3; 6:1/1; 7:1/1",
])


@pytest.fixture(autouse=True)
def _clear_store():
    """每个用例前清空角色卡、群配置与施法设置（缓存 + JSON）。"""
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file
    from nonebot_plugin_dnddicer.data import group_config as _group_config
    from nonebot_plugin_dnddicer.data import spell_settings as _spell_settings

    _chars._cache = None
    _group_config._cache = None
    _spell_settings._cache = None
    for name in ("cards.json", "group_config.json", "spell_settings.json"):
        path = get_data_file(name)
        if path.exists():
            path.write_text("{}", encoding="utf-8")
    yield


def _event(text: str, user_id: int = 25041, group_id: int = _GROUP):
    return fake_group_message_event_v11(
        message=Message(text), group_id=group_id, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _record(app: App, card: str = _CARD, user_id: int = 25041):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(
        app, char_matcher,
        _event(f".角色卡新建 测试卡\n{card}", user_id=user_id),
        "已新建角色卡「测试卡」并绑定到本群。",
    )


# =========================================================================
# 解析与回写
# =========================================================================


def test_parse_heal_spell_and_roundtrip():
    spell = parse_spell_item(
        "治疗真言:1*|类型:治疗|治疗:2d4+4|升环:+2d4|时间:1附赠动作|距离:60尺"
    )
    assert spell.kind == "治疗"
    assert spell.heal_expr == "2d4+4"
    assert spell.get_info() == (
        "治疗真言:1*|类型:治疗|治疗:2d4+4|升环:+2d4|时间:1附赠动作|距离:60尺"
    )
    assert "治疗 2d4+4" in spell.get_combat_summary()
    assert "升环+2d4" in spell.get_combat_summary()


def test_parse_flat_heal_spell():
    spell = parse_spell_item("医疗术:6|类型:治疗|治疗:70|升环:+10")
    assert spell.heal_expr == "70"
    assert spell.get_info() == "医疗术:6|类型:治疗|治疗:70|升环:+10"


def test_split_upcast_flat_and_free_text():
    assert split_spell_upcast("+10") == (("10", ""), "")
    assert split_spell_upcast("+2d4") == (("2d4", ""), "")
    assert split_spell_upcast("+1目标") == (None, "+1目标")
    assert split_spell_upcast("+1发") == (None, "+1发")


def test_build_heal_expression_upcast_dice():
    spell = parse_spell_item("治疗真言:1|类型:治疗|治疗:2d4+4|升环:+2d4")
    assert build_heal_expression(spell, 1) == ("2d4+4", "")
    assert build_heal_expression(spell, 3) == ("6d4+4", "")


def test_build_heal_expression_upcast_flat():
    spell = parse_spell_item("医疗术:6|类型:治疗|治疗:70|升环:+10")
    assert build_heal_expression(spell, 6) == ("70", "")
    assert build_heal_expression(spell, 8) == ("90", "")


def test_build_damage_parts_upcast_flat():
    spell = parse_spell_item("火焰箭:0|类型:攻击|伤害:2d10火焰")
    spell.upcast = "+10"
    parts, note = build_damage_parts(spell, 1)
    assert note == ""
    assert parts[0].expr == "2d10+10"


@pytest.mark.parametrize(
    "text, message",
    [
        (
            "治疗真言:1|类型:治疗|效果:恢复 2d4+4 生命值",
            "治疗型法术必须写 治疗",
        ),
        (
            "火球术:3|类型:自动|伤害:8d6火焰|治疗:2d4+3",
            "类型为自动的法术不能写 治疗",
        ),
        (
            "治疗真言:1|类型:治疗|治疗:2d4+3|伤害:2d6火焰",
            "治疗型法术不能写 攻击 / 豁免 / DC / 成功 / 伤害 / 多发",
        ),
        (
            "治疗真言:1|类型:治疗|治疗:2d4+3|攻击:+7",
            "治疗型法术不能写 攻击 / 豁免 / DC / 成功 / 伤害 / 多发",
        ),
        (
            "治疗真言:1|类型:治疗|治疗:2d4+3|豁免:敏捷",
            "治疗型法术不能写 攻击 / 豁免 / DC / 成功 / 伤害 / 多发",
        ),
        (
            "治疗真言:1|类型:治疗|治疗:2d4+3|多发:3",
            "治疗型法术不能写 攻击 / 豁免 / DC / 成功 / 伤害 / 多发",
        ),
        (
            "治疗真言:1|类型:治疗|治疗:2d4+3|升环:+2d4光耀",
            "治疗型升环不能写伤害类型",
        ),
        (
            "治疗真言:1|类型:治疗|治疗:2d4+3|升环:+1发",
            "不能写 升环:+N发",
        ),
        (
            "治疗真言:1|类型:治疗|治疗:2d4+",
            "法术治疗量无效",
        ),
        (
            "治疗真言:1|治疗:2d4+3",
            "法术写了战斗字段但没有写类型",
        ),
    ],
)
def test_parse_heal_spell_errors(text, message):
    with pytest.raises(AssertionError) as exc:
        parse_spell_item(text)
    assert message in str(exc.value)


# =========================================================================
# .施法：治疗型
# =========================================================================


@pytest.mark.asyncio
async def test_cast_heal_single(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app)
    token = set_runtime(SequenceRuntime([2, 3]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 治疗真言"),
            "布鲁姆施展了「治疗真言」（1环）\n"
            "消耗1环法术位：4/4 → 3/4\n"
            "布鲁姆的「治疗真言」恢复了 9 点生命值：\n"
            "2D4+4=[2+3]+4=9",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_cast_heal_upcast_dice(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app)
    token = set_runtime(SequenceRuntime([1, 2, 3, 4]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 治疗真言2环"),
            "布鲁姆施展了「治疗真言」（2环）\n"
            "消耗2环法术位：3/3 → 2/3\n"
            "布鲁姆的「治疗真言」恢复了 14 点生命值：\n"
            "4D4+4=[1+2+3+4]+4=14",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_cast_heal_flat(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app)
    token = set_runtime(SequenceRuntime([]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 医疗术"),
            "布鲁姆施展了「医疗术」（6环）\n"
            "消耗6环法术位：1/1 → 0/1\n"
            "布鲁姆的「医疗术」恢复了 70 点生命值。",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_cast_heal_flat_upcast(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app)
    token = set_runtime(SequenceRuntime([]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 医疗术7环"),
            "布鲁姆施展了「医疗术」（7环）\n"
            "消耗7环法术位：1/1 → 0/1\n"
            "布鲁姆的「医疗术」恢复了 80 点生命值。",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_cast_group_heal_shows_effect(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app)
    token = set_runtime(SequenceRuntime([2, 2]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 群体治愈真言"),
            "布鲁姆施展了「群体治愈真言」（3环）\n"
            "消耗3环法术位：2/3 → 1/3\n"
            "布鲁姆的「群体治愈真言」恢复了 8 点生命值：\n"
            "2D4+4=[2+2]+4=8\n"
            "至多 6 个目标",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_heal_spell_rejects_attack_and_damage(app: App):
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher
    from nonebot_plugin_dnddicer.commands import text

    await _record(app)
    expected = text.TXT_SPELL_IS_HEAL.format(spell="治疗真言")

    await _expect(app, weapon_matcher, _event(".治疗真言攻击"), expected)
    await _expect(app, weapon_matcher, _event(".治疗真言伤害"), expected)


@pytest.mark.asyncio
async def test_set_spell_heal_overrides(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher, set_spell_matcher

    await _record(app)
    await _expect(
        app, set_spell_matcher,
        _event(".设置法术 治疗真言:1|类型:治疗|治疗:2d8+4|升环:+1d8"),
        (
            "已设置法术：治疗真言（当前共 3 项）\n"
            "1. 治疗真言 1环（已准备）\n"
            "2. 群体治愈真言 3环（已准备）\n"
            "3. 医疗术 6环（已准备）"
        ),
    )
    token = set_runtime(SequenceRuntime([5, 6]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 治疗真言"),
            "布鲁姆施展了「治疗真言」（1环）\n"
            "消耗1环法术位：4/4 → 3/4\n"
            "布鲁姆的「治疗真言」恢复了 15 点生命值：\n"
            "2D8+4=[5+6]+4=15",
        )
    finally:
        reset_runtime(token)
