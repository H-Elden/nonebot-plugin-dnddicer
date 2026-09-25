"""文档示例用的规则查询假数据源（**合成内容**，非规则原文）。

背景：文档站《规则查询》页的示例必须逐字来自真实执行（取证纪律），但页面属
入库文件，不能转录《5e不全书》的正文。折中办法：示例时间线装一个**合成数据源**
——查询命令的真实行为（候选列表、数字选择、翻页、图片开关、查询范围）全部
真实执行，只有「词条内容」用自写演示文本（结构照真实响应形态：2024 竖线式
条目头、章节页聚合、分类字段等）。页面里注明「示例内容为演示用合成文本」。

合成页面复用 ``tests/query_fakes.py`` 里既有的自写样例（该文件即为测试与文档
共用的演示语料，正文皆为自写短句）。
"""

from __future__ import annotations

import urllib.parse
from typing import Dict, List

from query_fakes import (
    PAGE_SPELLS_2024,
    FakeTransport,
    make_result,
    make_search_response,
)

from nonebot_plugin_dnddicer.query.source import FiveChmSource

#: 演示用关键词 → 候选页（页面标题, 分类）；章节页聚合：页面标题是章节名
_DEMO_PAGES: Dict[str, List[tuple]] = {
    # 名称检索：页面「二环」内有条目头「镜影术｜Mirror Image」
    "镜影术": [("二环", "玩家手册2024")],
    # 全文检索：12 条候选（跨两页，用于演示 + / - 翻页）
    "借机攻击": [
        ("借机攻击", "玩家手册2024"),
        ("徒手打击", "玩家手册2024"),
        ("战斗动作", "玩家手册2024"),
        ("反应", "玩家手册2024"),
        ("移动与位置", "玩家手册2024"),
        ("近战攻击", "玩家手册2024"),
        ("触及范围", "玩家手册2024"),
        ("借机攻击速查", "速查"),
        ("擒抱", "玩家手册2024"),
        ("推撞", "玩家手册2024"),
        ("撤离", "玩家手册2024"),
        ("回避", "玩家手册2024"),
    ],
    # 多关键词（或）：火焰｜闪电——两个词任一命中即进候选
    "火焰|闪电": [
        ("三环", "玩家手册2024"),
        ("二环", "玩家手册2024"),
        ("元素法术速查", "速查"),
    ],
    # 多关键词（且）：空格分隔——同一页要同时含这两个词才进候选
    "火焰 伤害": [
        ("三环", "玩家手册2024"),
        ("法术速查", "速查"),
    ],
}

#: 演示页面的正文（自写短句；2024 竖线式条目头 + 正文段落）。
#: 「二环」页复用测试同款合成章节页（含三个法术条目），选 1 即切出「镜影术」词条
_PAGE_BODY = {
    "二环": PAGE_SPELLS_2024,
}

#: 演示页面的默认正文（全文检索的候选，条目头 + 一句话）
_DEFAULT_BODY = (
    "{name}｜{english}\n"
    "这里演示的是全文检索的候选页：正文里出现了该关键词，条目头用于定位切分。\n"
    "\n"
    "本页内容为文档演示用的合成文本，不是《5e不全书》的规则原文。"
)

#: 演示页面的英文名（条目头第二段）
_ENGLISH = {
    "镜影术": "Mirror Image",
    "借机攻击": "Opportunity Attacks",
    "徒手打击": "Unarmed Strike",
    "战斗动作": "Combat Actions",
    "反应": "Reactions",
    "移动与位置": "Movement and Position",
    "近战攻击": "Melee Attacks",
    "触及范围": "Reach",
    "借机攻击速查": "Opportunity Attacks (Quick Reference)",
    "擒抱": "Grappling",
    "推撞": "Shoving",
    "撤离": "Disengage",
    "回避": "Dodge",
    "三环": "Level 3 Spells",
    "二环": "Level 2 Spells",
    "法术速查": "Spell Quick Reference",
    "元素法术速查": "Elemental Spells Quick Reference",
}


def _page_result(index: int, name: str, category: str = "玩家手册2024") -> dict:
    """构造一条演示候选（页面粒度）。"""
    body = _PAGE_BODY.get(name) or _DEFAULT_BODY.format(
        name=name, english=_ENGLISH.get(name, "Demo Page")
    )
    return make_result(index, name, body, category=category)


def _respond(url: str) -> dict:
    """按 URL 参数返回演示响应（标题查询 / 全文 / 逐目录三种形态）。"""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    keyword = query.get("keyword", [""])[0]
    title_only = query.get("titleOnly", ["false"])[0] == "true"
    category = query.get("category", [""])[0]

    pages = _DEMO_PAGES.get(keyword, [])
    results = [
        _page_result(index, name, page_category)
        for index, (name, page_category) in enumerate(pages, start=1)
    ]
    if category:
        # 逐目录检索（查询范围生效时）：只返回该目录下的候选，与真实服务同语义
        return make_search_response(
            [item for item in results if item.get("category") == category]
        )
    if title_only:
        # 标题查询：只返回标题命中者（演示「标题包含」档；其余靠全文兜底）
        return make_search_response(
            [item for item in results if keyword in str(item.get("title", ""))]
        )
    return make_search_response(results)


def build_demo_source() -> FiveChmSource:
    """构造演示用的数据源（走真实数据源逻辑，只替换网络层）。"""
    return FiveChmSource(
        ["https://5echmsearch.kagangtuya.top"],
        transport=FakeTransport([("api/search", _respond)]),
    )
