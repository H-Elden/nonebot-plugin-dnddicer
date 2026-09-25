"""规则查询图片显示的**按处开关**持久化（localstore + 单 JSON 文件 + 进程内缓存）。

语义（2026-09-25 用户需求）：
- 「本处」= 群聊**按群**（设置对该群全员生效）、私聊**按用户**（仅影响本人）；
- 默认**关闭**（文字）：骰主总开关 ``dnddicer_query_image_enabled`` 只决定
  「能不能用图片」（功能闸门与渲染依赖），各处在群里发送 ``.查询图片 on``
  才把本处切到图片；
- 骰主未配置（总开关未开或渲染依赖未装）时，``.查询图片 on`` 报错且**不写入**
  ——避免留下「看起来开了、实际没生效」的设置，当前仍以文字显示；
- 存储文件：``nonebot_plugin_localstore`` 数据目录下的 ``query_settings.json``，
  结构：``{"schema_version": 1, "data": {"image_enabled": ["<按处键>", ...]}}``
  （按处键形如 ``group_<群号>`` / ``private_<QQ号>``；关闭即移出集合，默认即文字）；
- 访问：进程内缓存 ``_cache`` + ``asyncio.Lock`` 保证读写一致性；落盘走
  ``asyncio.to_thread``（JSON 小文件），避免阻塞事件循环（与
  data/service_state.py 同一模式）。

注意：读取/写入均为异步函数，仅在 NoneBot 事件处理协程中调用
（此时插件已加载、localstore 可用）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional, Set

from ..data import get_data_file
from ..data.schema import dump_versioned_dict, load_versioned_dict

#: 存储文件名
_QUERY_SETTINGS_FILENAME = "query_settings.json"

#: 按处键前缀：群聊按群、私聊按用户
KEY_PREFIX_GROUP = "group_"
KEY_PREFIX_PRIVATE = "private_"

#: 进程内缓存：已开启图片显示的按处键集合
_cache: Optional[Set[str]] = None
_lock: Optional[asyncio.Lock] = None


def group_key(group_id: int | str) -> str:
    """群聊的按处键（设置对该群全员生效）。"""
    return f"{KEY_PREFIX_GROUP}{group_id}"


def private_key(user_id: int | str) -> str:
    """私聊的按处键（仅影响本人）。"""
    return f"{KEY_PREFIX_PRIVATE}{user_id}"


def _settings_file() -> Path:
    return get_data_file(_QUERY_SETTINGS_FILENAME)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _extract_enabled_keys(raw: dict) -> Set[str]:
    """从版本化字典中提取已开启的按处键集合（结构非法/损坏一律按空处理）。"""
    keys = raw.get("image_enabled", [])
    if not isinstance(keys, list):
        return set()
    return {str(key) for key in keys if isinstance(key, str) and key}


async def _load_if_needed() -> Set[str]:
    """首次访问时从磁盘加载（此后由写入路径维护内存缓存）。"""
    global _cache
    if _cache is not None:
        return _cache

    path = _settings_file()
    _cache = _extract_enabled_keys(await asyncio.to_thread(load_versioned_dict, path))
    return _cache


async def is_image_enabled(chat_key: str) -> bool:
    """判断某处（群/私聊）是否已开启图片显示（默认未开启 = 文字）。"""
    async with _get_lock():
        enabled = await _load_if_needed()
        return chat_key in enabled


async def set_image_enabled(chat_key: str, enabled: bool) -> None:
    """开启/关闭某处的图片显示（无变化时不重复落盘）。"""
    async with _get_lock():
        keys = await _load_if_needed()
        changed = (chat_key in keys) != enabled
        if not changed:
            return
        if enabled:
            keys.add(chat_key)
        else:
            keys.discard(chat_key)
        path = _settings_file()
        data = {"image_enabled": sorted(keys)}
        await asyncio.to_thread(dump_versioned_dict, path, data)
