""".施法 / .cast 的 nonebug 测试（2026-10-20 批③）。

覆盖：卡面环阶默认施法、绝对/相对升环、纯环阶、戏法、契约位兜底、
未准备提醒的版本/职业/开关三档判定、环位不足与写法错误；零网络。
"""

import nonebot
import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11

_GROUP = 87654360

_CARD_WIZARD = "\n".join([
    "$姓名$ 洛恩",
    "$职业$ 法师",
    "$等级$ 5",
    "$生命值$ 37/37",
    "$生命骰$ 5/5 D6",
    "$属性$ 8/15/16/18/10/8",
    "$武器$ 火焰箭x,2d10火焰",
    "$法术$ 施法属性:智力; 火球术:3*; 闪电束:3; 魔法飞弹:1*; 火焰箭:0",
    "$法术位$ 1:2/2; 2:3/3; 3:2/2",
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
    for name in ("characters.json", "group_config.json", "spell_settings.json"):
        path = get_data_file(name)
        if path.exists():
            path.write_text("{}", encoding="utf-8")
    yield


def _event(text: str, user_id: int = 25001, group_id: int = _GROUP):
    return fake_group_message_event_v11(
        message=Message(text), group_id=group_id, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _record(app: App, card: str, user_id: int = 25001, group_id: int = _GROUP):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(
        app, char_matcher,
        _event(f".角色卡记录\n{card}", user_id=user_id, group_id=group_id),
        "角色卡已设置",
    )


async def _set_rules_version(group_id: int, version: str) -> None:
    from nonebot_plugin_dnddicer.character import rules
    from nonebot_plugin_dnddicer.data.group_config import set_group_config_field

    await set_group_config_field(group_id, rules.RULES_VERSION_FIELD, version)


# =========================================================================
# 基本施法流程
# =========================================================================


@pytest.mark.asyncio
async def test_cast_default_absolute_relative_and_level_only(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app, _CARD_WIZARD)
    # 默认环阶：火球术 3 环（已准备，无提醒）
    await _expect(
        app, cast_matcher, _event(".施法 火球术"),
        "洛恩施展了「火球术」（3环）\n"
        "消耗3环法术位：2/2 → 1/2",
    )
    # 未准备：照常消耗，末尾提醒
    await _expect(
        app, cast_matcher, _event(".施法 闪电束"),
        "洛恩施展了「闪电束」（3环）\n"
        "消耗3环法术位：1/2 → 0/2\n"
        "（未标记为已准备，如需标记：.法术 准备 闪电束）",
    )
    # 绝对升环：魔法飞弹（1 环）用 2 环位
    await _expect(
        app, cast_matcher, _event(".施法 魔法飞弹2"),
        "洛恩施展了「魔法飞弹」（2环）\n"
        "消耗2环法术位：3/3 → 2/3",
    )
    # 相对升环：+1 → 2 环
    await _expect(
        app, cast_matcher, _event(".施法 魔法飞弹+1"),
        "洛恩施展了「魔法飞弹」（2环）\n"
        "消耗2环法术位：2/3 → 1/3",
    )
    # 纯环阶
    await _expect(
        app, cast_matcher, _event(".施法 2"),
        "洛恩消耗了1个2环法术位：1/3 → 0/3",
    )
    # 3 环位已用尽
    await _expect(
        app, cast_matcher, _event(".施法 3"),
        "没有可用的3环法术位（当前可用：1环 2/2）。",
    )


@pytest.mark.asyncio
async def test_cast_cantrip_and_weapon_hint(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app, _CARD_WIZARD)
    await _expect(
        app, cast_matcher, _event(".施法 火焰箭"),
        "洛恩施展了「火焰箭」（戏法）\n"
        "戏法不消耗法术位。\n"
        "可用 .火焰箭伤害 掷伤害。",
    )
    # 写 0 环等价于戏法本体
    await _expect(
        app, cast_matcher, _event(".施法 火焰箭0"),
        "洛恩施展了「火焰箭」（戏法）\n"
        "戏法不消耗法术位。\n"
        "可用 .火焰箭伤害 掷伤害。",
    )


@pytest.mark.asyncio
async def test_cast_alias_fuzzy_and_fullwidth(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app, _CARD_WIZARD)
    # .cast 别名 + 模糊命中
    await _expect(
        app, cast_matcher, _event(".cast 火球"),
        "洛恩施展了「火球术」（3环）\n"
        "消耗3环法术位：2/2 → 1/2",
    )
    # 全角数字
    await _expect(
        app, cast_matcher, _event(".施法 魔法飞弹２"),
        "洛恩施展了「魔法飞弹」（2环）\n"
        "消耗2环法术位：3/3 → 2/3",
    )


@pytest.mark.asyncio
async def test_cast_contract_slot_fallback(app: App):
    """魔契师：没有普通位时用契约位（低环法术按契约位环阶施放）。"""
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    card = "\n".join([
        "$姓名$ 魔契师",
        "$职业$ 魔契师",
        "$等级$ 5",
        "$生命值$ 30/30",
        "$生命骰$ 5/5 D8",
        "$属性$ 10/10/14/10/10/16",
        "$法术$ 施法属性:魅力; 魔法飞弹:1*; 火球术:3",
        "$法术位$ 契约3:1/1",
    ])
    await _record(app, card)
    await _expect(
        app, cast_matcher, _event(".施法 魔法飞弹"),
        "魔契师施展了「魔法飞弹」（3环）\n"
        "消耗契约魔法（3环）法术位：1/1 → 0/1",
    )
    await _expect(
        app, cast_matcher, _event(".施法 3"),
        "没有可用的3环法术位（当前可用：无）。",
    )
    await _expect(
        app, cast_matcher, _event(".施法 4"),
        "没有可用的4环法术位（当前可用：无）。",
    )


# =========================================================================
# 未准备提醒的判定
# =========================================================================


@pytest.mark.asyncio
async def test_prepare_reminder_2024_wizard_and_switch(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher, spell_matcher

    await _record(app, _CARD_WIZARD)
    await _expect(
        app, cast_matcher, _event(".施法 闪电束"),
        "洛恩施展了「闪电束」（3环）\n"
        "消耗3环法术位：2/2 → 1/2\n"
        "（未标记为已准备，如需标记：.法术 准备 闪电束）",
    )
    # 关闭提醒后同一法术不再附句
    await _expect(
        app, spell_matcher, _event(".法术 提醒 off"),
        "已关闭本处的施法未准备提醒。",
    )
    await _expect(
        app, cast_matcher, _event(".施法 闪电束"),
        "洛恩施展了「闪电束」（3环）\n"
        "消耗3环法术位：1/2 → 0/2",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "group_id, version, char_class, expected_hint",
    [
        (99121, "2014", "法师", True),
        (99122, "2014", "吟游诗人", False),
        (99123, "2014", "游荡者", False),
        (99124, "2024", "吟游诗人", True),
        (99125, "2024", "游荡者", False),
    ],
)
async def test_prepare_reminder_version_and_class(
    app: App, group_id: int, version: str, char_class: str, expected_hint: bool
):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _set_rules_version(group_id, version)
    card = "\n".join([
        "$姓名$ test",
        f"$职业$ {char_class}",
        "$等级$ 5",
        "$生命值$ 30/30",
        "$属性$ 10/10/14/10/10/14",
        "$法术$ 闪电束:3",
        "$法术位$ 3:1/1",
    ])
    await _record(app, card, user_id=25020, group_id=group_id)
    expected = "test施展了「闪电束」（3环）\n消耗3环法术位：1/1 → 0/1"
    if expected_hint:
        expected += "\n（未标记为已准备，如需标记：.法术 准备 闪电束）"
    await _expect(
        app, cast_matcher,
        _event(".施法 闪电束", user_id=25020, group_id=group_id),
        expected,
    )


# =========================================================================
# 写法错误与边界
# =========================================================================


@pytest.mark.asyncio
async def test_cast_errors(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app, _CARD_WIZARD)
    await _expect(app, cast_matcher, _event(".施法"), "用法：.施法 <法术名>[N环|+N环]；或 .施法 <环阶>")
    await _expect(
        app, cast_matcher, _event(".施法 不存在"),
        "未录入该法术「不存在」，可用 .设置法术 不存在:<环阶> 录入，"
        "或直接 .施法 <环阶>",
    )
    await _expect(
        app, cast_matcher, _event(".施法 火"),
        "名称不明确「火」：候选 火球术/火焰箭（请写更完整的名称）",
    )
    await _expect(
        app, cast_matcher, _event(".施法 火球术2"),
        "「火球术」最低为 3环，不能用 2环施展。",
    )
    await _expect(
        app, cast_matcher, _event(".施法 火球术10"),
        "法术位环阶需在 1~9 环之间。",
    )
    await _expect(
        app, cast_matcher, _event(".施法 火球术+0"),
        "升环数至少为 1。",
    )
    await _expect(
        app, cast_matcher, _event(".施法 火球术+7"),
        "法术位环阶需在 1~9 环之间。",
    )
    await _expect(
        app, cast_matcher, _event(".施法 火焰箭2"),
        "「火焰箭」是戏法，不能升环施法。",
    )
    await _expect(
        app, cast_matcher, _event(".施法 0"), "法术位环阶需在 1~9 环之间。"
    )
    await _expect(
        app, cast_matcher, _event(".施法 10"), "法术位环阶需在 1~9 环之间。"
    )
    await _expect(
        app, cast_matcher, _event(".施法 +1"),
        "用法：.施法 <法术名>[N环|+N环]；或 .施法 <环阶>",
    )
    # 环位不足：列出当前可用
    await _expect(
        app, cast_matcher, _event(".施法 火球术4"),
        "没有可用的4环法术位（当前可用：1环 2/2、2环 3/3、3环 2/2）。",
    )


@pytest.mark.asyncio
async def test_cast_requires_character(app: App):
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _expect(app, cast_matcher, _event(".施法 火球术"), "找不到角色卡")


@pytest.mark.asyncio
async def test_cast_makes_no_network_call(app: App, monkeypatch):
    """施法全程本地结算：任何网络调用都视为失败。"""
    import urllib.request

    def _fail(*args, **kwargs):
        raise AssertionError("施法流程不应发起网络请求")

    monkeypatch.setattr(urllib.request, "urlopen", _fail)
    from nonebot_plugin_dnddicer.commands.spell import cast_matcher

    await _record(app, _CARD_WIZARD)
    await _expect(
        app, cast_matcher, _event(".施法 火球术"),
        "洛恩施展了「火球术」（3环）\n"
        "消耗3环法术位：2/2 → 1/2",
    )
