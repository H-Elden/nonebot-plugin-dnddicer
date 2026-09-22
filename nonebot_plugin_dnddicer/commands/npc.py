"""NPC 管理命令：``.npc 持久`` / ``.npc 临时``（NPC 血量的跨战斗保持开关）。

- ``.npc 持久 名称``：该 NPC 血量跨战斗保持——``.ri`` 再次以新条目入先攻表
  时不自动回满（见 commands/initiative.py 的自动回满逻辑）；
- ``.npc 临时 名称``：恢复默认——每次新入先攻表时自动回满。

设计背景：同名 NPC 在新一场战斗中通常是不同个体（如多只「地精」），默认
每场回满可避免继承上一场的血量；需要长期延续血量的 NPC 用本命令一次性标记。

范围与约定：
- 目标解析复用 .hp 的三层搜索（PC 角色卡 → NPC 血量 → 先攻表，见 hp.py）；
- 仅作用于 NPC 血量条目：解析到玩家角色卡时提示不适用（@ 目标为真 @ 段提示）；
- 条目需先存在（``.hp 名称 当前/最大``），本命令不创建空记录。
"""

from __future__ import annotations

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ..data.npc_health import set_npc_persistent
from ..platform import onebot_v11
from . import base, text
from .hp import search_target

_HELP = (
    "NPC血量跨战斗保持开关（按名称，作用于一整条NPC血量记录）\n"
    ".npc 持久 名称 -> 跨战斗保持血量（每次入先攻表时不再自动回满）\n"
    ".npc 临时 名称 -> 恢复默认（每次新入先攻表时自动回满）\n"
    "目标可用名称中独一无二的一部分；记录需先用 .hp 名称 当前血量/最大血量 建立\n"
    "目标也支持 @ 玩家: @ 命中玩家角色卡时提示不是NPC（NPC血量按名称记录）\n"
    "示例：.npc 持久 向导 / .npc 临时 地精"
)
npc_matcher = base.on_dnd_command("npc", _HELP)


@npc_matcher.handle()
async def handle_npc(event: MessageEvent) -> None:
    """处理 .npc 持久 / .npc 临时。"""
    if not isinstance(event, GroupMessageEvent):
        await npc_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    mode = ""
    target_intent = ""
    for key in ("持久", "临时"):
        if rest.startswith(key):
            mode = key
            target_intent = rest[len(key):].strip()
            break
    if not mode or not target_intent:
        await npc_matcher.finish(_HELP)

    source_key, target_id = await search_target(target_intent, event.group_id)
    if source_key == "multiple":
        await npc_matcher.finish(
            text.TXT_HP_INFO_MULTI.format(name_list=target_id.split("/"))
        )
    if source_key == "at_miss":
        await npc_matcher.finish(
            onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
        )
    if not source_key:
        await npc_matcher.finish(
            text.TXT_HP_INFO_MISS.format(name=target_intent)
        )
    if source_key == "pc":
        target_qq = onebot_v11.parse_mention_token(target_intent)
        if target_qq is not None:
            await npc_matcher.finish(
                onebot_v11.at_reply(target_qq, text.TXT_NPC_PC_TARGET_AT)
            )
        await npc_matcher.finish(text.TXT_NPC_PC_TARGET.format(name=target_intent))

    persistent = mode == "持久"
    if not await set_npc_persistent(event.group_id, target_id, persistent):
        await npc_matcher.finish(text.TXT_NPC_NO_RECORD.format(name=target_id))
    if persistent:
        await npc_matcher.finish(text.TXT_NPC_PERSIST_ON.format(name=target_id))
    await npc_matcher.finish(text.TXT_NPC_PERSIST_OFF.format(name=target_id))
