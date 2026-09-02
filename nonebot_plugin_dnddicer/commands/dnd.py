"""DND 属性生成命令：``.dnd``（4D6K3 掷点）。

对齐 nonebot-dicepp ``module/misc/dnd_command.py`` 语义：
- ``.dnd`` = 一次生成 6 项属性，每项为 4D6K3（掷 4 个 d6、去最低、取 3 个和）；
- ``.dnd [次数] [原因]``：次数默认 1、上限 10（越界/非数字回退 1，与 DicePP 相同）；
  原因跟在次数之后（如 ``.dnd 1 开卡``），截断 50 字符；
- 反馈：``{昵称} DND人物作成:\n{结果}``（无原因）/ ``{昵称} DND人物作成——{原因}:\n{结果}``
  （有原因）；结果每行为 ``{六项合计} : {六项降序列表}``（与 DicePP 相同：只掷值、
  不绑定属性名，由玩家自行分配给 力量/敏捷/体质/智力/感知/魅力）；
- 群聊/私聊均可用（DicePP 群聊与私聊端口同款语义）。

设计说明（自研业务层）：
- DicePP 的 ``.dnd`` 直接用 ``random.randint`` 掷骰（不经 ast_engine）；本项目
  把随机源接到引擎同款 karma_runtime 注入点（``get_runtime()`` 存在时用其
  ``roll(6)``，否则回退 ``random.randint``），使 nonebug 测试可用 SequenceRuntime
  做确定性断言（与 ``.r`` 测试同思路），掷骰语义不变；
- 「标准购点（27 点）」DicePP/海豹骰均无先例，本期**不做**（另行规划，
  见 doc/骰娘插件开发计划.md 待讨论事项），仅实现 DicePP 对齐的 4D6K3 掷点。
"""

from __future__ import annotations

from random import randint
from typing import List, Tuple

from nonebot.adapters.onebot.v11 import MessageEvent

from ..engine.roll.karma_runtime import get_runtime
from . import base, text

#: 单次 .dnd 最多重复掷组数（与 DicePP MAX_DND_TIMES 一致）
MAX_DND_TIMES = 10
#: 原因截断长度（与 DicePP MAX_DND_RESULT_LEN 一致）
MAX_DND_REASON_LEN = 50

_HELP = (
    "DND5e 属性生成（4D6K3 掷点）\n"
    "用法：.dnd [次数] [原因]（如 .dnd、.dnd 5 开卡）\n"
    "每次生成 6 项属性：每项掷 4D6 去最低（4D6K3），按降序展示并附六项合计；\n"
    "次数默认 1、最大 10（.dnd5 或 .dnd 5）；原因（可选）跟在次数之后。\n"
    "掷出的 6 个数值不绑定属性，自行分配给 力量/敏捷/体质/智力/感知/魅力 后，"
    "可用 .角色卡记录 建卡。"
)

dnd_matcher = base.on_dnd_command("dnd", _HELP)


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


def parse_dnd_args(rest: str) -> Tuple[int, str]:
    """解析 ``.dnd`` 命令体 → (次数, 原因)。

    对齐 DicePP can_process_msg：首个空白词尝试解析为次数（1..10，越界/非数字回退
    1），其余文本（如果有）为原因并截断 50 字符；原因必须跟在次数之后。
    """
    parts = rest.strip().split(" ", 1)
    reason = parts[1].strip()[:MAX_DND_REASON_LEN] if len(parts) > 1 else ""
    try:
        times = int(parts[0])
        assert 1 <= times <= MAX_DND_TIMES
    except (ValueError, AssertionError):
        times = 1
    return times, reason


@dnd_matcher.handle()
async def handle_dnd(event: MessageEvent) -> None:
    """处理 .dnd（群聊/私聊均可用，对齐 DicePP 端口语义）。"""
    rest = base.get_command_rest(event) or ""
    times, reason = parse_dnd_args(rest)

    lines = []
    for _ in range(times):
        lines.append(format_dnd_line(generate_ability_scores()))
    result = "\n".join(lines)

    name = base.get_display_name(event)
    if reason:
        feedback = text.TXT_DND_RES.format(name=name, reason=reason, result=result)
    else:
        feedback = text.TXT_DND_RES_NOREASON.format(name=name, result=result)
    await dnd_matcher.finish(feedback)
