"""法术战斗字段与自动掷骰测试（2026-11-02）。

覆盖：卡面战斗字段解析与回写、.施法 四类型（攻击 / 豁免 / 自动 / 辅助）、
升环加骰、优劣势、.X攻击 / .X伤害 回退读法术段、重击与不支持的后缀、
旧卡未配置战斗字段的兼容提示、错误路径。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11
from nonebot_plugin_dnddicer.character.services import parse_spell_item
from nonebot_plugin_dnddicer.character.spell_combat import (
    build_damage_parts,
    combine_damage_terms,
    format_damage_parts,
)
from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_GROUP = 87654361

_CARD = "\n".join([
    "$姓名$ 洛恩",
    "$职业$ 法师",
    "$等级$ 5",
    "$生命值$ 37/37",
    "$生命骰$ 5/5 D6",
    "$属性$ 8/15/16/18/10/8",
    "$武器$ 匕首+5|1d4+2穿刺",
    "$法术$ 施法属性:智力; 豁免DC:15; 法术攻击:+8; "
    "火球术:3*|类型:豁免|豁免:敏捷|成功:半伤|伤害:8d6火焰|升环:+1d6; "
    "火焰箭:0|类型:攻击|伤害:2d10火焰; "
    "魔法飞弹:1*|类型:自动|伤害:1d4+1力场|多发:3|升环:+1发; "
    "护盾术:1*|类型:辅助|效果:AC+5; "
    "闪电束:3; "
    "灼热射线:2|类型:攻击|伤害:2d6火焰|多发:3|升环:+1发",
    "$法术位$ 1:4/4; 2:3/3; 3:2/2; 4:1/1",
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


def _event(text: str, user_id: int = 25031, group_id: int = _GROUP):
    return fake_group_message_event_v11(
        message=Message(text), group_id=group_id, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _record(app: App, card: str = _CARD, user_id: int = 25031):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(
        app, char_matcher,
        _event(f".角色卡新建 测试卡\n{card}", user_id=user_id),
        "已新建角色卡「测试卡」并绑定到本群。",
    )


def _with_runtime(values, func):
    """在固定骰值下执行（同步测试辅助，不用于命令）。"""
    token = set_runtime(SequenceRuntime(values))
    try:
        return func()
    finally:
        reset_runtime(token)


# =========================================================================
# 解析与回写
# =========================================================================


def test_parse_spell_combat_and_roundtrip():
    spell = parse_spell_item(
        "火球术:3*|类型:豁免|豁免:敏捷|成功:半伤|伤害:8d6火焰|升环:+1d6"
    )
    assert spell.kind == "豁免"
    assert spell.save_ability == "敏捷"
    assert spell.save_success == "半伤"
    assert spell.damage_parts[0].expr == "8d6"
    assert spell.damage_parts[0].damage_type == "火焰"
    assert spell.upcast == "+1d6"
    assert spell.get_info() == (
        "火球术:3*|类型:豁免|豁免:敏捷|成功:半伤|伤害:8d6火焰|升环:+1d6"
    )
    assert "敏捷豁免（成功半伤）" in spell.get_combat_summary()
    assert "8d6 火焰" in spell.get_combat_summary()


def test_parse_multi_shot_spell():
    spell = parse_spell_item(
        "魔法飞弹:1|类型:自动|伤害:1d4+1力场|多发:3|升环:+1发"
    )
    assert spell.shots == 3
    assert spell.get_info() == (
        "魔法飞弹:1|类型:自动|伤害:1d4+1力场|多发:3|升环:+1发"
    )
    assert "3 发" in spell.get_combat_summary()
    assert "升环+1发" in spell.get_combat_summary()


def test_parse_multi_part_damage_and_upcast_type():
    spell = parse_spell_item(
        "冰风暴:4|类型:豁免|豁免:敏捷|成功:半伤|"
        "伤害:2d10钝击+4d6寒冷|升环:+1d10钝击"
    )
    assert [part.damage_type for part in spell.damage_parts] == ["钝击", "寒冷"]
    parts, note = build_damage_parts(spell, 5)
    assert note == ""
    assert format_damage_parts(parts) == "3d10 钝击 + 4d6 寒冷"


def test_combine_damage_terms():
    assert combine_damage_terms("8d6+1d6") == "9d6"
    assert combine_damage_terms("3d4+3+2d4+2") == "5d4+5"
    assert combine_damage_terms("1d8+1d6+2") == "1d8+1d6+2"
    assert combine_damage_terms("1d6-2+1d6") == "2d6-2"


@pytest.mark.parametrize(
    "text, message",
    [
        (
            "火球术:3|类型:未知|伤害:8d6火焰",
            "法术类型无效",
        ),
        (
            "火球术:3|类型:豁免|豁免:敏捷|伤害:8d6火焰",
            "伤害型豁免法术必须写 成功",
        ),
        (
            "火焰箭:0|类型:攻击|伤害:2d10火焰|升环:+1d6",
            "戏法不能升环",
        ),
        (
            "冰风暴:4|类型:豁免|豁免:敏捷|成功:半伤|"
            "伤害:2d10钝击+4d6寒冷|升环:+1d10火焰",
            "升环伤害类型「火焰」与基础伤害类型不匹配",
        ),
        (
            "冰风暴:4|类型:豁免|豁免:敏捷|成功:半伤|"
            "伤害:2d10钝击+4d6寒冷|升环:+1d10",
            "多段伤害的升环必须写伤害类型",
        ),
        (
            "火球术:3|类型:豁免|豁免:敏捷|成功:半伤|"
            "伤害:8d6火焰|升环:+1d6火光",
            "升环伤害类型无效",
        ),
        (
            "魔法飞弹:1|类型:自动|伤害:1d4+1力场|多发:1",
            "法术多发数必须是 2~10 的整数",
        ),
        (
            "魔法飞弹:1|类型:自动|伤害:1d4+1力场|多发:11",
            "法术多发数必须是 2~10 的整数",
        ),
        (
            "火球术:3|类型:豁免|豁免:敏捷|成功:半伤|"
            "伤害:8d6火焰|多发:3",
            "不能写 多发",
        ),
        (
            "冰风暴:4|类型:豁免|豁免:敏捷|成功:半伤|"
            "伤害:2d10钝击+4d6寒冷|多发:3",
            "不能写 多发",
        ),
    ],
)
def test_parse_spell_combat_errors(text, message):
    with pytest.raises(AssertionError) as exc:
        parse_spell_item(text)
    assert message in str(exc.value)


# =========================================================================
# .施法：攻击 / 豁免 / 自动 / 辅助
# =========================================================================


@pytest.mark.asyncio
async def test_cast_attack_then_damage(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)

    token = set_runtime(SequenceRuntime([7]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 火焰箭"),
            "洛恩施展了「火焰箭」（戏法）\n"
            "戏法不消耗法术位。\n"
            "火焰箭法术攻击检定：\n"
            "1D20+8=[7]+8=15\n"
            "命中后可用 .火焰箭伤害 掷伤害。",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([6, 4]))
    try:
        await _expect(
            app, weapon_matcher, _event(".火焰箭伤害"),
            "洛恩的「火焰箭」造成了 10 点火焰伤害：\n"
            "2D10=[6+4]=10",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_cast_attack_advantage(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app)
    token = set_runtime(SequenceRuntime([4, 18]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 火焰箭 优势"),
            "洛恩施展了「火焰箭」（戏法）\n"
            "戏法不消耗法术位。\n"
            "火焰箭法术攻击检定：\n"
            "2D20K1+8=MAX{[4], [18]}+8=26\n"
            "命中后可用 .火焰箭伤害 掷伤害。",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_cast_save_and_upcast(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app)

    token = set_runtime(SequenceRuntime([1, 2, 3, 4, 5, 6, 1, 2]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 火球术"),
            "洛恩施展了「火球术」（3环）\n"
            "消耗3环法术位：2/2 → 1/2\n"
            "目标敏捷豁免 DC 15，成功半伤：\n"
            "洛恩的「火球术」造成了 24 点火焰伤害：\n"
            "8D6=[1+2+3+4+5+6+1+2]=24",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([2] * 9))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 火球术4"),
            "洛恩施展了「火球术」（4环）\n"
            "消耗4环法术位：1/1 → 0/1\n"
            "目标敏捷豁免 DC 15，成功半伤：\n"
            "洛恩的「火球术」造成了 18 点火焰伤害：\n"
            "9D6=[2+2+2+2+2+2+2+2+2]=18",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_cast_auto_support_and_non_attack_advantage(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app)

    token = set_runtime(SequenceRuntime([2, 4, 1]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 魔法飞弹"),
            "洛恩施展了「魔法飞弹」（1环）\n"
            "消耗1环法术位：4/4 → 3/4\n"
            "洛恩的「魔法飞弹」造成了 10 点力场伤害（3 发）：\n"
            "1. 1D4+1=[2]+1=3 点力场伤害\n"
            "2. 1D4+1=[4]+1=5 点力场伤害\n"
            "3. 1D4+1=[1]+1=2 点力场伤害",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([3, 1, 4, 2]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 魔法飞弹2"),
            "洛恩施展了「魔法飞弹」（2环）\n"
            "消耗2环法术位：3/3 → 2/3\n"
            "洛恩的「魔法飞弹」造成了 14 点力场伤害（4 发）：\n"
            "1. 1D4+1=[3]+1=4 点力场伤害\n"
            "2. 1D4+1=[1]+1=2 点力场伤害\n"
            "3. 1D4+1=[4]+1=5 点力场伤害\n"
            "4. 1D4+1=[2]+1=3 点力场伤害",
        )
    finally:
        reset_runtime(token)

    await _expect(
        app, cast_matcher, _event(".施法 护盾术"),
        "洛恩施展了「护盾术」（1环）\n"
        "消耗1环法术位：3/4 → 2/4\n"
        "AC+5",
    )

    token = set_runtime(SequenceRuntime([2, 2, 2, 2, 2, 2, 2, 2]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 火球术 优势"),
            "洛恩施展了「火球术」（3环）\n"
            "消耗3环法术位：2/2 → 1/2\n"
            "「火球术」不进行攻击检定。\n"
            "目标敏捷豁免 DC 15，成功半伤：\n"
            "洛恩的「火球术」造成了 16 点火焰伤害：\n"
            "8D6=[2+2+2+2+2+2+2+2]=16",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_cast_legacy_no_combat(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher
    from nonebot_plugin_dnddicer.commands import text

    await _record(app)
    await _expect(
        app, cast_matcher, _event(".施法 闪电束"),
        "洛恩施展了「闪电束」（3环）\n"
        "消耗3环法术位：2/2 → 1/2"
        + "\n" + text.TXT_CAST_NO_COMBAT.format(spell="闪电束")
        + "\n（未标记为已准备，如需标记：.法术 准备 闪电束）",
    )


# =========================================================================
# .X攻击 / .X伤害 读法术段
# =========================================================================


@pytest.mark.asyncio
async def test_attack_command_reads_spell(app: App):
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)

    token = set_runtime(SequenceRuntime([7]))
    try:
        await _expect(
            app, weapon_matcher, _event(".火焰箭攻击"),
            "洛恩进行【火焰箭法术攻击检定】：\n"
            "法术攻击加值:+8\n"
            "1D20+8=[7]+8=15",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([4, 18]))
    try:
        await _expect(
            app, weapon_matcher, _event(".火焰箭攻击优势"),
            "洛恩进行【火焰箭法术攻击检定】：\n"
            "法术攻击加值:+8 优势\n"
            "2D20K1+8=MAX{[4], [18]}+8=26",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_damage_command_reads_spell_and_upcast(app: App):
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)

    token = set_runtime(SequenceRuntime([5, 5, 5, 5]))
    try:
        await _expect(
            app, weapon_matcher, _event(".火焰箭重击伤害"),
            "洛恩的「火焰箭」造成了 20 点火焰伤害（重击）：\n"
            "4D10=[5+5+5+5]=20",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([1] * 9))
    try:
        await _expect(
            app, weapon_matcher, _event(".火球术4伤害"),
            "洛恩的「火球术」造成了 9 点火焰伤害：\n"
            "9D6=[1+1+1+1+1+1+1+1+1]=9",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_spell_damage_rejects_weapon_suffixes(app: App):
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)
    await _expect(
        app, weapon_matcher, _event(".火球术重击伤害"),
        "「火球术」不是法术攻击型，不能使用「重击」。",
    )
    await _expect(
        app, weapon_matcher, _event(".火焰箭副手伤害"),
        "法术伤害不支持「副手」。",
    )
    await _expect(
        app, weapon_matcher, _event(".火焰箭偷袭伤害"),
        "法术伤害不支持「偷袭」。",
    )


@pytest.mark.asyncio
async def test_spell_multi_attack_and_repeat_damage(app: App):
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)

    token = set_runtime(SequenceRuntime([7, 12, 2, 15]))
    try:
        await _expect(
            app, weapon_matcher, _event(".灼热射线3攻击"),
            "洛恩进行【灼热射线法术攻击检定】（4 发）：\n"
            "法术攻击加值:+8\n"
            "1. 1D20+8=[7]+8=15\n"
            "2. 1D20+8=[12]+8=20\n"
            "3. 1D20+8=[2]+8=10\n"
            "4. 1D20+8=[15]+8=23",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([3, 4]))
    try:
        await _expect(
            app, weapon_matcher, _event(".灼热射线伤害"),
            "洛恩的「灼热射线」造成了 7 点火焰伤害：\n"
            "2D6=[3+4]=7",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([3, 4, 1, 1, 5, 6]))
    try:
        await _expect(
            app, weapon_matcher, _event(".3#灼热射线伤害"),
            "洛恩的「灼热射线」掷了 3 次伤害：\n"
            "1. 2D6=[3+4]=7 点火焰伤害\n"
            "2. 2D6=[1+1]=2 点火焰伤害\n"
            "3. 2D6=[5+6]=11 点火焰伤害\n"
            "共计造成了 20 点火焰伤害",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_cast_multi_attack_hint(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app)
    token = set_runtime(SequenceRuntime([7, 12, 2]))
    try:
        await _expect(
            app, cast_matcher, _event(".施法 灼热射线"),
            "洛恩施展了「灼热射线」（2环）\n"
            "消耗2环法术位：3/3 → 2/3\n"
            "灼热射线法术攻击检定（3 发）：\n"
            "1. 1D20+8=[7]+8=15\n"
            "2. 1D20+8=[12]+8=20\n"
            "3. 1D20+8=[2]+8=10\n"
            "命中后可用 .灼热射线伤害 掷伤害；多道命中可写 .3#灼热射线伤害。\n"
            "（未标记为已准备，如需标记：.法术 准备 灼热射线）",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_spell_commands_reject_wrong_type(app: App):
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)
    await _expect(
        app, weapon_matcher, _event(".火球术攻击"),
        "「火球术」不进行攻击检定。",
    )
    await _expect(
        app, weapon_matcher, _event(".闪电束攻击"),
        "「闪电束」不进行攻击检定。",
    )


@pytest.mark.asyncio
async def test_spell_damage_command_allows_save_and_auto(app: App):
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)

    token = set_runtime(SequenceRuntime([3]))
    try:
        await _expect(
            app, weapon_matcher, _event(".魔法飞弹伤害"),
            "洛恩的「魔法飞弹」造成了 4 点力场伤害：\n"
            "1D4+1=[3]+1=4",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([1] * 8))
    try:
        await _expect(
            app, weapon_matcher, _event(".火球术伤害"),
            "洛恩的「火球术」造成了 8 点火焰伤害：\n"
            "8D6=[1+1+1+1+1+1+1+1]=8",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_cast_missing_combat_config(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    card = "\n".join([
        "$姓名$ 无配置",
        "$职业$ 法师",
        "$等级$ 5",
        "$生命值$ 30/30",
        "$属性$ 8/15/16/18/10/8",
        "$法术$ 火焰箭:0|类型:攻击|伤害:2d10火焰; "
        "火球术:3|类型:豁免|豁免:敏捷|成功:半伤|伤害:8d6火焰",
        "$法术位$ 3:1/1",
    ])
    await _record(app, card)
    await _expect(
        app, cast_matcher, _event(".施法 火焰箭"),
        "「火焰箭」缺少法术攻击加值："
        "请在 .设置法术 写 法术攻击:+N，或在条目里写 攻击:+N。",
    )
    await _expect(
        app, cast_matcher, _event(".施法 火球术"),
        "「火球术」缺少豁免 DC："
        "请在 .设置法术 写 豁免DC:15，或在条目里写 DC:15。",
    )


@pytest.mark.asyncio
async def test_damage_command_upcast_errors(app: App):
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)
    await _expect(
        app, weapon_matcher, _event(".火焰箭4伤害"),
        "「火焰箭」是戏法，不能升环。",
    )
    await _expect(
        app, weapon_matcher, _event(".火球术2伤害"),
        "「火球术」最低为 3环，不能用 2环。",
    )
