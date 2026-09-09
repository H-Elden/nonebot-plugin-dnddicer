"""群配置持久化（localstore + 单 JSON 文件 + 进程内缓存）。

设计：
- 存储文件：``nonebot_plugin_localstore`` 数据目录下的 ``group_config.json``
  （宿主配置 LOCALSTORE_DATA_DIR=data 时落 ``data/nonebot_plugin_dnddicer/``）；
- 结构：``{"schema_version": 1, "data": {"<group_id(str)>": {"default_dice": "D20", ...}}}``
  ——后续群配置项（默认骰面、功能开关等）在同一 dict 上扩展；早期 v0 裸字典
  读取时自动按原样使用、首次写入升级 v1（版本化机制见 data/schema.py）；
- 访问：进程内缓存 ``_cache`` + ``asyncio.Lock`` 保证读写一致性；落盘走
  ``asyncio.to_thread``（JSON 小文件），避免阻塞事件循环（商店合规：全异步）；
- 语义：首次访问时读盘一次并缓存；写入时同步更新缓存与磁盘。

注意：群配置读取/写入都是异步函数，仅在 NoneBot 事件处理协程中调用
（此时插件已加载、localstore 可用）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from ..data import get_data_file
from ..data.schema import dump_versioned_dict, load_versioned_dict

#: 群配置文件名
_GROUP_CONFIG_FILENAME = "group_config.json"

_cache: Optional[Dict[str, Dict[str, Any]]] = None
_lock: Optional[asyncio.Lock] = None


def _config_file() -> Path:
    return get_data_file(_GROUP_CONFIG_FILENAME)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def _load_if_needed() -> Dict[str, Dict[str, Any]]:
    """首次访问时从磁盘加载群配置（此后由写入路径维护内存缓存）。"""
    global _cache
    if _cache is not None:
        return _cache

    path = _config_file()
    _cache = await asyncio.to_thread(load_versioned_dict, path)
    return _cache


async def get_group_config(group_id: int | str) -> Dict[str, Any]:
    """返回某群的配置字典（不存在时返回空字典的副本）。"""
    key = str(group_id)
    async with _get_lock():
        configs = await _load_if_needed()
        return dict(configs.get(key, {}))


async def set_group_config_field(group_id: int | str, field: str, value: Any) -> None:
    """设置某群的单个配置项并落盘。"""
    key = str(group_id)
    async with _get_lock():
        configs = await _load_if_needed()
        configs.setdefault(key, {})[field] = value
        await _dump_locked(configs)


async def _dump_locked(configs: Dict[str, Dict[str, Any]]) -> None:
    """在持锁状态下写盘（异步线程，不阻塞事件循环）。"""
    path = _config_file()
    await asyncio.to_thread(dump_versioned_dict, path, configs)
