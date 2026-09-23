""".init/.ri/.先攻 nonebug 测试 + InitList 模型单元测试。

存储隔离：每个用例独立群号（先攻表按群隔离）；清理 characters.json 防止
角色卡名解析（resolve_self_name）受历史数据影响。掷骰用 SequenceRuntime。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from fake_event import fake_group_message_event_v11

from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_CLEAN_FILES = ("initiative.json", "characters.json")


@pytest.fixture(autouse=True)
def _clear_store():
    """每个用例前清空先攻表/角色卡数据（缓存 + JSON）。"""
    from nonebot_plugin_dnddicer.data import initiative as _init
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file

    _init._cache = None
    _chars._cache = None
    for name in _CLEAN_FILES:
        path = get_data_file(name)
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


# =========================================================================
# InitList 模型单元测试（实体列表 + 回合指针修正）
# =========================================================================


def test_model_add_sorts_desc_and_replaces_same_name():
    from nonebot_plugin_dnddicer.initiative.models import InitList

    init = InitList(group_id="1")
    init.add_entity("A", "", 15)
    init.add_entity("B", "", 20)
    init.add_entity("C", "", 15)
    assert [e.name for e in init.entities] == ["B", "A", "C"]
    assert init.turns_in_round == 3
    # 同名重掷：旧条目被替换
    init.add_entity("A", "", 30)
    assert [e.name for e in init.entities] == ["A", "B", "C"]
    assert [e.init for e in init.entities] == [30, 20, 15]


def test_model_del_entity_missing_raises():
    from nonebot_plugin_dnddicer.initiative.models import InitiativeError, InitList

    init = InitList(group_id="1")
    init.add_entity("A", "", 15)
    with pytest.raises(InitiativeError, match="不存在名称为X的条目"):
        init.del_entity("X")


def test_model_del_entity_removes_all_duplicates():
    from nonebot_plugin_dnddicer.initiative.models import InitEntity, InitList

    init = InitList(group_id="1")
    init.entities = [
        InitEntity(name="A", owner="", init=10),
        InitEntity(name="A", owner="", init=10),
    ]
    init.turns_in_round = 2
    init.del_entity("A")
    assert init.entities == []
    assert init.turns_in_round == 0


def test_model_turn_shift_on_add_and_del_during_battle():
    """战斗进行中（first_turn=False）插入/删除实体时回合指针修正。"""
    from nonebot_plugin_dnddicer.initiative.models import InitList

    init = InitList(group_id="1")
    for name, val in (("A", 20), ("B", 15), ("C", 10)):
        init.add_entity(name, "", val)
    init.first_turn = False
    init.turn = 2  # B 正在行动

    # 插入先攻 18 的 D：B 的回合位不变
    init.add_entity("D", "", 18)
    assert [e.name for e in init.entities] == ["A", "D", "B", "C"]
    assert init.turn == 3

    # 删除 A（当前回合位之前）：回合指针前移，仍指向 B
    init.del_entity("A")
    assert [e.name for e in init.entities] == ["D", "B", "C"]
    assert init.turn == 2


def test_model_size_limit():
    from nonebot_plugin_dnddicer.initiative.models import (
        INIT_LIST_SIZE,
        InitiativeError,
        InitList,
    )

    init = InitList(group_id="1")
    for i in range(INIT_LIST_SIZE):
        init.add_entity(f"E{i}", "", i)
    with pytest.raises(InitiativeError, match="大小超出限制"):
        init.add_entity("overflow", "", 999)


# =========================================================================
# 查看/无表场景
# =========================================================================


@pytest.mark.asyncio
async def test_init_no_list(app: App):
    """.init/.先攻 无先攻表 → 没有找到先攻列表。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(app, initiative_matcher, _event(100001, ".init"), "没有找到先攻列表")
    await _expect(app, initiative_matcher, _event(100001, ".先攻"), "没有找到先攻列表")


@pytest.mark.asyncio
async def test_init_inspect_with_self_roll(app: App):
    """.ri（无参数自掷）→ 入表；.init 查看含轮次头部与列表。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    token = set_runtime(SequenceRuntime([10]))
    try:
        await _expect(
            app, initiative_matcher, _event(100002, ".ri"),
            "test的先攻值是 1D20=[10]=10",
        )
    finally:
        reset_runtime(token)

    await _expect(
        app, initiative_matcher, _event(100002, ".init"),
        "先攻列表如下: \n当前是第1轮,test的回合\n1.test 先攻:10",
    )


@pytest.mark.asyncio
async def test_init_inspect_shows_pc_hp(app: App):
    """.init 列表为绑定角色卡（有 HP）的条目附上 HP 摘要。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    record = (
        "$姓名$ 伊丽莎白\n$等级$ 1\n$生命值$ 20/30\n"
        "$属性$ 10/10/10/10/10/10"
    )
    await _expect(app, char_matcher, _event(100003, f".角色卡记录 {record}", user_id=20001), "角色卡已设置")

    token = set_runtime(SequenceRuntime([7]))
    try:
        await _expect(
            app, initiative_matcher, _event(100003, ".ri", user_id=20001),
            "伊丽莎白的先攻值是 1D20=[7]=7",
        )
    finally:
        reset_runtime(token)

    await _expect(
        app, initiative_matcher, _event(100003, ".init"),
        "先攻列表如下: \n当前是第1轮,伊丽莎白的回合\n1.伊丽莎白 先攻:7 HP:20/30",
    )


# =========================================================================
# .ri 入表
# =========================================================================


@pytest.mark.asyncio
async def test_ri_fixed_value_and_multi_names(app: App):
    """.ri20 地精 固定值；.ri 地精/兽人 复数同掷、各自入表并排序。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(
        app, initiative_matcher, _event(100004, ".ri20 地精"),
        "地精的先攻值是 20",
    )
    token = set_runtime(SequenceRuntime([3, 4]))
    try:
        await _expect(
            app, initiative_matcher, _event(100004, ".ri 兽人/食尸鬼"),
            "兽人的先攻值是 1D20=[3]=3\n食尸鬼的先攻值是 1D20=[4]=4",
        )
    finally:
        reset_runtime(token)

    await _expect(
        app, initiative_matcher, _event(100004, ".init"),
        "先攻列表如下: \n当前是第1轮,地精的回合\n"
        "1.地精 先攻:20 \n2.食尸鬼 先攻:4 \n3.兽人 先攻:3",
    )


@pytest.mark.asyncio
async def test_ri_batch_with_hash(app: App):
    """.ri 3#地精 → 地精a/b/c 同值批量入表（播报合并 + 同值提示）。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    token = set_runtime(SequenceRuntime([4, 4, 4]))
    try:
        await _expect(
            app, initiative_matcher, _event(100005, ".ri 3#地精"),
            "地精a, 地精b, 地精c的先攻值是 1D20=[4]=4\n"
            "出现相同先攻值，请DM来决定由谁先行动，若不决定将保持默认顺序：\n"
            "回复.init first 名称 将该对象提前（同先攻值: 地精b / 地精a）\n"
            "回复.init first 名称 将该对象提前（同先攻值: 地精c / 地精a / 地精b）",
        )
    finally:
        reset_runtime(token)

    await _expect(
        app, initiative_matcher, _event(100005, ".init"),
        "先攻列表如下: \n当前是第1轮,地精a的回合\n"
        "1.地精a 先攻:4 \n2.地精b 先攻:4 \n3.地精c 先攻:4",
    )


@pytest.mark.asyncio
async def test_ri_invalid_batch_number(app: App):
    """.ri 11#地精 → 数量越界提示。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(
        app, initiative_matcher, _event(100006, ".ri 11#地精"),
        "11不是一个有效的数字 (1~10)",
    )


@pytest.mark.asyncio
async def test_ri_reroll_same_name_replaces(app: App):
    """同名重掷：提示重复并替换旧条目（先攻值更新）。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(app, initiative_matcher, _event(100007, ".ri20 地精"), "地精的先攻值是 20")
    await _expect(
        app, initiative_matcher, _event(100007, ".ri10 地精"),
        "你重复投掷了先攻\n地精的先攻值是 10",
    )
    await _expect(
        app, initiative_matcher, _event(100007, ".init"),
        "先攻列表如下: \n当前是第1轮,地精的回合\n1.地精 先攻:10",
    )


@pytest.mark.asyncio
async def test_ri_same_value_warning(app: App):
    """相同先攻值：提示由 DM 决定先后并给出 first 用法。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(app, initiative_matcher, _event(100008, ".ri10 地精"), "地精的先攻值是 10")
    await _expect(
        app, initiative_matcher, _event(100008, ".ri10 兽人"),
        "兽人的先攻值是 10\n"
        "出现相同先攻值，请DM来决定由谁先行动，若不决定将保持默认顺序：\n"
        "回复.init first 名称 将该对象提前（同先攻值: 兽人 / 地精）",
    )


@pytest.mark.asyncio
async def test_ri_named_npc_with_advantage(app: App):
    """.ri+1 地精优势 → 名称内优势并入掷骰表达式。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    token = set_runtime(SequenceRuntime([9, 7]))
    try:
        await _expect(
            app, initiative_matcher, _event(100009, ".ri+1 地精优势"),
            "地精的先攻值是 2D20K1+1=MAX{[9], [7]}+1=10",
        )
    finally:
        reset_runtime(token)


# =========================================================================
# 子指令：del / clr / first / swap
# =========================================================================


@pytest.mark.asyncio
async def test_init_delete_partial_multi(app: App):
    """del：部分匹配删除；A/B 多删；无匹配与歧义提示。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(app, initiative_matcher, _event(100010, ".ri20 地精a"), "地精a的先攻值是 20")
    await _expect(app, initiative_matcher, _event(100010, ".ri19 地精b"), "地精b的先攻值是 19")
    await _expect(app, initiative_matcher, _event(100010, ".ri18 兽人"), "兽人的先攻值是 18")
    await _expect(app, initiative_matcher, _event(100010, ".ri17 豺狼人"), "豺狼人的先攻值是 17")

    # 模糊命中多个 → 歧义报错
    await _expect(
        app, initiative_matcher, _event(100010, ".init del 地精"),
        "先攻对象名称地精存在歧义，可能是['地精a', '地精b']",
    )
    # 单删（部分匹配地精a）与批量删
    await _expect(
        app, initiative_matcher, _event(100010, ".init del 精a"),
        "已从先攻列表中移除 地精a",
    )
    await _expect(
        app, initiative_matcher, _event(100010, ".init del 地精b/兽人"),
        "已从先攻列表中移除 地精b\n已从先攻列表中移除 兽人",
    )
    # 不存在的名字
    await _expect(
        app, initiative_matcher, _event(100010, ".init del 不存在"),
        "先攻里没有不存在",
    )
    await _expect(
        app, initiative_matcher, _event(100010, ".init"),
        "先攻列表如下: \n当前是第1轮,豺狼人的回合\n1.豺狼人 先攻:17",
    )


@pytest.mark.asyncio
async def test_init_clear_aliases(app: App):
    """.init clr / .先攻清除 清空列表。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(app, initiative_matcher, _event(100011, ".ri20 地精"), "地精的先攻值是 20")
    await _expect(app, initiative_matcher, _event(100011, ".init clr"), "已清除先攻列表")
    await _expect(app, initiative_matcher, _event(100011, ".先攻"), "没有找到先攻列表")

    await _expect(app, initiative_matcher, _event(100012, ".ri20 地精"), "地精的先攻值是 20")
    await _expect(app, initiative_matcher, _event(100012, ".先攻清除"), "已清除先攻列表")


@pytest.mark.asyncio
async def test_init_first_and_swap(app: App):
    """.init first 同值提前；.init swap 互换条目。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(app, initiative_matcher, _event(100013, ".ri10 地精"), "地精的先攻值是 10")
    await _expect(app, initiative_matcher, _event(100013, ".ri10 兽人"), "兽人的先攻值是 10\n出现相同先攻值，请DM来决定由谁先行动，若不决定将保持默认顺序：\n回复.init first 名称 将该对象提前（同先攻值: 兽人 / 地精）")

    # first：把兽人提前到同值的地精之前
    await _expect(
        app, initiative_matcher, _event(100013, ".init first 兽人"),
        "兽人的先攻已在相同先攻值中被提前",
    )
    await _expect(
        app, initiative_matcher, _event(100013, ".init"),
        "先攻列表如下: \n当前是第1轮,兽人的回合\n1.兽人 先攻:10 \n2.地精 先攻:10",
    )

    # swap：交换兽人与地精的先攻值与位置
    await _expect(
        app, initiative_matcher, _event(100013, ".init swap 地精/兽人"),
        "地精与兽人的先攻值已互换",
    )
    await _expect(
        app, initiative_matcher, _event(100013, ".init"),
        "先攻列表如下: \n当前是第1轮,地精的回合\n1.地精 先攻:10 \n2.兽人 先攻:10",
    )


@pytest.mark.asyncio
async def test_init_unknown_subcommand(app: App):
    """.init 未知子指令 → 提示可用子指令。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(
        app, initiative_matcher, _event(100014, ".init 乱来"),
        "子指令乱来无效，可用的子指令为list/列表, clr/清除, del/删除, first/fst/提前, swap/交换",
    )


# =========================================================================
# .先攻检定 联动
# =========================================================================

_RECORD_SIMPLE = (
    "$姓名$ 伊丽莎白\n$等级$ 1\n$属性$ 10/10/10/10/10/10"
)


@pytest.mark.asyncio
async def test_check_initiative_linkage(app: App):
    """.先攻检定 → 掷骰行被替换为入表反馈，并进入先攻表。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(
        app, char_matcher,
        _event(100020, f".角色卡记录 {_RECORD_SIMPLE}", user_id=30001),
        "角色卡已设置",
    )
    token = set_runtime(SequenceRuntime([5]))
    try:
        await _expect(
            app, check_matcher, _event(100020, ".先攻检定", user_id=30001),
            "伊丽莎白进行【先攻检定】：\n无熟练加值 敏捷调整值:0\n"
            "伊丽莎白的先攻值是 1D20=[5]=5",
        )
    finally:
        reset_runtime(token)

    await _expect(
        app, initiative_matcher, _event(100020, ".init"),
        "先攻列表如下: \n当前是第1轮,伊丽莎白的回合\n1.伊丽莎白 先攻:5",
    )


@pytest.mark.asyncio
async def test_check_initiative_reroll_replaces(app: App):
    """.先攻检定 重复掷 → 提示重复并替换（列表仍单条目）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(
        app, char_matcher,
        _event(100021, f".角色卡记录 {_RECORD_SIMPLE}", user_id=30002),
        "角色卡已设置",
    )
    token = set_runtime(SequenceRuntime([5]))
    try:
        await _expect(
            app, check_matcher, _event(100021, ".先攻检定", user_id=30002),
            "伊丽莎白进行【先攻检定】：\n无熟练加值 敏捷调整值:0\n"
            "伊丽莎白的先攻值是 1D20=[5]=5",
        )
    finally:
        reset_runtime(token)

    # 同名同 owner 重掷：replace 出 "你重复投掷了先攻" 前缀行
    token = set_runtime(SequenceRuntime([9]))
    try:
        await _expect(
            app, check_matcher, _event(100021, ".先攻检定", user_id=30002),
            "伊丽莎白进行【先攻检定】：\n无熟练加值 敏捷调整值:0\n"
            "你重复投掷了先攻\n伊丽莎白的先攻值是 1D20=[9]=9",
        )
    finally:
        reset_runtime(token)

    await _expect(
        app, initiative_matcher, _event(100021, ".init"),
        "先攻列表如下: \n当前是第1轮,伊丽莎白的回合\n1.伊丽莎白 先攻:9",
    )


@pytest.mark.asyncio
async def test_check_initiative_20_no_critical(app: App):
    """.先攻检定 掷 20 → 正常入表，但不播报大成功（先攻掷骰无大成功一说）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _expect(
        app, char_matcher,
        _event(100022, f".角色卡记录 {_RECORD_SIMPLE}", user_id=30003),
        "角色卡已设置",
    )
    token = set_runtime(SequenceRuntime([20]))
    try:
        await _expect(
            app, check_matcher, _event(100022, ".先攻检定", user_id=30003),
            "伊丽莎白进行【先攻检定】：\n无熟练加值 敏捷调整值:0\n"
            "伊丽莎白的先攻值是 1D20=[20]=20",
        )
    finally:
        reset_runtime(token)


# =========================================================================
# @ 提及目标（2026-09-22：DM 代不在场的玩家掷先攻）
# =========================================================================


def _mention_event(group_id: int, *parts, user_id: int = 10001):
    """构造带 @ 段的群消息事件（parts 依次拼接，可为文本或消息段）。"""
    message = Message()
    for part in parts:
        message += part
    return fake_group_message_event_v11(
        message=message, group_id=group_id, user_id=user_id
    )


@pytest.mark.asyncio
async def test_ri_mention_binds_owner(app: App):
    """.ri+3 @玩家 → 条目名取角色卡名、归属绑定该玩家（不再静默给自己掷）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.initiative import get_init_list

    g = 100030
    await _expect(
        app, char_matcher,
        _event(g, f".角色卡记录 {_RECORD_SIMPLE}", user_id=30010),
        "角色卡已设置",
    )
    token = set_runtime(SequenceRuntime([10]))
    try:
        await _expect(
            app, initiative_matcher,
            _mention_event(g, ".ri+3 ", MessageSegment.at(30010), user_id=30000),
            "伊丽莎白的先攻值是 1D20+3=[10]+3=13",
        )
    finally:
        reset_runtime(token)

    init_data = await get_init_list(g)
    assert init_data is not None
    assert [(e.name, e.owner, e.init) for e in init_data.entities] == [
        ("伊丽莎白", "30010", 13)
    ]
    # 发送者（DM）自己未入表
    await _expect(
        app, initiative_matcher, _event(g, ".init"),
        "先攻列表如下: \n当前是第1轮,伊丽莎白的回合\n1.伊丽莎白 先攻:13",
    )


@pytest.mark.asyncio
async def test_ri_mention_fixed_value_and_suffix(app: App):
    """.ri 20 @玩家 固定值；.ri @玩家+2 加值写在标记之后。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 100031
    await _expect(
        app, char_matcher,
        _event(g, f".角色卡记录 {_RECORD_SIMPLE}", user_id=30011),
        "角色卡已设置",
    )
    await _expect(
        app, initiative_matcher,
        _mention_event(g, ".ri 20 ", MessageSegment.at(30011), user_id=30000),
        "伊丽莎白的先攻值是 20",
    )
    token = set_runtime(SequenceRuntime([8]))
    try:
        await _expect(
            app, initiative_matcher,
            _mention_event(g, ".ri ", MessageSegment.at(30011), "+2", user_id=30000),
            "你重复投掷了先攻\n伊丽莎白的先攻值是 1D20+2=[8]+2=10",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_ri_mention_advantage_suffix(app: App):
    """.ri @玩家优势 → 优劣势写在标记之后同样并入掷骰表达式。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 100032
    await _expect(
        app, char_matcher,
        _event(g, f".角色卡记录 {_RECORD_SIMPLE}", user_id=30012),
        "角色卡已设置",
    )
    token = set_runtime(SequenceRuntime([9, 7]))
    try:
        await _expect(
            app, initiative_matcher,
            _mention_event(g, ".ri ", MessageSegment.at(30012), "优势", user_id=30000),
            "伊丽莎白的先攻值是 2D20K1=MAX{[9], [7]}=9",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_ri_mention_mixed_with_npc(app: App):
    """.ri 地精/@玩家 → NPC 条目与 @ 目标混写（各自掷骰与归属）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.initiative import get_init_list

    g = 100033
    await _expect(
        app, char_matcher,
        _event(g, f".角色卡记录 {_RECORD_SIMPLE}", user_id=30013),
        "角色卡已设置",
    )
    token = set_runtime(SequenceRuntime([3, 4]))
    try:
        await _expect(
            app, initiative_matcher,
            _mention_event(g, ".ri 地精/", MessageSegment.at(30013), user_id=30000),
            "地精的先攻值是 1D20=[3]=3\n伊丽莎白的先攻值是 1D20=[4]=4",
        )
    finally:
        reset_runtime(token)

    init_data = await get_init_list(g)
    assert init_data is not None
    assert [(e.name, e.owner) for e in init_data.entities] == [
        ("伊丽莎白", "30013"),
        ("地精", ""),
    ]


@pytest.mark.asyncio
async def test_ri_mention_no_char_and_batch_guard(app: App):
    """@ 目标无卡 → 真 @ 段引导建卡；3#@玩家 → 批量写法守卫。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 100034
    await _expect(
        app, initiative_matcher,
        _mention_event(g, ".ri+3 ", MessageSegment.at(39999), user_id=30000),
        Message(MessageSegment.at("39999"))
        + " 还没有在本群建立角色卡（可用 .角色卡记录 建卡后再试）；"
        "如需临时加同名怪物条目，可直接写名称（.ri+3 名称）",
    )
    await _expect(
        app, initiative_matcher,
        _mention_event(g, ".ri 3#", MessageSegment.at(39999), user_id=30000),
        "@ 目标不支持 N# 批量写法，请直接写条目名称",
    )


@pytest.mark.asyncio
async def test_ri_stray_mention_not_executed(app: App):
    """游离 @（@ 落在表达式段或命令前）→ 提示且不给发送者自己掷先攻。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.initiative import get_init_list

    g = 100035
    hint = "未执行：目标请写在表达式右侧，例如 .ri+3 @小明"
    await _expect(
        app, initiative_matcher,
        _mention_event(g, ".ri ", MessageSegment.at(39998), " 布兰克", user_id=30000),
        hint,
    )
    await _expect(
        app, initiative_matcher,
        _mention_event(g, MessageSegment.at(39998), " .ri+3", user_id=30000),
        hint,
    )
    assert await get_init_list(g) is None


# =========================================================================
# .init 子指令的 @ 目标（2026-09-22：按归属定位条目）
# =========================================================================


@pytest.mark.asyncio
async def test_init_delete_mention_survives_rename(app: App):
    """.init del @玩家：按归属定位条目——角色卡改名后仍能删除。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 100040
    await _expect(
        app, char_matcher,
        _event(g, f".角色卡记录 {_RECORD_SIMPLE}", user_id=30020),
        "角色卡已设置",
    )
    await _expect(
        app, initiative_matcher,
        _mention_event(g, ".ri20 ", MessageSegment.at(30020), user_id=30000),
        "伊丽莎白的先攻值是 20",
    )
    # 改名后条目名仍是入表时的快照：@ 按 owner 定位照常删除
    await _expect(
        app, char_matcher,
        _event(
            g,
            ".角色卡记录 $姓名$ 白伊丽莎\n$等级$ 1\n$属性$ 10/10/10/10/10/10",
            user_id=30020,
        ),
        "角色卡已设置",
    )
    await _expect(
        app, initiative_matcher,
        _mention_event(g, ".init del ", MessageSegment.at(30020), user_id=30000),
        "已从先攻列表中移除 伊丽莎白",
    )
    await _expect(app, initiative_matcher, _event(g, ".init"), "没有找到先攻列表")


@pytest.mark.asyncio
async def test_init_first_mention(app: App):
    """.init first @玩家：同先攻值内提前该玩家条目。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 100041
    await _expect(
        app, char_matcher,
        _event(g, f".角色卡记录 {_RECORD_SIMPLE}", user_id=30021),
        "角色卡已设置",
    )
    await _expect(app, initiative_matcher, _event(g, ".ri10 地精"), "地精的先攻值是 10")
    await _expect(
        app, initiative_matcher,
        _mention_event(g, ".ri10 ", MessageSegment.at(30021), user_id=30000),
        "伊丽莎白的先攻值是 10\n"
        "出现相同先攻值，请DM来决定由谁先行动，若不决定将保持默认顺序：\n"
        "回复.init first 名称 将该对象提前（同先攻值: 伊丽莎白 / 地精）",
    )
    await _expect(
        app, initiative_matcher,
        _mention_event(g, ".init first ", MessageSegment.at(30021), user_id=30000),
        "伊丽莎白的先攻已在相同先攻值中被提前",
    )
    await _expect(
        app, initiative_matcher, _event(g, ".init"),
        "先攻列表如下: \n当前是第1轮,伊丽莎白的回合\n"
        "1.伊丽莎白 先攻:10 \n2.地精 先攻:10",
    )


@pytest.mark.asyncio
async def test_init_swap_mention_and_not_in_list(app: App):
    """.init swap @玩家/兽人 互换；@ 目标不在先攻表 → 真 @ 段提示。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 100042
    await _expect(
        app, char_matcher,
        _event(g, f".角色卡记录 {_RECORD_SIMPLE}", user_id=30022),
        "角色卡已设置",
    )
    await _expect(app, initiative_matcher, _event(g, ".ri20 兽人"), "兽人的先攻值是 20")
    await _expect(
        app, initiative_matcher,
        _mention_event(g, ".ri5 ", MessageSegment.at(30022), user_id=30000),
        "伊丽莎白的先攻值是 5",
    )
    await _expect(
        app, initiative_matcher,
        _mention_event(
            g, ".init swap ", MessageSegment.at(30022), "/兽人", user_id=30000
        ),
        "伊丽莎白与兽人的先攻值已互换",
    )
    await _expect(
        app, initiative_matcher, _event(g, ".init"),
        "先攻列表如下: \n当前是第1轮,伊丽莎白的回合\n"
        "1.伊丽莎白 先攻:20 \n2.兽人 先攻:5",
    )
    await _expect(
        app, initiative_matcher,
        _mention_event(g, ".init del ", MessageSegment.at(39997), user_id=30000),
        Message(MessageSegment.at("39997")) + " 不在先攻列表中",
    )
