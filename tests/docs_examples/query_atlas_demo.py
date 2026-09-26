"""文档示例用的速查索引假数据（**合成内容**，非规则原文）。

背景与 ``query_demo.py`` 相同：速查子命令（``.查询法术`` 等）的文档示例必须
逐字来自真实执行，而站点页面属入库文件、不能转录《5e不全书》正文。做法是给
示例时间线装一个**演示索引**——索引条目与详情页都是内置合成数据（结构照站点
页面形态：2024 竖线式条目头、专长紫红标题块、单位小节），命令行为（候选列表、
版本排序、回复数字、正文切分与来源标注）全部真实执行。

说明：

- 索引条目**直接注入**（不经网络构建），详情页由假传输按路径返回（全离线）；
- 演示索引只覆盖示例用到的四类（法术 / 物品 / 专长 / 单位），其余类别未建，
  示例时间线不会查询它们；
- 演示页面正文一律为自写短句；**刻意不用表格**：文字模式下表格行以 `` | ``
  连接（如 ``金币 | gp``），会撞上 ``::: chat`` 容器的「昵称 | 内容」行格式。
"""

from __future__ import annotations

import urllib.parse
from typing import Dict, List

from query_fakes import FakeTransport

from nonebot_plugin_dnddicer.data import get_data_file
from nonebot_plugin_dnddicer.query.atlas import AtlasEntry, AtlasStore
from nonebot_plugin_dnddicer.query.fetch import HtmlFetcher

# ── 演示详情页（结构照站点形态；正文为自写短句）─────────────────────────

#: 法术页（2024 版，一环）：条目头形如「塔莎狂笑术｜Tasha's Hideous Laughter」
_PAGE_SPELL_2024 = """<html><body>
<H2>一环法术</H2>
<H4 id="Tasha's_Hideous_Laughter">塔莎狂笑术｜Tasha's Hideous Laughter</H4>
<P><EM>一环 惑控（吟游诗人、魔契师、法师）</EM> <BR><STRONG>施法时间：</STRONG>动作<BR><STRONG>施法距离：</STRONG>30尺<BR><STRONG>法术成分：</STRONG>V、S、M<BR><STRONG>持续时间：</STRONG>专注，至多1分钟<BR>演示说明：目标须通过一次感知豁免，否则会倒在地上大笑不止。</P>
<H4 id="Other_Spell">别的法术｜Other Spell</H4>
<P>其它演示内容。</P>
</body></html>"""

#: 法术页（2014 版）：条目头形如「塔莎狂笑术 Tasha's Hideous Laughter」
_PAGE_SPELL_2014 = """<html><body>
<H2>法术详述</H2>
<H4 id="Tasha's_Hideous_Laughter">塔莎狂笑术 Tasha's Hideous Laughter</H4>
<P><EM>一环 惑控</EM> <BR><STRONG>施法时间：</STRONG>动作<BR><STRONG>施法距离：</STRONG>30尺<BR><STRONG>法术成分：</STRONG>V、S、M<BR><STRONG>持续时间：</STRONG>专注，至多1分钟<BR>演示说明：旧版页面的条目正文（自写短句）。</P>
<H4 id="Other_Spell">别的法术 Other Spell</H4>
<P>其它演示内容。</P>
</body></html>"""

#: 神器页（2024 版）：条目头是 ``<H6 id=…>``，正文含段落与词条列表
_PAGE_ARTIFACT = """<html><body>
<H2>神器</H2>
<H6 id="Orb_of_Dragonkind">
龙珠 Orb of Dragonkind
</H6>
<P><EM>奇物，神器（需同调）</EM><BR>演示文本：这一段是自写的条目来历说明，用来展示段落形态。<BR>演示文本：第二段说明文字，句末以句号收束。</P>
<P><STRONG>随机词条</STRONG> 演示文本：下列词条为自写短句。</P>
<UL><LI><DIV>演示词条甲：自写短句说明。</DIV></LI>
<LI><DIV>演示词条乙：自写短句说明。</DIV></LI></UL>
<H6 id="Other_Artifact">别的神器 Other Artifact</H6>
<P>其它演示内容。</P>
</body></html>"""

#: 专长页（2024 版）：条目是紫红加粗标题块（无锚点），下一块标题作为切分边界。
#: 标题块内「中文名 + 换行 + 英文名」照站点形态（换行会被折叠成一个空格）
_PAGE_FEAT = """<html><body>
<h2>通用专长</h2>
<p><b><FONT color=#800000>冲锋手 
Charger</FONT> 
<BR></b><i>通用专长（先决：等级4+）<BR></i>演示文本：你获得以下增益。</p>
<UL><LI><DIV><b>演示增益一。</b>自写短句说明。</DIV></LI>
<LI><DIV><b>演示增益二。</b>自写短句说明。</DIV></LI></UL>
<p><b><FONT color=#800000>大厨 
Chef</FONT> 
<BR></b><i>通用专长（先决：等级4+）</i>厨子演示内容。</p>
</body></html>"""

#: 单位转换页：小节标题同为紫红块（带 size 属性），独占一段
_PAGE_UNIT = """<html><body>
<P>演示页：单位换算（内容为自写短句）。</P>
<P><STRONG><FONT color=#800000 size=5>长度</FONT></STRONG></P>
<P>演示文本：长度单位之间的换算。</P>
<P><STRONG><FONT color=#800000 size=5>货币</FONT></STRONG></P>
<P>演示文本：硬币之间的换算如下。</P>
<UL><LI><DIV>1 金币（GP）= 10 银币（SP）</DIV></LI>
<LI><DIV>1 银币（SP）= 10 铜币（CP）</DIV></LI></UL>
</body></html>"""

#: 站内相对路径 → 演示页 HTML（假传输按此路由）
_PAGES: Dict[str, str] = {
    "玩家手册2024/法术详述/1环.htm": _PAGE_SPELL_2024,
    "玩家手册/魔法/法术详述/1环.htm": _PAGE_SPELL_2014,
    "城主指南2024/7.宝藏/魔法物品详述/奇物/其他物品/神器.htm": _PAGE_ARTIFACT,
    "玩家手册2024/专长/通用专长.htm": _PAGE_FEAT,
    "速查/单位转换.htm": _PAGE_UNIT,
}


def _respond_page(url: str) -> str:
    """按 URL 返回演示页面 HTML（路径未配置时报错，便于定位场景笔误）。"""
    path = urllib.parse.unquote(url.split("/topics/", 1)[-1])
    if path not in _PAGES:
        raise AssertionError(f"演示索引未配置该页面：{path}")
    return _PAGES[path]


def demo_entries() -> Dict[str, List[AtlasEntry]]:
    """演示索引的条目（只含示例用到的四类；字段形态照站点速查表）。"""
    return {
        # 同名不同版本：候选按书架顺序把 2024 版排在前
        "spell": [
            AtlasEntry(
                kind="spell",
                name="塔莎狂笑术",
                name_en="Tasha's Hideous Laughter",
                category="玩家手册2024",
                page_path="玩家手册2024/法术详述/1环.htm",
                anchor="Tasha's_Hideous_Laughter",
                meta="一环 · 惑控",
            ),
            AtlasEntry(
                kind="spell",
                name="塔莎狂笑术",
                name_en="Tasha's Hideous Laughter",
                category="玩家手册",
                page_path="玩家手册/魔法/法术详述/1环.htm",
                anchor="Tasha's_Hideous_Laughter",
                meta="一环 · 惑控",
            ),
        ],
        "item": [
            AtlasEntry(
                kind="item",
                name="龙珠",
                name_en="Orb of Dragonkind",
                category="城主指南2024",
                page_path="城主指南2024/7.宝藏/魔法物品详述/奇物/其他物品/神器.htm",
                anchor="Orb_of_Dragonkind",
                meta="神器 · 奇物",
            ),
        ],
        "feat": [
            AtlasEntry(
                kind="feat",
                name="冲锋手",
                name_en="Charger",
                category="玩家手册2024",
                page_path="玩家手册2024/专长/通用专长.htm",
                meta="通用专长",
            ),
        ],
        "unit": [
            AtlasEntry(
                kind="unit",
                name="货币",
                category="速查",
                page_path="速查/单位转换.htm",
                meta="单位转换",
            ),
        ],
    }


def build_demo_store() -> AtlasStore:
    """构造演示索引（条目直接注入、详情页由假传输返回；全离线）。"""
    fetcher = HtmlFetcher(
        ["https://5echm.kagangtuya.top"],
        transport=FakeTransport([("topics/", _respond_page)]),
        min_interval=0.0,
    )
    store = AtlasStore(fetcher, cache_file=get_data_file("query_atlas_demo.json"))
    store.merge_and_save(demo_entries())
    return store
