"""``.help`` 的版式表：7 个分组的清单行 + 只进帮助的条目（2026-09-28 重做）。

分工：

- **本模块**放结构性与整块文案：分组清单行、只进帮助的条目（``.[属性]检定`` /
  ``.武器名攻击`` 这类按消息模式触发的写法）；
- ``commands/text.py`` 放总览 / 目录 / 链接 / 关于 / 骰主 / 联系 / 未命中等单块文案；
- 各命令自己的详情文案仍在各自模块的 ``_HELP``（``.help <命令>`` 直接返回）。

版式（用户手改稿定稿）：组清单一律「命令[参数]　#短说明」单行式，每行 ≤ 30 字；
需要先记录角色卡的分组在行首加一行 ``⚠️以下命令需要先记录角色卡：``；
组清单整体 ≤ 10 行（含标题与末尾的文档站链接行，链接行由渲染层追加）。

每条分组与只进帮助的条目还带一个 ``doc``（文档站页面的站内相对路径，如
``guide/hp``）：回复末尾的链接行据此给出**对应页深链**，留空则回落站点首页
（见 ``commands/help.py``）。已注册命令的 ``doc`` 登记在各命令模块的注册处。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

#: 帮助的分组：关键词（``.help <关键词>`` 用它）→ 该组清单的展示行 → 对应文档页。
#: 文档页为站内相对路径（如 ``guide/hp``），组清单末尾的链接行据此生成深链。
HELP_GROUPS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    (
        "掷骰",
        (
            "【掷骰相关命令】",
            ".r[标志][表达式] [原因]　#掷骰表达式",
            ".dnd[次数] [原因]　#不绑定属性生成",
            ".dndx[次数] [原因]　#绑定属性生成",
        ),
        "guide/roll-basics",
    ),
    (
        "角色",
        (
            "【角色卡相关命令】",
            ".角色卡　　　#查看自己角色卡",
            ".角色卡模板　#查看角色卡模板",
            ".角色卡记录　#记录角色卡",
            ".角色卡清除　#清除当前角色卡",
            "⚠️以下命令需要先记录角色卡：",
            ".状态[@玩家]　#查看 HP 与生命骰摘要",
            ".[属性]检定[优势|劣势]　#进行属性检定",
            ".[技能]检定[优势|劣势]　#进行技能检定",
            ".[属性]豁免[优势|劣势]　#进行豁免检定",
        ),
        "guide/character-card",
    ),
    (
        "武器",
        (
            "【武器相关命令】",
            "⚠️以下命令需要先记录角色卡：",
            ".设置武器　#无参数直接列出当前武器",
            ".设置武器 名称+命中,伤害表达式　#记录武器到角色卡",
            ".删除武器 名称　#删除卡上武器（支持模糊匹配）",
            ".武器名攻击　#用卡上武器掷攻击检定",
            ".武器名命中　#用卡上武器掷攻击检定",
            ".武器名伤害[后缀]　#掷武器伤害",
            "后缀支持：副手/重击/偷袭等",
        ),
        "guide/weapons",
    ),
    (
        "生命",
        (
            "【生命值相关命令】",
            ".hp　#查看当前生命值",
            ".hp 12/12(5)　#记录生命值和临时生命",
            ".hp [目标] [表达式]　#给自己或他人加减生命",
            ".长休 [@玩家]　#长休结算",
            ".npc 持久/临时 名称　#NPC血量跨战斗保持开关",
        ),
        "guide/hp",
    ),
    (
        "先攻",
        (
            "【先攻与战斗命令】",
            ".ri [优劣势][±加值] [名称]　#掷先攻并入表",
            ".先攻列表　#查看先攻列表（HP 随条目展示）",
            ".先攻清除　#清空先攻列表",
            ".先攻删除/提前/交换 名称　#删除 / 提前 / 互换条目",
            ".先攻检定 [优劣势][±加值]　#掷先攻并自动入表",
            ".br / .战斗轮　#新建战斗轮（清空先攻表）",
            ".回合 / .轮次　#查看 / 修改回合与轮次",
            ".ed / .结束　#结束当前回合并推进",
        ),
        "guide/initiative",
    ),
    (
        "查询",
        (
            "【规则查询命令】",
            ".查询法术 <名称>　#法术速查（另有 7 类）",
            ".查询 <关键词>　#按名称检索（.q）",
            ".搜索 <关键词>　#全文检索（.s / .检索）",
            ".查询图片 [on|off]　#本处图片/文字开关",
            ".查询范围 [缩写|全部]　#收窄可查书目",
            ".规则书　#书目缩写与中文名对照",
        ),
        "guide/query",
    ),
    (
        "管理",
        (
            "【群管理专用命令】",
            ".dset [表达式]　#设置/查看本群默认骰面",
            ".bot [on|off]　#本群服务开关，需@",
        ),
        "guide/faq",
    ),
)

#: 组名的静默别名（不写进目录，输入这些同样回该组清单）
GROUP_SYNONYMS: Tuple[Tuple[str, str], ...] = (
    ("掷骰与属性", "掷骰"),
    ("骰子", "掷骰"),
    ("角色卡", "角色"),
    ("角色与检定", "角色"),
    ("武器与攻击", "武器"),
    ("装备", "武器"),
    ("生命值", "生命"),
    ("血量", "生命"),
    ("先攻与战斗", "先攻"),
    ("战斗", "先攻"),
    ("规则查询", "查询"),
    ("规则", "查询"),
    ("群管理与帮助", "管理"),
    ("群管理", "管理"),
    ("群管", "管理"),
)

#: 目录入口的关键词（``.help 命令`` 及其静默别名）
CATALOG_KEYWORDS: Tuple[str, ...] = ("命令", "列表", "指令", "菜单", "list")

#: 其余专用入口的关键词
LINK_KEYWORD = "链接"
ABOUT_KEYWORD = "关于"
MASTER_KEYWORD = "骰主"
CONTACT_KEYWORD = "联系"


@dataclass(frozen=True)
class HelpOnlyEntry:
    """只进帮助、不参与命令匹配的条目。

    ``tokens`` 用于包含式匹配（``.help 力量检定`` → 检定条目）：先按名称/别名
    精确命中，未命中时取**最长**被包含的 token（``先攻检定`` 优先于 ``检定``）。
    ``doc`` 为对应文档页的站内相对路径（空串 = 站点首页）。
    """

    name: str
    text: str
    tokens: Tuple[str, ...] = ()
    doc: str = ""


#: 只进帮助的条目：检定点 / 豁免 / 先攻检定 / 武器攻击 / 武器伤害（按消息模式触发）。
#: ``.master`` 曾暂列于此，2026-09-30 起已实现为正式命令（见 commands/master.py）。
HELP_ONLY_ENTRIES: Tuple[HelpOnlyEntry, ...] = (
    HelpOnlyEntry(
        "检定",
        ".[N#][属性/技能]检定[优势|劣势][±加值] [@玩家]\n"
        "  读角色卡代入属性与熟练，只掷 D20+加值\n"
        "  不做 DC 判定；需先记录角色卡\n"
        "  属性 6 项、技能 18 项（如 隐匿、察觉、运动）\n"
        "  示例：.力量检定 ｜ .敏捷检定优势+d4 ｜ .隐匿检定",
        tokens=("检定",),
        doc="guide/checks",
    ),
    HelpOnlyEntry(
        "豁免",
        ".[N#][属性]豁免[优势|劣势][±加值] [@玩家]\n"
        "  读角色卡代入属性与熟练，只掷 D20+加值\n"
        "  不做 DC 判定；需先记录角色卡\n"
        "  示例：.力量豁免 ｜ .体质豁免+d4 ｜ .3#敏捷豁免优势",
        tokens=("豁免",),
        doc="guide/checks",
    ),
    HelpOnlyEntry(
        "先攻检定",
        ".先攻检定[优势|劣势][±加值] [@玩家]\n"
        "  掷先攻并自动写入本群先攻列表\n"
        "  @玩家 以该玩家角色卡名入表并绑定\n"
        "  示例：.先攻检定 ｜ .先攻检定优势 ｜ .先攻检定 @玩家",
        tokens=("先攻检定",),
        doc="guide/initiative",
    ),
    HelpOnlyEntry(
        "武器攻击",
        ".武器名攻击 / .武器名命中\n"
        "  用卡上武器的命中加值掷 D20；名称支持模糊匹配\n"
        "  可加 优势/劣势、N# 连掷、±加值、@玩家\n"
        "  天然 20 提示重击，天然 1 提示必失\n"
        "  示例：.刺剑攻击 ｜ .2#刺剑攻击+2 ｜ .匕首命中优势",
        tokens=("武器名攻击", "武器名命中", "武器攻击", "武器命中", "攻击", "命中"),
        doc="guide/weapons",
    ),
    HelpOnlyEntry(
        "武器伤害",
        ".武器名伤害 [后缀][±加值] [@玩家]\n"
        "  后缀：副手 / 重击 / 偷袭，可组合\n"
        "  副手不加加值、重击伤害骰翻倍、偷袭按等级加骰\n"
        "  多件武器一次结算：.刺剑伤害、匕首副手伤害\n"
        "  示例：.刺剑重击伤害+1d6 ｜ .火球术伤害 @玩家",
        tokens=("武器名伤害", "武器伤害", "伤害"),
        doc="guide/weapons",
    ),
)


def find_group(keyword: str) -> Optional[Tuple[str, Tuple[str, ...], str]]:
    """按分组关键词或静默别名查分组（大小写不敏感；未命中返回 None）。

    返回 ``(组名, 清单行, 文档页)``。
    """
    key = (keyword or "").strip()
    if not key:
        return None
    lowered = key.lower()
    for name, lines, doc in HELP_GROUPS:
        if name.lower() == lowered:
            return name, lines, doc
    for alias, target in GROUP_SYNONYMS:
        if alias.lower() == lowered:
            for name, lines, doc in HELP_GROUPS:
                if name == target:
                    return name, lines, doc
    return None


def is_catalog_keyword(keyword: str) -> bool:
    """是否为 ``.help 命令`` 入口的关键词（含静默别名）。"""
    return (keyword or "").strip().lower() in {k.lower() for k in CATALOG_KEYWORDS}


def find_help_only(keyword: str) -> Optional[HelpOnlyEntry]:
    """把写法匹配到只进帮助的条目（先精确、再取最长被包含 token）。"""
    key = (keyword or "").strip()
    if not key:
        return None
    lowered = key.lower()
    for entry in HELP_ONLY_ENTRIES:
        if entry.name.lower() == lowered or any(
            token.lower() == lowered for token in entry.tokens
        ):
            return entry
    best: Optional[HelpOnlyEntry] = None
    best_len = 0
    for entry in HELP_ONLY_ENTRIES:
        for token in (entry.name, *entry.tokens):
            if token and token.lower() in lowered and len(token) > best_len:
                best, best_len = entry, len(token)
    return best
