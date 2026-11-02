"""牌堆随机源：默认系统随机；测试与文档取证可替换为固定序列。

与掷骰引擎的 ``SequenceRuntime`` 同思路：固定序列耗尽即抛错，避免“少抽/多抽”
被静默放过。ContextVar 让命令层无需显式传递随机源，测试/取证按上下文注入。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from random import Random
from typing import Optional, Protocol, Sequence


class DeckRuntime(Protocol):
    """牌堆随机源协议：返回 ``[0, total)`` 的整数。"""

    def randbelow(self, total: int) -> int:
        """返回 0 到 total-1 的随机整数（total 必须 > 0）。"""
        ...


class RandomDeckRuntime:
    """默认随机源：包装 ``random.Random``。"""

    def __init__(self, rng: Optional[Random] = None) -> None:
        self._rng = rng or Random()

    def randbelow(self, total: int) -> int:
        assert total > 0, "total must be positive"
        return self._rng.randrange(total)


class SequenceDeckRuntime:
    """固定序列随机源（测试/取证）。

    ``seq`` 中的值按 1 起算并归一化到 ``[1, total]``，与掷骰的骰值写法一致；
    序列耗尽抛 ``IndexError``，暴露“实际抽取次数与预期不符”。
    """

    def __init__(self, seq: Sequence[int]) -> None:
        self._seq = [int(value) for value in seq]
        self._idx = 0

    def randbelow(self, total: int) -> int:
        assert total > 0, "total must be positive"
        if self._idx >= len(self._seq):
            raise IndexError(
                f"SequenceDeckRuntime exhausted: requested draw #{self._idx + 1} "
                f"but only {len(self._seq)} values available"
            )
        raw = self._seq[self._idx]
        self._idx += 1
        return (raw - 1) % total

    def get_consumed_count(self) -> int:
        return self._idx

    def get_remaining_count(self) -> int:
        return len(self._seq) - self._idx


_DEFAULT_RUNTIME = RandomDeckRuntime()
_RUNTIME: ContextVar[Optional[DeckRuntime]] = ContextVar(
    "dnddicer_deck_runtime", default=None
)


def get_runtime() -> DeckRuntime:
    """返回当前上下文的随机源（未设置时用默认系统随机）。"""
    return _RUNTIME.get() or _DEFAULT_RUNTIME


def set_runtime(runtime: DeckRuntime) -> Token:
    """设置当前上下文的随机源，返回可用于恢复的 token。"""
    return _RUNTIME.set(runtime)


def reset_runtime(token: Token) -> None:
    """恢复设置前的随机源。"""
    _RUNTIME.reset(token)


__all__ = [
    "DeckRuntime",
    "RandomDeckRuntime",
    "SequenceDeckRuntime",
    "get_runtime",
    "set_runtime",
    "reset_runtime",
]
