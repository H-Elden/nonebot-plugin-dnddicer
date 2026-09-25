"""规则查询（T2）：数据源、条目定位与候选交互。

模块划分：
- ``models``      数据模型（Candidate / Entry / QueryUnavailableError）；
- ``source``      数据源（5echm 搜索服务：多端点回退 + 冷却 + 缓存 + 排序去重）；
- ``locating``    条目级定位（章节页正文 → 词条正文，三级回退）；
- ``interaction`` 候选列表的短时交互状态（按「会话 + 用户」隔离、默认 60 秒）。

合规与内容边界：查询结果只用于当次回复与短时内存缓存（不落盘、不随插件分发），
输出统一标注来源（《5e不全书》）；索引与内容由上游项目与各位骰主的部署提供。
"""

from __future__ import annotations

from .interaction import (
    DEFAULT_TTL,
    PAGE_SIZE,
    SelectionRecord,
    SelectionStore,
    default_store,
    parse_selection_token,
)
from .locating import locate_entry, split_entry_head
from .models import Candidate, QueryUnavailableError
from .source import (
    MAX_CANDIDATES,
    MODE_FULL,
    MODE_NAME,
    FiveChmSource,
)

__all__ = [
    "DEFAULT_TTL",
    "MAX_CANDIDATES",
    "MODE_FULL",
    "MODE_NAME",
    "PAGE_SIZE",
    "Candidate",
    "FiveChmSource",
    "QueryUnavailableError",
    "SelectionRecord",
    "SelectionStore",
    "default_store",
    "locate_entry",
    "parse_selection_token",
    "split_entry_head",
]
