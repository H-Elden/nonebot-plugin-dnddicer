""".dnd 属性生成命令（4D6K3 掷点）的 nonebug 测试。

确定性策略：与 .r 测试一致——掷骰引擎的骰子来源走 karma_runtime 注入点，
测试通过 SequenceRuntime（固定序列）注入以精确断言生成的 6 项属性。
. 一次 .dnd = 6 项属性 × 每项 4 个 d6 = 24 次掷骰，序列需足量。

用例覆盖：基本生成（格式与合计）、4D6K3 取最低与降序、次数（含无空格 .dnd2）、
原因（跟在次数后 / 无空格粘连 / 不给次数直接给出——2026-09-14 修订）、
次数越界回退 1、私聊可用、reason 截断。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.commands.dnd import (
    MAX_DND_REASON_LEN,
    dnd_matcher,
    format_dnd_line,
    generate_ability_scores,
    parse_dnd_args,
)
from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_GROUP = 87654321

#: 一组 .dnd 消耗的骰子数：6 属性 × 4 d6 = 24
_DND_DICE_PER_GROUP = 24

#: 固定 24 个 d6（全部 6）→ 每项属性 4d6 去最低 = 6+6+6 = 18
_ALL_SIX = [6] * _DND_DICE_PER_GROUP


def _group_event(text: str, user_id: int = 10001):
    return fake_group_message_event_v11(
        message=Message(text), group_id=_GROUP, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_dnd_basic(app: App):
    """无参数 .dnd：一行六属性（每项 4d6 全 6 → 18），含合计与降序列表。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        event = _group_event(".dnd")
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成:\n108 : [18, 18, 18, 18, 18, 18]",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_drop_lowest_and_sort(app: App):
    """4D6K3 语义：每项去最低，六项按降序排列，合计正确。

    序列按 4 个一组构造：每组 4d6 去掉最小值后求和；六项分别期望
    18/17/14/12/9/13 → 降序 [18, 17, 14, 13, 12, 9]，合计 83。
    """
    seq = [
        6, 6, 6, 1,   # → 18（去 1）
        6, 6, 5, 1,   # → 17（去 1）
        5, 5, 4, 2,   # → 14（去 2）
        5, 4, 3, 3,   # → 12（去 3）
        4, 3, 2, 1,   # → 9（去 1）
        6, 6, 1, 1,   # → 13（去一个 1）
    ]
    token = set_runtime(SequenceRuntime(seq))
    try:
        event = _group_event(".dnd")
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成:\n83 : [18, 17, 14, 13, 12, 9]",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_times(app: App):
    """.dnd 2：掷两组，逐行输出。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX * 2))
    try:
        event = _group_event(".dnd 2")
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成:\n"
            "108 : [18, 18, 18, 18, 18, 18]\n"
            "108 : [18, 18, 18, 18, 18, 18]",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_times_no_space(app: App):
    """.dnd2（命令名后无空格）与 .dnd 2 等价。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX * 2))
    try:
        event = _group_event(".dnd2")
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成:\n"
            "108 : [18, 18, 18, 18, 18, 18]\n"
            "108 : [18, 18, 18, 18, 18, 18]",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_reason(app: App):
    """.dnd 1 原因：反馈带「DND人物作成——原因:」标题。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        event = _group_event(".dnd 1 为了勇者")
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成——为了勇者:\n108 : [18, 18, 18, 18, 18, 18]",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_reason_no_space(app: App):
    """.dnd1 原因：无空格次数 + 原因（对齐 DicePP 解析语义）。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        event = _group_event(".dnd1 为了勇者")
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成——为了勇者:\n108 : [18, 18, 18, 18, 18, 18]",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_reason_without_times(app: App):
    """.dnd 原因（不给次数）：原因照常显示（2026-09-14 修订——原实现静默丢弃）。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        event = _group_event(".dnd 为了勇者")
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成——为了勇者:\n108 : [18, 18, 18, 18, 18, 18]",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_times_with_reason(app: App):
    """.dnd5 原因（次数在前）：与「不给次数的原因」写法行为一致。"""
    line = "108 : [18, 18, 18, 18, 18, 18]"
    token = set_runtime(SequenceRuntime(_ALL_SIX * 5))
    try:
        event = _group_event(".dnd5 为了勇者")
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成——为了勇者:\n" + "\n".join([line] * 5),
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_times_out_of_range(app: App):
    """次数越界（>10）回退 1 次。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        event = _group_event(".dnd 11")
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成:\n108 : [18, 18, 18, 18, 18, 18]",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_times_zero(app: App):
    """次数 0 回退 1 次。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        event = _group_event(".dnd 0")
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成:\n108 : [18, 18, 18, 18, 18, 18]",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_private(app: App):
    """私聊也可用（DicePP 端口语义：群聊/私聊均可）。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        event = fake_private_message_event_v11(message=Message(".dnd"))
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成:\n108 : [18, 18, 18, 18, 18, 18]",
        )
    finally:
        reset_runtime(token)


# ── 纯函数单测（不依赖 nonebug）──────────────────────────────────────────


def test_parse_dnd_args():
    """参数解析：次数/原因/回退规则。"""
    assert parse_dnd_args("") == (1, "")
    assert parse_dnd_args("5") == (5, "")
    assert parse_dnd_args("2 为了勇者") == (2, "为了勇者")
    assert parse_dnd_args("11") == (1, "")     # 越界回退
    assert parse_dnd_args("0") == (1, "")      # 越界回退
    # 2026-09-14 修订：首词非数字时整段视为原因（原实现丢弃原因、回退 1）
    assert parse_dnd_args("abc") == (1, "abc")
    assert parse_dnd_args("为了勇者") == (1, "为了勇者")
    assert parse_dnd_args("为了勇者 开卡") == (1, "为了勇者 开卡")  # 整段（含空格）
    assert parse_dnd_args("11 为了勇者") == (1, "为了勇者")  # 越界数字：回退 1、其余为原因


def test_parse_dnd_args_reason_truncated():
    """原因超过 50 字符被截断（对齐 DicePP MAX_DND_RESULT_LEN）。"""
    long_reason = "长" * (MAX_DND_REASON_LEN + 20)
    times, reason = parse_dnd_args(f"1 {long_reason}")
    assert times == 1
    assert reason == "长" * MAX_DND_REASON_LEN
    # 不带次数的整段原因同样截断
    times, reason = parse_dnd_args(long_reason)
    assert times == 1
    assert reason == "长" * MAX_DND_REASON_LEN


def test_format_dnd_line():
    """结果行格式：{合计} : {降序列表}。"""
    assert format_dnd_line([18, 17, 14, 13, 12, 9]) == "83 : [18, 17, 14, 13, 12, 9]"
    assert format_dnd_line([18] * 6) == "108 : [18, 18, 18, 18, 18, 18]"


def test_generate_ability_scores_deterministic():
    """generate_ability_scores 走 karma_runtime 注入：固定序列 → 固定六项。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        scores = generate_ability_scores()
        assert scores == [18, 18, 18, 18, 18, 18]
    finally:
        reset_runtime(token)
