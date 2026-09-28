""".dnd 属性生成命令（4D6K3 掷点）的 nonebug 测试。

确定性策略：与 .r 测试一致——掷骰引擎的骰子来源走 karma_runtime 注入点，
测试通过 SequenceRuntime（固定序列）注入以精确断言生成的 6 项属性。
. 一次 .dnd = 6 项属性 × 每项 4 个 d6 = 24 次掷骰，序列需足量。

用例覆盖：基本生成（格式与合计）、4D6K3 取最低与降序、次数（含无空格 .dnd2）、
原因（跟在次数后 / 无空格粘连 / 不给次数直接给出——2026-09-14 修订）、
次数越界（0 / 负数 / 超过上限 20）提示且**不掷点**（2026-09-28 修订：早先静默
回退为 1 次）、私聊可用、reason 截断；
.dndx（2026-09-21 新增）：属性名绑定不排序、标题后缀、次数/原因/私聊与 .dnd 同规则。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.commands.dnd import (
    MAX_DND_REASON_LEN,
    MAX_DND_TIMES,
    DndTimesOutOfRange,
    dnd_matcher,
    dndx_matcher,
    format_dnd_line,
    format_dnd_times_error,
    format_dndx_line,
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
    """.dnd1 原因：无空格次数 + 原因（次数连写解析）。"""
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
async def test_dnd_times_at_limit(app: App):
    """`.dnd 20`（恰好等于上限）照常掷 20 组。"""
    line = "108 : [18, 18, 18, 18, 18, 18]"
    token = set_runtime(SequenceRuntime(_ALL_SIX * MAX_DND_TIMES))
    try:
        event = _group_event(f".dnd {MAX_DND_TIMES}")
        await _expect(
            app,
            dnd_matcher,
            event,
            "test DND人物作成:\n" + "\n".join([line] * MAX_DND_TIMES),
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_times_out_of_range(app: App):
    """次数超过上限：提示上限（不掷点、不静默回退 1 次）。

    骰值序列故意留空：一旦实现回退成「照掷 1 组」，取骰子会 IndexError、
    回复就会变成内部错误文案，本用例即失败。
    """
    runtime = SequenceRuntime([])
    token = set_runtime(runtime)
    try:
        event = _group_event(".dnd 21")
        await _expect(
            app,
            dnd_matcher,
            event,
            "次数超出上限：最多 20 次",
        )
        assert runtime.get_consumed_count() == 0
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_times_zero(app: App):
    """次数 0：提示下限（不掷点）。"""
    runtime = SequenceRuntime([])
    token = set_runtime(runtime)
    try:
        event = _group_event(".dnd 0")
        await _expect(
            app,
            dnd_matcher,
            event,
            "次数至少为 1",
        )
        assert runtime.get_consumed_count() == 0
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_times_negative(app: App):
    """次数为负数：与 0 同口径（提示下限、不掷点）。"""
    runtime = SequenceRuntime([])
    token = set_runtime(runtime)
    try:
        event = _group_event(".dnd -3")
        await _expect(
            app,
            dnd_matcher,
            event,
            "次数至少为 1",
        )
        assert runtime.get_consumed_count() == 0
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_private(app: App):
    """私聊也可用（群聊/私聊均可）。"""
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


# =========================================================================
# .dndx（属性名绑定，2026-09-21 新增）
# =========================================================================


@pytest.mark.asyncio
async def test_dndx_basic(app: App):
    """无参数 .dndx：一行绑定属性名（每项 18），标题带 (属性绑定) 后缀。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        event = _group_event(".dndx")
        await _expect(
            app,
            dndx_matcher,
            event,
            "test DND人物作成(属性绑定):\n"
            "108 : 力量 18、敏捷 18、体质 18、智力 18、感知 18、魅力 18",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dndx_binding_not_sorted(app: App):
    """六项按固定属性顺序与掷值配对（不降序）——与 .dnd 的降序列表相反。"""
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
        event = _group_event(".dndx")
        await _expect(
            app,
            dndx_matcher,
            event,
            "test DND人物作成(属性绑定):\n"
            "83 : 力量 18、敏捷 17、体质 14、智力 12、感知 9、魅力 13",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dndx_times_and_reason(app: App):
    """.dndx 2 为了勇者：掷两组逐行输出，标题含原因（参数规则同 .dnd）。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX * 2))
    try:
        event = _group_event(".dndx 2 为了勇者")
        await _expect(
            app,
            dndx_matcher,
            event,
            "test DND人物作成(属性绑定)——为了勇者:\n"
            "108 : 力量 18、敏捷 18、体质 18、智力 18、感知 18、魅力 18\n"
            "108 : 力量 18、敏捷 18、体质 18、智力 18、感知 18、魅力 18",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dndx_no_space(app: App):
    """.dndx2（命令名后无空格）与 .dndx 2 等价（最长前缀匹配）。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX * 2))
    try:
        event = _group_event(".dndx2")
        await _expect(
            app,
            dndx_matcher,
            event,
            "test DND人物作成(属性绑定):\n"
            "108 : 力量 18、敏捷 18、体质 18、智力 18、感知 18、魅力 18\n"
            "108 : 力量 18、敏捷 18、体质 18、智力 18、感知 18、魅力 18",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dndx_private(app: App):
    """私聊也可用（与 .dnd 同端口语义）。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        event = fake_private_message_event_v11(message=Message(".dndx"))
        await _expect(
            app,
            dndx_matcher,
            event,
            "test DND人物作成(属性绑定):\n"
            "108 : 力量 18、敏捷 18、体质 18、智力 18、感知 18、魅力 18",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dndx_times_out_of_range(app: App):
    """.dndx 次数越界与 .dnd 同口径（同一解析入口、同一提示、同样不掷点）。"""
    runtime = SequenceRuntime([])
    token = set_runtime(runtime)
    try:
        event = _group_event(".dndx 30")
        await _expect(
            app,
            dndx_matcher,
            event,
            "次数超出上限：最多 20 次",
        )
        assert runtime.get_consumed_count() == 0
    finally:
        reset_runtime(token)


# ── 纯函数单测（不依赖 nonebug）──────────────────────────────────────────


def test_parse_dnd_args():
    """参数解析：次数/原因/越界规则。"""
    assert parse_dnd_args("") == (1, "")
    assert parse_dnd_args("1") == (1, "")
    assert parse_dnd_args("5") == (5, "")
    assert parse_dnd_args("20") == (MAX_DND_TIMES, "")  # 上限本身合法
    assert parse_dnd_args("2 为了勇者") == (2, "为了勇者")
    # 2026-09-28 修订：越界不再静默回退 1 次，改为抛出由命令层转成提示
    with pytest.raises(DndTimesOutOfRange) as over:
        parse_dnd_args("21")
    assert over.value.times == 21
    with pytest.raises(DndTimesOutOfRange) as zero:
        parse_dnd_args("0")
    assert zero.value.times == 0
    with pytest.raises(DndTimesOutOfRange) as negative:
        parse_dnd_args("-1")
    assert negative.value.times == -1
    with pytest.raises(DndTimesOutOfRange) as over_with_reason:
        parse_dnd_args("21 为了勇者")
    assert over_with_reason.value.times == 21
    # 2026-09-14 修订：首词非数字时整段视为原因（原实现丢弃原因、回退 1）
    assert parse_dnd_args("abc") == (1, "abc")
    assert parse_dnd_args("为了勇者") == (1, "为了勇者")
    assert parse_dnd_args("为了勇者 开卡") == (1, "为了勇者 开卡")  # 整段（含空格）


def test_format_dnd_times_error():
    """越界提示：超过上限报上限、低于下限报下限（2026-09-28 用户复核后不回显输入）。"""
    assert format_dnd_times_error(21) == "次数超出上限：最多 20 次"
    assert format_dnd_times_error(999) == "次数超出上限：最多 20 次"
    assert format_dnd_times_error(0) == "次数至少为 1"
    assert format_dnd_times_error(-1) == "次数至少为 1"


def test_parse_dnd_args_reason_truncated():
    """原因超过 50 字符被截断（MAX_DND_REASON_LEN）。"""
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


def test_format_dndx_line():
    """结果行格式：{合计} : 力量 18、敏捷 17、…（固定顺序、不排序）。"""
    assert format_dndx_line([18, 17, 14, 12, 9, 13]) == (
        "83 : 力量 18、敏捷 17、体质 14、智力 12、感知 9、魅力 13"
    )
    assert format_dndx_line([18] * 6) == (
        "108 : 力量 18、敏捷 18、体质 18、智力 18、感知 18、魅力 18"
    )


def test_generate_ability_scores_deterministic():
    """generate_ability_scores 走 karma_runtime 注入：固定序列 → 固定六项。"""
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        scores = generate_ability_scores()
        assert scores == [18, 18, 18, 18, 18, 18]
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_dnd_uses_char_name(app: App):
    """有角色卡时落款用角色名（统一名称回退链：角色名 → 群名片 → QQ 昵称）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file

    _chars._cache = None
    path = get_data_file("characters.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")

    group_id, user_id = 88002, 88102
    await _expect(
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
    token = set_runtime(SequenceRuntime(_ALL_SIX))
    try:
        event = fake_group_message_event_v11(
            message=Message(".dnd"), group_id=group_id, user_id=user_id
        )
        await _expect(
            app, dnd_matcher, event,
            "伊丽莎白 DND人物作成:\n108 : [18, 18, 18, 18, 18, 18]",
        )
    finally:
        reset_runtime(token)
