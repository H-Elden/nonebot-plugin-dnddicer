"""先攻表/战斗轮状态持久化（localstore + 单 JSON 文件 + 进程内缓存）。

结构：``{"schema_version": 1, "data": {"<group_id(str)>": <InitList model_dump>, ...}}``
——与 DicePP 一致，每个群一张先攻表（含战斗轮指针），群级隔离；版本化机制见
data/schema.py。

读写模式与 data/characters.py 相同：内存缓存 + asyncio.Lock + asyncio.to_thread 落盘。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from ..initiative.models import InitList
from ..data import get_data_file
from ..data.schema import dump_versioned_dict, load_versioned_dict

_FILENAME = "initiative.json"

_cache: Optional[Dict[str, Dict[str, Any]]] = None
_lock: Optional[asyncio.Lock] = None


def _data_file() -> Path:
    return get_data_file(_FILENAME)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def _load_if_needed() -> Dict[str, Dict[str, Any]]:
    global _cache
    if _cache is not None:
        return _cache
    path = _data_file()
    _cache = await asyncio.to_thread(load_versioned_dict, path)
    return _cache


async def _dump_locked(data: Dict[str, Dict[str, Any]]) -> None:
    path = _data_file()
    await asyncio.to_thread(dump_versioned_dict, path, data)


async def get_init_list(group_id: int | str) -> Optional[InitList]:
    """读取某群的先攻表（无或数据损坏返回 None）。"""
    key = str(group_id)
    async with _get_lock():
        data = await _load_if_needed()
        raw = data.get(key)
    if raw is None:
        return None
    try:
        return InitList.model_validate(raw)
    except Exception:  # noqa: BLE001 - 脏数据按无表处理
        return None


async def save_init_list(init_list: InitList) -> None:
    """保存/覆盖某群的先攻表。"""
    async with _get_lock():
        data = await _load_if_needed()
        data[str(init_list.group_id)] = init_list.model_dump(mode="json")
        await _dump_locked(data)


async def clear_init_list(group_id: int | str) -> None:
    """删除某群的先攻表（含战斗轮指针；.br/.init clr 均走此路径）。"""
    async with _get_lock():
        data = await _load_if_needed()
        data.pop(str(group_id), None)
        await _dump_locked(data)
