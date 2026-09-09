"""插件信息与群聊服务开关命令：``.bot``（宿主新需求，2026-09-09 登记，见计划文档 8.5 节）。

- ``.bot``：查看插件信息（名称/版本/简介）；群聊内附带本群服务状态；
- ``.bot on`` / ``.bot off``：仅限群聊、仅群主/管理员——在本群开启/关闭本插件的服务；
- 服务开关语义：群聊默认关闭（白名单），未开启的群除 .bot 外不响应任何命令
  （静默，事件继续交给宿主其他插件），私聊不受限制——门禁见 commands/base.py
  ``group_service_rule``，持久化见 data/service_state.py。
"""

from __future__ import annotations

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ..data.service_state import is_service_enabled, set_service_enabled
from ..platform import onebot_v11
from ..version import __version__
from . import base, text

_HELP = (
    "查看插件信息或开关本群服务：.bot on / .bot off（仅群聊，需群主或管理员权限）\n"
    "用法：\n"
    "· .bot —— 查看插件信息（版本/简介），群聊内附带本群服务状态\n"
    "· .bot on —— 在本群开启服务（未开启的群仅 .bot 命令可用）\n"
    "· .bot off —— 在本群关闭服务（本群不再响应本插件命令，.bot 不受影响）\n"
    "说明：.bot on/off 仅限群聊使用，需群主或管理员权限；私聊不受群聊服务开关限制。"
)

bot_matcher = base.on_dnd_command("bot", _HELP)


async def _build_info(event: MessageEvent) -> str:
    """拼装 .bot 插件信息文案（群聊附带本群服务状态）。"""
    lines = [
        text.TXT_BOT_HEAD.format(version=__version__),
        text.TXT_BOT_INTRO,
    ]
    if isinstance(event, GroupMessageEvent):
        enabled = await is_service_enabled(event.group_id)
        lines.append(text.TXT_BOT_STATE_ON if enabled else text.TXT_BOT_STATE_OFF)
    else:
        lines.append(text.TXT_BOT_STATE_PRIVATE)
    lines.append(text.TXT_BOT_USAGE)
    return "\n".join(lines)


@bot_matcher.handle()
async def handle_bot(event: MessageEvent) -> None:
    """处理 .bot（信息/开关）。"""
    rest = (base.get_command_rest(event) or "").strip()

    if not rest:
        await bot_matcher.finish(await _build_info(event))

    action = rest.lower()
    if action not in ("on", "off"):
        await bot_matcher.finish(text.TXT_BOT_BAD_ARG)
    if not isinstance(event, GroupMessageEvent):
        await bot_matcher.finish(text.TXT_GROUP_ONLY)
    if not onebot_v11.is_group_manager(event):
        await bot_matcher.finish(text.TXT_BOT_NO_PERMISSION)

    await set_service_enabled(event.group_id, enabled=(action == "on"))
    await bot_matcher.finish(
        text.TXT_BOT_ON if action == "on" else text.TXT_BOT_OFF
    )
