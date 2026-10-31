"""``.物品`` 命令测试（2026-11-01）：查看 / 增加 / 扣减与边界。"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

_GROUP = 87654383
_USER = 26002

_CARD = "\n".join([
    "$姓名$ 测试",
    "$等级$ 5",
    "$属性$ 10/10/10/10/10/10",
    "$武器$ 短剑+5|1d6+3穿刺",
    "$物品$ 治疗药水x2; 箭矢x20; 巨斧",
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


def _event(text: str, user_id: int = _USER):
    return fake_group_message_event_v11(
        message=Message(text), group_id=_GROUP, user_id=user_id
    )


def _private(text: str, user_id: int = _USER):
    return fake_private_message_event_v11(
        message=Message(text), user_id=user_id
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _record(
    app: App,
    card: str = _CARD,
    user_id: int = _USER,
    card_name: str = "测试卡",
    expected: str | None = None,
):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(
        app, char_matcher, _event(f".角色卡新建 {card_name}\n{card}", user_id),
        expected or f"已新建角色卡「{card_name}」并绑定到本群。",
    )


async def _items(user_id: int = _USER):
    from nonebot_plugin_dnddicer.data.characters import get_character

    character = await get_character(_GROUP, user_id)
    return character.items


@pytest.mark.asyncio
async def test_items_view_add_remove_delete(app: App):
    from nonebot_plugin_dnddicer.commands.items import items_matcher

    await _record(app)
    await _expect(
        app, items_matcher, _event(".物品"),
        "当前物品（3 项）：\n1. 治疗药水 ×2\n2. 箭矢 ×20\n3. 巨斧",
    )
    await _expect(
        app, items_matcher, _event(".物品 箭矢+3"),
        "物品「箭矢」：20 → 23",
    )
    await _expect(
        app, items_matcher, _event(".物品 解毒药+2"),
        "已添加物品「解毒药」×2。",
    )
    await _expect(
        app, items_matcher, _event(".物品 火把+"),
        "已添加物品「火把」×1。",
    )
    await _expect(
        app, items_matcher, _event(".物品"),
        "当前物品（5 项）：\n1. 治疗药水 ×2\n2. 箭矢 ×23"
        "\n3. 巨斧\n4. 解毒药 ×2\n5. 火把",
    )
    await _expect(
        app, items_matcher, _event(".物品 箭矢-3"),
        "物品「箭矢」：23 → 20",
    )
    await _expect(
        app, items_matcher, _event(".物品 治疗药水-2"),
        "物品「治疗药水」：2 → 0，已从背包移除。",
    )
    await _expect(
        app, items_matcher, _event(".物品 巨斧 -"),
        "物品「巨斧」：1 → 0，已从背包移除。",
    )
    await _expect(
        app, items_matcher, _event(".物品"),
        "当前物品（3 项）：\n1. 箭矢 ×20\n2. 解毒药 ×2\n3. 火把",
    )
    assert await _items() == ["箭矢x20", "解毒药x2", "火把x1"]


@pytest.mark.asyncio
async def test_items_errors_keep_card_unchanged(app: App):
    from nonebot_plugin_dnddicer.commands.items import items_matcher

    await _record(app)
    before = await _items()
    await _expect(
        app, items_matcher, _event(".物品 箭矢-99"),
        "物品「箭矢」只有 20 个，无法扣减 99 个。",
    )
    await _expect(
        app, items_matcher, _event(".物品 短剑-1"),
        "背包里没有物品「短剑」。",
    )
    await _expect(
        app, items_matcher, _event(".物品 箭矢"),
        "物品写法无效（写成 名称+数量、名称-数量 或 名称-；例：.物品 箭矢-3）",
    )
    await _expect(
        app, items_matcher, _event(".物品 箭矢;+1"),
        "物品名称不能包含符号「;」: 箭矢;",
    )
    assert await _items() == before


@pytest.mark.asyncio
async def test_items_fuzzy_match_and_duplicate(app: App):
    from nonebot_plugin_dnddicer.commands.items import items_matcher

    card = _CARD.replace(
        "$物品$ 治疗药水x2; 箭矢x20; 巨斧",
        "$物品$ 治疗药水x2; 强效治疗药水x1; 箭矢x20",
    )
    await _record(app, card=card)
    await _expect(
        app, items_matcher, _event(".物品 药水-1"),
        "物品「药水」匹配到多项：治疗药水 ×2、强效治疗药水。"
        "请写得更完整一些。",
    )
    # 精确命中优先：全名不会被子串歧义影响
    await _expect(
        app, items_matcher, _event(".物品 治疗药水-1"),
        "物品「治疗药水」：2 → 1",
    )

    duplicate_card = _CARD.replace(
        "$物品$ 治疗药水x2; 箭矢x20; 巨斧",
        "$物品$ 箭矢x2; 箭矢x3",
    )
    await _record(
        app, card=duplicate_card, card_name="重复卡",
        expected="已新建角色卡「重复卡」并绑定到本群，原绑定「测试卡」已解除。",
    )
    await _expect(
        app, items_matcher, _event(".物品 箭矢-1"),
        "物品「箭矢」在卡上出现了多次，请先用 .角色卡修改 修正。",
    )


@pytest.mark.asyncio
async def test_items_fullwidth_and_name_with_sign(app: App):
    from nonebot_plugin_dnddicer.commands.items import items_matcher

    card = _CARD.replace(
        "$物品$ 治疗药水x2; 箭矢x20; 巨斧",
        "$物品$ 箭矢x20; 长弓+1x2",
    )
    await _record(app, card=card)
    await _expect(
        app, items_matcher, _event(".物品 箭矢－３"),
        "物品「箭矢」：20 → 17",
    )
    await _expect(
        app, items_matcher, _event(".物品 长弓+1-1"),
        "物品「长弓+1」：2 → 1",
    )
    await _expect(
        app, items_matcher, _event(".物品 长弓+1-"),
        "物品「长弓+1」：1 → 0，已从背包移除。",
    )


@pytest.mark.asyncio
async def test_items_limits(app: App):
    from nonebot_plugin_dnddicer.commands.items import items_matcher

    full = "; ".join(f"物品{i}x1" for i in range(50))
    card = _CARD.replace("$物品$ 治疗药水x2; 箭矢x20; 巨斧", f"$物品$ {full}")
    await _record(app, card=card, card_name="满卡")
    await _expect(
        app, items_matcher, _event(".物品 新物品+1"),
        "物品最多 50 项，无法再添加。",
    )

    max_card = _CARD.replace(
        "$物品$ 治疗药水x2; 箭矢x20; 巨斧", "$物品$ 箭矢x999"
    )
    await _record(
        app, card=max_card, card_name="上限卡",
        expected="已新建角色卡「上限卡」并绑定到本群，原绑定「满卡」已解除。",
    )
    await _expect(
        app, items_matcher, _event(".物品 箭矢+1"),
        "物品「箭矢」数量不能超过 999 个。",
    )


@pytest.mark.asyncio
async def test_items_requires_bound_card_and_group(app: App):
    from nonebot_plugin_dnddicer.commands.items import items_matcher

    await _expect(
        app, items_matcher, _event(".物品"),
        "你还没有在本群绑定角色卡，可发 .角色卡列表 查看卡库并绑定",
    )
    await _expect(
        app, items_matcher, _private(".物品"),
        "该指令仅在群聊中可用。",
    )
