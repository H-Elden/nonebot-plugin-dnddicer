# ---------------------------------------------------------------------------
# 本文件移植自 nonebot-dicepp (https://github.com/pear-studio/nonebot-dicepp)
# Copyright (c) 2022 pear-studio, MIT License（许可全文见本项目 LICENSE）。
# Ported from nonebot-dicepp — 逻辑语义与上游一致，仅做 import/路径适配；
# 改动记录见移植说明文件头注释。
# ---------------------------------------------------------------------------
from __future__ import annotations

"""
业力骰子运行时上下文，用于在 roll 函数内部感知当前群聊的业力环境。
"""

from contextvars import ContextVar
from typing import Optional, Protocol


class DiceRuntime(Protocol):
    """定义运行时需要实现的最小接口。"""

    def roll(self, dice_type: int) -> int:
        ...


_current_runtime: ContextVar[Optional[DiceRuntime]] = ContextVar("karma_runtime", default=None)


def get_runtime() -> Optional[DiceRuntime]:
    """获取当前上下文中的运行时对象。"""
    return _current_runtime.get()


def set_runtime(runtime: DiceRuntime):
    """写入新的运行时对象并返回 token 以便恢复。"""
    return _current_runtime.set(runtime)


def reset_runtime(token):
    """恢复上下文到之前的状态。"""
    _current_runtime.reset(token)

