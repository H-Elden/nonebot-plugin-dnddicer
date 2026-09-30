"""DND 属性生成命令：``.dnd`` / ``.dndx``（4D6K3 掷点）。

``.dnd`` 语义：
- 一次生成 6 项属性，每项为 4D6K3（掷 4 个 d6、去最低、取 3 个和）；
- ``.dnd [次数] [原因]``：次数默认 1、上限 20；**次数越界不再静默回退**
  （2026-09-28 修订：早先越界回退为 1 次、玩家看不出参数被改过）——小于 1
  或大于上限时回复「超出上限 / 至少为 1」的提示并终止，不掷点；
  原因截断 50 字符——给次数时跟在次数之后（``.dnd 1 开卡``），不给次数时
  直接给出（``.dnd 开卡``；2026-09-14 有意 UX 修正：早先仅取第二段，
  会把原因静默丢弃）；
- 反馈：``{昵称} DND人物作成:\n{结果}``（无原因）/ ``{昵称} DND人物作成——{原因}:\n{结果}``
  （有原因）；结果每行为 ``{六项合计} : {六项降序列表}``（只掷值、
  不绑定属性名，由玩家自行分配给 力量/敏捷/体质/智力/感知/魅力）；
- 群聊/私聊均可用。

``.dndx`` 扩展（2026-09-21，用户需求）：
- 同为 4D6K3，但六项数值**按固定顺序绑定属性名**（力量/敏捷/体质/智力/感知/魅力）
  且**不降序排列**——掷出即定配对，直接可抄进角色卡，省去自行分配一步；
- 参数（次数/原因）规则与 ``.dnd`` 完全相同（复用 ``parse_dnd_args``）；
- 命令名 ``dndx`` 经注册表最长前缀匹配，与 ``.dnd`` 互不干扰（``.dndx2`` 亦可）。

设计说明：
- 掷点随机源接入引擎的 karma_runtime 注入点（``get_runtime()`` 存在时用其
  ``roll(6)``，否则回退 ``random.randint``），使 nonebug 测试可用 SequenceRuntime
  做确定性断言（与 ``.r`` 测试同思路），掷骰语义不变；
- 「标准购点（27 点）」本期**不做**（另行规划），仅实现 4D6K3 掷点。
"""

from __future__ import annotations

from random import randint
from typing import List, Tuple

from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.matcher import Matcher

from ..character.constants import ABILITY_LIST
from ..engine.roll.karma_runtime import get_runtime
from . import base, text

#: 单次 .dnd / .dndx 最多重复掷组数（2026-09-28 由 10 提高到 20）
MAX_DND_TIMES = 20
#: 原因截断长度
MAX_DND_REASON_LEN = 50

_HELP = (
    ".dnd[次数] [原因]\n"
    "  4D6K3 属性生成，六项降序展示、自行分配\n"
    "  次数默认 1、最大 20（越界提示、不掷点）\n"
    "  想掷出即绑定属性名用 .dndx\n"
    "  示例：.dnd ｜ .dnd5 ｜ .dnd 开卡"
)

dnd_matcher = base.on_dnd_command("dnd", _HELP)

_HELP_DNDX = (
    ".dndx[次数] [原因]\n"
    "  4D6K3 属性生成，六项按固定顺序对应六属性\n"
    "  顺序：力量/敏捷/体质/智力/感知/魅力（不降序）\n"
    "  次数默认 1、最大 20；原因规则同 .dnd\n"
    "  示例：.dndx ｜ .dndx 5 开卡"
)

dndx_matcher = base.on_dnd_command("dndx", _HELP_DNDX)


class DndTimesOutOfRange(ValueError):
    """次数参数越界：小于 1 或超过 ``MAX_DND_TIMES``。

    2026-09-28 起越界不再静默回退为 1 次——解析层抛出本异常，命令层据此回复
    「超出上限 / 至少为 1」的提示并终止（不掷点）。异常携带玩家原输入的次数，
    供命令层区分「超过上限」与「低于下限」两种提示。
    """

    def __init__(self, times: int) -> None:
        super().__init__(str(times))
        self.times = times


def format_dnd_times_error(times: int) -> str:
    """次数越界的提示文案：超过上限与低于下限两种（文案见 ``commands/text.py``）。"""
    if times > MAX_DND_TIMES:
        return text.TXT_DND_TIMES_OVER_LIMIT.format(max=MAX_DND_TIMES)
    return text.TXT_DND_TIMES_TOO_SMALL


def _roll_d6() -> int:
    """掷一个 d6：优先走 karma_runtime 注入点（测试确定性），否则系统随机。"""
    runtime = get_runtime()
    if runtime is not None:
        return runtime.roll(6)
    return randint(1, 6)


def generate_ability_scores() -> List[int]:
    """掷一组 6 项属性：每项 = 4D6K3（掷 4 个 d6、去最低、3 个求和）。

    Returns:
        按生成顺序排列的 6 项属性值（不绑定属性名，由玩家自行分配）。
    """
    scores: List[int] = []
    for _ in range(6):
        rolls = sorted((_roll_d6() for _ in range(4)), reverse=True)
        scores.append(sum(rolls[:3]))
    return scores


def format_dnd_line(scores: List[int]) -> str:
    """把一组属性渲染为结果行：``{六项合计} : {六项降序列表}``。"""
    return f"{sum(scores)} : {sorted(scores, reverse=True)}"


def format_dndx_line(scores: List[int]) -> str:
    """把一组属性渲染为绑定属性名的结果行：``{合计} : 力量 18、敏捷 17、…``。

    属性名按 ``ABILITY_LIST`` 固定顺序与掷值一一配对、不排序（``.dnd`` 则
    只出降序数值、由玩家自行分配）。
    """
    pairs = "、".join(
        f"{name} {value}" for name, value in zip(ABILITY_LIST, scores)
    )
    return f"{sum(scores)} : {pairs}"


def parse_dnd_args(rest: str) -> Tuple[int, str]:
    """解析 ``.dnd`` 命令体 → (次数, 原因)。

    解析规则：首个空白词尝试解析为次数（1..``MAX_DND_TIMES``），
    其余文本（如果有）为原因并截断 50 字符；首个词不是数字时整段视为原因
    （2026-09-14 有意 UX 修正：早先仅取第二段，``.dnd 开卡`` 的原因会被静默
    丢弃，而 ``.dnd5 开卡`` 因数字在前反而正常——修正后两种写法行为一致）。

    Raises:
        DndTimesOutOfRange: 次数小于 1 或超过 ``MAX_DND_TIMES``（2026-09-28
            修订：早先越界静默回退为 1 次、不给任何提示，玩家只会以为自己
            掷出的就是 1 组）。
    """
    text = rest.strip()
    if not text:
        return 1, ""
    parts = text.split(None, 1)
    tail = parts[1].strip() if len(parts) > 1 else ""
    try:
        times = int(parts[0])
    except ValueError:
        return 1, text[:MAX_DND_REASON_LEN]
    if not 1 <= times <= MAX_DND_TIMES:
        raise DndTimesOutOfRange(times)
    return times, tail[:MAX_DND_REASON_LEN]


async def _resolve_dnd_args(matcher: Matcher, event: MessageEvent) -> Tuple[int, str]:
    """取命令体并解析为 (次数, 原因)；次数越界时提示并终止（不掷点）。

    ``.dnd`` 与 ``.dndx`` 共用本入口，保证两个命令的次数口径与提示完全一致。
    """
    rest = base.get_command_rest(event) or ""
    try:
        return parse_dnd_args(rest)
    except DndTimesOutOfRange as exc:
        await matcher.finish(format_dnd_times_error(exc.times))


@dnd_matcher.handle()
async def handle_dnd(bot: Bot, event: MessageEvent) -> None:
    """处理 .dnd（群聊/私聊均可用）。"""
    times, reason = await _resolve_dnd_args(dnd_matcher, event)

    lines = []
    for _ in range(times):
        lines.append(format_dnd_line(generate_ability_scores()))
    result = "\n".join(lines)

    name = await base.resolve_display_name(bot, event)
    if reason:
        feedback = text.TXT_DND_RES.format(name=name, reason=reason, result=result)
    else:
        feedback = text.TXT_DND_RES_NOREASON.format(name=name, result=result)
    await dnd_matcher.finish(feedback)


@dndx_matcher.handle()
async def handle_dndx(bot: Bot, event: MessageEvent) -> None:
    """处理 .dndx（4D6K3 掷点并绑定属性名；群聊/私聊均可用）。"""
    times, reason = await _resolve_dnd_args(dndx_matcher, event)

    lines = [format_dndx_line(generate_ability_scores()) for _ in range(times)]
    result = "\n".join(lines)

    name = await base.resolve_display_name(bot, event)
    if reason:
        feedback = text.TXT_DNDX_RES.format(name=name, reason=reason, result=result)
    else:
        feedback = text.TXT_DNDX_RES_NOREASON.format(name=name, result=result)
    await dndx_matcher.finish(feedback)
