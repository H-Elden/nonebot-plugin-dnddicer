"""死亡豁免闭环与群级规则版本命令测试（nonebug）。

覆盖批①的两项功能：

- ``.hp`` 伤害联动：HP 归 0 进入濒死、濒死中受击记失败、重击 +2、伤害 ≥ 上限即死、
  治疗清状态、稳定中受击重新开始、已死亡不被治疗复活；
- 击晕参数（两版结果不同：2024 降为 1 HP、2014 归 0 且伤势稳定）；
- ``.死亡豁免`` / ``.ds``：四种出目的掷骰结算、优势取高、手动裁决、状态与重置；
- ``.规则版本``：查看 / 设置 / 清除、写法归一、非法参数与私聊限制。

存储隔离：每个用例前清空角色卡与群配置缓存（含磁盘 JSON）；掷骰用
SequenceRuntime 固定骰值，断言逐字对齐实际输出。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_GROUP = 771001

#: 进入濒死的引导行（.hp 伤害把 HP 打到 0 时追加）
ENTER_DYING = "已进入濒死，请在自己回合开始时掷 .死亡豁免（3 次成功稳定、3 次失败死亡）。"
#: 稳定中再受伤的引导行
RESTART_DYING = "伤势稳定被打破，重新开始死亡豁免（请在自己回合开始时掷 .死亡豁免）。"


@pytest.fixture(autouse=True)
def _clear_data():
    """清空角色卡 / 群配置 / 先攻表（缓存 + JSON），保证用例互不干扰。"""
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file
    from nonebot_plugin_dnddicer.data import group_config as _group_config
    from nonebot_plugin_dnddicer.data import initiative as _init
    from nonebot_plugin_dnddicer.data import npc_health as _npc

    for module in (_chars, _group_config, _init, _npc):
        module._cache = None
    for name in ("characters.json", "group_config.json", "initiative.json",
                 "npc_health.json"):
        path = get_data_file(name)
        if path.exists():
            path.write_text("{}", encoding="utf-8")
    yield


def _event(text: str, user_id: int = 10001, group_id: int = _GROUP):
    return fake_group_message_event_v11(
        message=Message(text), group_id=group_id, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _set_rules_version(group_id: int, version: str) -> None:
    """直接写群级规则版本（绕过命令，供击晕闸门类用例铺垫）。"""
    from nonebot_plugin_dnddicer.character import rules
    from nonebot_plugin_dnddicer.data.group_config import set_group_config_field

    await set_group_config_field(group_id, rules.RULES_VERSION_FIELD, version)


def _roll(seq):
    return set_runtime(SequenceRuntime(seq))


async def _die(app: App, hp_matcher, uid: int, *, hp: str = "10/30", damage: int = 10):
    """把角色打到 0 HP 进入濒死（先记录 HP 再受一次伤害）。"""
    await _expect(app, hp_matcher, _event(f".hp {hp}", uid), f"test: HP={hp}\n当前HP:{hp}")
    max_hp = hp.split("/")[1]
    await _expect(
        app, hp_matcher, _event(f".hp -{damage}", uid),
        f"test: 当前HP减少{damage}\nHP:{hp} -> HP:0/{max_hp} 昏迷 濒死(成功0 失败0)\n{ENTER_DYING}",
    )


# =========================================================================
# .hp 伤害 → 死亡豁免闭环
# =========================================================================


@pytest.mark.asyncio
async def test_hp_damage_to_zero_enters_dying(app: App):
    """HP 归 0 → 昏迷 + 濒死引导（本次伤害不记失败）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    uid = 21001
    await _die(app, hp_matcher, uid, hp="20/30", damage=25)
    await _expect(app, hp_matcher, _event(".hp", uid), "test: HP:0/30 昏迷 濒死(成功0 失败0)")


@pytest.mark.asyncio
async def test_hp_damage_while_dying_records_failure(app: App):
    """濒死中再受伤 → 失败 +1（追加播报）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    uid = 21002
    await _die(app, hp_matcher, uid)
    await _expect(
        app, hp_matcher, _event(".hp -5", uid),
        "test: 当前HP减少5\nHP:0/30 昏迷 濒死(成功0 失败0) -> HP:0/30 昏迷 濒死(成功0 失败1)\n"
        "正在濒死中受到伤害：死亡豁免失败+1（成功0 失败1）",
    )


@pytest.mark.asyncio
async def test_hp_damage_over_max_is_instant_death(app: App):
    """单次伤害 ≥ HP 上限 → 即死（不进入濒死引导）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    uid = 21003
    await _expect(app, hp_matcher, _event(".hp 30/30", uid), "test: HP=30/30\n当前HP:30/30")
    await _expect(
        app, hp_matcher, _event(".hp -30", uid),
        "test: 当前HP减少30\nHP:30/30 -> HP:0/30 昏迷 已死亡\n"
        "受到30点伤害（≥生命值上限 30）——死亡。",
    )


@pytest.mark.asyncio
async def test_hp_heal_clears_death_state(app: App):
    """治疗使 HP 回正 → 濒死状态清除。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    uid = 21004
    await _die(app, hp_matcher, uid)
    await _expect(
        app, hp_matcher, _event(".hp +5", uid),
        "test: 当前HP增加5\nHP:0/30 昏迷 濒死(成功0 失败0) -> HP:5/30",
    )


@pytest.mark.asyncio
async def test_hp_dead_character_not_revived_by_heal(app: App):
    """已死亡的角色不被治疗复活（需 .死亡豁免 重置 裁决）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    uid = 21005
    await _expect(app, hp_matcher, _event(".hp 20/20", uid), "test: HP=20/20\n当前HP:20/20")
    await _expect(
        app, hp_matcher, _event(".hp -20", uid),
        "test: 当前HP减少20\nHP:20/20 -> HP:0/20 昏迷 已死亡\n"
        "受到20点伤害（≥生命值上限 20）——死亡。",
    )
    await _expect(
        app, hp_matcher, _event(".hp +10", uid),
        "test: 当前HP增加10\nHP:0/20 昏迷 已死亡 -> HP:0/20 昏迷 已死亡",
    )


@pytest.mark.asyncio
async def test_hp_weapon_critical_records_two_failures(app: App):
    """武器重击打在濒死者身上 → 失败 +2（重击伤害骰翻倍，表头与扣血一致）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    uid = 21006
    await _expect(
        app, char_matcher,
        _event(".角色卡记录 $姓名$ 甲 $等级$ 1 $生命值$ 10/30 "
               "$属性$ 10/10/10/10/10/10 $武器$ 短剑+5,1d8+3穿刺", uid),
        "角色卡已设置",
    )
    await _expect(
        app, hp_matcher, _event(".hp -10", uid),
        "甲: 当前HP减少10\nHP:10/30 -> HP:0/30 昏迷 濒死(成功0 失败0)\n" + ENTER_DYING,
    )
    token = _roll([3, 3])  # 重击：2d8 → [3+3]，加值 +3 只算一次 → 9
    try:
        await _expect(
            app, hp_matcher, _event(".hp 甲 -短剑重击伤害", uid),
            "甲用【短剑】造成了 9 点穿刺伤害（重击）：\n"
            "甲: 当前HP减少[3+3]+3=9\n"
            "HP:0/30 昏迷 濒死(成功0 失败0) -> HP:0/30 昏迷 濒死(成功0 失败2)\n"
            "正在濒死中受到伤害：死亡豁免失败+2（成功0 失败2）",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_hp_damage_while_stable_restarts(app: App):
    """伤势稳定中再受伤 → 解除稳定并重新开始死亡豁免。"""
    from nonebot_plugin_dnddicer.commands.hp import ds_matcher, hp_matcher

    uid = 21007
    await _die(app, hp_matcher, uid)
    await _expect(
        app, ds_matcher, _event(".ds 成功+3", uid),
        "test：死亡豁免成功已满 3 次：伤势稳定。",
    )
    await _expect(
        app, hp_matcher, _event(".hp -5", uid),
        "test: 当前HP减少5\nHP:0/30 昏迷 伤势稳定 -> HP:0/30 昏迷 濒死(成功0 失败0)\n" + RESTART_DYING,
    )
    await _expect(app, hp_matcher, _event(".hp", uid), "test: HP:0/30 昏迷 濒死(成功0 失败0)")


@pytest.mark.asyncio
async def test_hp_damage_to_npc_has_no_death_save(app: App):
    """NPC 血量走同一条伤害路径但不进死亡豁免（怪物不做死亡豁免）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    group, uid = 21008, 21009
    token = _roll([20])
    try:
        await _expect(
            app, initiative_matcher,
            _event(".ri 地精", uid, group),
            "地精的先攻值是 1D20=[20]=20",
        )
    finally:
        reset_runtime(token)
    await _expect(
        app, hp_matcher, _event(".hp 地精 10/10", uid, group),
        "地精: HP=10/10\n当前HP:10/10",
    )
    await _expect(
        app, hp_matcher, _event(".hp 地精 -10", uid, group),
        "地精: 当前HP减少10\nHP:10/10 -> HP:0/10 昏迷",
    )


# =========================================================================
# 击晕参数（两版结果不同）
# =========================================================================


@pytest.mark.asyncio
async def test_hp_stun_to_one_hp_in_2024_group(app: App):
    """5r 群内 .hp -N 击晕 → 改为降到 1 点 HP 并昏迷（2024 口径）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    uid = 23001
    await _expect(app, hp_matcher, _event(".hp 20/30", uid), "test: HP=20/30\n当前HP:20/30")
    await _expect(
        app, hp_matcher, _event(".hp -25 击晕", uid),
        "test: 已击晕（生命值降为 1 点并陷入昏迷，视为开始一次短休）",
    )
    await _expect(app, hp_matcher, _event(".hp", uid), "test: HP:1/30")


@pytest.mark.asyncio
async def test_hp_stun_to_zero_stable_in_2014_group(app: App):
    """5e 群内 .hp -N 击晕 → HP 归 0、昏迷但伤势稳定（2014 口径，截图同「稳定」语义）。"""
    from nonebot_plugin_dnddicer.commands.hp import ds_matcher, hp_matcher

    group, uid = 23002, 23003
    await _set_rules_version(group, "2014")
    await _expect(app, hp_matcher, _event(".hp 20/30", uid, group),
                  "test: HP=20/30\n当前HP:20/30")
    await _expect(
        app, hp_matcher, _event(".hp -25 击晕", uid, group),
        "test: 已击晕（生命值降为 0 点并陷入昏迷，但伤势稳定、无需死亡豁免）",
    )
    await _expect(
        app, hp_matcher, _event(".hp", uid, group), "test: HP:0/30 昏迷 伤势稳定"
    )
    # 稳定态下不需要掷死亡豁免（与「稳定」的通用语义一致）
    await _expect(
        app, ds_matcher, _event(".ds", uid, group),
        "伤势已稳定，无需再掷死亡豁免（再受伤将重新开始）。",
    )


@pytest.mark.asyncio
async def test_hp_stun_only_in_damage(app: App):
    """击晕只写在伤害写法里（设置/治疗时给用法引导）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, hp_matcher, _event(".hp 20/30 击晕", 23004),
        "击晕只能写在伤害写法里（用法：.hp 目标 -伤害表达式 击晕）。",
    )


# =========================================================================
# .死亡豁免 / .ds
# =========================================================================


@pytest.mark.asyncio
async def test_ds_no_character_card(app: App):
    """.ds 无角色卡 → 提示建卡。"""
    from nonebot_plugin_dnddicer.commands.hp import ds_matcher

    await _expect(app, ds_matcher, _event(".ds", 22001), "找不到角色卡")


@pytest.mark.asyncio
async def test_ds_hp_above_zero(app: App):
    """HP 大于 0 → 无需死亡豁免。"""
    from nonebot_plugin_dnddicer.commands.hp import ds_matcher, hp_matcher

    uid = 22002
    await _expect(app, hp_matcher, _event(".hp 20/30", uid), "test: HP=20/30\n当前HP:20/30")
    await _expect(app, ds_matcher, _event(".ds", uid), "HP 大于 0，无需死亡豁免。")


@pytest.mark.asyncio
async def test_ds_success_accumulates_and_stabilizes(app: App):
    """出目 15 与 12 各记一次成功；第三次成功转为稳定。"""
    from nonebot_plugin_dnddicer.commands.hp import ds_matcher, hp_matcher

    uid = 22003
    await _die(app, hp_matcher, uid)
    token = _roll([15, 12, 11])
    try:
        await _expect(
            app, ds_matcher, _event(".ds", uid),
            "test的死亡豁免：\n1D20=[15]=15\n"
            "死亡豁免成功 +1（成功1 失败0）\nHP:0/30 昏迷 濒死(成功1 失败0)",
        )
        await _expect(
            app, ds_matcher, _event(".ds", uid),
            "test的死亡豁免：\n1D20=[12]=12\n"
            "死亡豁免成功 +1（成功2 失败0）\nHP:0/30 昏迷 濒死(成功2 失败0)",
        )
        await _expect(
            app, ds_matcher, _event(".ds", uid),
            "test的死亡豁免：\n1D20=[11]=11\n"
            "死亡豁免成功：伤势稳定，不再需要掷死亡豁免（再受伤则重新开始死亡豁免）。\n"
            "HP:0/30 昏迷 伤势稳定",
        )
    finally:
        reset_runtime(token)
    await _expect(
        app, ds_matcher, _event(".ds", uid),
        "伤势已稳定，无需再掷死亡豁免（再受伤将重新开始）。",
    )
    await _expect(app, ds_matcher, _event(".ds 状态", uid), "test：HP:0/30 昏迷 伤势稳定")


@pytest.mark.asyncio
async def test_ds_natural_20_revives(app: App):
    """自然 20 → 回复 1 点 HP 并解除濒死。"""
    from nonebot_plugin_dnddicer.commands.hp import ds_matcher, hp_matcher

    uid = 22004
    await _die(app, hp_matcher, uid)
    token = _roll([20])
    try:
        await _expect(
            app, ds_matcher, _event(".ds", uid),
            "test的死亡豁免：\n1D20=[20]=20\n"
            "死亡豁免·自然20：回复 1 点 HP，伤势脱离濒死！\nHP:1/30",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_ds_natural_1_and_three_failures_die(app: App):
    """自然 1 → 失败 +2；再失败一次即死亡；死亡后掷骰被拦。"""
    from nonebot_plugin_dnddicer.commands.hp import ds_matcher, hp_matcher

    uid = 22005
    await _die(app, hp_matcher, uid)
    token = _roll([1, 5])
    try:
        await _expect(
            app, ds_matcher, _event(".ds", uid),
            "test的死亡豁免：\n1D20=[1]=1\n"
            "死亡豁免·自然1：失败 +2（成功0 失败2）\nHP:0/30 昏迷 濒死(成功0 失败2)",
        )
        await _expect(
            app, ds_matcher, _event(".ds", uid),
            "test的死亡豁免：\n1D20=[5]=5\n"
            "死亡豁免失败 +1，累计 3 次——死亡。\nHP:0/30 昏迷 已死亡",
        )
    finally:
        reset_runtime(token)
    await _expect(
        app, ds_matcher, _event(".ds", uid),
        "该角色已死亡。如需复活，请 DM 用 .死亡豁免 重置 裁决。",
    )
    await _expect(app, ds_matcher, _event(".ds 状态", uid), "test：HP:0/30 昏迷 已死亡")


@pytest.mark.asyncio
async def test_ds_advantage_keeps_higher_die(app: App):
    """优势取两颗中较高者（序列 20/3 → 保留 20）。"""
    from nonebot_plugin_dnddicer.commands.hp import ds_matcher, hp_matcher

    uid = 22006
    await _die(app, hp_matcher, uid)
    token = _roll([20, 3])
    try:
        await _expect(
            app, ds_matcher, _event(".ds 优势", uid),
            "test的死亡豁免：\n2D20K1=MAX{[20], [3]}=20\n"
            "死亡豁免·自然20：回复 1 点 HP，伤势脱离濒死！\nHP:1/30",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_ds_bad_modifier(app: App):
    """不支持的修饰串给用法引导；非法加值给参数提示（均不掷骰）。"""
    from nonebot_plugin_dnddicer.commands.hp import ds_matcher, hp_matcher

    uid = 22007
    await _die(app, hp_matcher, uid)
    await _expect(
        app, ds_matcher, _event(".ds abc", uid),
        "用法：.死亡豁免 [优势|劣势][±加值]；"
        "手动裁决 .死亡豁免 成功+1 / 失败+1 / 状态 / 重置",
    )
    await _expect(
        app, ds_matcher, _event(".ds 优势+abc", uid),
        "无效的死亡豁免修饰:+abc（支持 优势/劣势 与 ±加值）",
    )


@pytest.mark.asyncio
async def test_ds_manual_and_status_and_reset(app: App):
    """手动裁决、状态查询与重置（DM 裁决用）。"""
    from nonebot_plugin_dnddicer.commands.hp import ds_matcher, hp_matcher

    uid = 22008
    await _die(app, hp_matcher, uid)
    await _expect(
        app, ds_matcher, _event(".ds 成功+1", uid),
        "已记死亡豁免成功 +1（成功1 失败0）",
    )
    await _expect(
        app, ds_matcher, _event(".ds 失败+2", uid),
        "已记死亡豁免失败 +2（成功1 失败2）",
    )
    await _expect(
        app, ds_matcher, _event(".ds 状态", uid),
        "test：HP:0/30 昏迷 濒死(成功1 失败2)",
    )
    await _expect(
        app, ds_matcher, _event(".ds 重置", uid),
        "已重置test的死亡豁免状态（HP:0/30 昏迷 濒死(成功0 失败0)）。",
    )


# =========================================================================
# 长休与死亡豁免
# =========================================================================


@pytest.mark.asyncio
async def test_long_rest_clears_death_state(app: App):
    """长休回满 HP 并清空死亡豁免状态（不再濒死）。"""
    from nonebot_plugin_dnddicer.commands.hp import (
        ds_matcher,
        hp_matcher,
        long_rest_matcher,
    )

    uid = 22009
    await _die(app, hp_matcher, uid)
    await _expect(
        app, ds_matcher, _event(".ds 失败+1", uid),
        "已记死亡豁免失败 +1（成功0 失败1）",
    )
    await _expect(
        app, long_rest_matcher, _event(".长休", uid),
        "test进行了一次长休\n生命值回复至上限(30)",
    )
    await _expect(app, ds_matcher, _event(".ds", uid), "HP 大于 0，无需死亡豁免。")


# =========================================================================
# .规则版本
# =========================================================================


@pytest.mark.asyncio
async def test_rules_default_and_set(app: App):
    """未设置 → 跟随默认（2024）；设置后回显群级设置；默认 清除回落。"""
    from nonebot_plugin_dnddicer.commands.rules import rules_matcher

    group = 24001
    await _expect(
        app, rules_matcher, _event(".规则版本", 10001, group),
        "本群规则版本：2024（5r）（跟随骰主默认）。"
        "发送 .规则版本 5e 或 .规则版本 5r 可为本群单独设置。",
    )
    await _expect(
        app, rules_matcher, _event(".规则版本 5e", 10001, group),
        "已设置：本群规则版本为 2014（5e）。",
    )
    await _expect(
        app, rules_matcher, _event(".规则版本", 10001, group),
        "本群规则版本：2014（5e）。发送 .规则版本 5e 或 .规则版本 5r 修改。",
    )
    await _expect(
        app, rules_matcher, _event(".rules 5.5e", 10001, group),
        "已设置：本群规则版本为 2024（5r）。",
    )
    await _expect(
        app, rules_matcher, _event(".规则版本 默认", 10001, group),
        "已清除本群规则版本设置，恢复跟随骰主默认（当前 2024（5r））。",
    )


@pytest.mark.asyncio
async def test_rules_bad_arg_and_private(app: App):
    """非法写法给用法引导；私聊不可用。"""
    from nonebot_plugin_dnddicer.commands.rules import rules_matcher

    await _expect(
        app, rules_matcher, _event(".规则版本 6e", 10001, 24002),
        "无法识别「6e」。用法：.规则版本 [5e|5r]；无参数查看当前，"
        ".规则版本 默认 恢复跟随骰主默认",
    )
    event = fake_private_message_event_v11(message=Message(".规则版本"))
    await _expect(app, rules_matcher, event, "该指令仅在群聊中可用。")
