""".角色卡 / .状态 / 检定点命令 nonebug 测试。

存储隔离：每个用例使用独立 user_id（角色卡主键 = 群+QQ），互不干扰。
"""

import nonebot
import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_GROUP = 87654321


@pytest.fixture(autouse=True)
def _clear_store():
    """每个用例前清空角色卡/先攻表数据（缓存 + JSON）。

    查看他人整卡与名称搜索是群级查询，清空可避免历史残留带来的多匹配。
    """
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file
    from nonebot_plugin_dnddicer.data import initiative as _init
    from nonebot_plugin_dnddicer.data import npc_health as _npc

    _chars._cache = None
    _init._cache = None
    _npc._cache = None
    for name in ("characters.json", "initiative.json", "npc_health.json"):
        path = get_data_file(name)
        if path.exists():
            path.write_text("{}", encoding="utf-8")
    yield


def _event(text: str, user_id: int = 10001):
    return fake_group_message_event_v11(
        message=Message(text), group_id=_GROUP, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


_RECORD = (
    ".角色卡记录 $姓名$ 伊丽莎白\n"
    "$等级$ 5\n"
    "$生命值$ 20/30(5)\n"
    "$生命骰$ 3/4 D8\n"
    "$属性$ 15/14/13/12/10/8\n"
    "$熟练$ 力量/隐匿\n"
    "$额外加值$ 隐匿:优势"
)


@pytest.mark.asyncio
async def test_char_template(app: App):
    """.角色卡模板 → 示例角色卡文本 + 属性顺序/额外加值提示。"""
    from nonebot_plugin_dnddicer.character.services import gen_template_char
    from nonebot_plugin_dnddicer.commands.character import _gen_template_feedback, char_matcher

    expected = _gen_template_feedback()
    assert "$" not in expected.split("——提示")[1], "提示说明文字不得含 $ 字符"
    assert expected.endswith(
        "额外加值段键 = 六属性/技能/豁免/攻击条目, 另有作用于全部的全局键: 豁免 与 攻击\n"
        "额外加值取值 = 可选 优势/劣势 前缀 + ±掷骰表达式, 如: 隐匿:优势+2"
    )
    assert gen_template_char().get_char_info() in expected

    event = _event(".角色卡模板")
    await _expect(app, char_matcher, event, expected)


@pytest.mark.asyncio
async def test_char_miss(app: App):
    """无卡时查看 → 找不到角色卡。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    event = _event(".角色卡", user_id=10002)
    await _expect(app, char_matcher, event, "找不到角色卡")


@pytest.mark.asyncio
async def test_char_set_and_view(app: App):
    """记录 → 成功；再查看 → 输出与存储一致的卡文本。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _expect(app, char_matcher, _event(_RECORD, user_id=10003), "角色卡已设置")

    char = await get_character(_GROUP, 10003)
    assert char is not None and char.name == "伊丽莎白"
    expected = char.get_char_info()
    assert "$姓名$ 伊丽莎白" in expected
    assert "$属性$ 15/14/13/12/10/8" in expected

    event = _event(".角色卡", user_id=10003)
    await _expect(app, char_matcher, event, expected)


@pytest.mark.asyncio
async def test_char_state(app: App):
    """.状态 → HP 摘要（记录中含生命值/生命骰）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, state_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=10008), "角色卡已设置")

    event = _event(".状态", user_id=10008)
    await _expect(
        app,
        state_matcher,
        event,
        "HP:20/30 (5)\n生命骰:3/4 D8",
    )


@pytest.mark.asyncio
async def test_char_delete(app: App):
    """清除后 → 找不到角色卡。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=10005), "角色卡已设置")
    await _expect(app, char_matcher, _event(".角色卡清除", user_id=10005), "角色卡已删除")
    await _expect(app, char_matcher, _event(".角色卡", user_id=10005), "找不到角色卡")


@pytest.mark.asyncio
async def test_check_strength_full_feedback(app: App):
    """.力量检定 → 完整检定反馈（属性检定展示名=力量检定；骰 10，力量 15 → 15）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=10006), "角色卡已设置")

    token = set_runtime(SequenceRuntime([10]))
    try:
        event = _event(".力量检定", user_id=10006)
        # 伊丽莎白 5级 力量15：熟练(力量熟练)加值 3 + 力量调整 2，骰 10 → 15
        expected = (
            "伊丽莎白进行【力量检定】：\n"
            "熟练加值:3 力量调整值:2\n"
            "1D20+2+3=[10]+2+3=15"
        )
        await _expect(app, check_matcher, event, expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_check_saving_and_attack_display_name(app: App):
    """.体质豁免/.敏捷攻击 → 展示名用原名（不含「检定」后缀）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=10009), "角色卡已设置")

    # 伊丽莎白 体质13 → 调整+1，未熟练（默认全不熟练）
    token = set_runtime(SequenceRuntime([9]))
    try:
        event = _event(".体质豁免", user_id=10009)
        expected = (
            "伊丽莎白进行【体质豁免】：\n"
            "无熟练加值 体质调整值:1\n"
            "1D20+1=[9]+1=10"
        )
        await _expect(app, check_matcher, event, expected)
    finally:
        reset_runtime(token)

    # 伊丽莎白 敏捷14 → 调整+2；攻击默认不熟练，无熟练加值
    token = set_runtime(SequenceRuntime([3]))
    try:
        event = _event(".敏捷攻击", user_id=10009)
        expected = (
            "伊丽莎白进行【敏捷攻击】：\n"
            "无熟练加值 敏捷调整值:2\n"
            "1D20+2=[3]+2=5"
        )
        await _expect(app, check_matcher, event, expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_check_miss_without_char(app: App):
    """无卡时检定 → 找不到角色卡。"""
    from nonebot_plugin_dnddicer.commands.character import check_matcher

    event = _event(".力量检定", user_id=10007)
    await _expect(app, check_matcher, event, "找不到角色卡")


@pytest.mark.asyncio
async def test_check_critical_success_and_failure(app: App):
    """.力量检定 掷 20/1 → 播报大成功/大失败（检定与 .r 播报统一）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=10010), "角色卡已设置")

    token = set_runtime(SequenceRuntime([20]))
    try:
        event = _event(".力量检定", user_id=10010)
        expected = (
            "伊丽莎白进行【力量检定】：\n"
            "熟练加值:3 力量调整值:2\n"
            "1D20+2+3=[20]+2+3=25 好耶！大成功!"
        )
        await _expect(app, check_matcher, event, expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([1]))
    try:
        event = _event(".力量检定", user_id=10010)
        expected = (
            "伊丽莎白进行【力量检定】：\n"
            "熟练加值:3 力量调整值:2\n"
            "1D20+2+3=[1]+2+3=6 哇哦！大失败!"
        )
        await _expect(app, check_matcher, event, expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_attack_critical_failure(app: App):
    """.敏捷攻击 掷自然 1 → 播报大失败（攻击自然 1 必失误，与自然 20 对偶）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=10011), "角色卡已设置")

    token = set_runtime(SequenceRuntime([1]))
    try:
        event = _event(".敏捷攻击", user_id=10011)
        expected = (
            "伊丽莎白进行【敏捷攻击】：\n"
            "无熟练加值 敏捷调整值:2\n"
            "1D20+2=[1]+2=3 哇哦！大失败!"
        )
        await _expect(app, check_matcher, event, expected)
    finally:
        reset_runtime(token)


# =========================================================================
# @ 提及目标（2026-09-22：查看他人整卡 / .状态 / 代掷）
# =========================================================================


def _mention_event(*parts, user_id: int = 31000):
    """构造带 @ 段的群消息事件（parts 依次拼接，可为文本或消息段）。"""
    message = Message()
    for part in parts:
        message += part
    return fake_group_message_event_v11(
        message=message, group_id=_GROUP, user_id=user_id
    )


@pytest.mark.asyncio
async def test_char_view_other_by_mention_and_name(app: App):
    """.角色卡 @玩家 与 .角色卡 名称 → 查看他人整卡（含标题行，两种写法等价）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _expect(app, char_matcher, _event(_RECORD, user_id=31010), "角色卡已设置")
    target = await get_character(_GROUP, 31010)
    assert target is not None
    expected = "伊丽莎白 的角色卡：\n" + target.get_char_info()

    await _expect(
        app, char_matcher,
        _mention_event(".角色卡 ", MessageSegment.at(31010)),
        expected,
    )
    await _expect(app, char_matcher, _event(".角色卡 伊丽莎白"), expected)


@pytest.mark.asyncio
async def test_char_view_other_misses(app: App):
    """查看他人未命中：@ 无卡引导 / 名称命中NPC条目 / 名称查无此卡。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(
        app, initiative_matcher, _event(".ri20 独目守卫"),
        "独目守卫的先攻值是 20",
    )
    await _expect(
        app, char_matcher, _event(".角色卡 独目守卫"),
        "「独目守卫」是NPC条目，没有角色卡",
    )
    await _expect(
        app, char_matcher, _event(".角色卡 查无此人"),
        "找不到查无此人的角色卡",
    )
    await _expect(
        app, char_matcher,
        _mention_event(".角色卡 ", MessageSegment.at(39990)),
        Message(MessageSegment.at("39990"))
        + " 还没有在本群建立角色卡（可用 .角色卡记录 建卡后再试）",
    )


@pytest.mark.asyncio
async def test_char_record_and_clear_write_self_only(app: App):
    """记录/清除恒为发送者本人：带 @他人 不改变他人卡（查看开放、修改仅本人）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _expect(app, char_matcher, _event(_RECORD, user_id=31011), "角色卡已设置")
    # 发送者 31000 带 @31011 记录 → 只写自己的卡
    await _expect(
        app, char_matcher,
        _mention_event(
            ".角色卡记录 ",
            MessageSegment.at(31011),
            " $姓名$ 自己的卡\n$等级$ 1\n$属性$ 10/10/10/10/10/10",
        ),
        "角色卡已设置",
    )
    sender = await get_character(_GROUP, 31000)
    target = await get_character(_GROUP, 31011)
    assert sender is not None and sender.name == "自己的卡"
    assert target is not None and target.name == "伊丽莎白"

    # 发送者带 @31011 清除 → 只删自己的卡
    await _expect(
        app, char_matcher,
        _mention_event(".角色卡清除 ", MessageSegment.at(31011)),
        "角色卡已删除",
    )
    assert await get_character(_GROUP, 31000) is None
    assert await get_character(_GROUP, 31011) is not None


@pytest.mark.asyncio
async def test_state_mention_target(app: App):
    """.状态 @玩家 → 带角色名前缀的他人状态；无卡 → 真 @ 段引导。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, state_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=31012), "角色卡已设置")
    await _expect(
        app, state_matcher,
        _mention_event(".状态 ", MessageSegment.at(31012)),
        "伊丽莎白: HP:20/30 (5)\n生命骰:3/4 D8",
    )
    await _expect(
        app, state_matcher,
        _mention_event(".状态 ", MessageSegment.at(39992)),
        Message(MessageSegment.at("39992"))
        + " 还没有在本群建立角色卡（可用 .角色卡记录 建卡后再试）",
    )


@pytest.mark.asyncio
async def test_check_mention_target(app: App):
    """.力量豁免 @玩家 / .2#敏捷攻击优势 @玩家 → 用目标角色卡代掷。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=31013), "角色卡已设置")

    token = set_runtime(SequenceRuntime([9]))
    try:
        await _expect(
            app, check_matcher,
            _mention_event(".力量豁免 ", MessageSegment.at(31013)),
            "伊丽莎白进行【力量豁免】：\n无熟练加值 力量调整值:2\n"
            "1D20+2=[9]+2=11",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([9, 7]))
    try:
        await _expect(
            app, check_matcher,
            _mention_event(".敏捷攻击优势 ", MessageSegment.at(31013)),
            "伊丽莎白进行【敏捷攻击】：\n无熟练加值 敏捷调整值:2\n"
            "2D20K1+2=MAX{[9], [7]}+2=11",
        )
    finally:
        reset_runtime(token)

    # 连掷：.2#敏捷攻击 @玩家 → 两次代掷
    token = set_runtime(SequenceRuntime([3, 4]))
    try:
        await _expect(
            app, check_matcher,
            _mention_event(".2#敏捷攻击 ", MessageSegment.at(31013)),
            "伊丽莎白进行【2次敏捷攻击】：\n无熟练加值 敏捷调整值:2\n"
            "1D20+2=[3]+2=5\n1D20+2=[4]+2=6",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_check_mention_no_char(app: App):
    """检定点命令的 @ 目标无卡 → 真 @ 段引导建卡。"""
    from nonebot_plugin_dnddicer.commands.character import check_matcher

    await _expect(
        app, check_matcher,
        _mention_event(".力量豁免 ", MessageSegment.at(39993)),
        Message(MessageSegment.at("39993"))
        + " 还没有在本群建立角色卡（可用 .角色卡记录 建卡后再试）",
    )


@pytest.mark.asyncio
async def test_check_initiative_mention_binds_owner(app: App):
    """.先攻检定 @玩家 → 以该玩家为 owner 入先攻表（与 .ri @玩家 同源）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.initiative import get_init_list

    g = 100050
    await _expect(
        app, char_matcher,
        fake_group_message_event_v11(
            message=Message(f".角色卡记录 {_RECORD}"), group_id=g, user_id=31015
        ),
        "角色卡已设置",
    )
    token = set_runtime(SequenceRuntime([5]))
    try:
        event = fake_group_message_event_v11(
            message=Message(".先攻检定 ") + MessageSegment.at(31015),
            group_id=g,
            user_id=31000,
        )
        await _expect(
            app, check_matcher, event,
            "伊丽莎白进行【先攻检定】：\n无熟练加值 敏捷调整值:2\n"
            "伊丽莎白的先攻值是 1D20+2=[5]+2=7",
        )
    finally:
        reset_runtime(token)

    init_data = await get_init_list(g)
    assert init_data is not None
    assert [(e.name, e.owner, e.init) for e in init_data.entities] == [
        ("伊丽莎白", "31015", 7)
    ]
    await _expect(
        app, initiative_matcher,
        fake_group_message_event_v11(
            message=Message(".init"), group_id=g, user_id=31000
        ),
        "先攻列表如下: \n当前是第1轮,伊丽莎白的回合\n1.伊丽莎白 先攻:7 HP:20/30 (5)",
    )


# ── 私聊（仅群聊可用的命令在私聊要给出提示，而不是静默）────────────────────


@pytest.mark.asyncio
async def test_char_private_denied(app: App):
    """私聊使用 .角色卡 → 提示仅群聊可用。

    角色卡按「群」存放，私聊没有本群上下文；提示必须真的发得出去——
    处理器事件参数若注成 GroupMessageEvent，私聊事件在参数注入阶段就被滤掉、
    整个处理器不执行（表现为静默），与其他命令族的提示口径不一致。
    """
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    event = fake_private_message_event_v11(message=Message(".角色卡"))
    await _expect(app, char_matcher, event, "该指令仅在群聊中可用。")


@pytest.mark.asyncio
async def test_check_private_denied(app: App):
    """私聊使用检定点命令 → 提示仅群聊可用（检定读的是本群角色卡，同上）。"""
    from nonebot_plugin_dnddicer.commands.character import check_matcher

    event = fake_private_message_event_v11(message=Message(".力量检定"))
    await _expect(app, check_matcher, event, "该指令仅在群聊中可用。")
