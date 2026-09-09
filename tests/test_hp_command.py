""".hp / .长休 nonebug 测试。

存储隔离：每个用例使用独立 user_id（角色卡主键 = 群+QQ），互不干扰。
掷骰用 SequenceRuntime 固定骰值，确保断言确定性。
"""

import nonebot
import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11

from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_GROUP = 87654321
_LIST_GROUP = 99001
_LIST_EMPTY_GROUP = 99002


@pytest.fixture(autouse=True)
def _clear_character_data():
    """每个用例前清空角色卡数据（缓存 + JSON），避免跨运行残留。"""
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file

    _chars._cache = None
    path = get_data_file("characters.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")
    yield


def _event(text: str, user_id: int = 10001):
    return fake_group_message_event_v11(
        message=Message(text), group_id=_GROUP, user_id=user_id
    )


def _event_in_group(group_id: int, text: str, user_id: int = 10001):
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
# .hp 查看
# =========================================================================


@pytest.mark.asyncio
async def test_hp_view_no_char(app: App):
    """.hp 无角色卡 → 找不到生命值信息。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    event = _event(".hp", user_id=20001)
    await _expect(app, hp_matcher, event, "找不到test的生命值信息")


@pytest.mark.asyncio
async def test_hp_view_after_set(app: App):
    """.hp 20/30 → 设置；.hp → 查看。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, hp_matcher, _event(".hp 20/30", user_id=20002),
        "test: HP=20/30\n当前HP:20/30",
    )
    await _expect(
        app, hp_matcher, _event(".hp", user_id=20002),
        "test: HP:20/30",
    )


# =========================================================================
# .hp 设置 / 调整
# =========================================================================


@pytest.mark.asyncio
async def test_hp_heal(app: App):
    """.hp +5 → 治疗（20/30 → 25/30）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(app, hp_matcher, _event(".hp 20/30", user_id=20003), "test: HP=20/30\n当前HP:20/30")
    await _expect(
        app, hp_matcher, _event(".hp +5", user_id=20003),
        "test: 当前HP增加5\nHP:20/30 -> HP:25/30",
    )


@pytest.mark.asyncio
async def test_hp_damage(app: App):
    """.hp -10 → 伤害（25/30 → 15/30）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(app, hp_matcher, _event(".hp 25/30", user_id=20004), "test: HP=25/30\n当前HP:25/30")
    await _expect(
        app, hp_matcher, _event(".hp -10", user_id=20004),
        "test: 当前HP减少10\nHP:25/30 -> HP:15/30",
    )


@pytest.mark.asyncio
async def test_hp_damage_to_unconscious(app: App):
    """.hp -30 → 伤害至 0，昏迷。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(app, hp_matcher, _event(".hp 20/30", user_id=20005), "test: HP=20/30\n当前HP:20/30")
    await _expect(
        app, hp_matcher, _event(".hp -30", user_id=20005),
        "test: 当前HP减少30\nHP:20/30 -> HP:0/30 昏迷",
    )


@pytest.mark.asyncio
async def test_hp_recover_from_unconscious(app: App):
    """从昏迷中治疗恢复（20/30 -20 → 0/30 昏迷，+15 → 15/30）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(app, hp_matcher, _event(".hp 20/30", user_id=20006), "test: HP=20/30\n当前HP:20/30")
    await _expect(
        app, hp_matcher, _event(".hp -20", user_id=20006),
        "test: 当前HP减少20\nHP:20/30 -> HP:0/30 昏迷",
    )
    await _expect(
        app, hp_matcher, _event(".hp +15", user_id=20006),
        "test: 当前HP增加15\nHP:0/30 昏迷 -> HP:15/30",
    )


# =========================================================================
# 临时 HP
# =========================================================================


@pytest.mark.asyncio
async def test_hp_temp_set(app: App):
    """.hp (10) → 设置临时 HP。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(app, hp_matcher, _event(".hp 20/30", user_id=20007), "test: HP=20/30\n当前HP:20/30")
    await _expect(
        app, hp_matcher, _event(".hp (10)", user_id=20007),
        "test: 临时HP=10\n当前HP:20/30 (10)",
    )


@pytest.mark.asyncio
async def test_hp_temp_absorbs_damage(app: App):
    """临时 HP 先吸收伤害（20/30 (10) - 15 → 临时 0，当前 15/30）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(app, hp_matcher, _event(".hp 20/30", user_id=20008), "test: HP=20/30\n当前HP:20/30")
    await _expect(app, hp_matcher, _event(".hp (10)", user_id=20008), "test: 临时HP=10\n当前HP:20/30 (10)")
    await _expect(
        app, hp_matcher, _event(".hp -15", user_id=20008),
        "test: 当前HP减少15\nHP:20/30 (10) -> HP:15/30",
    )


# =========================================================================
# 掷骰表达式
# =========================================================================


@pytest.mark.asyncio
async def test_hp_dice_heal(app: App):
    """.hp +2d6 → 掷骰治疗（SequenceRuntime [3,4] → 7）。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(app, hp_matcher, _event(".hp 20/30", user_id=20009), "test: HP=20/30\n当前HP:20/30")

    token = set_runtime(SequenceRuntime([3, 4]))
    try:
        await _expect(
            app, hp_matcher, _event(".hp +2d6", user_id=20009),
            "test: 当前HP增加[3+4]=7\nHP:20/30 -> HP:27/30",
        )
    finally:
        reset_runtime(token)


# =========================================================================
# .hp list / .hp del
# =========================================================================


@pytest.mark.asyncio
async def test_hp_list(app: App):
    """.hp list → 列出群内所有 PC HP；无卡名成员名称回退链走群成员信息 API。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(app, hp_matcher, _event_in_group(_LIST_GROUP, ".hp 20/30", user_id=20010), "test: HP=20/30\n当前HP:20/30")
    await _expect(app, hp_matcher, _event_in_group(_LIST_GROUP, ".hp 15/25", user_id=20011), "test: HP=15/25\n当前HP:15/25")

    event = _event_in_group(_LIST_GROUP, ".hp list", user_id=20010)
    async with app.test_matcher(hp_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        # 无卡名成员逐个查询：20010 无群名片 → QQ 昵称「阿强」；
        # 20011 群名片「铁匠铺」优先于昵称「阿花」
        ctx.should_call_api(
            "get_group_member_info",
            data={"group_id": _LIST_GROUP, "user_id": 20010},
            result={"user_id": 20010, "card": "", "nickname": "阿强"},
        )
        ctx.should_call_api(
            "get_group_member_info",
            data={"group_id": _LIST_GROUP, "user_id": 20011},
            result={"user_id": 20011, "card": "铁匠铺", "nickname": "阿花"},
        )
        ctx.should_call_send(event, "阿强 HP:20/30\n铁匠铺 HP:15/25")
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_hp_list_char_name_takes_priority(app: App):
    """.hp list 有角色卡名的成员直接用卡名，不触发群成员信息 API。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, char_matcher,
        _event_in_group(_LIST_GROUP,
                        ".角色卡记录 $姓名$ 战士小明\n$等级$ 1\n$属性$ 10/10/10/10/10/10\n$生命值$ 20/30",
                        user_id=20014),
        "角色卡已设置",
    )
    await _expect(
        app, hp_matcher, _event_in_group(_LIST_GROUP, ".hp 10/20", user_id=20015),
        "test: HP=10/20\n当前HP:10/20",
    )

    event = _event_in_group(_LIST_GROUP, ".hp list", user_id=20014)
    async with app.test_matcher(hp_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        # 20015 无卡名仍需查询（结果昵称「阿花」）
        ctx.should_call_api(
            "get_group_member_info",
            data={"group_id": _LIST_GROUP, "user_id": 20015},
            result={"user_id": 20015, "card": "", "nickname": "阿花"},
        )
        ctx.should_call_send(event, "战士小明 HP:20/30\n阿花 HP:10/20")
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_hp_list_api_failure_falls_back(app: App):
    """.hp list 群成员 API 失败 → 回退「未知玩家」（非 QQ 号），列表不受影响。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(app, hp_matcher, _event_in_group(_LIST_GROUP, ".hp 20/30", user_id=20016), "test: HP=20/30\n当前HP:20/30")

    event = _event_in_group(_LIST_GROUP, ".hp list", user_id=20016)
    async with app.test_matcher(hp_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_api(
            "get_group_member_info",
            data={"group_id": _LIST_GROUP, "user_id": 20016},
            exception=Exception("群成员查询失败"),
        )
        ctx.should_call_send(event, "未知玩家 HP:20/30")
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_hp_list_empty(app: App):
    """.hp list 无 HP → 本群没有任何生命值信息。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, hp_matcher, _event_in_group(_LIST_EMPTY_GROUP, ".hp list", user_id=20012),
        "本群没有任何生命值信息",
    )


@pytest.mark.asyncio
async def test_hp_del(app: App):
    """.hp del → 删除 HP 信息。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(app, hp_matcher, _event(".hp 20/30", user_id=20013), "test: HP=20/30\n当前HP:20/30")
    await _expect(
        app, hp_matcher, _event(".hp del", user_id=20013),
        "已删除test的生命值信息",
    )
    await _expect(
        app, hp_matcher, _event(".hp", user_id=20013),
        "找不到test的生命值信息",
    )


# =========================================================================
# 目标指定
# =========================================================================


@pytest.mark.asyncio
async def test_hp_target_other(app: App):
    """.hp 爱丽丝 20/30 → 设置另一角色 HP。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    record = (
        "$姓名$ 爱丽丝\n$等级$ 1\n$生命值$ 20/30\n"
        "$属性$ 10/10/10/10/10/10"
    )
    await _expect(app, char_matcher, _event(f".角色卡记录 {record}", user_id=20014), "角色卡已设置")

    await _expect(
        app, hp_matcher, _event(".hp 爱丽丝 15/30", user_id=20015),
        "爱丽丝: HP=15/30\n当前HP:15/30",
    )


@pytest.mark.asyncio
async def test_hp_target_not_found(app: App):
    """.hp 不存在 10 → 找不到。"""
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, hp_matcher, _event(".hp 不存在 10", user_id=20016),
        "找不到不存在的生命值信息",
    )


# =========================================================================
# .长休
# =========================================================================


@pytest.mark.asyncio
async def test_long_rest(app: App):
    """.长休 → 恢复 HP 至上限 + 回复生命骰。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher, long_rest_matcher

    # 先设置角色卡（含生命骰）
    record = (
        "$姓名$ test\n$等级$ 4\n$生命值$ 20/30(5)\n"
        "$生命骰$ 2/4 D8\n$属性$ 10/10/10/10/10/10"
    )
    await _expect(app, char_matcher, _event(f".角色卡记录 {record}", user_id=20020), "角色卡已设置")

    # 再设置当前 HP 为 10/30 (5)
    await _expect(app, hp_matcher, _event(".hp 10/30 (5)", user_id=20020), "test: HP=10/30 (5)\n当前HP:10/30 (5)")

    event = _event(".长休", user_id=20020)
    async with app.test_matcher(long_rest_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(
            event,
            "test进行了一次长休\n"
            "生命值回复至上限(30) 5点临时生命值失效\n"
            "回复2个生命骰, 当前拥有4/4个D8生命骰",
        )
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_long_rest_no_char(app: App):
    """.长休 无角色卡 → 找不到角色卡信息。"""
    from nonebot_plugin_dnddicer.commands.hp import long_rest_matcher

    await _expect(
        app, long_rest_matcher, _event(".长休", user_id=20021),
        "找不到test的角色卡信息",
    )


# =========================================================================
# HPInfo 单元测试
# =========================================================================


def test_hp_info_take_damage_temp_absorbs():
    """临时 HP 完全吸收伤害。"""
    from nonebot_plugin_dnddicer.character.models import HPInfo

    hp = HPInfo(is_init=True, hp_cur=20, hp_max=30, hp_temp=10)
    hp.take_damage(8)
    assert hp.hp_temp == 2
    assert hp.hp_cur == 20
    assert hp.is_alive is True


def test_hp_info_take_damage_temp_overflow():
    """临时 HP 部分吸收，溢出扣当前 HP。"""
    from nonebot_plugin_dnddicer.character.models import HPInfo

    hp = HPInfo(is_init=True, hp_cur=20, hp_max=30, hp_temp=5)
    hp.take_damage(15)
    assert hp.hp_temp == 0
    assert hp.hp_cur == 10
    assert hp.is_alive is True


def test_hp_info_take_damage_lethal():
    """致命伤害 → 昏迷。"""
    from nonebot_plugin_dnddicer.character.models import HPInfo

    hp = HPInfo(is_init=True, hp_cur=10, hp_max=30)
    hp.take_damage(15)
    assert hp.hp_cur == 0
    assert hp.is_alive is False


def test_hp_info_heal_cap():
    """治疗不超过最大 HP。"""
    from nonebot_plugin_dnddicer.character.models import HPInfo

    hp = HPInfo(is_init=True, hp_cur=25, hp_max=30)
    hp.heal(100)
    assert hp.hp_cur == 30


def test_hp_info_heal_from_unconscious():
    """从昏迷（HP=0, is_alive=False）中恢复。"""
    from nonebot_plugin_dnddicer.character.models import HPInfo

    hp = HPInfo(is_init=True, hp_cur=0, hp_max=30, is_alive=False)
    hp.heal(15)
    assert hp.hp_cur == 15
    assert hp.is_alive is True


def test_hp_info_is_record_normal():
    """is_record_normal 双模式判断。"""
    from nonebot_plugin_dnddicer.character.models import HPInfo

    hp = HPInfo(is_init=True, hp_cur=10, hp_max=30)
    assert hp.is_record_normal() is True
    assert hp.is_record_damage() is False

    hp2 = HPInfo(is_init=True, hp_cur=0, hp_max=30, is_alive=True)
    assert hp2.is_record_normal() is False
    assert hp2.is_record_damage() is True

    hp3 = HPInfo(is_init=True, hp_cur=0, hp_max=30, is_alive=False)
    assert hp3.is_record_normal() is True


def test_hp_info_get_info_modes():
    """get_info 在不同 HP 模式下的输出。"""
    from nonebot_plugin_dnddicer.character.models import HPInfo

    hp = HPInfo(is_init=True, hp_cur=20, hp_max=30, hp_temp=5)
    assert hp.get_info() == "HP:20/30 (5)"

    hp2 = HPInfo(is_init=True, hp_cur=0, hp_max=30, is_alive=False)
    assert hp2.get_info() == "HP:0/30 昏迷"

    hp3 = HPInfo(is_init=True, hp_cur=-10, hp_max=30, is_alive=True)
    assert hp3.get_info() == "损失HP:10"


def test_hp_info_long_rest():
    """长休：恢复 HP、清除临时 HP、回复生命骰。"""
    from nonebot_plugin_dnddicer.character.models import HPInfo

    hp = HPInfo(
        is_init=True, hp_cur=10, hp_max=30, hp_temp=5,
        hp_dice_type=8, hp_dice_num=2, hp_dice_max=4,
    )
    info = hp.long_rest()
    assert hp.hp_cur == 30
    assert hp.hp_temp == 0
    assert hp.hp_dice_num == 4
    assert "生命值回复至上限(30)" in info
    assert "5点临时生命值失效" in info
    assert "回复2个生命骰" in info
    assert "4/4个D8生命骰" in info


def test_hp_info_fresh_set_zero_quirk():
    """对齐 DicePP 边界：全新 HPInfo（hp_cur=0, is_alive=True）不处于正常记录模式，
    直接设置 0/max 后 get_info 仍落入受损记录模式显示 损失HP:0（DicePP 原版行为）。"""
    from nonebot_plugin_dnddicer.character.models import HPInfo

    hp = HPInfo()
    assert hp.is_record_normal() is False
    hp.hp_cur = 0
    hp.hp_max = 30
    assert hp.get_info() == "损失HP:0"


# =========================================================================
# DM 掷伤害（目标 + 伤害表达式 / AOE 多目标 / 抗性·易伤后缀）
# =========================================================================


def _record_with_hp(name: str, user_id: int, hp: str = "20/30"):
    """返回带 $生命值$ 的角色卡记录命令文本（姓名唯一用于目标匹配）。"""
    return (
        f".角色卡记录 $姓名$ {name}\n$等级$ 1\n$生命值$ {hp}\n"
        "$属性$ 10/10/10/10/10/10"
    )


@pytest.mark.asyncio
async def test_hp_dm_single_target_damage_expr(app: App):
    """.hp 爱丽丝 -d8+3+d6 → 空格后 - 识别为伤害，表达式整体求值一次扣减。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, char_matcher, _event(_record_with_hp("爱丽丝", 22001), user_id=22001),
        "角色卡已设置",
    )

    token = set_runtime(SequenceRuntime([5, 2]))  # d8=5, d6=2 → 5+3+2=10
    try:
        await _expect(
            app, hp_matcher, _event(".hp 爱丽丝 -d8+3+d6", user_id=22000),
            "爱丽丝: 当前HP减少[5]+3+[2]=10\nHP:20/30 -> HP:10/30",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_hp_dm_aoe_multi_target(app: App):
    """.hp 爱丽丝；莎白 -d12-2 → AOE：伤害只掷一次，各目标分别扣减（短反馈单行）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, char_matcher, _event(_record_with_hp("爱丽丝", 22002), user_id=22002),
        "角色卡已设置",
    )
    await _expect(
        app, char_matcher,
        _event(_record_with_hp("莎白", 22003, hp="18/30"), user_id=22003),
        "角色卡已设置",
    )

    token = set_runtime(SequenceRuntime([7]))  # d12=7 → 7-2=5
    try:
        await _expect(
            app, hp_matcher, _event(".hp 爱丽丝；莎白 -d12-2", user_id=22000),
            "爱丽丝: 当前HP减少[7]-2=5; HP:20/30 -> HP:15/30\n"
            "莎白: 当前HP减少[7]-2=5; HP:18/30 -> HP:13/30",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_hp_dm_aoe_semicolon_halfwidth(app: App):
    """半角分号 ; 分隔多目标同样生效。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, char_matcher, _event(_record_with_hp("爱丽丝", 22004), user_id=22004),
        "角色卡已设置",
    )
    await _expect(
        app, char_matcher,
        _event(_record_with_hp("莎白", 22005, hp="18/30"), user_id=22005),
        "角色卡已设置",
    )

    token = set_runtime(SequenceRuntime([7]))
    try:
        await _expect(
            app, hp_matcher, _event(".hp 爱丽丝;莎白 -d12-2", user_id=22000),
            "爱丽丝: 当前HP减少[7]-2=5; HP:20/30 -> HP:15/30\n"
            "莎白: 当前HP减少[7]-2=5; HP:18/30 -> HP:13/30",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_hp_dm_resistance_and_vulnerability(app: App):
    """.hp 爱丽丝抗性；莎白易伤；布莱克 -d12-2 → 每目标按自身承伤因子结算。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, char_matcher, _event(_record_with_hp("爱丽丝", 22006), user_id=22006),
        "角色卡已设置",
    )
    await _expect(
        app, char_matcher,
        _event(_record_with_hp("莎白", 22007, hp="18/30"), user_id=22007),
        "角色卡已设置",
    )
    await _expect(
        app, char_matcher,
        _event(_record_with_hp("布莱克", 22008, hp="15/30"), user_id=22008),
        "角色卡已设置",
    )

    token = set_runtime(SequenceRuntime([7]))  # 掷出 5 点：抗性→2、易伤→10、全额→5
    try:
        await _expect(
            app, hp_matcher,
            _event(".hp 爱丽丝抗性；莎白易伤；布莱克 -d12-2", user_id=22000),
            "爱丽丝: 当前HP减少[7]-2=5（抗性减半→2）; HP:20/30 -> HP:18/30\n"
            "莎白: 当前HP减少[7]-2=5（易伤加倍→10）; HP:18/30 -> HP:8/30\n"
            "布莱克: 当前HP减少[7]-2=5; HP:15/30 -> HP:10/30",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_hp_factor_suffix_only_for_damage(app: App):
    """.hp 爱丽丝抗性 20（设置）→ 抗性/易伤后缀仅对伤害生效。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    await _expect(
        app, char_matcher, _event(_record_with_hp("爱丽丝", 22009), user_id=22009),
        "角色卡已设置",
    )
    await _expect(
        app, hp_matcher, _event(".hp 爱丽丝抗性 20", user_id=22000),
        "抗性/易伤后缀仅对伤害生效（用法：.hp 目标[抗性/易伤] -伤害表达式）。",
    )
