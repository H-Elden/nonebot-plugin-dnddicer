"""DND 属性生成命令：``.dnd`` / ``.dndx``（4D6K3 掷点）。

对齐 nonebot-dicepp ``module/misc/dnd_command.py`` 语义：
- ``.dnd`` = 一次生成 6 项属性，每项为 4D6K3（掷 4 个 d6、去最低、取 3 个和）；
- ``.dnd [次数] [原因]``：次数默认 1、上限 10（越界回退 1，与 DicePP 相同）；
  原因截断 50 字符——给次数时跟在次数之后（``.dnd 1 开卡``），不给次数时
  直接给出（``.dnd 开卡``；2026-09-14 有意 UX 修正：上游仅取第二段，该写法
  会把原因静默丢弃）；
- 反馈：``{昵称} DND人物作成:\n{结果}``（无原因）/ ``{昵称} DND人物作成——{原因}:\n{结果}``
  （有原因）；结果每行为 ``{六项合计} : {六项降序列表}``（与 DicePP 相同：只掷值、
  不绑定属性名，由玩家自行分配给 力量/敏捷/体质/智力/感知/魅力）；
- 群聊/私聊均可用（DicePP 群聊与私聊端口同款语义）。

本插件扩展 ``.dndx``（2026-09-21，用户需求；DicePP 无此命令）：
- 同为 4D6K3，但六项数值**按固定顺序绑定属性名**（力量/敏捷/体质/智力/感知/魅力）
  且**不降序排列**——掷出即定配对，直接可抄进角色卡，省去自行分配一步；
- 参数（次数/原因）规则与 ``.dnd`` 完全相同（复用 ``parse_dnd_args``）；
- 命令名 ``dndx`` 经注册表最长前缀匹配，与 ``.dnd`` 互不干扰（``.dndx2`` 亦可）。

设计说明（自研业务层）：
- DicePP 的 ``.dnd`` 直接用 ``random.randint`` 掷骰（不经 ast_engine）；本项目
  把随机源接到引擎同款 karma_runtime 注入点（``get_runtime()`` 存在时用其
  ``roll(6)``，否则回退 ``random.randint``），使 nonebug 测试可用 SequenceRuntime
  做确定性断言（与 ``.r`` 测试同思路），掷骰语义不变；
- 「标准购点（27 点）」DicePP/海豹骰均无先例，本期**不做**（另行规划），
  仅实现 DicePP 对齐的 4D6K3 掷点。
"""

from __future__ import annotations

from random import randint
from typing import List, Tuple

from nonebot.adapters.onebot.v11 import Bot, MessageEvent

from ..character.constants import ABILITY_LIST
from ..engine.roll.karma_runtime import get_runtime
from . import base, text

#: 单次 .dnd 最多重复掷组数（与 DicePP MAX_DND_TIMES 一致）
MAX_DND_TIMES = 10
#: 原因截断长度（与 DicePP MAX_DND_RESULT_LEN 一致）
MAX_DND_REASON_LEN = 50

_HELP = (
    "DND5e 属性生成（4D6K3 掷点）\n"
    "用法：.dnd [次数] [原因]（如 .dnd、.dnd 5 开卡、.dnd 开卡）\n"
    "每次生成 6 项属性：每项掷 4D6 去最低（4D6K3），按降序展示并附六项合计；\n"
    "次数默认 1、最大 10（.dnd5 或 .dnd 5）；原因（可选）可跟在次数之后，"
    "省略次数时直接给出。\n"
    "掷出的 6 个数值不绑定属性，自行分配给 力量/敏捷/体质/智力/感知/魅力 后，"
    "可用 .角色卡记录 建卡。\n"
    "另有绑定属性名的版本：.dndx（数值按固定顺序直接对应六属性、不降序）。"
)

dnd_matcher = base.on_dnd_command("dnd", _HELP)

_HELP_DNDX = (
    "DND5e 属性生成（4D6K3 掷点，属性名绑定）\n"
    "用法：.dndx [次数] [原因]（如 .dndx、.dndx 5 开卡）\n"
    "与 .dnd 同为 4D6K3，但六项数值按固定顺序直接对应 力量/敏捷/体质/智力/感知/"
    "魅力（不降序排列，掷出即定配对），可直接抄进角色卡的 $属性$ 行。\n"
    "次数默认 1、最大 10；原因规则与 .dnd 相同。\n"
    "需要自行分配数值给属性（掷值降序展示）请用 .dnd。"
)

dndx_matcher = base.on_dnd_command("dndx", _HELP_DNDX)


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
    """把一组属性渲染为结果行：``{六项合计} : {六项降序列表}``（DicePP 同款）。"""
    return f"{sum(scores)} : {sorted(scores, reverse=True)}"


def format_dndx_line(scores: List[int]) -> str:
    """把一组属性渲染为绑定属性名的结果行：``{合计} : 力量 18、敏捷 17、…``。

    属性名按 ``ABILITY_LIST`` 固定顺序与掷值一一配对（不排序）——与 DicePP 的
    ``.dnd`` 相反：那边只出降序数值、由玩家自行分配。
    """
    pairs = "、".join(
        f"{name} {value}" for name, value in zip(ABILITY_LIST, scores)
    )
    return f"{sum(scores)} : {pairs}"


def parse_dnd_args(rest: str) -> Tuple[int, str]:
    """解析 ``.dnd`` 命令体 → (次数, 原因)。

    对齐 DicePP can_process_msg：首个空白词尝试解析为次数（1..10，越界回退 1），
    其余文本（如果有）为原因并截断 50 字符；首个词不是数字时整段视为原因
    （2026-09-14 有意 UX 修正：上游仅取第二段，``.dnd 开卡`` 的原因会被静默
    丢弃，而 ``.dnd5 开卡`` 因数字在前反而正常——修正后两种写法行为一致）。
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
        times = 1
    return times, tail[:MAX_DND_REASON_LEN]


@dnd_matcher.handle()
async def handle_dnd(bot: Bot, event: MessageEvent) -> None:
    """处理 .dnd（群聊/私聊均可用，对齐 DicePP 端口语义）。"""
    rest = base.get_command_rest(event) or ""
    times, reason = parse_dnd_args(rest)

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
    rest = base.get_command_rest(event) or ""
    times, reason = parse_dnd_args(rest)

    lines = [format_dndx_line(generate_ability_scores()) for _ in range(times)]
    result = "\n".join(lines)

    name = await base.resolve_display_name(bot, event)
    if reason:
        feedback = text.TXT_DNDX_RES.format(name=name, reason=reason, result=result)
    else:
        feedback = text.TXT_DNDX_RES_NOREASON.format(name=name, result=result)
    await dndx_matcher.finish(feedback)
