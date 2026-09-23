""".r / .rh 掷骰命令的 nonebug 测试。

确定性策略：掷骰引擎的骰子来源走 karma_runtime 注入点（默认 None = 随机），
测试通过 SequenceRuntime（固定序列）注入以精确断言结果文案。
用例覆盖：基本表达式、r 后无空格、中文句号、宿主 COMMAND_START、连掷、
暗骰（群内提示 + 私聊结果）、s 只显数值、错误语法、大成功文案。

说明：nonebug 拦截到的是 matcher 传入的原始 message（字符串），
因此 ``should_call_send`` / ``should_call_api`` 的期望一律使用纯字符串。
"""

import nonebot
import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime


@pytest.fixture
def roll_matcher():
    """被测命令：.r（含 .rh 暗骰，命令名 r 匹配时 rest 交给参数解析层）。"""
    from nonebot_plugin_dnddicer.commands.roll import roll_matcher as _m

    return _m


async def _expect_send(app: App, matcher, event, expected: str, api_calls=None):
    """驱动一次群消息事件并断言唯一一次 send 的内容为 expected。

    先注册期望、再投递事件，避免事件处理与期望注册的时序歧义。
    使用 nonebug 的 fake adapter 创建 bot，使 call_api（如暗骰私聊）
    被 nonebug 拦截记录，而非走真实协议连接。
    """
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        if api_calls:
            for api, data in api_calls:
                ctx.should_call_api(api, data=data)
        ctx.receive_event(bot, event)
    return bot


@pytest.mark.asyncio
async def test_roll_basic(app: App, roll_matcher):
    """基本表达式 .r 2d6+3（固定序列 [5,2] → [5+2]+3=10）。"""
    token = set_runtime(SequenceRuntime([5, 2]))
    try:
        event = fake_group_message_event_v11(message=Message(".r 2d6+3"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 2D6+3=[5+2]+3=10")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_no_space_after_r(app: App, roll_matcher):
    """命令名后无空白：.r2d6+3 与 .r 2d6+3 等价。"""
    token = set_runtime(SequenceRuntime([4, 1]))
    try:
        event = fake_group_message_event_v11(message=Message(".r2d6+3"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 2D6+3=[4+1]+3=8")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_constant_multiplication_operand(app: App, roll_matcher):
    """常量复合子表达式：.rd6+2*2 的说明文字按四则运算给出（[4]+2*2）。

    乘号只作用于相邻常量，不得改写骰块（旧行为曾显示 [4]*2+4，与算式结构、
    四则运算均不符）。
    """
    token = set_runtime(SequenceRuntime([4]))
    try:
        event = fake_group_message_event_v11(message=Message(".rd6+2*2"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 1D6+2*2=[4]+2*2=8")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_constant_multiplication_only_adjacent(app: App, roll_matcher):
    """无括号时乘号只作用于相邻骰子：.rd6+d8*2 → [3]+[5]*2=13。"""
    token = set_runtime(SequenceRuntime([3, 5]))
    try:
        event = fake_group_message_event_v11(message=Message(".rd6+d8*2"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 1D6+1D8*2=[3]+[5]*2=13")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_parenthesized_dice_sum_times_two(app: App, roll_matcher):
    """括号内整体乘：.r(d6+d8)*2 → ([3]+[5])*2=16（括号保留，语义清晰）。"""
    token = set_runtime(SequenceRuntime([3, 5]))
    try:
        event = fake_group_message_event_v11(message=Message(".r(d6+d8)*2"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 (1D6+1D8)*2=([3]+[5])*2=16")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_chinese_fullstop(app: App, roll_matcher):
    """中文句号起始：。r 2d6+3。"""
    token = set_runtime(SequenceRuntime([6, 3]))
    try:
        event = fake_group_message_event_v11(message=Message("。r 2d6+3"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 2D6+3=[6+3]+3=12")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_host_command_start(app: App, roll_matcher, monkeypatch):
    """宿主 COMMAND_START（默认 "/"）兼容由配置显式开启（默认关）：
    默认 /r 不命中（静默）；dnddicer_use_host_command_starts=true 时 /r 2d6+3 命中。"""
    from nonebot_plugin_dnddicer import config as config_mod
    from nonebot_plugin_dnddicer.commands import base

    async def _set_host_starts(enabled: bool) -> None:
        monkeypatch.setattr(
            config_mod,
            "_config",
            config_mod.Config(dnddicer_use_host_command_starts=enabled),
        )
        base._compute_command_starts.cache_clear()

    event = fake_group_message_event_v11(message=Message("/r 2d6+3"))

    # 默认（false）：斜杠起始符不命中 → 静默
    await _set_host_starts(False)
    async with app.test_matcher(roll_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.receive_event(bot, event)

    # 开启兼容：/r 2d6+3 命中并正常掷骰
    token = set_runtime(SequenceRuntime([3, 5]))
    try:
        await _set_host_starts(True)
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 2D6+3=[3+5]+3=11")
    finally:
        reset_runtime(token)
        base._compute_command_starts.cache_clear()


@pytest.mark.asyncio
async def test_roll_multi_times(app: App, roll_matcher):
    """连掷：# 语法（.r 2#1d6 → 两次独立 d6，多行明细、无外层中括号）。"""
    token = set_runtime(SequenceRuntime([5, 2]))
    try:
        event = fake_group_message_event_v11(message=Message(".r 2#1d6"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 2次 1D6:\n[5]=5,\n[2]=2")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_multi_times_sum_only(app: App, roll_matcher):
    """s 连掷：# 语法 + s 前缀 → 单行紧凑数值列表 [v1, v2]。"""
    token = set_runtime(SequenceRuntime([5, 2]))
    try:
        event = fake_group_message_event_v11(message=Message(".r s 2#1d6"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 2次 1D6: [5, 2]")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_crit_success(app: App, roll_matcher):
    """唯一 d20 大成功 → 追加「好耶！大成功!」。"""
    token = set_runtime(SequenceRuntime([20]))
    try:
        event = fake_group_message_event_v11(message=Message(".r d20"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 1D20=[20]=20 好耶！大成功!")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_d100_no_critical(app: App, roll_matcher):
    """.r 1d100 掷 100 → 不播大成功/大失败（DNDDicer 无 COC/d100 体系，仅 d20 有）。"""
    token = set_runtime(SequenceRuntime([100]))
    try:
        event = fake_group_message_event_v11(message=Message(".r 1d100"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 1D100=[100]=100")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_hidden_group(app: App, roll_matcher):
    """暗骰 .rh 群消息：群内只播报提示，结果经 send_private_msg 私聊掷骰者。"""
    token = set_runtime(SequenceRuntime([9]))
    try:
        event = fake_group_message_event_v11(message=Message(".rh 1d20"))
        await _expect_send(
            app,
            roll_matcher,
            event,
            "test 进行了一次暗骰",
            api_calls=[
                (
                    "send_private_msg",
                    {
                        "user_id": event.user_id,
                        "message": "test 的暗骰结果为 1D20=[9]=9",
                    },
                )
            ],
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_hidden_private(app: App, roll_matcher):
    """暗骰发生在私聊：直接返回结果（无群提示）。"""
    token = set_runtime(SequenceRuntime([7]))
    try:
        event = fake_private_message_event_v11(message=Message(".rh 1d20 偷袭"))
        await _expect_send(app, roll_matcher, event, "test 为 偷袭 进行的暗骰结果为 1D20=[7]=7")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_sum_only(app: App, roll_matcher):
    """s 前缀：只显示最终数值（不展示逐骰过程）。"""
    token = set_runtime(SequenceRuntime([2, 6]))
    try:
        event = fake_group_message_event_v11(message=Message(".r s 2d6+3"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 2D6+3=11")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_reason(app: App, roll_matcher):
    """原因后缀：.r 2d6+3 力量检定 → 带原因文案。"""
    token = set_runtime(SequenceRuntime([4, 4]))
    try:
        event = fake_group_message_event_v11(message=Message(".r 2d6+3 力量检定"))
        await _expect_send(
            app,
            roll_matcher,
            event,
            "test 为 力量检定 进行的掷骰结果为 2D6+3=[4+4]+3=11",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_default_dice(app: App, roll_matcher):
    """默认骰面注入：裸 d → 默认 D20。"""
    token = set_runtime(SequenceRuntime([13]))
    try:
        event = fake_group_message_event_v11(message=Message(".r d"))
        await _expect_send(app, roll_matcher, event, "test 的掷骰结果为 1D20=[13]=13")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_syntax_error(app: App, roll_matcher):
    """非法表达式：回复引擎语法错误文案（非静默）。

    注：表达式以 a/n 等字母开头会被识别为特殊判定模式（见下方
    test_roll_special_mode_a_placeholder），因此这里用 q 开头的非法表达式。
    """
    event = fake_group_message_event_v11(message=Message(".r qqq"))
    await _expect_send(app, roll_matcher, event, "意外字符 'Q' 在位置 1")


@pytest.mark.asyncio
async def test_roll_special_mode_a_placeholder(app: App, roll_matcher):
    """a 判定模式（.r a<阈值>）第一期未实现 → 显式提示而非静默。"""
    event = fake_group_message_event_v11(message=Message(".r a70 力量检定"))
    await _expect_send(app, roll_matcher, event, "该掷骰模式（a）尚未实现，敬请期待。")


@pytest.mark.asyncio
async def test_roll_alias_misplaced_face_hint(app: App, roll_matcher):
    """面数写错位（.rd劣势20+6 / .rd优势20+6）：回可读指引而非荒谬结果。

    2026-09-22 修复：此前别名展开会把 ``KL1``/``K1`` 与后随数字静默粘成
    ``2D20KL120``（保留 120 个 = 两骰求和），得到「MIN{[9], [18]}+6=33」
    这类显示与数值不自洽的结果。
    """
    hint = (
        "优势/劣势 后不能直接跟数字：骰子面数请写在前面（如 d20劣势+6），"
        "加值请写成 +N（如 d劣势+2）"
    )
    for text_msg in (".rd劣势20+6", ".rd优势20+6"):
        event = fake_group_message_event_v11(message=Message(text_msg))
        await _expect_send(app, roll_matcher, event, hint)


@pytest.mark.asyncio
async def test_roll_alias_valid_forms(app: App, roll_matcher):
    """正确写法回归：.rd劣势+6 与 .rd20劣势+6 均正常（两骰取低 + 加值）。"""
    token = set_runtime(SequenceRuntime([5, 15, 5, 15]))
    try:
        for text_msg in (".rd劣势+6", ".rd20劣势+6"):
            event = fake_group_message_event_v11(message=Message(text_msg))
            await _expect_send(
                app, roll_matcher, event,
                "test 的掷骰结果为 2D20KL1+6=MIN{[5], [15]}+6=11",
            )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_roll_keep_count_exceeding_dice_hint(app: App, roll_matcher):
    """手输超量取点（.r2d20kl120）：报可读错误而非静默两骰求和。"""
    event = fake_group_message_event_v11(message=Message(".r2d20kl120"))
    await _expect_send(app, roll_matcher, event, "取点数不能超过骰子数量：120 > 2")


@pytest.mark.asyncio
async def test_roll_uses_char_name(app: App, roll_matcher):
    """有角色卡时落款用角色名（统一名称回退链：角色名 → 群名片 → QQ 昵称）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file

    _chars._cache = None
    path = get_data_file("characters.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")

    group_id, user_id = 88001, 88101
    await _expect_send(
        app, char_matcher,
        fake_group_message_event_v11(
            message=Message(
                ".角色卡记录 $姓名$ 伊丽莎白\n$等级$ 1\n$属性$ 10/10/10/10/10/10"
            ),
            group_id=group_id,
            user_id=user_id,
        ),
        "角色卡已设置",
    )
    token = set_runtime(SequenceRuntime([5, 2]))
    try:
        event = fake_group_message_event_v11(
            message=Message(".r 2d6+3"), group_id=group_id, user_id=user_id
        )
        await _expect_send(
            app, roll_matcher, event, "伊丽莎白 的掷骰结果为 2D6+3=[5+2]+3=10"
        )
    finally:
        reset_runtime(token)
