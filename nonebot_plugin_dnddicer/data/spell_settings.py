"""施法相关**按处设置**持久化（localstore + 单 JSON 文件 + 进程内缓存）。

当前只有一项：``.法术 提醒 on|off`` 的**未准备提醒开关**（2026-10-20 批②）。
默认**开启**；显式设置后按群持久保存（角色卡本身按群归属，群内设置对该群
全员生效，与 ``.查询图片`` / ``.help 链接`` 的按处一致）。

提醒的**判定**（是否对未标记准备的法术提醒，随群级规则版本与职业变化）在
施法命令层实现，本模块只负责存取开关。

存储文件：``nonebot_plugin_localstore`` 数据目录下的 ``spell_settings.json``，
结构::

    {"schema_version": 1,
     "data": {"reminder_enabled": {"group_<群号>": false}}}

键不存在 = 用默认值（开启）。

访问：进程内缓存 + ``asyncio.Lock`` + ``asyncio.to_thread`` 落盘（与
``data/help_settings.py`` 同一模式）；读取/写入均为异步函数，仅在 NoneBot
事件处理协程中调用。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict, Optional

from ..data import get_data_file
from ..data.schema import dump_versioned_dict, load_versioned_dict

#: 存储文件名
_SPELL_SETTINGS_FILENAME = "spell_settings.json"

_KEY_PREFIX_GROUP = "group_"

#: 未准备提醒默认开启
DEFAULT_REMINDER_ENABLED = True


def group_key(group_id: int | str) -> str:
    """群聊的按处键（设置对该群全员生效）。"""
    return f"{_KEY_PREFIX_GROUP}{group_id}"


_cache: Optional[Dict[str, bool]] = None
_lock: Optional[asyncio.Lock] = None


def _settings_file() -> Path:
    return get_data_file(_SPELL_SETTINGS_FILENAME)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _extract(raw: dict) -> Dict[str, bool]:
    """从版本化字典提取设置（结构非法/损坏一律按默认处理）。"""
    result: Dict[str, bool] = {}
    stored = raw.get("reminder_enabled")
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
    _cache = _extract(
        await asyncio.to_thread(load_versioned_dict, _settings_file())
    )
    return _cache


async def is_reminder_enabled(group_id: int | str) -> bool:
    """某群的未准备提醒是否开启（未显式设置时默认开启）。"""
    async with _get_lock():
        settings = await _load_if_needed()
        return settings.get(group_key(group_id), DEFAULT_REMINDER_ENABLED)


async def set_reminder_enabled(group_id: int | str, enabled: bool) -> None:
    """设置某群的未准备提醒开关（无变化时不重复落盘）。"""
    async with _get_lock():
        settings = await _load_if_needed()
        key = group_key(group_id)
        if settings.get(key) == enabled:
            return
        settings[key] = enabled
        await asyncio.to_thread(
            dump_versioned_dict,
            _settings_file(),
            {"reminder_enabled": dict(sorted(settings.items()))},
        )
