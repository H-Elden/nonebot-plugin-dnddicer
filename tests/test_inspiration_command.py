"""``.激励`` 命令测试（2026-10-24）：状态 / 获得 / 消耗 / 按 @ 与角色名转赠。"""

import nonebot
import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from fake_event import fake_group_message_event_v11

_GROUP = 87654380

_CARD = "\n".join([
    "$姓名$ 测试",
    "$等级$ 5",
    "$属性$ 10/10/10/10/10/10",
    "$进度$ 经验:6500",
])


@pytest.fixture(autouse=True)
def _clear_store():
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


def _event(text: str, user_id: int = 24001):
    return fake_group_message_event_v11(
        message=Message(text), group_id=_GROUP, user_id=user_id
    )


def _mention_event(prefix: str, at_uid: int, suffix: str = "", user_id: int = 24001):
    return fake_group_message_event_v11(
        message=Message(prefix) + MessageSegment.at(at_uid) + suffix,
        group_id=_GROUP,
        user_id=user_id,
    )


async def _expect(app: App, matcher, event, expected):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _record(app: App, user_id: int = 24001, name: str = "测试"):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    card = _CARD.replace("$姓名$ 测试", f"$姓名$ {name}")
    await _expect(
        app, char_matcher,
        _event(f".角色卡新建 测试卡\n{card}", user_id),
        "已新建角色卡「测试卡」并绑定到本群。",
    )


async def _char(user_id: int = 24001):
    from nonebot_plugin_dnddicer.data.characters import get_character

    return await get_character(_GROUP, user_id)


@pytest.mark.asyncio
async def test_inspiration_state_gain_and_spend(app: App):
    from nonebot_plugin_dnddicer.commands.inspiration import inspiration_matcher

    await _record(app)
    await _expect(
        app, inspiration_matcher, _event(".激励"),
        "测试的英雄激励：未记录",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 +"),
        "测试获得了英雄激励。",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 状态"),
        "测试的英雄激励：有",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 +"),
        "测试已经有英雄激励了，不能叠加；可用 .激励 给予 目标 转赠。",
    )
    # 改激励不清掉经验
    character = await _char()
    assert character.progress == {"经验": "6500", "激励": "有"}
    await _expect(
        app, inspiration_matcher, _event(".激励 -"),
        "测试消耗了英雄激励。",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励"),
        "测试的英雄激励：无",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 -"),
        "测试当前没有英雄激励。",
    )
    # .角色卡 文本仍写「激励:」，不随称呼改名
    character = await _char()
    assert "激励:无" in character.get_char_info()
    await _expect(
        app, inspiration_matcher, _event(".激励 随便"),
        "用法：.激励 [状态|+|-|给予 目标]",
    )


@pytest.mark.asyncio
async def test_inspiration_2014_label(app: App):
    from nonebot_plugin_dnddicer.commands.inspiration import inspiration_matcher
    from nonebot_plugin_dnddicer.data.group_config import set_group_config_field

    await _record(app)
    await set_group_config_field(_GROUP, "rules_version", "5e")
    await _expect(
        app, inspiration_matcher, _event(".激励"),
        "测试的激励：未记录",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 +"),
        "测试获得了激励。",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 -"),
        "测试消耗了激励。",
    )
    # 数据键不随版本改名
    character = await _char()
    assert character.progress.get("激励") == "无"


@pytest.mark.asyncio
async def test_inspiration_give_by_name_and_mention(app: App):
    from nonebot_plugin_dnddicer.commands.inspiration import inspiration_matcher

    await _record(app)
    await _record(app, user_id=24002, name="塔莉")
    await _record(app, user_id=24003, name="塔莉娅")

    await _expect(
        app, inspiration_matcher, _event(".激励 +"),
        "测试获得了英雄激励。",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 给予 塔莉"),
        "测试将英雄激励转赠给塔莉。",
    )
    assert (await _char()).progress["激励"] == "无"
    assert (await _char(24002)).progress["激励"] == "有"

    await _expect(
        app, inspiration_matcher, _event(".激励 +"),
        "测试获得了英雄激励。",
    )
    await _expect(
        app, inspiration_matcher,
        _mention_event(".激励 给予 ", 24003),
        "测试将英雄激励转赠给塔莉娅。",
    )
    assert (await _char(24003)).progress["激励"] == "有"


@pytest.mark.asyncio
async def test_inspiration_give_errors(app: App):
    from nonebot_plugin_dnddicer.commands.inspiration import inspiration_matcher

    await _record(app)
    await _record(app, user_id=24002, name="塔莉")
    await _record(app, user_id=24003, name="塔莉娅")

    # 没有激励不能转赠
    await _expect(
        app, inspiration_matcher, _event(".激励 给予 塔莉"),
        "你当前没有英雄激励，无法转赠。",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 +"),
        "测试获得了英雄激励。",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 给予 测试"),
        "不能把英雄激励给予自己。",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 给予 塔"),
        "目标名称不明确「塔」：候选 塔莉/塔莉娅（请写完整角色名或 @玩家）",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 给予 查无此人"),
        "找不到查无此人的角色卡",
    )
    await _expect(
        app, inspiration_matcher,
        _mention_event(".激励 给予 ", 39990),
        Message(MessageSegment.at("39990")) + " 未在本群绑定角色卡",
    )
    # 目标已有激励
    await _expect(
        app, inspiration_matcher, _event(".激励 给予 塔莉"),
        "测试将英雄激励转赠给塔莉。",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 +"),
        "测试获得了英雄激励。",
    )
    await _expect(
        app, inspiration_matcher, _event(".激励 给予 塔莉"),
        "塔莉已经有英雄激励，无法接收。",
    )


@pytest.mark.asyncio
async def test_inspiration_requires_card(app: App):
    from nonebot_plugin_dnddicer.commands.inspiration import inspiration_matcher

    await _expect(
        app, inspiration_matcher, _event(".激励"),
        "你还没有在本群绑定角色卡，可发 .角色卡列表 查看卡库并绑定",
    )
