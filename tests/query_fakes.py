"""规则查询测试夹具：合成页面文本与假传输（全离线，不触碰真实网络）。

**内容说明**：本文件里的页面文本是**合成样例**——结构照真实查询服务的响应形态
（2024 版条目头 ``名称｜English``、2014 版 ``名称 English``、章节页/叙述页等），
正文文字为自写短句，**不复制《5e不全书》的译文内容**（合规：不随插件分发规则原文）。
真实响应的字段与格式已由调研探针取证（详见文档目录下的调研记录）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# ── 合成页面文本（结构照真实格式，正文为自写短句）─────────────────────────

#: 2024 版聚合页（法术按环阶成页）：条目头形如 ``镜影术｜Mirror Image``，
#: 且条目头处于块首（前一行空行、或上一段以句末标点收束）——照真实页面排版
PAGE_SPELLS_2024 = """二环

镜影术｜Mirror Image

二环 幻术
施法时间：1 动作
距离：自身
成分：V、S
持续时间：1 分钟
三个镜像出现在你周围，用于迷惑攻击者。

灼热射线｜Scorching Ray

二环 塑能
施法时间：1 动作
距离：120 尺
成分：V、S
持续时间：立即
你射出三道火焰射线，分别攻击射程内的目标。

火球术｜Fireball

三环 塑能
施法时间：1 动作
距离：150 尺
成分：V、S、M
持续时间：立即
一道亮光从你的指尖射出，在指定点炸成烈焰。
"""

#: 硬换行造成的「假条目头」页面：句中片段恰好形如 ``借机攻击Opportunity Attack``
PAGE_WRAPPED_FALSE_HEAD = """借机攻击是当你“可见的生物”离开你触及范围时发生的事。

当发动
借机攻击Opportunity Attack
时，我可以用它擒抱或推撞敌人吗？

可以的。你可以选择发动徒手打击。
"""

#: 2014 版词条（条目头形如 ``借机攻击 Opportunity Attacks``）
PAGE_TERM_2014 = """借机攻击 Opportunity Attacks
当敌人离开你的触及范围时，你可以用反应发动一次近战攻击。

徒手打击 Unarmed Strike
你可以用拳头进行一次近战攻击，伤害基于力量。
"""

#: 无条目头的叙述页（走段落回退）
PAGE_NARRATIVE = """优势与劣势
有时，特殊能力或环境会给你带来优势或劣势，表现为多掷一颗 d20。

优势
多掷一颗 d20 并取较高者。

劣势
多掷一颗 d20 并取较低者。
"""

#: 索引/速查表式页面（只有一行条目、无正文，排序应低于真词条页）
PAGE_INDEX_LINE = "火球术｜Fireball"


def make_result(
    index: int,
    title: str,
    content: str,
    *,
    category: str = "玩家手册2024",
    rank: int = 10,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """构造一条 ``/api/search`` 结果项（字段与服务端响应一致）。"""
    return {
        "index": index,
        "title": title,
        "rawTitle": title,
        "path": path or f"topics/{category}/法术/二环.htm",
        "sourcePath": f"{category}/法术/二环.htm",
        "rank": rank,
        "preview": content[:60],
        "content": content,
        "category": category,
    }


def make_search_response(results: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """构造一次 ``/api/search`` 响应。"""
    return {
        "results": list(results),
        "total": len(results),
        "page": 1,
        "totalPages": 1,
        "pageSize": 20,
    }


def make_candidate(
    index: int,
    title: str = "",
    content: str = "",
    *,
    category: str = "玩家手册2024",
    rank: int = 10,
    base_url: str = "https://5echmsearch.kagangtuya.top",
    score: int = 0,
) -> "Candidate":
    """构造一个候选对象（交互状态测试用）。"""
    from nonebot_plugin_dnddicer.query.models import Candidate

    return Candidate(
        index=index,
        title=title or f"页面 #{index}",
        category=category,
        path=f"topics/{category}/法术/二环.htm",
        rank=rank,
        content=content,
        base_url=base_url,
        score=score,
    )


class FakeTransport:
    """假传输：按 URL 子串匹配路由，记录调用序列（供断言外呼次数/顺序）。

    路由值为 ``dict``（正常响应）、``Exception`` 实例（抛出）或
    ``callable(url) -> dict``（按 URL 动态返回）。
    """

    def __init__(self, routes: Sequence[Tuple[str, Any]]) -> None:
        self.routes: List[Tuple[str, Any]] = list(routes)
        self.calls: List[str] = []

    async def __call__(self, url: str, timeout: float, headers: Dict[str, str]) -> dict:
        self.calls.append(url)
        for key, value in self.routes:
            if key in url:
                if isinstance(value, Exception):
                    raise value
                if callable(value):
                    return value(url)
                return value
        raise AssertionError(f"FakeTransport 未配置该请求：{url}")

    def calls_for(self, key: str) -> List[str]:
        """返回命中某路由键的调用序列。"""
        return [url for url in self.calls if key in url]
