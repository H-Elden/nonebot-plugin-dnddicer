"""JSON 存储的 ``schema_version`` 版本化读写基座。

背景（见 doc/NoneBot最佳实践调研报告.md 1.8 节）：orm 方案最有价值的是
Alembic 式版本化迁移思想——顶层结构统一升级为
``{"schema_version": 1, "data": {...}}``，读取时按版本迁移；避免未来字段
演进时写一次性脚本、存量数据读不进来的坑。

规则：
- **v0（无版本字段）**：文件为裸 ``{key: value}`` 字典（本项目早期格式），
  读取时按原样使用，首次写入时自动升级为 v1 包装；
- **v1（当前）**：``{"schema_version": 1, "data": {...}}``；
- 未知/更高主版本：按损坏数据处理（拒绝静默降级写入），记录错误日志。

本模块只提供同步读写原语，调用方（各 data/*.py）负责 to_thread/缓存/锁。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from nonebot import logger

SCHEMA_VERSION = 1


def load_versioned_dict(path: Path) -> Dict[str, Any]:
    """读取 JSON 存储文件并按其 schema 版本返回内层数据字典。

    文件不存在 / JSON 损坏 / 结构不合法一律返回空字典（不阻塞命令，
    与早期 data 层语义一致）；更高主版本拒绝降级读取（返回空并记错误）。
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(raw, dict):
        return {}

    version = raw.get("schema_version")
    if version is None:
        # v0：早期裸字典（键 → 数据条目）
        return raw

    if not isinstance(version, int) or version > SCHEMA_VERSION:
        logger.error(
            "数据文件 {} 的 schema_version={} 高于当前支持的 {}，"
            "已按空数据读取（拒绝降级写入，请升级插件）",
            path,
            version,
            SCHEMA_VERSION,
        )
        return {}

    data = raw.get("data")
    return data if isinstance(data, dict) else {}


def dump_versioned_dict(path: Path, data: Dict[str, Any]) -> None:
    """以当前 schema 版本（v1 包装）落盘数据字典。"""
    document = {
        "schema_version": SCHEMA_VERSION,
        "data": data,
    }
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
