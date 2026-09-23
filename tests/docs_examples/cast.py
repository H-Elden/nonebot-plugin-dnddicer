"""文档站示例团：固定人物、角色卡与 NPC 名册（示例数据的唯一来源）。

约定：
- 群号 / QQ 段与既有测试用例不重叠，避免数据互相污染；
- 角色卡文本即 ``.角色卡记录`` 的负载（不含命令名），与站点《示例团与人物》页的卡面逐字一致；
- 调整人名、数值或配色时三处同步：本文件、气泡容器的示例团名册（``docs/.vitepress/plugins/
  chat-container.mts``）、``docs/`` 页面正文；
- 建卡口径：27 点购点 → 背景属性加值（+2/+1）→ 4 级属性值提升，只用 2024 核心三书
  （玩家手册 / 城主指南 / 怪物图鉴）；卡面只登记该角色真实拥有的熟练项与「能算的部分」，
  额外加值来源为 2024 城主指南的魔法物品（5–10 级开卡给 1 件普通 + 1 件非普通）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

# ── 示例群与机器人 ────────────────────────────────────────────────────────
GROUP_ID = 76000001
BOT_QQ = 76000000
BOT_NAME = "屠龙骰"
PRIVATE_BOT_NAME = f"{BOT_NAME}（私聊）"


@dataclass(frozen=True)
class Persona:
    """一名群成员的固定身份。"""

    nickname: str  # 群昵称（气泡与转录里显示的名字）
    qq: int
    role: str  # 群角色：owner / admin / member
    card_name: str  # QQ 群名片（回退链第二级；此处与群昵称一致）
    qq_nickname: str  # QQ 昵称（回退链第三级；刻意与群名片不同，用于验证取值顺序）
    character: Optional[str] = None  # 角色卡姓名（无卡为 None）


DM = Persona("白鸦", 76_010_001, "owner", "白鸦", "老白")
A_CHA = Persona("阿茶", 76_010_002, "member", "阿茶", "茶茶", "薇拉")
XIAO_MAN = Persona("小满", 76_010_003, "member", "小满", "满仔", "洛恩")
LAO_MAO = Persona("老猫", 76_010_004, "member", "老猫", "猫叔", "塔莉")
A_YAN = Persona("阿岩", 76_010_005, "member", "阿岩", "岩石", "布鲁姆")
XIAO_LU = Persona("小鹿", 76_010_006, "member", "小鹿", "鹿角")

PERSONAS: List[Persona] = [DM, A_CHA, XIAO_MAN, LAO_MAO, A_YAN, XIAO_LU]
BY_NAME: Dict[str, Persona] = {persona.nickname: persona for persona in PERSONAS}

#: NPC 名册（首战：碎星隘口的哥布林哨站；「向导」用于跨战斗保持血量示例）
NPCS = ["哥布林", "熊地精", "狼", "向导"]

# ── 四张角色卡（5r / 2024 玩家手册；`.角色卡记录` 负载，不含命令名）──────────
CARDS: Dict[str, str] = {
    "薇拉": "\n".join(
        [
            "$姓名$ 薇拉",
            "$等级$ 5",
            "$生命值$ 54/54",
            "$生命骰$ 5/5 D10",
            "$属性$ 18/10/14/8/10/16",
            "$熟练$ 力量攻击/感知豁免/魅力豁免/运动/威吓/洞悉/游说/察觉",
            "$额外加值$ 力量攻击:+1",
        ]
    ),
    "洛恩": "\n".join(
        [
            "$姓名$ 洛恩",
            "$等级$ 5",
            "$生命值$ 37/37",
            "$生命骰$ 5/5 D6",
            "$属性$ 8/15/16/18/10/8",
            "$熟练$ 敏捷攻击/智力豁免/感知豁免/2*奥秘/历史/调查/宗教/察觉",
        ]
    ),
    "塔莉": "\n".join(
        [
            "$姓名$ 塔莉",
            "$等级$ 5",
            "$生命值$ 43/43",
            "$生命骰$ 5/5 D8",
            "$属性$ 8/18/16/10/14/10",
            "$熟练$ 敏捷攻击/敏捷豁免/智力豁免/2*隐匿/2*巧手/先攻/欺瞒/察觉/游说/洞悉",
            "$额外加值$ 隐匿:优势",
        ]
    ),
    "布鲁姆": "\n".join(
        [
            "$姓名$ 布鲁姆",
            "$等级$ 5",
            "$生命值$ 48/48",
            "$生命骰$ 5/5 D8",
            "$属性$ 14/8/16/8/18/11",
            "$熟练$ 力量攻击/感知豁免/魅力豁免/医药/游说/洞悉/宗教",
            "$额外加值$ 隐匿:劣势/豁免:+1",
        ]
    ),
}

#: 名称 → QQ（@ 标记解析用；含骰娘自身）
_QQ_BY_NAME: Dict[str, int] = {persona.nickname: persona.qq for persona in PERSONAS}
_QQ_BY_NAME[BOT_NAME] = BOT_QQ


def parse_mentions(text: str):
    """把输入原文里的 ``@名字`` 转成真实的 at 段（返回 onebot v11 的 Message）。"""
    from nonebot.adapters.onebot.v11 import Message, MessageSegment

    names = sorted(_QQ_BY_NAME, key=len, reverse=True)
    pattern = re.compile("@(" + "|".join(re.escape(name) for name in names) + ")")

    message = Message()
    cursor = 0
    for match in pattern.finditer(text):
        if match.start() > cursor:
            message += MessageSegment.text(text[cursor : match.start()])
        message += MessageSegment.at(str(_QQ_BY_NAME[match.group(1)]))
        cursor = match.end()
    if cursor < len(text):
        message += MessageSegment.text(text[cursor:])
    return message


def display_for_qq(qq: int | str) -> str:
    """把 QQ 号映射回展示名（转录里的 @ 目标），名册外保留 ``QQ<数字>``。"""
    target = str(qq)
    if target == str(BOT_QQ):
        return BOT_NAME
    for persona in PERSONAS:
        if str(persona.qq) == target:
            return persona.nickname
    return f"QQ{target}"


def member_info(user_id: int | str, **_: object) -> Dict[str, object]:
    """``get_group_member_info`` 的离线应答：从名册返回群名片与昵称。"""
    target = str(user_id)
    for persona in PERSONAS:
        if str(persona.qq) == target:
            return {
                "user_id": persona.qq,
                "nickname": persona.qq_nickname,
                "card": persona.card_name,
            }
    return {"user_id": int(target) if target.isdigit() else target, "nickname": "", "card": ""}
