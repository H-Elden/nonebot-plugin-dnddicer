"""数据层：本地数据存储的统一出口（商店合规要求：必须使用 nonebot-plugin-localstore）。

- 所有数据/缓存/配置文件一律经本模块获取路径，禁止直接写任意磁盘位置；
- localstore 目录由宿主决定：月白机器人已配置 ``LOCALSTORE_DATA_DIR=data``，
  数据将落于 ``data/nonebot_plugin_dnddicer/`` 下，与宿主体系兼容；
- 不得使用宿主项目私有工具（如月白的 makepath.py）——独立插件不能依赖宿主实现。

存储格式（json vs aiosqlite）与迁移/备份策略待功能落地时定案
（见 doc/骰娘插件开发计划.md 第 9 节待讨论项 8）。
"""

from pathlib import Path

from nonebot import require

# 幂等：插件包顶层 __init__.py 已 require 过，这里再次声明以保证本模块可独立使用
require("nonebot_plugin_localstore")

import nonebot_plugin_localstore as store  # noqa: E402

__all__ = ["get_data_dir", "get_data_file"]


def get_data_dir() -> Path:
    """返回本插件的数据目录（localstore 保证目录已存在）。"""
    return store.get_plugin_data_dir()


def get_data_file(filename: str) -> Path:
    """返回本插件数据目录下的文件路径（localstore 保证目录已存在）。"""
    return store.get_plugin_data_file(filename)
