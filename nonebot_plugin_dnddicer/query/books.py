"""查询范围的书目表：可设置项（缩写 → 站内目录）与整目录键。

背景（2026-09-25 实测《5E不全书》站点与检索服务）：查询的「范围」本质是
**站内一级目录**——检索接口 ``/api/search`` 的 ``category`` 参数只接受单个
目录名，且站点目录与「书架」（站点首页的藏书展示）并不是一一对应：

- 多数官方书是 1:1（书即目录）：玩家手册2024 / 珊娜萨的万事指南 / …；
- 一部分作品共用一个目录（**整目录**）：
  ``第三方``（合作内容，35 本）、``模组``（冒险，38 个）、
  ``被遗忘的国度``（费伦英雄等 5 本）、``其他``（英雄盛宴等）；
- 少数书的内容寄居在别的目录下（魔法船在 ``星界冒险者指南``、耀光城之旅在 ``模组``）。

因此**可设置的最小单位 = 目录**：1:1 的书直接用书目缩写设置；整目录用
``3PP`` / ``FR`` / ``ADV`` / ``MISC`` 四个键设置（书目缩写只在「提示」里出现，
帮助用户把书名对应到目录，避免出现「以为只开了一本、实际开了整个目录」）。

书目与缩写取自站点「书架」的公开元数据（条目名 | 缩写 | 出版分组），
2026-09-25 依站点 v20260913 版与线上逐本核对；站点目录名与书名不一致处按**实际目录名**入库
（如书架「玩家手册2014」↔目录「玩家手册」）。站点新增书籍时需同步本表
（插件侧静态数据，不做在线拉取：检索服务的响应里没有书目信息）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

#: 展示分组（按书架顺序；最后一组为本插件新增的「整目录」说明组——
#: 书架「合作内容 / 其他出版物」分组里的作品都归整目录，故不单列）
SECTION_TITLES: Tuple[Tuple[str, str], ...] = (
    ("core", "新版核心资源（2024）"),
    ("legacy", "旧版资源"),
    ("official", "规则扩展"),
    ("setting", "战役设定"),
    ("category", "整目录（多个作品共用一个站内目录）"),
)


@dataclass(frozen=True)
class ScopeEntry:
    """一个可设置的条目（1:1 的书，或一个整目录）。

    Attributes:
        key: 设置用的键（书目缩写或整目录键，大小写不敏感）。
        category: 站内一级目录名（检索接口 ``category`` 参数的值）。
        title: 中文展示名。
        section: 展示分组（见 ``SECTION_TITLES``）。
        note: 补充说明（整目录用它列明包含哪些作品）；无则空串。
    """

    key: str
    category: str
    title: str
    section: str
    note: str = ""


#: 可设置条目：1:1 对应站内目录的书 + 四个整目录键
SCOPE_ENTRIES: Tuple[ScopeEntry, ...] = (
    # ── 新版核心资源（2024）────────────────────────────────────────────
    ScopeEntry("PHB24", "玩家手册2024", "玩家手册2024", "core"),
    ScopeEntry("DMG24", "城主指南2024", "城主指南2024", "core"),
    ScopeEntry("MM25", "怪物图鉴2025", "怪物图鉴2025", "core"),
    # ── 旧版资源（2014 与已停更内容）────────────────────────────────────
    ScopeEntry("PHB14", "玩家手册", "玩家手册2014", "legacy"),
    ScopeEntry("DMG14", "城主指南", "城主指南2014", "legacy"),
    ScopeEntry("MM14", "怪物图鉴", "怪物图鉴2014", "legacy"),
    ScopeEntry("VGtM", "瓦罗怪物指南", "瓦罗的怪物指南", "legacy"),
    ScopeEntry("MToF", "魔邓肯的众敌卷册", "魔邓肯的众敌卷册", "legacy"),
    # ── 规则扩展 ───────────────────────────────────────────────────────
    ScopeEntry("XGE", "珊娜萨的万事指南", "珊娜萨的万事指南", "official"),
    ScopeEntry("TCE", "塔莎的万事坩埚", "塔莎的万事坩埚", "official"),
    ScopeEntry("FTD", "费资本的巨龙宝库", "费资本的巨龙宝库", "official"),
    ScopeEntry("MPMM", "多元宇宙的怪物", "魔邓肯巨献：多元宇宙的怪物", "official"),
    ScopeEntry("BPGG", "巨人之荣耀", "毕格比巨献：巨人之荣耀", "official"),
    ScopeEntry("BMT", "万象无常书", "万象无常书", "official"),
    ScopeEntry("AU", "启封奥秘", "启封奥秘", "official"),
    # ── 战役设定 ───────────────────────────────────────────────────────
    ScopeEntry("SCAG", "剑湾冒险者指南", "剑湾冒险者指南", "setting"),
    ScopeEntry("WGE", "艾伯伦寻路者指南", "艾伯伦寻路者指南", "setting"),
    ScopeEntry("GGR", "拉尼卡公会长指南", "拉尼卡公会长指南", "setting"),
    ScopeEntry("AI", "艾奎兹玄有限责任公司", "艾奎兹玄有限责任公司", "setting"),
    ScopeEntry("ERLW", "艾伯伦：从终末战争中崛起", "艾伯伦：从终末战争中崛起", "setting"),
    ScopeEntry("EGW", "荒洲探险家指南", "荒洲探险家指南", "setting"),
    ScopeEntry("MOoT", "塞洛斯之神话奥德赛", "塞洛斯之神话奥德赛", "setting"),
    ScopeEntry("VRGR", "范·里希腾的鸦阁魔域指南", "范·里希腾的鸦阁魔域指南", "setting"),
    ScopeEntry("SCC", "斯翠海文：混沌研习", "斯翠海文：混沌研习", "setting"),
    ScopeEntry("AAG", "星界冒险者指南", "星界冒险者指南", "setting"),
    ScopeEntry("BAM", "布布的星界怪兽展", "布布的星界怪兽展", "setting"),
    ScopeEntry("DSotDQ", "龙枪：龙后之影", "龙枪：龙后之影", "setting"),
    ScopeEntry("SO", "印记城与外域", "印记城与外域", "setting"),
    ScopeEntry("MPP", "莫提的位面游记", "莫提的位面游记", "setting"),
    ScopeEntry("EFA", "艾伯伦：奇械锻炉", "艾伯伦：奇械锻炉", "setting"),
    ScopeEntry("RHD", "鸦阁魔域：魔障深藏", "鸦阁魔域：魔障深藏", "setting"),
    # ── 整目录（多作品共用一个站内目录）────────────────────────────────
    ScopeEntry(
        "3PP",
        "第三方",
        "第三方（合作内容）",
        "category",
        note="含德拉肯海姆、鬼魅幽谷、塔尔多雷等 35 本合作出版物",
    ),
    ScopeEntry(
        "FR",
        "被遗忘的国度",
        "被遗忘的国度",
        "category",
        note="含费伦英雄、费伦冒险、洛温初光、阿斯代伦、耐瑟瑞尔 5 本",
    ),
    ScopeEntry(
        "ADV",
        "模组",
        "冒险模组",
        "category",
        note="含耀光城、施特拉德的诅咒、湮灭之墓等 38 个冒险",
    ),
    ScopeEntry(
        "MISC",
        "其他",
        "其他出版物",
        "category",
        note="含英雄盛宴、穆克、新 UA、异界传送、beyond drops",
    ),
)

#: 键（原样）→ 条目
_ENTRY_BY_KEY: Dict[str, ScopeEntry] = {entry.key: entry for entry in SCOPE_ENTRIES}

#: 键（小写）→ 条目（设置时大小写不敏感）
_ENTRY_BY_LOWER_KEY: Dict[str, ScopeEntry] = {
    entry.key.lower(): entry for entry in SCOPE_ENTRIES
}

#: 目录名 → 条目（反查；每个目录恰有一个条目）
_ENTRY_BY_CATEGORY: Dict[str, ScopeEntry] = {
    entry.category: entry for entry in SCOPE_ENTRIES
}

#: 不能单独设置的作品（缩写 → 应使用的整目录/宿主键）。
#: 用于设置报错时给出精确提示：合作内容整组归 3PP、其他出版物整组归 MISC，
#: 被遗忘的国度五本归 FR；耀光城之旅的内容在模组目录、魔法船在星界冒险者指南、
#: 异度风景在印记城与外域目录下。
UMBRELLA_HINTS: Dict[str, str] = {
    # 合作内容（书架「合作内容」分组，内容在 第三方 目录下）
    **{
        key: "3PP"
        for key in (
            "Dk", "SSS", "MoD", "VSS", "VSS:PP", "VSS:PP2", "GUN", "CM", "CBT",
            "AV", "GH", "GHPG", "GHCG", "OSW:HAP", "Eberron", "EE", "FoEQ",
            "PUG", "FPW", "TGS1", "DDDD", "Northlands", "NW", "NS", "SGEH:PP",
            "VTMBB", "FGFD", "TCSR", "DoD", "HW", "TGS2", "BH", "DT", "ILL",
            "AHA",
        )
    },
    # 被遗忘的国度（2025 设定集，同目录）
    "FRHoF": "FR",
    "FRAiF": "FR",
    "LFL": "FR",
    "FoN": "FR",
    "ABH": "FR",
    # 其他出版物
    "AwM": "MISC",
    "MTCE": "MISC",
    "HF": "MISC",
    # 内容寄居在别的目录下
    "JRC": "ADV",
    "SAiS": "AAG",
    "PAitM": "SO",
}

#: 设置「恢复全部」的保留字（大小写不敏感）
ALL_WORDS: Tuple[str, ...] = ("全部", "all")


def find_entry(key: str) -> Optional[ScopeEntry]:
    """按键查找可设置条目（大小写不敏感）；不是可设置项时返回 None。"""
    return _ENTRY_BY_LOWER_KEY.get(key.strip().lower())


def entry_by_category(category: str) -> Optional[ScopeEntry]:
    """按站内目录名反查条目（用于展示已设置的范围）。"""
    return _ENTRY_BY_CATEGORY.get(category)


def umbrella_hint(key: str) -> Optional[ScopeEntry]:
    """键不是可设置项、但属于某个整目录/宿主目录时，返回应使用的条目。

    例：``Dk``（德拉肯海姆）→ ``3PP`` 条目；``JRC`` → ``ADV`` 条目。
    """
    target = UMBRELLA_HINTS.get(key.strip(), "")
    if not target:
        return None
    if target in _ENTRY_BY_KEY:
        return _ENTRY_BY_KEY[target]
    # 宿主是某本可设置的书（如 SAiS → AAG、PAitM → SO）
    return _ENTRY_BY_LOWER_KEY.get(target.lower())


def is_all_word(text: str) -> bool:
    """判断文本是否为「恢复全部」的保留字（全部 / all）。"""
    return text.strip().lower() in {word.lower() for word in ALL_WORDS}


def sections_for_display() -> List[Tuple[str, List[ScopeEntry]]]:
    """按展示分组返回可设置条目（空分组不返回；分组顺序见 ``SECTION_TITLES``）。"""
    groups: List[Tuple[str, List[ScopeEntry]]] = []
    for section, title in SECTION_TITLES:
        entries = [entry for entry in SCOPE_ENTRIES if entry.section == section]
        if entries:
            groups.append((title, entries))
    return groups


def category_display(category: str) -> str:
    """目录名的展示形式：可设置项显示「键 中文名」，其他目录原样返回。"""
    entry = entry_by_category(category)
    if entry is None:
        return category
    return f"{entry.key} {entry.title}"


__all__ = [
    "ALL_WORDS",
    "SCOPE_ENTRIES",
    "SECTION_TITLES",
    "ScopeEntry",
    "UMBRELLA_HINTS",
    "category_display",
    "entry_by_category",
    "find_entry",
    "is_all_word",
    "sections_for_display",
    "umbrella_hint",
]
