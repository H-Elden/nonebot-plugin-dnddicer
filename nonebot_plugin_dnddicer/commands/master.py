"""反馈命令：``.master <消息>``（把你的意见转发给骰主）。

语义（2026-09-30 定稿）：

- **群聊与私聊都可用**：群聊照常受 ``.bot`` 分组服务门禁（未开启服务的群不响应），
  私聊不受限；
- **收件人**取配置项 ``dnddicer_master_qq``（**单个** QQ），刻意不复用宿主
  ``SUPERUSERS``（那是集合、可能配了多个号，与「发给骰主本人」不是一回事）；
  未配置（或不是纯数字 QQ）时只回提示、不外呼；
- 骰娘**私聊**骰主转达，正文格式为「【骰娘反馈】来自<来源>」+ 消息正文；
- 正文上限 200 字，超出截断并在末尾标注「（已截断）」；
- 频率限制：同一人 60 秒最多一条（只计成功投递的那一条）；
- 日志只记「谁发的、成功与否、字数」，**不落正文**（隐私）。

发现入口：``.help`` 总览的 ``.help 联系``、``.help 联系`` 正文与 ``.help master``
详情本身；``.help 管理`` 组清单**不列**本命令（2026-09-30 拍板）。
"""

from __future__ import annotations

import math
import time
from typing import Callable, Optional

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent

from ..config import get_config
from ..platform import onebot_v11
from . import base, text

_HELP = (
    ".master <消息>\n"
    "  给骰主发送消息（反馈问题或建议）\n"
    "  群聊、私聊都可以用；骰娘私聊转达\n"
    "  骰主会看到你的 QQ 号与群号\n"
    "  示例：.master 先攻列表的顺序好像不对"
)

master_matcher = base.on_dnd_command("master", _HELP, doc="guide/faq")

#: 转发正文的长度上限（字）
MAX_MESSAGE_CHARS = 200
#: 同一人的发送间隔（秒）
RATE_LIMIT_SECONDS = 60.0

#: 时间源（测试可注入）；按人记录上次成功投递的时刻
_clock: Callable[[], float] = time.monotonic
_last_sent_at: dict[str, float] = {}


def reset_rate_limit() -> None:
    """清空频率限制记录（测试用）。"""
    _last_sent_at.clear()


def set_clock(clock: Optional[Callable[[], float]] = None) -> None:
    """替换时间源（测试用）；传 None 恢复默认的 ``time.monotonic``。"""
    global _clock
    _clock = clock or time.monotonic


def remaining_wait(user_id: str) -> float:
    """距离该用户下次可发送还需等待的秒数（0 = 现在可发）。"""
    last = _last_sent_at.get(user_id)
    if last is None:
        return 0.0
    return max(0.0, RATE_LIMIT_SECONDS - (_clock() - last))


def truncate_message(body: str) -> str:
    """按上限截断正文；超出时在末尾标注「（已截断）」。"""
    if len(body) <= MAX_MESSAGE_CHARS:
        return body
    return body[:MAX_MESSAGE_CHARS] + text.TXT_MASTER_TRUNCATED


def format_source(event: MessageEvent) -> str:
    """来源行：群聊写「群 <群号>（<群名片或昵称> / QQ <QQ号>）」，私聊写「私聊（QQ <QQ号>）」。

    群名片优先、取不到用昵称（事件自带字段，零 API 调用）；两者都取不到时
    省略姓名部分。
    """
    user_id = str(getattr(event, "user_id", ""))
    group_id = getattr(event, "group_id", None)
    if group_id is None:
        return text.TXT_MASTER_SOURCE_PRIVATE.format(qq=user_id)
    name = onebot_v11.event_sender_nickname(event)
    if name:
        return text.TXT_MASTER_SOURCE_GROUP.format(
            group=group_id, name=name, qq=user_id
        )
    return text.TXT_MASTER_SOURCE_GROUP_NO_NAME.format(group=group_id, qq=user_id)


def master_qq() -> str:
    """配置的骰主 QQ（未配置或不是纯数字时返回空串）。"""
    value = (getattr(get_config(), "dnddicer_master_qq", "") or "").strip()
    return value if value.isdigit() else ""


@master_matcher.handle()
async def handle_master(bot: Bot, event: MessageEvent) -> None:
    """处理 .master <消息>。"""
    body = (base.get_command_rest(event) or "").strip()
    if not body:
        await master_matcher.finish(text.TXT_MASTER_USAGE)

    receiver = master_qq()
    if not receiver:
        await master_matcher.finish(text.TXT_MASTER_NOT_CONFIGURED)

    user_id = str(getattr(event, "user_id", ""))
    wait = remaining_wait(user_id)
    if wait > 0:
        await master_matcher.finish(
            text.TXT_MASTER_RATE_LIMITED.format(seconds=max(1, math.ceil(wait)))
        )

    forwarded = text.TXT_MASTER_FORWARD.format(
        source=format_source(event), body=truncate_message(body)
    )
    try:
        await onebot_v11.send_private_msg(bot, int(receiver), forwarded)
    except Exception as exc:  # noqa: BLE001 - 投递失败要给用户可读提示，不能落入全局兜底
        # 隐私：只记来源与异常，不落用户正文
        logger.warning(
            "DNDDicer .master 转发失败 user_id={} group_id={}: {}",
            user_id,
            getattr(event, "group_id", None),
            exc,
        )
        await master_matcher.finish(text.TXT_MASTER_SEND_FAILED)

    _last_sent_at[user_id] = _clock()
    logger.info(
        "DNDDicer .master 已转发反馈 user_id={} group_id={} chars={} truncated={}",
        user_id,
        getattr(event, "group_id", None),
        len(body),
        len(body) > MAX_MESSAGE_CHARS,
    )
    await master_matcher.finish(text.TXT_MASTER_SENT)
