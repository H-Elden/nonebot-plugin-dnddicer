"""群聊服务开关持久化（localstore + 单 JSON 文件 + 进程内缓存）。

语义（宿主新需求，2026-09-09 登记）：
- 群聊服务默认**关闭**（白名单）：未开启的群不响应本插件命令（管理命令 .bot 除外），
  由群主/管理员发送 ``.bot on`` 开启、``.bot off`` 关闭；
- 私聊不设门禁（可直接使用全部功能）；
- 存储文件：localstore 数据目录下 ``service_state.json``，
  结构：``{"schema_version": 1, "data": {"enabled_groups": ["<group_id(str)>", ...]}}``；
- 访问：进程内缓存 + ``asyncio.Lock`` + ``asyncio.to_thread`` 落盘（与
  data/group_config.py 同一模式；写入时同步更新缓存与磁盘）。

注意：读取/写入均为异步函数，仅在 NoneBot 事件处理协程中调用。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional, Set

from ..data import get_data_file
from ..data.schema import dump_versioned_dict, load_versioned_dict

#: 服务开关存储文件名
_SERVICE_STATE_FILENAME = "service_state.json"

#: 进程内缓存：已开启服务的群号集合（str）
_cache: Optional[Set[str]] = None
_lock: Optional[asyncio.Lock] = None


def _state_file() -> Path:
    return get_data_file(_SERVICE_STATE_FILENAME)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _extract_enabled_groups(raw: dict) -> Set[str]:
    """从版本化字典中提取开启服务群号集合（结构非法/损坏一律按空处理）。"""
    groups = raw.get("enabled_groups", [])
    if not isinstance(groups, list):
        return set()
    return {str(g) for g in groups if isinstance(g, (int, str))}


async def _load_if_needed() -> Set[str]:
    """首次访问时从磁盘加载（此后由写入路径维护内存缓存）。"""
    global _cache
    if _cache is not None:
        return _cache

    path = _state_file()
    _cache = _extract_enabled_groups(await asyncio.to_thread(load_versioned_dict, path))
    return _cache


async def is_service_enabled(group_id: int | str) -> bool:
    """判断某群的 DNDDicer 服务是否已开启（未开启 = 群聊门禁拦截）。"""
    key = str(group_id)
    async with _get_lock():
        groups = await _load_if_needed()
        return key in groups


async def set_service_enabled(group_id: int | str, enabled: bool) -> None:
    """开启/关闭某群的服务（无变化时不重复落盘）。"""
    key = str(group_id)
    async with _get_lock():
        groups = await _load_if_needed()
        changed = (key in groups) != enabled
        if not changed:
            return
        if enabled:
            groups.add(key)
        else:
            groups.discard(key)
        path = _state_file()
        data = {"enabled_groups": sorted(groups)}
        await asyncio.to_thread(dump_versioned_dict, path, data)
