"""NPC/怪物血量 nonebug 测试（.hp 目标解析 / 先攻联动 / 清理语义）。

存储隔离：每个用例前清空先攻/NPC 血量/角色卡数据（缓存 + JSON），
每个用例使用独立群号；掷骰用 SequenceRuntime 固定骰值确保确定性。

语义基准（对齐 DicePP npc_health）：
- NPC 血量条目需经先攻表解析创建：先 ``.ri`` 入表，再 ``.hp 名称 ...``；
- 先攻列表展示 NPC 血量；``.init clr`` / ``.br`` 清理「未设最大值」的临时血量；
- ``.init del`` 删除 NPC 条目时一并删除其血量记录。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11

from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_CLEAN_FILES = ("initiative.json", "characters.json", "npc_health.json")


@pytest.fixture(autouse=True)
def _clear_store():
    """每个用例前清空先攻/NPC 血量/角色卡数据（缓存 + JSON）。"""
    from nonebot_plugin_dnddicer.data import get_data_file
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import initiative as _init
    from nonebot_plugin_dnddicer.data import npc_health as _npc

    _chars._cache = None
    _init._cache = None
    _npc._cache = None
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
# 创建与查看（先 .ri 入表，再 .hp 记录）
# =========================================================================


@pytest.mark.asyncio
async def test_npc_create_via_init_then_view(app: App):
    """NPC：.ri 入先攻表后 .hp 记录血量；.init 与 .hp list 均展示。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 110001
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")
    await _expect(app, hp_matcher, _event(g, ".hp 哥布林 7/7"), "哥布林: HP=7/7\n当前HP:7/7")
    await _expect(
        app, initiative_matcher, _event(g, ".init"),
        "先攻列表如下: \n当前是第1轮,哥布林的回合\n1.哥布林 先攻:20 HP:7/7",
    )
    await _expect(app, hp_matcher, _event(g, ".hp list"), "哥布林 HP:7/7")


@pytest.mark.asyncio
async def test_npc_requires_init_entry(app: App):
    """未入先攻表且无血量记录：.hp 名称 ... → 找不到（对齐 DicePP，先 .ri）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, hp_matcher, _event(110002, ".hp 哥布林 7/7"),
        "找不到哥布林的生命值信息",
    )


# =========================================================================
# 伤害 / 抗性（DM 掷怪物伤害）
# =========================================================================


@pytest.mark.asyncio
async def test_npc_damage_and_resistance(app: App):
    """NPC 伤害表达式；抗性后缀减半生效（DM 结算怪物伤害）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 110003
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")
    await _expect(app, hp_matcher, _event(g, ".hp 哥布林 20/20"), "哥布林: HP=20/20\n当前HP:20/20")

    token = set_runtime(SequenceRuntime([4]))
    try:
        await _expect(
            app, hp_matcher, _event(g, ".hp 哥布林 -d6"),
            "哥布林: 当前HP减少[4]=4\nHP:20/20 -> HP:16/20",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([5]))
    try:
        await _expect(
            app, hp_matcher, _event(g, ".hp 哥布林抗性 -d6"),
            "哥布林: 当前HP减少[5]=5（抗性减半→2）\nHP:16/20 -> HP:14/20",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_npc_damage_only_display(app: App):
    """不设血量直接扣（对齐 DicePP）：显示为「损失HP:N」，多次扣血累加、治疗回补。

    .init 与 .hp list 均按 HPInfo 受损记录模式展示（负数扣血量），无需先设 10/10。
    """
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 110011
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")

    token = set_runtime(SequenceRuntime([4]))
    try:
        await _expect(
            app, hp_matcher, _event(g, ".hp 哥布林 -d6"),
            "哥布林: 当前HP减少[4]=4\n损失HP:0 -> 损失HP:4",
        )
    finally:
        reset_runtime(token)

    await _expect(
        app, initiative_matcher, _event(g, ".init"),
        "先攻列表如下: \n当前是第1轮,哥布林的回合\n1.哥布林 先攻:20 损失HP:4",
    )
    await _expect(app, hp_matcher, _event(g, ".hp list"), "哥布林 损失HP:4")

    # 再次扣血：损失值累加
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林 -3"),
        "哥布林: 当前HP减少3\n损失HP:4 -> 损失HP:7",
    )
    # 治疗：受损记录回补（不越过 0）
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林 +2"),
        "哥布林: 当前HP增加2\n损失HP:7 -> 损失HP:5",
    )


@pytest.mark.asyncio
async def test_npc_ambiguous_target(app: App):
    """同名部分匹配多个 NPC → 歧义提示。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 110009
    await _expect(
        app, initiative_matcher, _event(g, ".ri20 哥布林a/哥布林b"),
        "哥布林a, 哥布林b的先攻值是 20\n"
        "出现相同先攻值，请DM来决定由谁先行动，若不决定将保持默认顺序：\n"
        "回复.init first 名称 将该对象提前（同先攻值: 哥布林b / 哥布林a）",
    )
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林 10/10"),
        "存在多个匹配目标：['哥布林a', '哥布林b']",
    )


# =========================================================================
# .hp list 混合 / .hp del 对象
# =========================================================================


@pytest.mark.asyncio
async def test_npc_list_mixed_with_pc(app: App):
    """".hp list"：PC 在前、NPC 在后（对齐 DicePP）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 110004
    record = (
        ".角色卡记录 $姓名$ 爱丽丝\n$等级$ 1\n$生命值$ 20/30\n"
        "$属性$ 10/10/10/10/10/10"
    )
    await _expect(app, char_matcher, _event(g, record, user_id=40001), "角色卡已设置")
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")
    await _expect(app, hp_matcher, _event(g, ".hp 哥布林 7/7"), "哥布林: HP=7/7\n当前HP:7/7")

    await _expect(app, hp_matcher, _event(g, ".hp list"), "爱丽丝 HP:20/30\n哥布林 HP:7/7")


@pytest.mark.asyncio
async def test_npc_del_target(app: App):
    """.hp del 名称：删除 NPC 血量；条目仍在先攻表可再次创建。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.npc_health import get_npc_health

    g = 110005
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")
    await _expect(app, hp_matcher, _event(g, ".hp 哥布林 5/5"), "哥布林: HP=5/5\n当前HP:5/5")
    await _expect(app, hp_matcher, _event(g, ".hp del 哥布林"), "已删除哥布林的生命值信息")
    assert await get_npc_health(g, "哥布林") is None
    await _expect(app, hp_matcher, _event(g, ".hp list"), "本群没有任何生命值信息")
    # 条目仍在先攻表：可再次记录
    await _expect(app, hp_matcher, _event(g, ".hp 哥布林 3/3"), "哥布林: HP=3/3\n当前HP:3/3")


@pytest.mark.asyncio
async def test_npc_del_missing_target(app: App):
    """.hp del 不存在的对象 → 找不到。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, hp_matcher, _event(110010, ".hp del 哥布林"),
        "找不到哥布林的生命值信息",
    )


# =========================================================================
# 先攻联动：清空（.init clr / .br）与删除（.init del）时的清理语义
# =========================================================================


async def _setup_temp_and_max_npc(app: App, g: int):
    """准备两条 NPC：哥布林=仅扣血（临时血量）、兽人=已设最大值（保留）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")
    token = set_runtime(SequenceRuntime([4]))
    try:
        await _expect(
            app, hp_matcher, _event(g, ".hp 哥布林 -d6"),
            "哥布林: 当前HP减少[4]=4\n损失HP:0 -> 损失HP:4",
        )
    finally:
        reset_runtime(token)
    await _expect(app, initiative_matcher, _event(g, ".ri19 兽人"), "兽人的先攻值是 19")
    await _expect(app, hp_matcher, _event(g, ".hp 兽人 10/10"), "兽人: HP=10/10\n当前HP:10/10")


@pytest.mark.asyncio
async def test_init_clear_removes_temp_npc_health_only(app: App):
    """.init clr：清理未设最大值的 NPC 临时血量；已设最大值的保留。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.npc_health import get_npc_health

    g = 110006
    await _setup_temp_and_max_npc(app, g)
    await _expect(app, initiative_matcher, _event(g, ".init clr"), "已清除先攻列表")
    assert await get_npc_health(g, "哥布林") is None
    assert await get_npc_health(g, "兽人") is not None


@pytest.mark.asyncio
async def test_br_removes_temp_npc_health_only(app: App):
    """.br 新建战斗轮：与 .init clr 同款 NPC 临时血量清理。"""
    from nonebot_plugin_dnddicer.commands.battle import br_matcher
    from nonebot_plugin_dnddicer.data.npc_health import get_npc_health

    g = 110007
    await _setup_temp_and_max_npc(app, g)
    await _expect(app, br_matcher, _event(g, ".br"), "已创建新战斗轮。清除先攻表、当前回合。")
    assert await get_npc_health(g, "哥布林") is None
    assert await get_npc_health(g, "兽人") is not None


@pytest.mark.asyncio
async def test_init_del_removes_npc_health(app: App):
    """.init del 名称：删除 NPC 条目时一并删除其血量记录（对齐 DicePP）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.npc_health import get_npc_health

    g = 110008
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")
    await _expect(app, hp_matcher, _event(g, ".hp 哥布林 5/5"), "哥布林: HP=5/5\n当前HP:5/5")
    await _expect(
        app, initiative_matcher, _event(g, ".init del 哥布林"),
        "已从先攻列表中移除 哥布林",
    )
    assert await get_npc_health(g, "哥布林") is None
