"""候选列表的短时交互状态（内存，不落盘）。

`.查询` / `.搜索` 返回候选列表后（唯一候选会直接展示词条、不生成列表，见命令层），
需要接着响应「回复数字查看详情、+/- 翻页」。本模块保存这份短时状态：

- **仅发起者本人可操作**：记录按「会话 + 用户」隔离，别人发数字不会命中；
- **60 秒窗口**：超时即失效（``DEFAULT_TTL``），过期后连数字都不再拦截；
- **不干扰其他插件**：只有「该用户在该会话有未过期记录」且「消息恰为
  数字 / + / -」时才触发（由命令层的规则判定），其余消息一律不拦截；
- 记录条数有上限（``MAX_RECORDS``，超出淘汰最旧），避免极端情况下内存增长。

状态只活在进程内：重启骰娘即失效，符合「候选列表本就短时有效」的语义。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .models import Candidate

#: 候选列表默认有效期（秒）
DEFAULT_TTL = 60.0

#: 候选列表每页条数
PAGE_SIZE = 8

#: 记录条数上限（超出淘汰最旧）
MAX_RECORDS = 256


def parse_selection_token(text: str) -> Optional[str]:
    """把消息文本解析为选择标记：返回数字串、``+``、``-``；其余返回 None。

    只接受 ASCII 数字（避免全角形近字符被误判），且不超过 3 位。
    """
    token = text.strip()
    if token in ("+", "-"):
        return token
    if token.isascii() and token.isdigit() and len(token) <= 3:
        return token
    return None


@dataclass
class SelectionRecord:
    """一次查询的候选列表状态（按会话 + 用户隔离）。"""

    session_id: str
    user_id: str
    keyword: str
    mode: str
    candidates: List[Candidate]
    page: int = 1
    touched_at: float = field(default_factory=time.monotonic)

    @property
    def page_count(self) -> int:
        """总页数（至少 1 页）。"""
        total = len(self.candidates)
        return max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    def move_page(self, delta: int) -> None:
        """翻页（页码收敛到 [1, page_count]，到头/到尾再翻保持不动）。"""
        self.page = min(max(1, self.page + delta), self.page_count)

    def page_slice(self) -> List[Candidate]:
        """当前页的候选列表（页码越界时收敛到合法范围）。"""
        self.page = min(max(1, self.page), self.page_count)
        start = (self.page - 1) * PAGE_SIZE
        return self.candidates[start : start + PAGE_SIZE]


class SelectionStore:
    """候选列表状态存储（内存、TTL、按会话+用户隔离）。"""

    def __init__(
        self,
        ttl: float = DEFAULT_TTL,
        *,
        clock: Callable[[], float] = time.monotonic,
        max_records: int = MAX_RECORDS,
    ) -> None:
        self._ttl = float(ttl)
        self._clock = clock
        self._max_records = max(1, int(max_records))
        self._records: Dict[Tuple[str, str], SelectionRecord] = {}

    def put(
        self,
        session_id: str,
        user_id: str,
        *,
        keyword: str,
        mode: str,
        candidates: List[Candidate],
    ) -> SelectionRecord:
        """写入（或覆盖）一条记录并返回它。"""
        record = SelectionRecord(
            session_id=session_id,
            user_id=str(user_id),
            keyword=keyword,
            mode=mode,
            candidates=list(candidates),
            touched_at=self._clock(),
        )
        key = (str(session_id), str(user_id))
        self._records.pop(key, None)
        self._records[key] = record
        self._evict()
        return record

    def get(self, session_id: str, user_id: str) -> Optional[SelectionRecord]:
        """取一条未过期记录（过期即清除并返回 None）。"""
        key = (str(session_id), str(user_id))
        record = self._records.get(key)
        if record is None:
            return None
        if self._is_expired(record):
            self._records.pop(key, None)
            return None
        return record

    def touch(self, record: SelectionRecord) -> None:
        """续期（查看详情/翻页后仍可继续选择，直到静默超时）。"""
        record.touched_at = self._clock()

    def clear(self, session_id: str, user_id: str) -> None:
        """清除某条记录（会话级清理用）。"""
        self._records.pop((str(session_id), str(user_id)), None)

    def reset(self) -> None:
        """清空全部记录（测试用）。"""
        self._records.clear()

    @property
    def size(self) -> int:
        """当前记录数（测试与排障用）。"""
        return len(self._records)

    def _is_expired(self, record: SelectionRecord) -> bool:
        return self._clock() - record.touched_at > self._ttl

    def _evict(self) -> None:
        """按需淘汰：先清过期，再按插入顺序淘汰最旧。"""
        if len(self._records) <= self._max_records:
            return
        for key, record in list(self._records.items()):
            if self._is_expired(record):
                self._records.pop(key, None)
        while len(self._records) > self._max_records:
            oldest_key = next(iter(self._records))
            self._records.pop(oldest_key, None)


#: 命令层共用的默认存储（测试可直接操作本对象或自建实例）
default_store = SelectionStore()
