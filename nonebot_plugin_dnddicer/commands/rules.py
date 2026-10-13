"""群级规则版本命令：``.规则版本``（别名 ``.rules``）。

语义（2026-10-01，批①）：
- **仅群聊可用**（私聊提示不可用），**不设管理权限**——与 ``.查询范围`` /
  ``.查询图片`` 同口径：规则版本是「本桌跑哪版规则」，全群成员都该能改；
- 无参数 → 查看本群生效版本与来源（群级显式设置 / 跟随骰主默认）；
- ``.规则版本 5e`` / ``.规则版本 5r`` → 写入群级设置（接受 ``2014`` /
  ``2024`` 等写法，见 ``character/rules.py`` 的归一表）；
- ``.规则版本 默认`` → 清除群级设置，回落配置项
  ``dnddicer_default_rules_version``。

群级设置被所有这些 5e/5r 差异点读取：长休生命骰恢复量（2014 一半 / 2024 全
恢复）、``.hp`` 的击晕结果（2014 归 0 且伤势稳定 / 2024 降为 1 HP）；后续
新增差异点一律走同一接口。
"""

from __future__ import annotations

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ..character import rules
from ..data.group_config import set_group_config_field
from . import base, text

_HELP = (
    ".规则版本 [5e|5r]\n"
    "  查看 / 设置本群使用的规则版本\n"
    "  影响长休生命骰恢复、击晕结果等差异点\n"
    "  无参数查看当前；.规则版本 默认 跟随骰主默认\n"
    "  示例：.规则版本 ｜ .规则版本 5r ｜ .规则版本 默认"
)

rules_matcher = base.on_dnd_command(
    "规则版本", _HELP, aliases=("rules",), doc="guide/rules-version"
)

#: 清除群级设置的参数写法
_RESET_WORDS = ("默认", "default", "重置", "reset")


def _display(version: str) -> str:
    """规则版本的展示名（``2014（5e）`` / ``2024（5r）``）。"""
    if version == rules.RULES_2014:
        return "2014（5e）"
    return "2024（5r）"


@rules_matcher.handle()
async def handle_rules_version(event: MessageEvent) -> None:
    """处理 .规则版本（查看 / 设置 / 清除群级设置）。"""
    if not isinstance(event, GroupMessageEvent):
        await rules_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    if not rest:
        version, is_group_level = await rules.read_rules_version(event.group_id)
        template = (
            text.TXT_RULES_CURRENT_SELF if is_group_level
            else text.TXT_RULES_CURRENT_DEFAULT
        )
        await rules_matcher.finish(template.format(version=_display(version)))

    if rest.lower() in _RESET_WORDS:
        await set_group_config_field(
            event.group_id, rules.RULES_VERSION_FIELD, None
        )
        version = await rules.rules_version(event.group_id)
        await rules_matcher.finish(
            text.TXT_RULES_RESET.format(version=_display(version))
        )

    version = rules.normalize_rules_version(rest)
    if version is None:
        await rules_matcher.finish(
            text.TXT_RULES_BAD_ARG.format(arg=rest, usage=text.TXT_RULES_USAGE)
        )
    await set_group_config_field(event.group_id, rules.RULES_VERSION_FIELD, version)
    await rules_matcher.finish(text.TXT_RULES_SET.format(version=_display(version)))
