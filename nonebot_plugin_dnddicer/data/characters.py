"""角色卡持久化（localstore + 单 JSON 文件 + 进程内缓存）。

结构：``{"<group_id>:<user_id>": <DNDCharacter model_dump>, ...}``——
与 DicePP 一致：每人在每群一张卡（group+QQ 为主键，天然隔离、只能操作自己的卡）。

读写模式与 data/group_config.py 相同：内存缓存 + asyncio.Lock + asyncio.to_thread 落盘。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

from ..character.models import DNDCharacter
from ..data import get_data_file

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

    def _read() -> Dict[str, Dict[str, Any]]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    _cache = await asyncio.to_thread(_read)
    return _cache


async def _dump_locked(data: Dict[str, Dict[str, Any]]) -> None:
    path = _config_file()

    def _write() -> None:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    await asyncio.to_thread(_write)


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
