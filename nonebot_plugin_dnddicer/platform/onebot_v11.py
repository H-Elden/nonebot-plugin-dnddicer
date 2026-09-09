"""OneBot V11 专属能力适配层（2026-09-09 建立）。

命令层只依赖本模块暴露的小接口集，不直接触碰 onebot v11 专属 API
与事件字段；多平台扩展时按适配器类型分派/替换本模块实现即可。

接口集（随验收修复收敛的现有 onebot 依赖点）：
- ``at_segment``：@ 消息段（battle.py 播报，原 ``_cq_at`` 拼 CQ 码文本）；
- ``event_sender_nickname``：事件 sender 字段的离线展示名（base.py
  get_display_name 回退链，群名片 → 昵称）；
- ``get_group_member_nickname``：get_group_member_info 查询群成员展示名
  （.hp list 名称回退链；本插件放宽「离线可用」的唯一一处，失败返回
  None 由调用方兜底、不影响列表主流程）；
- ``send_private_msg``：私聊发送（.rh 暗骰结果，原 roll.py 直连 call_api）。
"""

from __future__ import annotations

from typing import Optional, Union

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment


def at_segment(user_id: Union[int, str]) -> MessageSegment:
    """构造 @ 消息段（OneBot V11）。"""
    return MessageSegment.at(str(user_id))


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
