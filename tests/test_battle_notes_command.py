"""``.战斗记录`` 命令测试（2026-10-24）：查看 / 追加 / 删除 / 清空与上限。"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11

_GROUP = 87654381

_CARD = "\n".join([
    "$姓名$ 测试",
    "$等级$ 5",
    "$属性$ 10/10/10/10/10/10",
    "$武器$ 短剑+5|1d6+3穿刺",
    "$战斗记录$ 祝福术(专注,3轮); 中毒",
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


def _event(text: str, user_id: int = 25001):
    return fake_group_message_event_v11(
        message=Message(text), group_id=_GROUP, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _record(app: App, card: str = _CARD):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(
        app, char_matcher, _event(f".角色卡新建 测试卡\n{card}"),
        "已新建角色卡「测试卡」并绑定到本群。",
    )


@pytest.mark.asyncio
async def test_combat_notes_view_add_and_delete(app: App):
    from nonebot_plugin_dnddicer.commands.combat_notes import combat_notes_matcher

    await _record(app)
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录"),
        "战斗记录（2 条）：\n1. 祝福术(专注,3轮)\n2. 中毒",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 +法师护甲(8小时)"),
        "已添加 1 条战斗记录：法师护甲(8小时)（当前共 3 条）",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 +目盲; 恐慌"),
        "已添加 2 条战斗记录：目盲；恐慌（当前共 5 条）",
    )
    # 多个序号：从大到小删除，序号不位移
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 -1/4"),
        "已删除战斗记录：祝福术(专注,3轮)；目盲",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录"),
        "战斗记录（3 条）：\n1. 中毒\n2. 法师护甲(8小时)\n3. 恐慌",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 -9/2"),
        "已删除战斗记录：法师护甲(8小时)；序号无效或超出范围：9",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 清"),
        "已清空战斗记录（2 条）",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录"),
        "还没有战斗记录。可用 .战斗记录 +文本 添加（多项用 ; 分隔）",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 清"),
        "战斗记录本来就是空的",
    )


@pytest.mark.asyncio
async def test_combat_notes_limits_and_validation(app: App):
    from nonebot_plugin_dnddicer.commands.combat_notes import combat_notes_matcher

    await _record(app)
    await _expect(
        app, combat_notes_matcher, _event(f".战斗记录 +{'长' * 61}"),
        f"战斗记录每条最多 60 字：{'长' * 61}",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 +含有$符号"),
        "战斗记录不能包含 $ 符号：含有$符号",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 -99"),
        "没有删除任何记录：序号无效或超出范围 99",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 -随便"),
        "没有删除任何记录：序号无效或超出范围 随便",
    )


@pytest.mark.asyncio
async def test_combat_notes_max_count(app: App):
    from nonebot_plugin_dnddicer.commands.combat_notes import combat_notes_matcher

    notes = "; ".join(f"效果{i}" for i in range(1, 20))
    card = _CARD.replace("祝福术(专注,3轮); 中毒", notes)
    await _record(app, card=card)
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 +效果20"),
        "已添加 1 条战斗记录：效果20（当前共 20 条）",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 +效果21"),
        "战斗记录最多 20 条（当前 20 条，本次添加 1 条）",
    )
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 +甲; 乙"),
        "战斗记录最多 20 条（当前 20 条，本次添加 2 条）",
    )


@pytest.mark.asyncio
async def test_combat_notes_keeps_other_segments(app: App):
    from nonebot_plugin_dnddicer.commands.combat_notes import combat_notes_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _record(app)
    await _expect(
        app, combat_notes_matcher, _event(".战斗记录 +隐身"),
        "已添加 1 条战斗记录：隐身（当前共 3 条）",
    )
    character = await get_character(_GROUP, 25001)
    assert character.weapons[0].name == "短剑"
    assert character.combat_notes[-1] == "隐身"
    assert character.progress == {}


@pytest.mark.asyncio
async def test_combat_notes_requires_card(app: App):
    from nonebot_plugin_dnddicer.commands.combat_notes import combat_notes_matcher

    await _expect(
        app, combat_notes_matcher, _event(".战斗记录"),
        "你还没有在本群绑定角色卡，可发 .角色卡列表 查看卡库并绑定",
    )
