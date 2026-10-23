"""无卡玩家的 HP 记录（localstore + 单 JSON 文件 + 进程内缓存）。

存储：``{"schema_version": 1, "data": {"<群号>:<QQ>": <HPInfo model_dump>, ...}}``
——群 + QQ 为主键，与角色卡库解耦。本群没有绑定角色卡时，``.hp`` 与
``.死亡豁免`` 读写这里的记录；一旦绑定角色卡，绑定入口会删除对应记录，
之后 HP 完全以卡面 ``$生命值$`` 为准。NPC 血量仍走 ``npc_health.json``。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from nonebot import logger

from ..character.models import HPInfo
from ..data import get_data_file
from ..data.schema import dump_versioned_dict, load_versioned_dict

_FILENAME = "hp_records.json"

_cache: Optional[Dict[str, Dict[str, Any]]] = None
_lock: Optional[asyncio.Lock] = None


def _data_file() -> Path:
    return get_data_file(_FILENAME)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _key(group_id: int | str, user_id: int | str) -> str:
    return f"{group_id}:{user_id}"


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


async def get_hp_record(
    group_id: int | str, user_id: int | str
) -> Optional[HPInfo]:
    """读取某人在某群的无卡 HP 记录（无记录或数据损坏返回 None）。"""
    async with _get_lock():
        data = await _load_if_needed()
        raw = data.get(_key(group_id, user_id))
    if raw is None:
        return None
    try:
        return HPInfo.model_validate(raw)
    except Exception:  # noqa: BLE001 - 脏数据按无记录处理
        return None


async def save_hp_record(
    group_id: int | str, user_id: int | str, hp_info: HPInfo
) -> None:
    """保存/覆盖某人在某群的无卡 HP 记录。

    落盘失败时回滚内存缓存并继续抛出——否则进程内会读到一份没写进磁盘的
    新值，重启后又变回旧值（2026-10-23 与 ``delete_hp_record`` 对齐）。
    """
    key = _key(group_id, user_id)
    async with _get_lock():
        data = await _load_if_needed()
        previous = data.get(key)
        data[key] = hp_info.model_dump(mode="json")
        try:
            await _dump_locked(data)
        except OSError:
            if previous is None:
                data.pop(key, None)
            else:
                data[key] = previous
            raise


async def delete_hp_record(
    group_id: int | str, user_id: int | str
) -> bool:
    """删除某人在某群的无卡 HP 记录；无记录返回 False。

    绑定角色卡时调用：删除失败只记日志，不阻断绑定（卡面才是后续唯一事实来源）。
    """
    async with _get_lock():
        data = await _load_if_needed()
        key = _key(group_id, user_id)
        if key not in data:
            return False
        removed = data.pop(key)
        try:
            await _dump_locked(data)
        except OSError:
            data[key] = removed
            logger.warning("DNDDicer 删除无卡 HP 记录失败: {}", key)
            return False
        return True


async def list_hp_records(
    group_id: int | str,
) -> List[Tuple[str, HPInfo]]:
    """列出某群全部无卡 HP 记录，返回 (QQ, HPInfo)，保持存储顺序。"""
    prefix = f"{group_id}:"
    async with _get_lock():
        data = await _load_if_needed()
        raw_items = [
            (key[len(prefix):], value)
            for key, value in data.items()
            if key.startswith(prefix)
        ]
    result: List[Tuple[str, HPInfo]] = []
    for user_id, raw in raw_items:
        try:
            result.append((user_id, HPInfo.model_validate(raw)))
        except Exception:  # noqa: BLE001 - 脏数据跳过
            continue
    return result
