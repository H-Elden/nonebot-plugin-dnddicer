"""帮助体系的**按处设置**持久化（localstore + 单 JSON 文件 + 进程内缓存）。

当前只有一项：``.help 链接`` 的**文档站链接开关**（2026-09-28 用户定稿）——
控制帮助回复末尾 ``帮助文档：<站点>`` 一行是否附带。

默认值按场景给（用户拍板）：**群聊默认关、私聊默认开**。显式 ``on`` / ``off``
后按处持久保存：群聊设置对该群全员生效，私聊仅影响本人（同 ``.查询图片`` 口径）。

存储文件：``nonebot_plugin_localstore`` 数据目录下的 ``help_settings.json``，
结构::

    {"schema_version": 1,
     "data": {"link_enabled": {"group_<群号>": false, "private_<QQ号>": true}}}

键不存在 = 用默认值（因此默认值可随场景变化，不必预先写盘）。

访问：进程内缓存 + ``asyncio.Lock`` + ``asyncio.to_thread`` 落盘（与
``data/query_settings.py`` 同一模式）；读取/写入均为异步函数，仅在 NoneBot
事件处理协程中调用。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Optional

from ..data import get_data_file
from ..data.schema import dump_versioned_dict, load_versioned_dict

#: 存储文件名
_HELP_SETTINGS_FILENAME = "help_settings.json"

#: 按处键前缀：群聊按群、私聊按用户（与 data/query_settings.py 同一约定）
KEY_PREFIX_GROUP = "group_"
KEY_PREFIX_PRIVATE = "private_"


def group_key(group_id: int | str) -> str:
    """群聊的按处键（设置对该群全员生效）。"""
    return f"{KEY_PREFIX_GROUP}{group_id}"


def private_key(user_id: int | str) -> str:
    """私聊的按处键（仅影响本人）。"""
    return f"{KEY_PREFIX_PRIVATE}{user_id}"


_cache: Optional[Dict[str, bool]] = None
_lock: Optional[asyncio.Lock] = None


def _settings_file() -> Path:
    return get_data_file(_HELP_SETTINGS_FILENAME)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _extract(raw: dict) -> Dict[str, bool]:
    """从版本化字典提取设置（结构非法/损坏一律按默认处理）。"""
    result: Dict[str, bool] = {}
    stored = raw.get("link_enabled")
    if isinstance(stored, dict):
        for chat_key, value in stored.items():
            if isinstance(chat_key, str) and chat_key and isinstance(value, bool):
                result[chat_key] = value
    return result


async def _load_if_needed() -> Dict[str, bool]:
    """首次访问时从磁盘加载（此后由写入路径维护内存缓存）。"""
    global _cache
    if _cache is not None:
        return _cache
    _cache = _extract(await asyncio.to_thread(load_versioned_dict, _settings_file()))
    return _cache


async def is_link_enabled(chat_key: str, *, default: bool) -> bool:
    """判断某处帮助回复是否附带文档站链接行（未显式设置时用 ``default``）。"""
    async with _get_lock():
        settings = await _load_if_needed()
        return settings.get(chat_key, default)


async def set_link_enabled(chat_key: str, enabled: bool) -> None:
    """设置某处的文档站链接开关（无变化时不重复落盘）。"""
    async with _get_lock():
        settings = await _load_if_needed()
        if settings.get(chat_key) == enabled:
            return
        settings[chat_key] = enabled
        await asyncio.to_thread(
            dump_versioned_dict, _settings_file(), {"link_enabled": dict(sorted(settings.items()))}
        )
