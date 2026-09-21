"""NPC/怪物血量持久化（localstore + 单 JSON 文件 + 进程内缓存）。

存储：``{"schema_version": 1, "data": {"<group_id>:<name>": <NPCHealth model_dump>, ...}}``
——对齐 DicePP npc_health 表（group+name 为主键），群级隔离；版本化机制见
data/schema.py。

读写模式与 data/characters.py 相同：内存缓存 + asyncio.Lock + asyncio.to_thread 落盘。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..character.models import HPInfo, NPCHealth
from ..data import get_data_file
from ..data.schema import dump_versioned_dict, load_versioned_dict

_FILENAME = "npc_health.json"

_cache: Optional[Dict[str, Dict[str, Any]]] = None
_lock: Optional[asyncio.Lock] = None


def _data_file() -> Path:
    return get_data_file(_FILENAME)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _key(group_id: int | str, name: str) -> str:
    return f"{group_id}:{name}"


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


async def get_npc_record(group_id: int | str, name: str) -> Optional[NPCHealth]:
    """读取某群某名称的完整 NPC 血量条目（无记录或数据损坏返回 None）。"""
    async with _get_lock():
        data = await _load_if_needed()
        raw = data.get(_key(group_id, name))
    if raw is None:
        return None
    try:
        return NPCHealth.model_validate(raw)
    except Exception:  # noqa: BLE001 - 脏数据按无记录处理
        return None


async def get_npc_health(group_id: int | str, name: str) -> Optional[HPInfo]:
    """读取某群某名称 NPC 的血量（无记录或数据损坏返回 None）。"""
    record = await get_npc_record(group_id, name)
    return record.hp_info if record is not None else None


async def save_npc_health(
    group_id: int | str,
    name: str,
    hp_info: HPInfo,
    persistent: Optional[bool] = None,
) -> None:
    """保存/覆盖某群某名称 NPC 的血量。

    ``persistent`` 为 None 时**继承已有条目的跨战斗保持标记**——常规血量
    保存路径（.hp 结算）不会抹掉 ``.npc 持久`` 状态；条目不存在时视为 False。
    """
    async with _get_lock():
        data = await _load_if_needed()
        key = _key(group_id, name)
        if persistent is None:
            existing = data.get(key)
            persistent = (
                bool(existing.get("persistent")) if isinstance(existing, dict) else False
            )
        record = NPCHealth(
            group_id=str(group_id), name=name, hp_info=hp_info, persistent=persistent
        )
        data[key] = record.model_dump(mode="json")
        await _dump_locked(data)


async def set_npc_persistent(
    group_id: int | str, name: str, persistent: bool
) -> bool:
    """设置某群某名称 NPC 的跨战斗保持标记；条目不存在返回 False。"""
    async with _get_lock():
        data = await _load_if_needed()
        key = _key(group_id, name)
        raw = data.get(key)
        if raw is None:
            return False
        try:
            record = NPCHealth.model_validate(raw)
        except Exception:  # noqa: BLE001 - 脏数据视为无记录
            return False
        record.persistent = persistent
        data[key] = record.model_dump(mode="json")
        await _dump_locked(data)
        return True


async def delete_npc_health(group_id: int | str, name: str) -> None:
    """删除某群某名称 NPC 的血量（无记录时静默）。"""
    async with _get_lock():
        data = await _load_if_needed()
        data.pop(_key(group_id, name), None)
        await _dump_locked(data)


async def list_npc_health(group_id: int | str) -> List[NPCHealth]:
    """列出某群全部 NPC 血量条目（保持存储顺序）。"""
    async with _get_lock():
        data = await _load_if_needed()
        prefix = f"{group_id}:"
        raw_list = [v for k, v in data.items() if k.startswith(prefix)]
    result: List[NPCHealth] = []
    for raw in raw_list:
        try:
            result.append(NPCHealth.model_validate(raw))
        except Exception:  # noqa: BLE001 - 脏数据跳过
            continue
    return result
