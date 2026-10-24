"""能力 / 法术 / 法术位命令的 nonebug 测试（2026-10-20 批②）。

覆盖：``.能力`` 清单 / 详情 / 消耗恢复 / 模糊匹配、``.设置能力`` / ``.删除能力``；
``.法术`` 清单 / 准备切换 / 提醒开关、``.设置法术`` / ``.删除法术``；
``.法术位`` / ``.ss`` 的查看 / set / ±N / reset。存储按群隔离，掷骰无关。
"""

import nonebot
import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11

_GROUP = 87654340

_CARD = "\n".join([
    "$姓名$ 测试",
    "$等级$ 5",
    "$属性$ 10/10/10/10/10/10",
    "$限定资源$ 引导神力:2/2短休+1,长休; 圣疗:25/25长休",
    "$法术$ 施法属性:智力; 火球术:3*; 闪电束:3; 火焰箭:0",
    "$法术位$ 1:4/4; 2:3/3; 契约3:2/2",
])

_DETAIL_CARD = "\n".join([
    "$姓名$ 测试",
    "$等级$ 5",
    "$属性$ 10/10/10/10/10/10",
    "$法术$ 施法属性:智力; 豁免DC:15; "
    "火球术:3*|时间=1动作,距离=150尺,材料=是,备注=8d6 火焰",
])


@pytest.fixture(autouse=True)
def _clear_store():
    """每个用例前清空角色卡与施法设置（缓存 + JSON）。"""
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file
    from nonebot_plugin_dnddicer.data import spell_settings as _spell_settings

    _chars._cache = None
    _spell_settings._cache = None
    for name in ("cards.json", "spell_settings.json"):
        path = get_data_file(name)
        if path.exists():
            path.write_text("{}", encoding="utf-8")
    yield


def _event(text: str, user_id: int = 23001):
    return fake_group_message_event_v11(
        message=Message(text), group_id=_GROUP, user_id=user_id
    )


def _mention_event(
    prefix: str, at_uid: int, suffix: str = "", user_id: int = 23001
):
    from nonebot.adapters.onebot.v11 import MessageSegment

    return fake_group_message_event_v11(
        message=Message(prefix) + MessageSegment.at(at_uid) + suffix,
        group_id=_GROUP,
        user_id=user_id,
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _record(app: App, user_id: int = 23001, card: str = _CARD):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    content = card
    if "$姓名$" not in content:
        content = "$姓名$ 测试角色\n" + content
    await _expect(
        app, char_matcher, _event(f".角色卡新建 测试卡\n{content}", user_id), "已新建角色卡「测试卡」并绑定到本群。"
    )


# =========================================================================
# .能力
# =========================================================================


@pytest.mark.asyncio
async def test_ability_list_detail_and_modify(app: App):
    from nonebot_plugin_dnddicer.commands.feature import ability_matcher

    await _record(app)
    await _expect(
        app, ability_matcher, _event(".能力"),
        "当前限定资源（2 项）：\n"
        "1. 引导神力 2/2（短休+1，长休）\n"
        "2. 圣疗 25/25（长休）\n"
        "用法：.能力 名称 查看详情；.能力 名称 -N 消耗、+N 恢复",
    )
    await _expect(
        app, ability_matcher, _event(".能力 引导神力"),
        "引导神力：2/2（短休+1，长休）",
    )
    await _expect(
        app, ability_matcher, _event(".能力 引导神力 -1"),
        "引导神力：2/2 → 1/2",
    )
    await _expect(
        app, ability_matcher, _event(".能力 引导神力 -1"),
        "引导神力：1/2 → 0/2（已用尽）",
    )
    # 已经 0 时再消耗：明确提示用尽，不保存、不再显示 0/2 → 0/2
    await _expect(
        app, ability_matcher, _event(".能力 引导神力 -1"),
        "「引导神力」已经用尽（0/2）",
    )
    await _expect(
        app, ability_matcher, _event(".能力 引导神力 +1"),
        "引导神力：0/2 → 1/2",
    )
    await _expect(
        app, ability_matcher, _event(".能力 引导神力 +5"),
        "引导神力：1/2 → 2/2（已满）",
    )


@pytest.mark.asyncio
async def test_ability_fuzzy_match_and_errors(app: App):
    from nonebot_plugin_dnddicer.commands.feature import ability_matcher

    card = "\n".join([
        "$等级$ 5",
        "$属性$ 10/10/10/10/10/10",
        "$限定资源$ 引导神力:2/2短休; 引路神力:1/1长休",
    ])
    await _record(app, card=card)
    # 精确优先：输入完整名称命中同名条目
    await _expect(
        app, ability_matcher, _event(".能力 引路神力"),
        "引路神力：1/1（长休）",
    )
    # 子串同时命中两条：列候选、不执行
    await _expect(
        app, ability_matcher, _event(".能力 引"),
        "名称不明确「引」：候选 引导神力/引路神力（请写更完整的名称）",
    )
    await _expect(
        app, ability_matcher, _event(".能力 不存在"),
        "找不到限定资源「不存在」（可用 .设置能力 录入，.能力 查看清单）",
    )
    await _expect(
        app, ability_matcher, _event(".能力 引导神力 -0"), "次数至少为 1"
    )
    await _expect(
        app, ability_matcher, _event(".能力 +1"),
        "用法：.能力 [名称[±N]]；录入用 .设置能力 名称:当前/上限恢复，删除用 .删除能力 名称",
    )


@pytest.mark.asyncio
async def test_set_and_delete_ability(app: App):
    from nonebot_plugin_dnddicer.commands.feature import (
        ability_matcher,
        del_feature_matcher,
        set_feature_matcher,
    )

    await _record(app)
    await _expect(
        app, set_feature_matcher, _event(".设置能力 奥术回想:1/1短休"),
        "已设置限定资源：奥术回想（当前共 3 项）\n"
        "1. 引导神力 2/2（短休+1，长休）\n"
        "2. 圣疗 25/25（长休）\n"
        "3. 奥术回想 1/1（短休）",
    )
    # 同名覆盖：当前值一并按新写法重置
    await _expect(
        app, set_feature_matcher, _event(".设置能力 奥术回想:0/1短休"),
        "已设置限定资源：奥术回想（当前共 3 项）\n"
        "1. 引导神力 2/2（短休+1，长休）\n"
        "2. 圣疗 25/25（长休）\n"
        "3. 奥术回想 0/1（短休）",
    )
    await _expect(
        app, set_feature_matcher, _event(".设置能力 引导神力:2/2随便"),
        "限定资源恢复方式无效: 随便（可选：短休/长休/两者/手动，可加 +N 或 满）",
    )
    await _expect(
        app, del_feature_matcher, _event(".删除能力 奥术"),
        "已删除限定资源: 奥术回想",
    )
    await _expect(
        app, del_feature_matcher, _event(".删除能力 奥术"),
        "未找到限定资源: 奥术（可用 .设置能力 查看当前限定资源）",
    )
    await _expect(app, ability_matcher, _event(".能力"), (
        "当前限定资源（2 项）：\n"
        "1. 引导神力 2/2（短休+1，长休）\n"
        "2. 圣疗 25/25（长休）\n"
        "用法：.能力 名称 查看详情；.能力 名称 -N 消耗、+N 恢复"
    ))


@pytest.mark.asyncio
async def test_ability_requires_character(app: App):
    from nonebot_plugin_dnddicer.commands.feature import ability_matcher

    await _expect(app, ability_matcher, _event(".能力"), "你还没有在本群绑定角色卡，可发 .角色卡列表 查看卡库并绑定")


# =========================================================================
# .法术
# =========================================================================


@pytest.mark.asyncio
async def test_spell_list_prepare_and_cancel(app: App):
    from nonebot_plugin_dnddicer.commands.spell import spell_matcher

    await _record(app)
    await _expect(
        app, spell_matcher, _event(".法术"),
        "当前法术（3 项，施法属性：智力）：\n"
        "1. 火球术 3环（已准备）\n"
        "2. 闪电束 3环\n"
        "3. 火焰箭 戏法\n"
        "用法：.法术 准备/取消 名称；记录用 .设置法术 名称:环阶",
    )
    await _expect(
        app, spell_matcher, _event(".法术 准备 闪电束"),
        "已将「闪电束」标记为今日已准备（3环）。",
    )
    await _expect(
        app, spell_matcher, _event(".法术 准备 闪电束"),
        "「闪电束」已经是今日已准备状态（3环）。",
    )
    await _expect(
        app, spell_matcher, _event(".法术 取消 火球术"),
        "已取消「火球术」的准备标记（3环）。",
    )
    await _expect(
        app, spell_matcher, _event(".法术 取消 火球术"),
        "「火球术」当前没有准备标记（3环）。",
    )
    await _expect(
        app, spell_matcher, _event(".法术 准备 火焰箭"),
        "「火焰箭」是戏法，无需准备标记。",
    )
    await _expect(
        app, spell_matcher, _event(".法术 准备 火球"),
        "已将「火球术」标记为今日已准备（3环）。",
    )


@pytest.mark.asyncio
async def test_spell_reminder_toggle(app: App):
    from nonebot_plugin_dnddicer.commands.spell import spell_matcher

    await _record(app)
    await _expect(
        app, spell_matcher, _event(".法术 提醒"),
        "本处的施法未准备提醒：开启。发送 .法术 提醒 off 关闭。",
    )
    await _expect(
        app, spell_matcher, _event(".法术 提醒 off"),
        "已关闭本处的施法未准备提醒。",
    )
    await _expect(
        app, spell_matcher, _event(".法术 提醒"),
        "本处的施法未准备提醒：关闭。发送 .法术 提醒 on 开启。",
    )
    await _expect(
        app, spell_matcher, _event(".法术 提醒 开"),
        "已开启本处的施法未准备提醒。",
    )
    await _expect(
        app, spell_matcher, _event(".法术 提醒 随便"),
        "用法：.法术 提醒 on|off",
    )


@pytest.mark.asyncio
async def test_spell_reminder_works_without_card(app: App):
    """提醒是群级设置，无角色卡也能切换。"""
    from nonebot_plugin_dnddicer.commands.spell import spell_matcher

    await _expect(
        app, spell_matcher, _event(".法术 提醒 off"),
        "已关闭本处的施法未准备提醒。",
    )


@pytest.mark.asyncio
async def test_set_and_delete_spell(app: App):
    from nonebot_plugin_dnddicer.commands.spell import (
        del_spell_matcher,
        set_spell_matcher,
        spell_matcher,
    )

    await _record(app)
    await _expect(
        app, set_spell_matcher, _event(".设置法术 魔法飞弹:1*"),
        "已设置法术：魔法飞弹（当前共 4 项）\n"
        "1. 火球术 3环（已准备）\n"
        "2. 闪电束 3环\n"
        "3. 火焰箭 戏法\n"
        "4. 魔法飞弹 1环（已准备）",
    )
    # 普通设置不抹掉已准备标记；改环阶生效
    await _expect(
        app, set_spell_matcher, _event(".设置法术 火球术:4"),
        "已设置法术：火球术（当前共 4 项）\n"
        "1. 火球术 4环（已准备）\n"
        "2. 闪电束 3环\n"
        "3. 火焰箭 戏法\n"
        "4. 魔法飞弹 1环（已准备）",
    )
    await _expect(
        app, set_spell_matcher, _event(".设置法术 施法属性:感知"),
        "已设置施法属性：感知",
    )
    await _expect(
        app, spell_matcher, _event(".法术"),
        "当前法术（4 项，施法属性：感知）：\n"
        "1. 火球术 4环（已准备）\n"
        "2. 闪电束 3环\n"
        "3. 火焰箭 戏法\n"
        "4. 魔法飞弹 1环（已准备）\n"
        "用法：.法术 准备/取消 名称；记录用 .设置法术 名称:环阶",
    )
    await _expect(
        app, del_spell_matcher, _event(".删除法术 魔法"),
        "已删除法术: 魔法飞弹",
    )
    await _expect(
        app, del_spell_matcher, _event(".删除法术 不存在"),
        "未找到法术: 不存在（可用 .设置法术 查看当前法术）",
    )


@pytest.mark.asyncio
async def test_set_spell_details_and_header_keys(app: App):
    """批②：不写详情保留原值，写了详情整组覆盖；头键可单独设置。"""
    from nonebot_plugin_dnddicer.commands.spell import set_spell_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _record(app, card=_DETAIL_CARD)
    await _expect(
        app, set_spell_matcher, _event(".设置法术 火球术:4"),
        "已设置法术：火球术（当前共 1 项）\n"
        "1. 火球术 4环（已准备）",
    )
    char = await get_character(_GROUP, 23001)
    assert char.spells[0].cast_time == "1动作"
    assert char.spells[0].material is True
    assert char.spells[0].note == "8d6 火焰"

    await _expect(
        app, set_spell_matcher, _event(".设置法术 火球术:4|备注=新备注"),
        "已设置法术：火球术（当前共 1 项）\n"
        "1. 火球术 4环（已准备）",
    )
    char = await get_character(_GROUP, 23001)
    assert char.spells[0].cast_time == ""
    assert char.spells[0].note == "新备注"

    await _expect(
        app, set_spell_matcher, _event(".设置法术 豁免DC:16; 法术攻击:+8"),
        "已设置豁免 DC：16\n已设置法术攻击：+8",
    )
    char = await get_character(_GROUP, 23001)
    assert (char.spell_dc, char.spell_attack) == ("16", "+8")


# =========================================================================
# .法术位
# =========================================================================

@pytest.mark.asyncio
async def test_spell_slots_view_modify_and_reset(app: App):
    from nonebot_plugin_dnddicer.commands.spell import spell_slots_matcher

    await _record(app)
    await _expect(
        app, spell_slots_matcher, _event(".法术位"),
        "当前法术位：\n1环：4/4\n2环：3/3\n契约魔法（3环）：2/2",
    )
    await _expect(
        app, spell_slots_matcher, _event(".法术位 1 -1"),
        "1环：4/4 → 3/4",
    )
    await _expect(
        app, spell_slots_matcher, _event(".法术位 1 +1"),
        "1环：3/4 → 4/4（已满）",
    )
    await _expect(
        app, spell_slots_matcher, _event(".法术位 契约 -1"),
        "契约魔法（3环）：2/2 → 1/2",
    )
    await _expect(
        app, spell_slots_matcher, _event(".法术位 契约 -3"),
        "契约魔法（3环）：1/2 → 0/2（已用尽）",
    )
    await _expect(
        app, spell_slots_matcher, _event(".法术位 set 1:2, 2:1/3"),
        "已设置法术位：1环 2/2、2环 1/3\n"
        "当前法术位：\n1环：2/2\n2环：1/3\n契约魔法（3环）：0/2",
    )
    await _expect(
        app, spell_slots_matcher, _event(".ss"),
        "当前法术位：\n1环：2/2\n2环：1/3\n契约魔法（3环）：0/2",
    )
    await _expect(
        app, spell_slots_matcher, _event(".法术位 reset"),
        "已恢复全部法术位：\n1环：2/2\n2环：3/3\n契约魔法（3环）：2/2",
    )


@pytest.mark.asyncio
async def test_spell_slots_errors(app: App):
    from nonebot_plugin_dnddicer.commands.spell import spell_slots_matcher

    await _record(app)
    await _expect(
        app, spell_slots_matcher, _event(".法术位 4 -1"),
        "尚未记录4环法术位（可用 .法术位 set 4:4/4 设置）",
    )
    await _expect(
        app, spell_slots_matcher, _event(".法术位 set 1:5/4"),
        "法术位当前值不能超过上限: 1:5/4",
    )
    await _expect(
        app, spell_slots_matcher, _event(".法术位 随便"),
        "用法：.法术位 [set 环阶:当前/上限]；"
        ".法术位 1 -1 / 契约 -1 手动增减；.法术位 reset 恢复全部",
    )


@pytest.mark.asyncio
async def test_spell_slots_empty_and_no_card(app: App):
    from nonebot_plugin_dnddicer.commands.spell import spell_slots_matcher

    await _expect(
        app, spell_slots_matcher, _event(".法术位"), "你还没有在本群绑定角色卡，可发 .角色卡列表 查看卡库并绑定"
    )
    card = "$等级$ 1\n$属性$ 10/10/10/10/10/10"
    await _record(app, card=card)
    await _expect(
        app, spell_slots_matcher, _event(".法术位"),
        "还没有记录法术位。用法：.法术位 set 1:4,2:3"
        "（当前/上限写 1:4/4；契约魔法写 契约3:2/2）",
    )


# =========================================================================
# 目标代操作（2026-10-24：@玩家 / 角色名）
# =========================================================================

_TARGET_CARD = "\n".join([
    "$姓名$ 塔莉",
    "$等级$ 5",
    "$属性$ 10/10/10/10/10/10",
    "$限定资源$ 引导神力:2/2短休+1,长休; 圣疗:25/25长休",
    "$法术位$ 1:4/4; 2:3/3; 契约3:2/2",
])


async def _record_target(app: App, user_id: int = 23002, name: str = "塔莉"):
    card = _TARGET_CARD.replace("$姓名$ 塔莉", f"$姓名$ {name}")
    await _record(app, user_id=user_id, card=card)


@pytest.mark.asyncio
async def test_ability_target_by_mention_and_name(app: App):
    from nonebot_plugin_dnddicer.commands.feature import ability_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _record(app)
    await _record_target(app)

    await _expect(
        app, ability_matcher,
        _mention_event(".能力 ", 23002),
        "塔莉的限定资源（2 项）：\n"
        "1. 引导神力 2/2（短休+1，长休）\n"
        "2. 圣疗 25/25（长休）\n"
        "用法：.能力 名称 查看详情；.能力 名称 -N 消耗、+N 恢复",
    )
    await _expect(
        app, ability_matcher, _event(".能力 塔莉 引导神力 -1"),
        "塔莉的引导神力：2/2 → 1/2",
    )
    await _expect(
        app, ability_matcher,
        _mention_event(".能力 ", 23002, " 引导神力 +1"),
        "塔莉的引导神力：1/2 → 2/2（已满）",
    )
    await _expect(
        app, ability_matcher, _event(".能力 塔 圣疗"),
        "塔莉的圣疗：25/25（长休）",
    )
    # @ 自己：按目标形式查看本人，输出带角色名
    await _expect(
        app, ability_matcher, _mention_event(".能力 ", 23001),
        "测试的限定资源（2 项）：\n"
        "1. 引导神力 2/2（短休+1，长休）\n"
        "2. 圣疗 25/25（长休）\n"
        "用法：.能力 名称 查看详情；.能力 名称 -N 消耗、+N 恢复",
    )
    # 目标卡改动不影响本人卡
    self_char = await get_character(_GROUP, 23001)
    assert self_char.features[0].uses_cur == 2
    # DM 本人没有卡也能代操作
    await _expect(
        app, ability_matcher,
        _mention_event(".能力 ", 23002, " 圣疗 -1", user_id=23009),
        "塔莉的圣疗：25/25 → 24/25",
    )


@pytest.mark.asyncio
async def test_ability_target_errors(app: App):
    from nonebot.adapters.onebot.v11 import Message, MessageSegment

    from nonebot_plugin_dnddicer.commands.feature import ability_matcher

    await _record(app)
    await _record_target(app)
    await _record_target(app, user_id=23003, name="塔莉娅")

    await _expect(
        app, ability_matcher,
        _mention_event(".能力 ", 39990),
        Message(MessageSegment.at("39990")) + " 未在本群绑定角色卡",
    )
    await _expect(
        app, ability_matcher, _event(".能力 塔"),
        "目标名称不明确「塔」：候选 塔莉/塔莉娅（请写完整角色名或 @玩家）",
    )
    # 名称未命中任何卡：整段按本人能力名解析
    await _expect(
        app, ability_matcher, _event(".能力 查无此人"),
        "找不到限定资源「查无此人」（可用 .设置能力 录入，.能力 查看清单）",
    )


@pytest.mark.asyncio
async def test_spell_slots_target_operations(app: App):
    from nonebot_plugin_dnddicer.commands.spell import spell_slots_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _record(app)
    await _record_target(app)

    await _expect(
        app, spell_slots_matcher,
        _mention_event(".法术位 ", 23002),
        "塔莉的法术位：\n1环：4/4\n2环：3/3\n契约魔法（3环）：2/2",
    )
    await _expect(
        app, spell_slots_matcher,
        _mention_event(".法术位 ", 23002, " 1 -1"),
        "塔莉的1环：4/4 → 3/4",
    )
    await _expect(
        app, spell_slots_matcher, _event(".法术位 塔莉"),
        "塔莉的法术位：\n1环：3/4\n2环：3/3\n契约魔法（3环）：2/2",
    )
    await _expect(
        app, spell_slots_matcher, _event(".法术位 塔莉 set 1:2,2:1/3"),
        "已设置塔莉的法术位：1环 2/2、2环 1/3\n"
        "当前法术位：\n1环：2/2\n2环：1/3\n契约魔法（3环）：2/2",
    )
    await _expect(
        app, spell_slots_matcher, _event(".ss 塔莉 reset"),
        "已恢复塔莉的全部法术位：\n1环：2/2\n2环：3/3\n契约魔法（3环）：2/2",
    )
    self_char = await get_character(_GROUP, 23001)
    assert self_char.spell_slots.slots_cur[0] == 4
