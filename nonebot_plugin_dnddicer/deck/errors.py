"""牌堆业务异常（命令层映射为用户文案）。"""

from __future__ import annotations


class DeckError(Exception):
    """牌堆相关错误的基类。"""


class DeckEmpty(DeckError):
    """牌组没有可抽取的条目。"""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"牌堆「{name}」没有可抽取的条目")


class DeckCountOutOfRange(DeckError):
    """抽取次数越界。"""

    def __init__(self, value: int, maximum: int = 10):
        self.value = value
        self.maximum = maximum
        super().__init__(f"抽取次数 {value} 超出 1..{maximum}")


class DeckNotFound(DeckError):
    """找不到牌堆。"""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"找不到牌堆「{name}」")


class DeckAmbiguous(DeckError):
    """牌堆名匹配到多个候选。"""

    def __init__(self, name: str, candidates: list[str]):
        self.name = name
        self.candidates = candidates
        super().__init__(f"牌堆「{name}」匹配到多个候选：{', '.join(candidates)}")


__all__ = [
    "DeckAmbiguous",
    "DeckCountOutOfRange",
    "DeckEmpty",
    "DeckError",
    "DeckNotFound",
]
