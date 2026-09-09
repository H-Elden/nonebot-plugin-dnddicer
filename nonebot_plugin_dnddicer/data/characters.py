"""角色卡持久化（localstore + 单 JSON 文件 + 进程内缓存）。

存储：``{"schema_version": 1, "data": {"<group_id>:<user_id>": <DNDCharacter model_dump>, ...}}``
——与 DicePP 一致：每人在每群一张卡（group+QQ 为主键，天然隔离、只能操作自己的卡）。
早期 v0 裸字典（无 schema_version 字段）读取时自动按原样使用、首次写入升级 v1
（版本化机制见 data/schema.py）。

读写模式与 data/group_config.py 相同：内存缓存 + asyncio.Lock + asyncio.to_thread 落盘。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from ..character.models import DNDCharacter
from ..data import get_data_file
from ..data.schema import dump_versioned_dict, load_versioned_dict

_FILENAME = "characters.json"

_cache: Optional[Dict[str, Dict[str, Any]]] = None
_lock: Optional[asyncio.Lock] = None


def _config_file() -> Path:
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
    path = _config_file()
    _cache = await asyncio.to_thread(load_versioned_dict, path)
    return _cache


async def _dump_locked(data: Dict[str, Dict[str, Any]]) -> None:
    path = _config_file()
    await asyncio.to_thread(dump_versioned_dict, path, data)


async def get_character(group_id: int | str, user_id: int | str) -> Optional[DNDCharacter]:
    """读取某人在某群的角色卡（无则返回 None）。"""
    async with _get_lock():
        data = await _load_if_needed()
        raw = data.get(_key(group_id, user_id))
    if raw is None:
        return None
    try:
        return DNDCharacter.model_validate(raw)
    except Exception:  # noqa: BLE001 - 脏数据按无卡处理
        return None


async def save_character(character: DNDCharacter) -> None:
    """保存/覆盖角色卡。"""
    async with _get_lock():
        data = await _load_if_needed()
        data[_key(character.group_id, character.user_id)] = character.model_dump(mode="json")
        await _dump_locked(data)


async def delete_character(group_id: int | str, user_id: int | str) -> None:
    """删除某人某群的角色卡。"""
    async with _get_lock():
        data = await _load_if_needed()
        data.pop(_key(group_id, user_id), None)
        await _dump_locked(data)


async def list_characters_by_group(group_id: int | str) -> list[DNDCharacter]:
    """列出某群所有已初始化的角色卡。"""
    async with _get_lock():
        data = await _load_if_needed()
        prefix = f"{group_id}:"
        raw_list = [v for k, v in data.items() if k.startswith(prefix)]
    result: list[DNDCharacter] = []
    for raw in raw_list:
        try:
            char = DNDCharacter.model_validate(raw)
            if char.is_init:
                result.append(char)
        except Exception:  # noqa: BLE001
            continue
    return result
