"""规则查询的**按处设置**持久化（localstore + 单 JSON 文件 + 进程内缓存）。

两类设置（都是「群聊按群、私聊按用户」的按处粒度）：

1. **图片显示开关**（``.查询图片``）：存「已开启集合」——默认文字，开启即加入；
2. **查询范围**（``.查询范围``）：存「按处键 → 站内目录名列表」——默认**未设置
   = 全部开放**，设置为若干书目/整目录（见 ``query/books.py``）。

语义（2026-09-25 用户需求）：
- 图片开关的**总闸**是骰主配置 ``dnddicer_query_image_enabled``：总闸未开或渲染
  依赖未装时，``.查询图片 on`` 报错且**不写入**（不留「看起来开了、没生效」的设置）；
- 查询范围的**前置**是规则查询功能已开启（``dnddicer_query_enabled``，本模块不判定，
  由命令层把关）；未设置 = 全部目录都可查，与历史行为一致。

存储文件：``nonebot_plugin_localstore`` 数据目录下的 ``query_settings.json``，
结构::

    {"schema_version": 1,
     "data": {"image_enabled": ["<按处键>", ...],
              "scope": {"<按处键>": ["<站内目录名>", ...]}}}

（按处键形如 ``group_<群号>`` / ``private_<QQ号>``；关闭图片即移出集合，清除范围
即移除该键——两类设置的空值都等价于默认。）

访问：进程内缓存 + ``asyncio.Lock`` + ``asyncio.to_thread`` 落盘（与
data/service_state.py 同一模式）。读取/写入均为异步函数，仅在 NoneBot 事件处理
协程中调用（此时插件已加载、localstore 可用）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from ..data import get_data_file
from ..data.schema import dump_versioned_dict, load_versioned_dict

#: 存储文件名
_QUERY_SETTINGS_FILENAME = "query_settings.json"

#: 按处键前缀：群聊按群、私聊按用户
KEY_PREFIX_GROUP = "group_"
KEY_PREFIX_PRIVATE = "private_"


def group_key(group_id: int | str) -> str:
    """群聊的按处键（设置对该群全员生效）。"""
    return f"{KEY_PREFIX_GROUP}{group_id}"


def private_key(user_id: int | str) -> str:
    """私聊的按处键（仅影响本人）。"""
    return f"{KEY_PREFIX_PRIVATE}{user_id}"


@dataclass
class _Settings:
    """进程内缓存的两类设置。"""

    #: 已开启图片显示的按处键
    image_enabled: Set[str] = field(default_factory=set)
    #: 查询范围：按处键 → 站内目录名列表（键不存在 = 未设置 = 全部开放）
    scope: Dict[str, List[str]] = field(default_factory=dict)


_cache: Optional[_Settings] = None
_lock: Optional[asyncio.Lock] = None


def _settings_file() -> Path:
    return get_data_file(_QUERY_SETTINGS_FILENAME)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _extract(raw: dict) -> _Settings:
    """从版本化字典提取设置（结构非法/损坏一律按默认处理）。"""
    settings = _Settings()

    keys = raw.get("image_enabled", [])
    if isinstance(keys, list):
        settings.image_enabled = {
            str(key) for key in keys if isinstance(key, str) and key
        }

    scope = raw.get("scope")
    if isinstance(scope, dict):
        for chat_key, categories in scope.items():
            if not isinstance(chat_key, str) or not chat_key:
                continue
            if not isinstance(categories, list):
                continue
            cleaned = [str(c) for c in categories if isinstance(c, str) and c]
            if cleaned:
                settings.scope[chat_key] = cleaned

    return settings


def _dump_data(settings: _Settings) -> Dict[str, object]:
    """把缓存序列化为落盘结构（列表排序，便于人工查看与 diff）。"""
    return {
        "image_enabled": sorted(settings.image_enabled),
        "scope": {
            key: sorted(set(categories))
            for key, categories in sorted(settings.scope.items())
        },
    }


async def _load_if_needed() -> _Settings:
    """首次访问时从磁盘加载（此后由写入路径维护内存缓存）。"""
    global _cache
    if _cache is not None:
        return _cache

    path = _settings_file()
    _cache = _extract(await asyncio.to_thread(load_versioned_dict, path))
    return _cache


async def _save_locked(settings: _Settings) -> None:
    """在持锁状态下写盘（异步线程，不阻塞事件循环）。"""
    path = _settings_file()
    await asyncio.to_thread(dump_versioned_dict, path, _dump_data(settings))


# =========================================================================
# 图片显示开关（.查询图片）
# =========================================================================


async def is_image_enabled(chat_key: str) -> bool:
    """判断某处（群/私聊）是否已开启图片显示（默认未开启 = 文字）。"""
    async with _get_lock():
        settings = await _load_if_needed()
        return chat_key in settings.image_enabled


async def set_image_enabled(chat_key: str, enabled: bool) -> None:
    """开启/关闭某处的图片显示（无变化时不重复落盘）。"""
    async with _get_lock():
        settings = await _load_if_needed()
        changed = (chat_key in settings.image_enabled) != enabled
        if not changed:
            return
        if enabled:
            settings.image_enabled.add(chat_key)
        else:
            settings.image_enabled.discard(chat_key)
        await _save_locked(settings)


# =========================================================================
# 查询范围（.查询范围）
# =========================================================================


async def get_scope(chat_key: str) -> Optional[List[str]]:
    """返回某处的查询范围（站内目录名列表）；**未设置时返回 None（= 全部开放）**。"""
    async with _get_lock():
        settings = await _load_if_needed()
        categories = settings.scope.get(chat_key)
        return list(categories) if categories else None


async def set_scope(chat_key: str, categories: Optional[Sequence[str]]) -> None:
    """设置某处的查询范围；传 None 或空序列表示**清除**（回到全部开放）。"""
    async with _get_lock():
        settings = await _load_if_needed()
        cleaned = [str(c) for c in (categories or []) if str(c)]
        if cleaned:
            settings.scope[chat_key] = cleaned
        else:
            settings.scope.pop(chat_key, None)
        await _save_locked(settings)
