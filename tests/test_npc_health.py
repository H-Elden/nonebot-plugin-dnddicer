"""NPC/怪物血量 nonebug 测试（.hp 目标解析 / 先攻联动 / 清理与回满语义）。

存储隔离：每个用例前清空先攻/NPC 血量/角色卡数据（缓存 + JSON），
每个用例使用独立群号；掷骰用 SequenceRuntime 固定骰值确保确定性。

语义基准：
- NPC 血量条目需经先攻表解析创建：先 ``.ri`` 入表，再 ``.hp 名称 ...``；
- 先攻列表展示 NPC 血量；``.init clr`` / ``.br`` 清理「未设最大值」的临时血量；
- ``.init del`` 删除 NPC 条目时一并删除其血量记录。

本插件新增语义（2026-09-21）：
- NPC 以新条目入先攻表时，未标记跨战斗保持且已设上限的记录自动回满并提示
  （同名重掷不触发；``.npc 持久`` 标记的记录跳过）。
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
    """未入先攻表且无血量记录：.hp 名称 ... → 找不到（NPC 需先 .ri 入表）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, hp_matcher, _event(110002, ".hp 哥布林 7/7"),
        "找不到哥布林的生命值信息\n新NPC需要先加入先攻表才可设置HP",
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
    """不设血量直接扣：显示为「损失HP:N」，多次扣血累加、治疗回补。

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
async def test_npc_negative_damage_clamped(app: App):
    """负伤害按 0 计：表达式算出负值时不再变成回血（2026-09-21 修复）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 110013
    await _expect(app, initiative_matcher, _event(g, ".ri20 向导"), "向导的先攻值是 20")
    await _expect(
        app, hp_matcher, _event(g, ".hp 向导 12/18"),
        "向导: HP=12/18\n当前HP:12/18",
    )

    token = set_runtime(SequenceRuntime([1]))
    try:
        await _expect(
            app, hp_matcher, _event(g, ".hp 向导 -d12-2易伤"),
            "向导: 当前HP减少([1]-2)*2=-2（伤害最低为0）\nHP:12/18 -> HP:12/18",
        )
    finally:
        reset_runtime(token)


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


@pytest.mark.asyncio
async def test_npc_exact_match_priority(app: App):
    """完全匹配优先：「地精」与「熊地精」并存时，.hp 地精 命中地精、.hp del 只删地精。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.npc_health import get_npc_health

    g = 110012
    await _expect(app, initiative_matcher, _event(g, ".ri20 地精"), "地精的先攻值是 20")
    await _expect(app, initiative_matcher, _event(g, ".ri19 熊地精"), "熊地精的先攻值是 19")
    # 精确匹配优先：不再与「熊地精」冲突（2026-09-21 修订）
    await _expect(app, hp_matcher, _event(g, ".hp 地精 12/12"), "地精: HP=12/12\n当前HP:12/12")
    await _expect(
        app, hp_matcher, _event(g, ".hp 熊地精 15/15"),
        "熊地精: HP=15/15\n当前HP:15/15",
    )
    # 部分匹配（模糊）仍可用，且两条记录各自独立
    await _expect(
        app, hp_matcher, _event(g, ".hp 熊 -2"),
        "熊地精: 当前HP减少2\nHP:15/15 -> HP:13/15",
    )
    # del 指定对象：精确匹配只删「地精」，不动「熊地精」
    await _expect(app, hp_matcher, _event(g, ".hp del 地精"), "已删除地精的生命值信息")
    assert await get_npc_health(g, "地精") is None
    assert await get_npc_health(g, "熊地精") is not None


# =========================================================================
# .hp list 混合 / .hp del 对象
# =========================================================================


@pytest.mark.asyncio
async def test_npc_list_mixed_with_pc(app: App):
    """".hp list"：PC 在前、NPC 在后。"""
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
        "找不到哥布林的生命值信息\n新NPC需要先加入先攻表才可设置HP",
    )


@pytest.mark.asyncio
async def test_npc_del_multi_targets(app: App):
    """.hp del a/b：与 .init del 一致支持多目标，逐行反馈。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.npc_health import get_npc_health

    g = 110014
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林a"), "哥布林a的先攻值是 20")
    await _expect(app, initiative_matcher, _event(g, ".ri19 哥布林b"), "哥布林b的先攻值是 19")
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林a 7/7"),
        "哥布林a: HP=7/7\n当前HP:7/7",
    )
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林b 5/5"),
        "哥布林b: HP=5/5\n当前HP:5/5",
    )
    await _expect(
        app, hp_matcher, _event(g, ".hp del 哥布林a/哥布林b"),
        "已删除哥布林a的生命值信息\n已删除哥布林b的生命值信息",
    )
    assert await get_npc_health(g, "哥布林a") is None
    assert await get_npc_health(g, "哥布林b") is None


@pytest.mark.asyncio
async def test_hp_clr_clears_all_npc(app: App):
    """.hp clr：清空本群全部 NPC 血量记录（含跨战斗保持的），不触碰 PC。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.commands.npc import npc_matcher
    from nonebot_plugin_dnddicer.data.npc_health import list_npc_health

    g = 110015
    record = (
        ".角色卡记录 $姓名$ 爱丽丝\n$等级$ 1\n$生命值$ 20/30\n"
        "$属性$ 10/10/10/10/10/10"
    )
    await _expect(app, char_matcher, _event(g, record, user_id=40001), "角色卡已设置")
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林 7/7"),
        "哥布林: HP=7/7\n当前HP:7/7",
    )
    await _expect(app, initiative_matcher, _event(g, ".ri19 向导"), "向导的先攻值是 19")
    await _expect(
        app, hp_matcher, _event(g, ".hp 向导 12/12"),
        "向导: HP=12/12\n当前HP:12/12",
    )
    await _expect(
        app, npc_matcher, _event(g, ".npc 持久 向导"),
        "已将NPC「向导」设为跨战斗保持血量（.ri 再次入表时不再自动回满）",
    )

    await _expect(app, hp_matcher, _event(g, ".hp clr"), "已清空2条NPC血量记录")
    assert await list_npc_health(g) == []
    # PC 角色卡与其 HP 不受影响
    await _expect(app, hp_matcher, _event(g, ".hp list"), "爱丽丝 HP:20/30")


@pytest.mark.asyncio
async def test_hp_clr_empty(app: App):
    """.hp clr 无 NPC 记录 → 提示本群没有任何NPC生命值信息。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, hp_matcher, _event(110017, ".hp clr"),
        "本群没有任何NPC生命值信息",
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
    """.init del 名称：删除 NPC 条目时一并删除其血量记录。"""
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


# =========================================================================
# NPC 血量自动回满（.ri 新入表）与 .npc 跨战斗保持开关（2026-09-21 新增）
# =========================================================================


@pytest.mark.asyncio
async def test_npc_auto_refill_on_new_init(app: App):
    """新条目入先攻表且未标记保持、已设上限、未满 → 自动回满并给出提示。"""
    from nonebot_plugin_dnddicer.commands.battle import br_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.npc_health import get_npc_health

    g = 110021
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林 20/20"),
        "哥布林: HP=20/20\n当前HP:20/20",
    )
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林 -4"),
        "哥布林: 当前HP减少4\nHP:20/20 -> HP:16/20",
    )
    await _expect(
        app, br_matcher, _event(g, ".br"),
        "已创建新战斗轮。清除先攻表、当前回合。",
    )
    await _expect(
        app, initiative_matcher, _event(g, ".ri15 哥布林"),
        "哥布林的先攻值是 15\n"
        "注：哥布林 已自动回满 20/20（上次 16/20）\n"
        "如需沿用上次血量:\n"
        ".hp 哥布林 16/20\n"
        "如需跨战斗保持血量:\n"
        ".npc 持久 哥布林",
    )
    hp_info = await get_npc_health(g, "哥布林")
    assert hp_info is not None and hp_info.hp_cur == 20 and hp_info.hp_max == 20


@pytest.mark.asyncio
async def test_npc_persistent_skips_refill(app: App):
    """.npc 持久 后：.ri 新入表不回满；.hp 结算不会丢失保持标记。"""
    from nonebot_plugin_dnddicer.commands.battle import br_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.commands.npc import npc_matcher
    from nonebot_plugin_dnddicer.data.npc_health import get_npc_record

    g = 110022
    await _expect(app, initiative_matcher, _event(g, ".ri20 向导"), "向导的先攻值是 20")
    await _expect(
        app, hp_matcher, _event(g, ".hp 向导 12/12"),
        "向导: HP=12/12\n当前HP:12/12",
    )
    await _expect(
        app, npc_matcher, _event(g, ".npc 持久 向导"),
        "已将NPC「向导」设为跨战斗保持血量（.ri 再次入表时不再自动回满）",
    )
    # .hp 结算走 save_npc_health：保持标记需被继承（回归防护）
    await _expect(
        app, hp_matcher, _event(g, ".hp 向导 -5"),
        "向导: 当前HP减少5\nHP:12/12 -> HP:7/12",
    )
    record = await get_npc_record(g, "向导")
    assert record is not None and record.persistent and record.hp_info.hp_cur == 7

    await _expect(
        app, br_matcher, _event(g, ".br"),
        "已创建新战斗轮。清除先攻表、当前回合。",
    )
    await _expect(app, initiative_matcher, _event(g, ".ri15 向导"), "向导的先攻值是 15")
    record = await get_npc_record(g, "向导")
    assert record is not None and record.hp_info.hp_cur == 7


@pytest.mark.asyncio
async def test_npc_refill_skipped_on_reroll(app: App):
    """同名条目在同一场战斗中重掷：不回满（避免误清已受伤害）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.npc_health import get_npc_record

    g = 110023
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林 20/20"),
        "哥布林: HP=20/20\n当前HP:20/20",
    )
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林 -4"),
        "哥布林: 当前HP减少4\nHP:20/20 -> HP:16/20",
    )
    await _expect(
        app, initiative_matcher, _event(g, ".ri15 哥布林"),
        "你重复投掷了先攻\n哥布林的先攻值是 15",
    )
    record = await get_npc_record(g, "哥布林")
    assert record is not None and record.hp_info.hp_cur == 16


@pytest.mark.asyncio
async def test_npc_refill_aggregated_multi(app: App):
    """多个 NPC 同时回满：提示聚合为一条（含各自上次血量）。"""
    from nonebot_plugin_dnddicer.commands.battle import br_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    g = 110024
    await _expect(
        app, initiative_matcher, _event(g, ".ri20 哥布林a/哥布林b+3"),
        "哥布林a的先攻值是 20\n哥布林b的先攻值是 20+3=23",
    )
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林a 7/7"),
        "哥布林a: HP=7/7\n当前HP:7/7",
    )
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林b 5/5"),
        "哥布林b: HP=5/5\n当前HP:5/5",
    )
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林a -2"),
        "哥布林a: 当前HP减少2\nHP:7/7 -> HP:5/7",
    )
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林b -2"),
        "哥布林b: 当前HP减少2\nHP:5/5 -> HP:3/5",
    )
    await _expect(
        app, br_matcher, _event(g, ".br"),
        "已创建新战斗轮。清除先攻表、当前回合。",
    )
    await _expect(
        app, initiative_matcher, _event(g, ".ri20 哥布林a/哥布林b+3"),
        "哥布林a的先攻值是 20\n哥布林b的先攻值是 20+3=23\n"
        "注：哥布林a 7/7（上次 5/7）、哥布林b 5/5（上次 3/5） 已自动回满\n"
        "如需沿用上次血量:\n"
        ".hp 名称 当前/最大\n"
        "如需跨战斗保持血量:\n"
        ".npc 持久 名称",
    )


@pytest.mark.asyncio
async def test_npc_persistent_temp_record_kept_and_not_refilled(app: App):
    """跨战斗保持 + 未设上限的纯损失记录：.br 不清理、.ri 不回满。"""
    from nonebot_plugin_dnddicer.commands.battle import br_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.commands.npc import npc_matcher
    from nonebot_plugin_dnddicer.data.npc_health import get_npc_health

    g = 110025
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")
    await _expect(
        app, hp_matcher, _event(g, ".hp 哥布林 -4"),
        "哥布林: 当前HP减少4\n损失HP:0 -> 损失HP:4",
    )
    await _expect(
        app, npc_matcher, _event(g, ".npc 持久 哥布林"),
        "已将NPC「哥布林」设为跨战斗保持血量（.ri 再次入表时不再自动回满）",
    )
    await _expect(
        app, br_matcher, _event(g, ".br"),
        "已创建新战斗轮。清除先攻表、当前回合。",
    )
    hp_info = await get_npc_health(g, "哥布林")
    assert hp_info is not None and hp_info.hp_max == 0  # 保持标记豁免临时清理

    await _expect(app, initiative_matcher, _event(g, ".ri15 哥布林"), "哥布林的先攻值是 15")
    hp_info = await get_npc_health(g, "哥布林")
    assert hp_info is not None and hp_info.hp_cur == -4


@pytest.mark.asyncio
async def test_npc_temp_restores_auto_refill(app: App):
    """.npc 临时：恢复默认后新入先攻表再次自动回满。"""
    from nonebot_plugin_dnddicer.commands.battle import br_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.commands.npc import npc_matcher

    g = 110027
    await _expect(app, initiative_matcher, _event(g, ".ri20 向导"), "向导的先攻值是 20")
    await _expect(
        app, hp_matcher, _event(g, ".hp 向导 12/12"),
        "向导: HP=12/12\n当前HP:12/12",
    )
    await _expect(
        app, npc_matcher, _event(g, ".npc 持久 向导"),
        "已将NPC「向导」设为跨战斗保持血量（.ri 再次入表时不再自动回满）",
    )
    await _expect(
        app, hp_matcher, _event(g, ".hp 向导 -5"),
        "向导: 当前HP减少5\nHP:12/12 -> HP:7/12",
    )
    await _expect(
        app, npc_matcher, _event(g, ".npc 临时 向导"),
        "已将NPC「向导」恢复为默认（每次新入先攻表时自动回满）",
    )
    await _expect(
        app, br_matcher, _event(g, ".br"),
        "已创建新战斗轮。清除先攻表、当前回合。",
    )
    await _expect(
        app, initiative_matcher, _event(g, ".ri15 向导"),
        "向导的先攻值是 15\n"
        "注：向导 已自动回满 12/12（上次 7/12）\n"
        "如需沿用上次血量:\n"
        ".hp 向导 7/12\n"
        "如需跨战斗保持血量:\n"
        ".npc 持久 向导",
    )


@pytest.mark.asyncio
async def test_npc_command_errors(app: App):
    """.npc：无参数回帮助；无记录 / 找不到 / 目标是玩家角色卡各自提示。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.commands.npc import _HELP as NPC_HELP
    from nonebot_plugin_dnddicer.commands.npc import npc_matcher

    g = 110026
    await _expect(app, npc_matcher, _event(g, ".npc"), NPC_HELP)
    await _expect(
        app, npc_matcher, _event(g, ".npc 持久 不存在"),
        "找不到不存在的生命值信息",
    )
    # 已在先攻表但尚无血量记录：提示先建立记录
    await _expect(app, initiative_matcher, _event(g, ".ri20 哥布林"), "哥布林的先攻值是 20")
    await _expect(
        app, npc_matcher, _event(g, ".npc 持久 哥布林"),
        "找不到哥布林的血量记录，请先用 .hp 哥布林 当前血量/最大血量 记录",
    )
    # PC 角色卡：不适用本命令
    record = (
        ".角色卡记录 $姓名$ 爱丽丝\n$等级$ 1\n$生命值$ 20/30\n"
        "$属性$ 10/10/10/10/10/10"
    )
    await _expect(app, char_matcher, _event(g, record, user_id=40001), "角色卡已设置")
    await _expect(
        app, npc_matcher, _event(g, ".npc 持久 爱丽丝"),
        "「爱丽丝」是玩家角色卡，不是NPC",
    )


@pytest.mark.asyncio
async def test_npc_mention_target(app: App):
    """.npc 的 @ 目标：命中玩家角色卡提示不是NPC；无卡玩家给建卡引导（真 @ 段）。"""
    from nonebot.adapters.onebot.v11 import MessageSegment

    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.npc import npc_matcher

    g = 110027
    record = (
        ".角色卡记录 $姓名$ 爱丽丝\n$等级$ 1\n$生命值$ 20/30\n"
        "$属性$ 10/10/10/10/10/10"
    )
    await _expect(app, char_matcher, _event(g, record, user_id=40002), "角色卡已设置")

    event = fake_group_message_event_v11(
        message=Message(".npc 持久 ") + MessageSegment.at(40002),
        group_id=g,
        user_id=40000,
    )
    await _expect(
        app, npc_matcher, event,
        Message(MessageSegment.at("40002")) + " 是玩家角色卡，不是NPC",
    )

    event = fake_group_message_event_v11(
        message=Message(".npc 持久 ") + MessageSegment.at(49999),
        group_id=g,
        user_id=40000,
    )
    await _expect(
        app, npc_matcher, event,
        Message(MessageSegment.at("49999"))
        + " 还没有在本群建立角色卡（可用 .角色卡记录 建卡后再试）",
    )
