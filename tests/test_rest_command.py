""".生命骰 / .短休 / .长休 扩展的 nonebug 测试（2026-10-20 批③）。

覆盖：生命骰两版口径与 @ 代操作、短休能力/契约位恢复与生命骰提示、
长休恢复能力/法术位/准备提示；以及死亡、0 HP、无骰等守卫。
"""

import nonebot
import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from fake_event import fake_group_message_event_v11

from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_GROUP = 87654350


@pytest.fixture(autouse=True)
def _clear_store():
    """每个用例前清空角色卡与群配置（缓存 + JSON）。"""
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file
    from nonebot_plugin_dnddicer.data import group_config as _group_config

    _chars._cache = None
    _group_config._cache = None
    for name in ("cards.json", "group_config.json"):
        path = get_data_file(name)
        if path.exists():
            path.write_text("{}", encoding="utf-8")
    yield


def _event(text: str, user_id: int = 24001, group_id: int = _GROUP):
    return fake_group_message_event_v11(
        message=Message(text), group_id=group_id, user_id=user_id
    )


def _mention_event(text: str, qq: int, user_id: int = 24001, group_id: int = _GROUP):
    return fake_group_message_event_v11(
        message=Message(text) + MessageSegment.at(qq),
        group_id=group_id,
        user_id=user_id,
    )


async def _expect(app: App, matcher, event, expected):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _expect_with_dice(app: App, matcher, event, expected, dice):
    """固定骰值执行一条命令（生命骰结算用）。"""
    token = set_runtime(SequenceRuntime(dice))
    try:
        await _expect(app, matcher, event, expected)
    finally:
        reset_runtime(token)


async def _record(app: App, card: str, user_id: int = 24001, group_id: int = _GROUP):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(
        app, char_matcher,
        _event(f".角色卡新建 测试卡\n{card}", user_id=user_id, group_id=group_id),
        "已新建角色卡「测试卡」并绑定到本群。",
    )


async def _set_rules_version(group_id: int, version: str) -> None:
    from nonebot_plugin_dnddicer.character import rules
    from nonebot_plugin_dnddicer.data.group_config import set_group_config_field

    await set_group_config_field(group_id, rules.RULES_VERSION_FIELD, version)


_CARD_CAST = "\n".join([
    "$姓名$ 洛恩",
    "$职业$ 法师",
    "$等级$ 5",
    "$生命值$ 10/30",
    "$生命骰$ 3/4 D6",
    "$属性$ 8/15/16/18/10/8",
    "$限定资源$ 奥术回想:0/1短休; 圣疗:0/25长休",
    "$法术$ 施法属性:智力; 火球术:3*",
    "$法术位$ 1:0/2; 2:1/3; 契约3:0/2",
])


# =========================================================================
# .生命骰
# =========================================================================


@pytest.mark.asyncio
async def test_hp_dice_2024(app: App):
    """2024：骰点总和（至少 1）+ 枚数 × 体质调整。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_dice_matcher

    card = (
        "$姓名$ test\n$等级$ 5\n$生命值$ 10/30\n"
        "$生命骰$ 3/3 D8\n$属性$ 10/10/14/10/10/10"
    )
    await _record(app, card)
    await _expect_with_dice(
        app, hp_dice_matcher, _event(".生命骰 2"),
        "test使用了生命骰：\n"
        "使用2颗D8生命骰, 体质调整值为2, 骰点2D8=[4+6]=10, "
        "调整2×2=+4, 回复14点生命值\n"
        "HP:10/30 -> HP:24/30",
        [4, 6],
    )


@pytest.mark.asyncio
async def test_hp_dice_2014_differs_from_2024(app: App):
    """同一输入两版结果不同：2014 逐粒最低 0，2024 总和 + 枚数 × 体质。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_dice_matcher

    card = (
        "$姓名$ test\n$等级$ 5\n$生命值$ 10/30\n"
        "$生命骰$ 3/3 D8\n$属性$ 10/10/2/10/10/10"
    )
    group_2014, group_2024 = 99110, 99111
    await _set_rules_version(group_2014, "2014")
    await _set_rules_version(group_2024, "2024")
    await _record(app, card, user_id=24010, group_id=group_2014)
    await _record(app, card, user_id=24011, group_id=group_2024)

    await _expect_with_dice(
        app, hp_dice_matcher,
        _event(".生命骰 2", user_id=24010, group_id=group_2014),
        "test使用了生命骰：\n"
        "使用2颗D8生命骰, 体质调整值为-4, "
        "回复(([2]+-4)->0)+([6]+-4)=2点生命值\n"
        "HP:10/30 -> HP:12/30",
        [2, 6],
    )
    await _expect_with_dice(
        app, hp_dice_matcher,
        _event(".生命骰 2", user_id=24011, group_id=group_2024),
        "test使用了生命骰：\n"
        "使用2颗D8生命骰, 体质调整值为-4, "
        "骰点2D8=[2+6]=8, 调整2×-4=-8, 回复0点生命值（最低为0）\n"
        "HP:10/30 -> HP:10/30",
        [2, 6],
    )


@pytest.mark.asyncio
async def test_hp_dice_mention_target(app: App):
    """.生命骰 @玩家：用目标角色的体质与生命骰。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_dice_matcher

    card = (
        "$姓名$ 布兰克\n$等级$ 5\n$生命值$ 5/30\n"
        "$生命骰$ 2/2 D8\n$属性$ 10/10/14/10/10/10"
    )
    await _record(app, card, user_id=24012)
    await _expect_with_dice(
        app, hp_dice_matcher,
        _mention_event(".生命骰 1 ", 24012, user_id=24000),
        "布兰克使用了生命骰：\n"
        "使用1颗D8生命骰, 体质调整值为2, 骰点1D8=[6]=6, "
        "调整1×2=+2, 回复8点生命值\n"
        "HP:5/30 -> HP:13/30",
        [6],
    )


@pytest.mark.asyncio
async def test_hp_dice_guards_and_errors(app: App):
    from nonebot_plugin_dnddicer.commands.hp import hp_dice_matcher

    await _expect(
        app, hp_dice_matcher, _event(".生命骰", user_id=24020),
        "找不到test的角色卡信息",
    )
    card = (
        "$姓名$ test\n$等级$ 5\n$生命值$ 0/30\n"
        "$生命骰$ 2/2 D8\n$属性$ 10/10/14/10/10/10"
    )
    await _record(app, card, user_id=24021)
    await _expect(
        app, hp_dice_matcher, _event(".生命骰", user_id=24021),
        "HP 为 0，无法使用生命骰（请先治疗或稳定）。",
    )
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, hp_matcher, _event(".hp 5/30", user_id=24021),
        "test: HP=5/30\n当前HP:5/30",
    )
    await _expect(
        app, hp_dice_matcher, _event(".生命骰 3", user_id=24021),
        "生命骰数量不足, 还有2颗生命骰",
    )
    await _expect(
        app, hp_dice_matcher, _event(".生命骰 0", user_id=24021),
        "生命骰数量至少为 1",
    )
    await _expect(
        app, hp_dice_matcher, _event(".生命骰 两个", user_id=24021),
        "用法：.生命骰 [数量] [@玩家]（缺省 1 颗）",
    )


@pytest.mark.asyncio
async def test_hp_dice_dead_guard(app: App):
    from nonebot_plugin_dnddicer.commands.hp import hp_dice_matcher

    card = (
        "$姓名$ test\n$等级$ 5\n$生命值$ 1/30\n"
        "$生命骰$ 2/2 D8\n$属性$ 10/10/14/10/10/10"
    )
    await _record(app, card, user_id=24030)
    # 用一次 30 点伤害直接判死（伤害 ≥ 上限）
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, hp_matcher, _event(".hp 1/30", user_id=24030),
        "test: HP=1/30\n当前HP:1/30",
    )
    await _expect(
        app, hp_matcher, _event(".hp -30", user_id=24030),
        "test: 当前HP减少30\nHP:1/30 -> HP:0/30 昏迷 已死亡\n"
        "受到30点伤害（≥生命值上限 30）——死亡。",
    )
    await _expect(
        app, hp_dice_matcher, _event(".生命骰", user_id=24030),
        "该角色已死亡，无法使用生命骰。",
    )


# =========================================================================
# .短休
# =========================================================================


@pytest.mark.asyncio
async def test_short_rest_restores_features_and_pact(app: App):
    from nonebot_plugin_dnddicer.commands.hp import short_rest_matcher

    await _record(app, _CARD_CAST)
    await _expect(
        app, short_rest_matcher, _event(".短休"),
        "洛恩进行了一次短休\n"
        "恢复能力：奥术回想 0/1 → 1/1\n"
        "恢复法术位：契约魔法（3环） 0/2 → 2/2\n"
        "可用生命骰3颗，需要回血请用 .生命骰 N",
    )
    # 第二次：能力与契约位都满了
    await _expect(
        app, short_rest_matcher, _event(".短休"),
        "洛恩进行了一次短休\n"
        "没有可自动恢复的能力或契约魔法法术位\n"
        "可用生命骰3颗，需要回血请用 .生命骰 N",
    )


@pytest.mark.asyncio
async def test_short_rest_mention_and_dice_states(app: App):
    from nonebot_plugin_dnddicer.commands.hp import short_rest_matcher

    await _record(app, _CARD_CAST, user_id=24040)
    await _expect(
        app, short_rest_matcher,
        _mention_event(".短休 ", 24040, user_id=24000),
        "洛恩进行了一次短休\n"
        "恢复能力：奥术回想 0/1 → 1/1\n"
        "恢复法术位：契约魔法（3环） 0/2 → 2/2\n"
        "可用生命骰3颗，需要回血请用 .生命骰 N",
    )

    # 生命骰用尽
    card_empty = (
        "$姓名$ test\n$等级$ 5\n$生命值$ 5/30\n"
        "$生命骰$ 0/3 D8\n$属性$ 10/10/14/10/10/10"
    )
    await _record(app, card_empty, user_id=24041)
    await _expect(
        app, short_rest_matcher, _event(".短休", user_id=24041),
        "test进行了一次短休\n"
        "没有可自动恢复的能力或契约魔法法术位\n"
        "生命骰已用尽（0/3），无法用 .生命骰 回血",
    )

    # 未记录生命骰
    card_no_dice = (
        "$姓名$ test\n$等级$ 5\n$生命值$ 5/30\n"
        "$属性$ 10/10/14/10/10/10"
    )
    await _record(app, card_no_dice, user_id=24042)
    await _expect(
        app, short_rest_matcher, _event(".短休", user_id=24042),
        "test进行了一次短休\n"
        "没有可自动恢复的能力或契约魔法法术位\n"
        "未记录生命骰，无法用 .生命骰 回血",
    )


@pytest.mark.asyncio
async def test_short_rest_guards(app: App):
    from nonebot_plugin_dnddicer.commands.hp import short_rest_matcher

    card = (
        "$姓名$ test\n$等级$ 5\n$生命值$ 0/30\n"
        "$生命骰$ 2/2 D8\n$属性$ 10/10/14/10/10/10"
    )
    await _record(app, card, user_id=24050)
    await _expect(
        app, short_rest_matcher, _event(".短休", user_id=24050),
        "HP 为 0，无法进行短休（请先治疗或稳定）。",
    )


# =========================================================================
# .长休 扩展
# =========================================================================


@pytest.mark.asyncio
async def test_long_rest_restores_features_slots_and_hint(app: App):
    from nonebot_plugin_dnddicer.commands.hp import long_rest_matcher

    await _record(app, _CARD_CAST)
    await _expect(
        app, long_rest_matcher, _event(".长休"),
        "洛恩进行了一次长休\n"
        "生命值回复至上限(30)\n"
        "回复1个生命骰, 当前拥有4/4个D6生命骰\n"
        "恢复能力：圣疗 0/25 → 25/25\n"
        "恢复法术位：1环 0/2 → 2/2；2环 1/3 → 3/3；"
        "契约魔法（3环） 0/2 → 2/2\n"
        "可重新准备法术（.法术 准备 <名称>）。",
    )
    # 长休不改短休类能力（奥术回想仍是 0/1）
    from nonebot_plugin_dnddicer.commands.feature import ability_matcher

    await _expect(
        app, ability_matcher, _event(".能力 奥术回想"),
        "奥术回想：0/1（短休回满）",
    )


@pytest.mark.asyncio
async def test_long_rest_prepare_hint_depends_on_class(app: App):
    """准备提示只给准备型施法职业：2014 法师提示、2014 吟游诗人不提示。"""
    from nonebot_plugin_dnddicer.commands.hp import long_rest_matcher

    group_wizard, group_bard = 99130, 99131
    await _set_rules_version(group_wizard, "2014")
    await _set_rules_version(group_bard, "2014")
    card_template = (
        "$姓名$ test\n$职业$ {char_class}\n$等级$ 5\n"
        "$生命值$ 10/30\n$生命骰$ 2/2 D8\n"
        "$属性$ 10/10/14/10/10/14\n"
        "$法术$ 火球术:3*\n$法术位$ 3:1/1"
    )
    base_text = (
        "test进行了一次长休\n"
        "生命值回复至上限(30)\n"
        "回复0个生命骰, 当前拥有2/2个D8生命骰"
    )
    await _record(
        app, card_template.format(char_class="法师"),
        user_id=24070, group_id=group_wizard,
    )
    await _expect(
        app, long_rest_matcher,
        _event(".长休", user_id=24070, group_id=group_wizard),
        base_text + "\n可重新准备法术（.法术 准备 <名称>）。",
    )
    await _record(
        app, card_template.format(char_class="吟游诗人"),
        user_id=24071, group_id=group_bard,
    )
    await _expect(
        app, long_rest_matcher,
        _event(".长休", user_id=24071, group_id=group_bard),
        base_text,
    )


@pytest.mark.asyncio
async def test_long_rest_without_spells_has_no_hint(app: App):
    from nonebot_plugin_dnddicer.commands.hp import long_rest_matcher

    card = (
        "$姓名$ test\n$等级$ 5\n$生命值$ 10/30\n"
        "$生命骰$ 2/4 D8\n$属性$ 10/10/14/10/10/10"
    )
    await _record(app, card, user_id=24060)
    await _expect(
        app, long_rest_matcher, _event(".长休", user_id=24060),
        "test进行了一次长休\n"
        "生命值回复至上限(30)\n"
        "回复2个生命骰, 当前拥有4/4个D8生命骰",
    )
