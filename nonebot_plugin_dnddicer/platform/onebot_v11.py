"""OneBot V11 专属能力适配层（2026-09-09 建立）。

命令层只依赖本模块暴露的小接口集，不直接触碰 onebot v11 专属 API
与事件字段；多平台扩展时按适配器类型分派/替换本模块实现即可。

接口集（随验收修复收敛的现有 onebot 依赖点）：
- ``at_segment``：@ 消息段（battle.py 播报，原 ``_cq_at`` 拼 CQ 码文本）；
- ``event_sender_nickname``：事件 sender 字段的离线展示名（commands/base.py
  resolve_display_name 统一回退链的「本人」两级：群名片 → 昵称）；
- ``get_group_member_nickname``：get_group_member_info 查询群成员展示名
  （统一回退链中查询他人/本人的 API 兜底；失败返回 None 由调用方继续回退，
  不影响命令主流程）；
- ``send_private_msg``：私聊发送（.rh 暗骰结果，原 roll.py 直连 call_api）。
- @ 提及目标（2026-09-22 新增）：``rebuild_text_with_mentions`` / ``list_mentions``
  / ``iter_mentions`` / ``parse_mention_token`` / ``strip_mentions`` /
  ``strip_leading_mentions`` / ``at_reply``——onebot v11 的 at 段不进
  extract_plain_text（``.hp @小明 -d4`` 的 @ 目标会凭空消失），故把 at 段重建为
  ``@<qq>`` 标记保留在参数文本中供命令层直连该 QQ 的角色卡；机器人自身 @ 丢弃。
"""

from __future__ import annotations

import re
from typing import List, Optional, Union

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment

#: @ 标记形态：``@`` + QQ 数字（消息重建文本中的 at 段占位）
_MENTION_RE = re.compile(r"@(\d+)")


def at_segment(user_id: Union[int, str]) -> MessageSegment:
    """构造 @ 消息段（OneBot V11）。"""
    return MessageSegment.at(str(user_id))


def rebuild_text_with_mentions(event: MessageEvent) -> str:
    """把事件消息重建为带 @ 标记的纯文本（命令层 @ 目标的取参基础）。

    - text 段原样拼接；at 段重建为 ``@<qq>`` 标记（保留目标 QQ，供命令层
      直连该玩家的角色卡，而非回填名称重新落入模糊搜索）；
    - **机器人自身的 @ 段与 @全体成员丢弃**（``@骰娘 .hp -d4`` 维持
      「等于给自己」的语义）；
    - 其他段（图片/表情等）与适配器 ``extract_plain_text`` 同语义：不进文本。
    """
    message = getattr(event, "message", None)
    if message is None:
        return ""
    self_id = str(getattr(event, "self_id", "") or "")
    parts: List[str] = []
    for segment in message:
        seg_type = getattr(segment, "type", "")
        data = getattr(segment, "data", None) or {}
        if seg_type == "text":
            parts.append(str(data.get("text", "")))
        elif seg_type == "at":
            qq = str(data.get("qq", "") or "")
            if qq.isdigit() and qq != self_id:
                parts.append(f"@{qq}")
    return "".join(parts)


def list_mentions(event: MessageEvent) -> List[str]:
    """按消息顺序返回非机器人 @ 的 QQ 列表（含手打的同形 ``@数字`` 文本）。"""
    return iter_mentions(rebuild_text_with_mentions(event))


def iter_mentions(text: str) -> List[str]:
    """按序提取文本中的全部 ``@<qq>`` 标记。"""
    return _MENTION_RE.findall(text)


def parse_mention_token(text: str) -> Optional[str]:
    """文本恰为一个 ``@<qq>`` 标记时返回 QQ，否则返回 None。"""
    match = _MENTION_RE.fullmatch(text.strip())
    return match.group(1) if match else None


def strip_mentions(text: str) -> str:
    """移除文本中的全部 ``@<qq>`` 标记（检定修正串拆目标用）。"""
    return _MENTION_RE.sub("", text)


def strip_leading_mentions(text: str) -> str:
    """剥离文本开头的空白与连续 ``@<qq>`` 标记。

    对应「先点名字再敲命令」的输入习惯（``@小明 .hp -d4``）：命令前的 @ 不属
    目标位置，是否提示由命令层判定（见 commands/hp.py 的游离 @ 拦截）。
    """
    result = text.lstrip()
    while True:
        match = _MENTION_RE.match(result)
        if match is None:
            return result
        result = result[match.end():].lstrip()


def at_reply(user_id: Union[int, str], content: str) -> Message:
    """真 @ 消息段 + 文案组装（群里显示为对方昵称，而非 ``@12345`` 字样）。"""
    return MessageSegment.at(str(user_id)) + f" {content}"


#: 群管理角色（群主/管理员；sender.role 字段取值）
MANAGER_ROLES = ("owner", "admin")


def event_sender_role(event: MessageEvent) -> str:
    """取消息事件 sender 的角色字段（群聊：owner/admin/member；私聊等为空）。"""
    sender = getattr(event, "sender", None)
    return getattr(sender, "role", "") if sender is not None else ""


def is_group_manager(event: MessageEvent) -> bool:
    """判断发送者是否为群主/管理员（.dset 修改与 .bot on/off 共用口径）。"""
    return event_sender_role(event) in MANAGER_ROLES


def event_sender_nickname(event: MessageEvent) -> str:
    """取事件 sender 字段的展示名（群名片 → 昵称），无则返回空串。

    基于消息事件自带字段（离线可用、零 API 调用）。
    """
    sender = getattr(event, "sender", None)
    if sender is not None:
        card = getattr(sender, "card", None) or ""
        if card:
            return card
        nickname = getattr(sender, "nickname", None) or ""
        if nickname:
            return nickname
    return ""


async def get_group_member_nickname(
    bot: Bot, group_id: int, user_id: int
) -> Optional[str]:
    """查询群成员展示名（群名片 → 昵称）；API 失败/字段缺失返回 None。

    API 异常由本函数吞掉并记日志，调用方对 None 做兜底。
    """
    try:
        info = await bot.call_api(
            "get_group_member_info", group_id=group_id, user_id=user_id
        )
    except Exception as exc:  # noqa: BLE001 - 查询失败不应影响列表主流程
        logger.warning(
            "DNDDicer 群成员信息查询失败 group_id={} user_id={}: {}",
            group_id,
            user_id,
            exc,
        )
        return None
    data = info if isinstance(info, dict) else {}
    card = (data.get("card") or "").strip()
    if card:
        return card
    nickname = (data.get("nickname") or "").strip()
    return nickname or None


async def send_private_msg(bot: Bot, user_id: int, message: str) -> None:
    """私聊发送消息（onebot v11 无便捷方法，走通用 call_api）。"""
    await bot.call_api("send_private_msg", user_id=user_id, message=message)
