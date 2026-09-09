""".br/.回合/.轮次/.ed 战斗轮 nonebug 测试。

战斗状态（InitList 含 round/turn 指针）以 data/initiative.py 直接播种，
命令消息用 nonebug matcher 驱动，避免 .ri 掷骰噪音。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from fake_event import fake_group_message_event_v11


@pytest.fixture(autouse=True)
def _clear_store():
    """每个用例前清空先攻表数据（缓存 + JSON）。"""
    from nonebot_plugin_dnddicer.data import get_data_file
    from nonebot_plugin_dnddicer.data import initiative as _init

    _init._cache = None
    path = get_data_file("initiative.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")
    yield


def _event(group_id: int, text: str, user_id: int = 10001):
    return fake_group_message_event_v11(
        message=Message(text), group_id=group_id, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _seed(group_id: int, pairs: list[tuple[str, int]], owner: str = ""):
    """向某群先攻表播种实体（值降序自动排序；全部无主 NPC 或统一 owner）。"""
    from nonebot_plugin_dnddicer.data.initiative import save_init_list
    from nonebot_plugin_dnddicer.initiative.models import InitList

    init = InitList(group_id=str(group_id))
    for name, val in pairs:
        init.add_entity(name, owner if owner else "", val)
    await save_init_list(init)


# =========================================================================
# .br 与空表提示
# =========================================================================


@pytest.mark.asyncio
async def test_br_creates_and_clears(app: App):
    """.br 新建战斗轮；随后 .回合/.ed 报空表提示。"""
    from nonebot_plugin_dnddicer.commands.battle import (
        br_matcher, ed_matcher, turn_matcher,
    )

    await _expect(
        app, br_matcher, _event(110001, ".br"),
        "已创建新战斗轮。清除先攻表、当前回合。",
    )
    await _expect(
        app, turn_matcher, _event(110001, ".回合"),
        "目前先攻列表为空，故不存在回合与轮次。",
    )
    await _expect(
        app, ed_matcher, _event(110001, ".ed"),
        "目前先攻列表为空，故不存在回合与轮次。",
    )


@pytest.mark.asyncio
async def test_br_resets_existing_table(app: App):
    """.br 清空既有先攻表与轮次指针。"""
    from nonebot_plugin_dnddicer.commands.battle import br_matcher
    from nonebot_plugin_dnddicer.data.initiative import get_init_list

    await _seed(110002, [("兽人", 20), ("哥布林", 10)])
    await _expect(
        app, br_matcher, _event(110002, ".战斗轮"),
        "已创建新战斗轮。清除先攻表、当前回合。",
    )
    assert await get_init_list(110002) is None


# =========================================================================
# 查看
# =========================================================================


@pytest.mark.asyncio
async def test_turn_query(app: App):
    """.回合 无参数 → 当前轮/回合/行动者。"""
    from nonebot_plugin_dnddicer.commands.battle import turn_matcher

    await _seed(110003, [("兽人", 20), ("哥布林", 10)])
    await _expect(
        app, turn_matcher, _event(110003, ".回合"),
        "现在是第1轮第1回合，兽人的回合。",
    )


# =========================================================================
# .回合/.轮次 数值与名字跳转
# =========================================================================


@pytest.mark.asyncio
async def test_turn_set_and_wrap(app: App):
    """.回合=3 跳转；.回合+1 在轮尾溢出自动进位。"""
    from nonebot_plugin_dnddicer.commands.battle import turn_matcher

    await _seed(110004, [("兽人", 30), ("地精", 20), ("哥布林", 10)])
    await _expect(
        app, turn_matcher, _event(110004, ".回合=3"),
        "现在是哥布林的回合。",
    )
    # 第 3 回合 +1 → 越界进位到第 2 轮第 1 回合
    await _expect(
        app, turn_matcher, _event(110004, ".回合+1"),
        "新的一轮，现在是第2轮。\n现在是兽人的回合。",
    )


@pytest.mark.asyncio
async def test_turn_name_jump(app: App):
    """.回合 哥布林（模糊）→ 跳到对应回合。"""
    from nonebot_plugin_dnddicer.commands.battle import turn_matcher

    await _seed(110005, [("兽人", 30), ("地精", 20), ("哥布林", 10)])
    await _expect(
        app, turn_matcher, _event(110005, ".回合 哥布林"),
        "现在是哥布林的回合。",
    )


@pytest.mark.asyncio
async def test_turn_jump_errors(app: App):
    """名字无/多匹配与数值越界的报错。"""
    from nonebot_plugin_dnddicer.commands.battle import turn_matcher

    await _seed(110006, [("兽人队长", 30), ("兽人士兵", 20)])
    await _expect(
        app, turn_matcher, _event(110006, ".回合 不存在"),
        "没有找到这个回合。",
    )
    await _expect(
        app, turn_matcher, _event(110006, ".回合 兽人"),
        "找到复数回合，请换一个关键词。",
    )
    await _expect(app, turn_matcher, _event(110006, ".回合=9"), "这个数字太大了。")
    await _expect(app, turn_matcher, _event(110006, ".回合=0"), "这个数字太小了。")
    await _expect(app, turn_matcher, _event(110006, ".回合+abc"), "这不是数字。")


@pytest.mark.asyncio
async def test_round_modify(app: App):
    """.轮次+1 进位轮次并播报当前行动者；数值不变时播报完整轮/回合。"""
    from nonebot_plugin_dnddicer.commands.battle import round_matcher

    await _seed(110007, [("兽人", 30), ("哥布林", 10)])
    await _expect(
        app, round_matcher, _event(110007, ".轮次+1"),
        "现在变成第2轮了。\n现在是兽人的回合。",
    )
    await _expect(
        app, round_matcher, _event(110007, ".轮次-1"),
        "现在变成第1轮了。\n现在是兽人的回合。",
    )
    # 轮次与回合都不变 → 完整轮/回合播报
    await _expect(
        app, round_matcher, _event(110007, ".轮次 1"),
        "现在是第1轮第1回合，兽人的回合。",
    )


# =========================================================================
# .ed 结束回合
# =========================================================================


@pytest.mark.asyncio
async def test_ed_advance_and_new_round(app: App):
    """.ed 播报结束并推进；走完一轮自动进位。"""
    from nonebot_plugin_dnddicer.commands.battle import ed_matcher

    await _seed(110008, [("兽人", 20), ("哥布林", 10)])
    await _expect(
        app, ed_matcher, _event(110008, ".ed"),
        "兽人的回合结束了。\n现在是哥布林的回合。",
    )
    await _expect(
        app, ed_matcher, _event(110008, ".ed"),
        "哥布林的回合结束了。\n新的一轮，现在是第2轮。\n现在是兽人的回合。",
    )


@pytest.mark.asyncio
async def test_ed_announce_with_at_for_player(app: App):
    """.ed 轮到绑定 QQ 的玩家时输出 @ 提醒。"""
    from nonebot_plugin_dnddicer.commands.battle import ed_matcher

    await _seed(110009, [("兽人", 20), ("哥布林", 10)], owner="")
    # 玩家 30010 以自己身份加入（名称 test、绑定 owner，先攻 30 排最前）
    from nonebot_plugin_dnddicer.data.initiative import get_init_list, save_init_list
    from nonebot_plugin_dnddicer.initiative.models import InitList

    init = await get_init_list(110009)
    init.entities.append(type(init.entities[0])(name="test", owner="30010", init=30))
    init.entities = sorted(init.entities, key=lambda x: -x.init)
    init.turns_in_round = len(init.entities)
    await save_init_list(init)

    # 轮到玩家时 @；其余为无主 NPC 平铺播报
    await _expect(
        app, ed_matcher, _event(110009, ".ed", user_id=40000),
        "test的回合结束了。\n现在是兽人的回合。",
    )
    await _expect(
        app, ed_matcher, _event(110009, ".ed", user_id=40000),
        "兽人的回合结束了。\n现在是哥布林的回合。",
    )
    await _expect(
        app, ed_matcher, _event(110009, ".ed", user_id=40000),
        Message("哥布林的回合结束了。\n新的一轮，现在是第2轮。\n现在是test的回合。请玩家")
        + MessageSegment.at("30010")
        + "开始行动。",
    )


# =========================================================================
# 回合推进：.ed 之外 DM 用 .回合±n 连续推进
# =========================================================================


@pytest.mark.asyncio
async def test_turn_jump_to_player_announces_with_at(app: App):
    """.回合 跳到绑定 QQ 玩家的回合 → @ 消息段播报。"""
    from nonebot_plugin_dnddicer.commands.battle import turn_matcher
    from nonebot_plugin_dnddicer.data.initiative import get_init_list, save_init_list

    await _seed(110012, [("兽人", 20), ("哥布林", 10)])
    init = await get_init_list(110012)
    init.entities.append(type(init.entities[0])(name="test", owner="30010", init=30))
    init.entities = sorted(init.entities, key=lambda x: -x.init)
    init.turns_in_round = len(init.entities)
    await save_init_list(init)

    # 当前第 1 回合是 test（owner 30010）；跳到第 2 回合兽人（无主）无 @
    await _expect(
        app, turn_matcher, _event(110012, ".回合+1"),
        "现在是兽人的回合。",
    )
    # 跳回第 1 回合 test → @ 消息段
    await _expect(
        app, turn_matcher, _event(110012, ".回合-1"),
        Message("现在是test的回合。请玩家")
        + MessageSegment.at("30010")
        + "开始行动。",
    )


@pytest.mark.asyncio
async def test_turn_advance_multiple(app: App):
    """.回合+1 推进一位；.回合+2 跨越多位并进位轮次。"""
    from nonebot_plugin_dnddicer.commands.battle import turn_matcher

    await _seed(110010, [("兽人", 30), ("地精", 20), ("哥布林", 10)])
    await _expect(
        app, turn_matcher, _event(110010, ".回合+1"),
        "现在是地精的回合。",
    )
    await _expect(
        app, turn_matcher, _event(110010, ".回合+2"),
        "新的一轮，现在是第2轮。\n现在是兽人的回合。",
    )
