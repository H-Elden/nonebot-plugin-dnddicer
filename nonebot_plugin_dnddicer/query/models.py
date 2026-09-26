"""规则查询数据模型。

- ``Candidate``：一条「候选」（服务端以章节页为粒度返回，正文为整页文本）；
- ``QueryUnavailableError``：所有端点都不可用时抛出（命令层据此给出降级提示）。

命名与字段语义对齐在线查询服务（5echm 搜索服务，MIT）的响应字段：
``index`` / ``title`` / ``category`` / ``path`` / ``rank`` / ``content``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Candidate:
    """一条候选（页面粒度）。

    Attributes:
        index: 服务端文档索引（去重键，与服务端 ``/api/content/:index`` 对应）。
        title: 页面标题（展示名）。
        category: 分类（通常是书名/章节组，如「玩家手册2024」）。
        path: 源文件路径（仅用于排查与来源标注）。
        rank: 服务端排序分（保留用于次级排序与调试）。
        content: 整页正文（条目级定位的输入）。
        base_url: 命中的端点地址（多端点回退时便于排查）。
        score: 插件侧排序分（标题精确 > 标题包含 > 条目头 > 全文）。
    """

    index: int
    title: str
    category: str
    path: str
    rank: int
    content: str
    base_url: str
    score: int = 0
    #: 条目锚点（速查索引候选特有；空串表示无锚点、按标题形态定位）
    anchor: str = ""
    #: 展示用元数据（速查索引候选特有，如「一环 · 惑控」「CR2 · 大型巨人」）
    meta: str = ""


class QueryUnavailableError(Exception):
    """查询服务不可用（全部端点尝试失败）。

    Attributes:
        attempts: 尝试过的端点地址列表（命令层用于提示已尝试数量）。
        last_error: 最后一个端点的失败原因（仅日志用，不展示给用户）。
    """

    def __init__(self, attempts: list[str], last_error: Optional[Exception] = None) -> None:
        super().__init__(f"查询服务不可用（已尝试 {len(attempts)} 个端点）")
        self.attempts = list(attempts)
        self.last_error = last_error
