"""``.钱币`` 命令测试（2026-10-24）：查看 / 紧凑收支 / 破币换算 / 原子拒绝。"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11

_GROUP = 87654382

_CARD = "\n".join([
    "$姓名$ 测试",
    "$等级$ 5",
    "$属性$ 10/10/10/10/10/10",
    "$钱币$ CP:0; SP:0; EP:0; GP:0; PP:0",
])


@pytest.fixture(autouse=True)
def _clear_store():
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file

    _chars._cache = None
    path = get_data_file("cards.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")
    yield


def _event(text: str, user_id: int = 26001):
    return fake_group_message_event_v11(
        message=Message(text), group_id=_GROUP, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _record(app: App, coins: str = "$钱币$ CP:0; SP:0; EP:0; GP:0; PP:0"):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    card = "\n".join([
        "$姓名$ 测试",
        "$等级$ 5",
        "$属性$ 10/10/10/10/10/10",
        coins,
    ])
    await _expect(
        app, char_matcher, _event(f".角色卡新建 测试卡\n{card}"),
        "已新建角色卡「测试卡」并绑定到本群。",
    )


async def _coins():
    from nonebot_plugin_dnddicer.data.characters import get_character

    character = await get_character(_GROUP, 26001)
    return character.coins


@pytest.mark.asyncio
async def test_coins_view_and_compact_flow(app: App):
    from nonebot_plugin_dnddicer.commands.coins import coins_matcher

    await _record(app)
    await _expect(
        app, coins_matcher, _event(".钱币"),
        "钱币：CP 0；SP 0；EP 0；GP 0；PP 0",
    )
    await _expect(
        app, coins_matcher, _event(".钱币 +20GP-5SP"),
        "钱币：+20GP，-5SP\n"
        "SP 不足：拆 1 GP → +10 SP，扣 5 SP，余 5 SP\n"
        "GP:0 → 19；SP:0 → 5；CP / EP / PP 不变",
    )
    assert await _coins() == {"CP": 0, "SP": 5, "EP": 0, "GP": 19, "PP": 0}
    # 同币种充足：直接扣，不换算
    await _expect(
        app, coins_matcher, _event(".钱币 -1GP"),
        "钱币：-1GP\n"
        "GP:19 → 18；CP / SP / EP / PP 不变",
    )
    # 大小写不敏感、操作间允许空白
    await _expect(
        app, coins_matcher, _event(".钱币 +20gp -5sp"),
        "钱币：+20GP，-5SP\n"
        "GP:18 → 38；SP:5 → 0；CP / EP / PP 不变",
    )
    assert await _coins() == {"CP": 0, "SP": 0, "EP": 0, "GP": 38, "PP": 0}


@pytest.mark.asyncio
async def test_coins_addition_does_not_convert(app: App):
    from nonebot_plugin_dnddicer.commands.coins import coins_matcher

    await _record(app, "$钱币$ SP:15")
    await _expect(
        app, coins_matcher, _event(".钱币 +20GP"),
        "钱币：+20GP\n"
        "GP:0 → 20；CP / SP / EP / PP 不变",
    )
    assert (await _coins()) == {"SP": 15, "GP": 20}


@pytest.mark.asyncio
async def test_coins_lower_denomination_conversion(app: App):
    from nonebot_plugin_dnddicer.commands.coins import coins_matcher

    await _record(app, "$钱币$ SP:15")
    await _expect(
        app, coins_matcher, _event(".钱币 -1GP"),
        "钱币：-1GP\n"
        "GP 不足：用 10 SP 折算 1 GP，扣 10 SP，余 5 SP\n"
        "GP:0 → 0；SP:15 → 5；CP / EP / PP 不变",
    )
    assert (await _coins()) == {"SP": 5}


@pytest.mark.asyncio
async def test_coins_ep_and_cp_boundaries(app: App):
    from nonebot_plugin_dnddicer.commands.coins import coins_matcher

    await _record(app, "$钱币$ EP:1")
    await _expect(
        app, coins_matcher, _event(".钱币 -2SP"),
        "钱币：-2SP\n"
        "SP 不足：拆 1 EP → +5 SP，扣 2 SP，余 3 SP\n"
        "SP:0 → 3；EP:1 → 0；CP / GP / PP 不变",
    )
    assert (await _coins()) == {"SP": 3, "EP": 0}

    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file

    _chars._cache = None
    get_data_file("cards.json").write_text("{}", encoding="utf-8")
    await _record(app, "$钱币$ CP:5")
    await _expect(
        app, coins_matcher, _event(".钱币 -1SP"),
        "钱币不足：扣 1SP 需要 10 CP，现有总价值 5 CP（本次未做任何改动）",
    )
    assert (await _coins()) == {"CP": 5}

    _chars._cache = None
    get_data_file("cards.json").write_text("{}", encoding="utf-8")
    await _record(app, "$钱币$ CP:15")
    await _expect(
        app, coins_matcher, _event(".钱币 -1SP"),
        "钱币：-1SP\n"
        "SP 不足：用 10 CP 折算 1 SP，扣 10 CP，余 5 CP\n"
        "SP:0 → 0；CP:15 → 5；EP / GP / PP 不变",
    )
    assert (await _coins()) == {"CP": 5}


@pytest.mark.asyncio
async def test_coins_atomic_reject(app: App):
    from nonebot_plugin_dnddicer.commands.coins import coins_matcher

    await _record(app, "$钱币$ GP:5")
    await _expect(
        app, coins_matcher, _event(".钱币 +5GP-100PP"),
        "钱币不足：扣 100PP 需要 100000 CP，现有总价值 500 CP"
        "（本次未做任何改动）",
    )
    assert (await _coins()) == {"GP": 5}


@pytest.mark.asyncio
async def test_coins_invalid_input(app: App):
    from nonebot_plugin_dnddicer.commands.coins import coins_matcher

    await _record(app)
    await _expect(
        app, coins_matcher, _event(".钱币 20GP"),
        "钱币写法无效：20GP（格式：+20GP-5SP，币种 CP/SP/EP/GP/PP）",
    )
    await _expect(
        app, coins_matcher, _event(".钱币 +0GP"),
        "钱币数量必须为正整数：+0GP",
    )
    await _expect(
        app, coins_matcher, _event(".钱币 +5GP随便"),
        "钱币写法无效：+5GP随便（格式：+20GP-5SP，币种 CP/SP/EP/GP/PP）",
    )


@pytest.mark.asyncio
async def test_coins_missing_denominations_treated_as_zero(app: App):
    from nonebot_plugin_dnddicer.commands.coins import coins_matcher

    await _record(app, "$钱币$ GP:3")
    await _expect(
        app, coins_matcher, _event(".钱币"),
        "钱币：CP 0；SP 0；EP 0；GP 3；PP 0",
    )
    await _expect(
        app, coins_matcher, _event(".钱币 +2SP"),
        "钱币：+2SP\n"
        "SP:0 → 2；CP / EP / GP / PP 不变",
    )
    assert (await _coins()) == {"GP": 3, "SP": 2}


@pytest.mark.asyncio
async def test_coins_requires_card(app: App):
    from nonebot_plugin_dnddicer.commands.coins import coins_matcher

    await _expect(
        app, coins_matcher, _event(".钱币"),
        "你还没有在本群绑定角色卡，可发 .角色卡列表 查看卡库并绑定",
    )
