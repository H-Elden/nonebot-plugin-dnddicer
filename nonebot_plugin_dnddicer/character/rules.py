"""规则版本（2014 / 2024）归一与群级读取。

DND5e 与 DND5r（2024 规则）在若干处结算口径不同（当前为长休生命骰恢复量、
``.hp`` 的击晕结果等）。这些差异点**统一走本模块**：

- 归一：对外接受 ``2024`` / ``5r`` / ``2024版`` / ``2014`` / ``5e`` 等写法，
  内部一律用规范串 ``"2024"`` / ``"2014"``；
- 读取：``rules_version(group_id)`` 优先取群级设置（``.规则版本`` 写入群配置），
  群内未设置时回落配置项 ``dnddicer_default_rules_version``（默认 2024）。

数据层只做存储（见 data/group_config.py），配置只做默认值（见 config.py），
「群级优先 → 配置回落」的取舍集中在本模块。
"""

from __future__ import annotations

from typing import Optional, Tuple

from ..config import get_config
from ..data.group_config import get_group_config

#: 规则版本规范值（存储与比较一律用它）
RULES_2014 = "2014"
RULES_2024 = "2024"

#: 群配置里存规则版本的字段名
RULES_VERSION_FIELD = "rules_version"

#: 默认规则版本（配置项缺省值）
DEFAULT_RULES_VERSION = RULES_2024

#: 输入写法 → 规范值（先做小写与去空白；键均为小写）。
#: 「5r」「5.5e」「2024」（含版本后缀）都指 2024 规则；「5e」「2014」指 2014 规则。
_RULES_VERSION_ALIASES = {
    "2024": RULES_2024,
    "5r": RULES_2024,
    "5.5e": RULES_2024,
    "5e2024": RULES_2024,
    "2024版": RULES_2024,
    "2014": RULES_2014,
    "5e": RULES_2014,
    "5e2014": RULES_2014,
    "2014版": RULES_2014,
}


def normalize_rules_version(value: Optional[str]) -> Optional[str]:
    """把玩家/配置里的规则版本写法归一为 ``"2014"`` / ``"2024"``；无法识别返回 None。"""
    if value is None:
        return None
    key = str(value).strip().lower().replace(" ", "")
    return _RULES_VERSION_ALIASES.get(key)


def default_rules_version() -> str:
    """返回配置项里的默认规则版本（写错/为空时按内置默认 2024）。"""
    try:
        configured = get_config().dnddicer_default_rules_version
    except ValueError:
        # NoneBot 未初始化（纯函数单测等场景）：按内置默认值
        return DEFAULT_RULES_VERSION
    return normalize_rules_version(configured) or DEFAULT_RULES_VERSION


async def read_rules_version(group_id: int | str) -> Tuple[str, bool]:
    """返回某群生效的规则版本与来源：``(版本, 是否为群级显式设置)``。

    群级设置优先（``.规则版本 5e`` 写入），未设置时回落配置项默认值。
    群配置里的脏值（无法归一）按未设置处理，不让它把结算带偏。
    """
    config = await get_group_config(group_id)
    group_value = normalize_rules_version(config.get(RULES_VERSION_FIELD))
    if group_value is not None:
        return group_value, True
    return default_rules_version(), False


async def rules_version(group_id: int | str) -> str:
    """返回某群生效的规则版本（各差异点统一调用此接口）。"""
    version, _is_group_level = await read_rules_version(group_id)
    return version
