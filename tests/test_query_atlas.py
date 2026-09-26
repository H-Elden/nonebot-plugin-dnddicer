"""速查索引（query/atlas.py）的单元测试（全离线：自写合成 HTML 夹具）。

覆盖：速查表解析（法术/怪物/物品）、名称中英拆分、术语索引、专长页扫描
（章节性标题过滤）、目录页筛出职业/起源/专长页、单位小节、索引查询排序与
范围过滤、缓存往返与「条目数异常保留旧数据」自检。

夹具说明：HTML 结构照站点形态（行属性 ``spell=/monster=/item=``、2024 竖线式
条目头、紫红加粗标题等），内容为自写样例，不复制站点规则文本。
"""

from __future__ import annotations

import pytest

from nonebot_plugin_dnddicer.query import atlas

# ── 合成夹具 ───────────────────────────────────────────────────────────

_SPELL_TABLE = """<TABLE>
<TR tags="惑控 一环 PHB24" spell="塔莎狂笑术Tasha's Hideous Laughter">
<TD><a href="../玩家手册2024/法术详述/1环.htm#Tasha's_Hideous_Laughter">塔莎狂笑术Tasha's Hideous Laughter</a></TD>
<TD>一环</TD><TD>惑控</TD><TD>诗 法 锁</TD><TD>动作</TD>
<TD>V</TD><TD>S</TD><TD>M</TD><TD>×</TD><TD>√</TD><TD>PHB24</TD>
</TR>
<TR tags="塑能 三环 第三方" spell="示例火球术Sample Fireball">
<TD><a href="../第三方/某模组/法术.htm#Sample_Fireball">示例火球术Sample Fireball</a></TD>
<TD>三环</TD><TD>塑能</TD><TD>法</TD><TD>动作</TD>
<TD>V</TD><TD>S</TD><TD>M</TD><TD>×</TD><TD>×</TD><TD>3PP</TD>
</TR>
</TABLE>"""

_MONSTER_TABLE = """<TR tags="大型 巨人 无 2 MM25" monster="食人魔Ogre">
<TD><a href="../怪物图鉴2025/巨人/食人魔/食人魔.htm#Ogre">食人魔Ogre</a></TD>
<TD>大型</TD><TD>巨人</TD><TD>无</TD><TD>2</TD><TD>MM25</TD>
</TR>"""

_ITEM_TABLE = """<TR tags="神器 奇物 是 DMG24" item="样例法球Sample Orb">
<TD><a href="../城主指南2024/7.宝藏/神器.htm#Sample_Orb">样例法球Sample Orb</a></TD>
<TD>神器</TD><TD>奇物</TD><TD></TD><TD>是</TD><TD></TD><TD>DMG24</TD>
</TR>"""

_TERM_PAGE = """<table>
<TR><TD><A href="./状态.htm#Prone">倒地</A></TD><TD><A href="./状态.htm#Stunned">震慑</A></TD></TR>
<TR><TD><A href="./动作.htm#Attack">攻击</A></TD></TR>
</table>"""

_FEAT_PAGE = """<p><b><FONT color=#800000>专长描述 Feat Descriptions</FONT></b></p>
<p><b><FONT color=#800000>冲锋手 <BR>Charger</FONT></b></p>
<p>正文内容。</p>
<p><b><FONT color=#800000>大厨 <BR>Chef</FONT></b></p>
"""

_TOC = """<div class="nav-node">
<a href="topics/玩家手册2024/角色职业/野蛮人/野蛮人.htm" target="content"><img src="1.gif" alt=""><span id="l5">野蛮人</span></a>
<a href="topics/玩家手册2024/角色职业/野蛮人/狂战士道途.htm"><span>狂战士道途</span></a>
<a href="topics/玩家手册2024/角色起源/背景/士兵.htm"><span>士兵</span></a>
<a href="topics/玩家手册2024/角色起源/种族/人类.htm"><span>人类</span></a>
<a href="topics/玩家手册2024/角色起源/背景详述.htm"><span>背景详述</span></a>
<a href="topics/玩家手册2024/专长/通用专长.htm"><span>通用专长</span></a>
</div>"""


# ── 解析函数 ───────────────────────────────────────────────────────────


def test_parse_quickref_spell() -> None:
    """速查表（法术）：名称中英拆分、元数据、类别（含合作表的第三方目录）。"""
    entries = atlas.parse_quickref(_SPELL_TABLE, kind=atlas.KIND_SPELL)
    assert [entry.name for entry in entries] == ["塔莎狂笑术", "示例火球术"]
    first = entries[0]
    assert first.name_en == "Tasha's Hideous Laughter"
    assert first.category == "玩家手册2024"
    assert first.page_path == "玩家手册2024/法术详述/1环.htm"
    assert first.anchor == "Tasha's_Hideous_Laughter"
    assert first.meta == "一环 · 惑控"
    assert entries[1].category == "第三方"


def test_parse_quickref_monster_and_item() -> None:
    """速查表（怪物/物品）：元数据取对应列。"""
    monster = atlas.parse_quickref(_MONSTER_TABLE, kind=atlas.KIND_MONSTER)[0]
    assert monster.name == "食人魔"
    assert monster.name_en == "Ogre"
    assert monster.meta == "大型 · 巨人 · CR2"
    assert monster.anchor == "Ogre"

    item = atlas.parse_quickref(_ITEM_TABLE, kind=atlas.KIND_ITEM)[0]
    assert item.name == "样例法球"
    assert item.meta == "神器 · 奇物"


def test_split_name_zh_en() -> None:
    """名称拆分：连写、带空格、带星号、纯中文各形态。"""
    assert atlas.split_name_zh_en("塔莎狂笑术Tasha's Hideous Laughter") == (
        "塔莎狂笑术",
        "Tasha's Hideous Laughter",
    )
    assert atlas.split_name_zh_en("龙珠 Orb of Dragonkind") == (
        "龙珠",
        "Orb of Dragonkind",
    )
    assert atlas.split_name_zh_en("元素掌控* Elemental Adept*") == (
        "元素掌控",
        "Elemental Adept",
    )
    assert atlas.split_name_zh_en("纯中文名") == ("纯中文名", "")


def test_parse_terms() -> None:
    """术语页：相对链接解析为「页面 + 锚点」。"""
    entries = atlas.parse_terms(
        _TERM_PAGE, page_path="玩家手册2024/术语汇编/术语速查.htm"
    )
    assert [(e.name, e.page_path, e.anchor) for e in entries] == [
        ("倒地", "玩家手册2024/术语汇编/状态.htm", "Prone"),
        ("震慑", "玩家手册2024/术语汇编/状态.htm", "Stunned"),
        ("攻击", "玩家手册2024/术语汇编/动作.htm", "Attack"),
    ]


def test_parse_feat_page_filters_section_titles() -> None:
    """专长页：紫红块取条目，「专长描述」这类章节标题被过滤。"""
    entries = atlas.parse_feat_page(
        _FEAT_PAGE, page_path="玩家手册2024/专长/通用专长.htm"
    )
    assert [entry.name for entry in entries] == ["冲锋手", "大厨"]
    assert entries[0].name_en == "Charger"
    assert entries[0].page_path == "玩家手册2024/专长/通用专长.htm"


def test_toc_entries_and_feat_pages() -> None:
    """目录页：筛出职业/子职与起源（背景/种族），并给出专长页清单。"""
    pages = atlas.parse_toc_pages(_TOC)
    entries = atlas.entries_from_toc(pages)
    classes = [entry for entry in entries if entry.kind == atlas.KIND_CLASS]
    origins = [entry for entry in entries if entry.kind == atlas.KIND_ORIGIN]
    assert [(e.name, e.meta) for e in classes] == [("野蛮人", "职业"), ("狂战士道途", "子职")]
    assert [(e.name, e.meta) for e in origins] == [("士兵", "背景"), ("人类", "种族")]
    # 章节导览页（角色起源/背景详述）不进索引
    assert all(e.name != "背景详述" for e in entries)
    assert atlas.feat_page_paths(pages) == ["玩家手册2024/专长/通用专长.htm"]


def test_parse_unit_sections() -> None:
    """单位页：紫红小节标题成为「单位」条目。"""
    html = (
        '<STRONG><FONT color=#800000 size=5>货币</FONT></STRONG>'
        '<STRONG><FONT color=#800000 size=5>长度单位</FONT></STRONG>'
    )
    entries = atlas.parse_unit_sections(html, page_path="速查/单位转换.htm")
    assert [(e.name, e.kind, e.page_path) for e in entries] == [
        ("货币", atlas.KIND_UNIT, "速查/单位转换.htm"),
        ("长度单位", atlas.KIND_UNIT, "速查/单位转换.htm"),
    ]


# ── 索引存储（构建 / 查询 / 缓存 / 自检）──────────────────────────────


class _FakeFetcher:
    """假抓取器：按路径返回预置 HTML（未配置的路径即报错）。"""

    def __init__(self, pages: dict) -> None:
        self.pages = pages
        self.calls: list = []

    async def get_page(self, path: str) -> str:
        self.calls.append(path)
        if path not in self.pages:
            raise AssertionError(f"未配置页面：{path}")
        return self.pages[path]


def _make_store(tmp_path, pages: dict) -> atlas.AtlasStore:
    return atlas.AtlasStore(
        _FakeFetcher(pages), cache_file=tmp_path / "query_atlas.json"
    )


def _spell_entry(name: str, category: str = "玩家手册2024") -> atlas.AtlasEntry:
    return atlas.AtlasEntry(
        kind=atlas.KIND_SPELL,
        name=name,
        category=category,
        page_path=f"{category}/法术详述/1环.htm",
        anchor="Anchor",
        name_en="Sample",
        meta="一环 · 惑控",
    )


@pytest.mark.asyncio
async def test_store_build_and_lookup(tmp_path) -> None:
    """构建（合并落盘）后可按精确/前缀/子串与英文名查询，并支持范围过滤。"""
    official, coop = atlas._QUICKREF_PAGES[atlas.KIND_SPELL]
    store = _make_store(tmp_path, {official: _SPELL_TABLE, coop: "<TABLE></TABLE>"})
    built = await store.build([atlas.KIND_SPELL])
    outcomes = store.merge_and_save(built)
    assert outcomes == {atlas.KIND_SPELL: "new"}
    assert store.ready

    assert [e.name for e in store.lookup(atlas.KIND_SPELL, "塔莎狂笑术")] == ["塔莎狂笑术"]
    assert [e.name for e in store.lookup(atlas.KIND_SPELL, "狂笑")] == ["塔莎狂笑术"]
    assert [e.name for e in store.lookup(atlas.KIND_SPELL, "sample")] == ["示例火球术"]
    assert store.lookup(atlas.KIND_SPELL, "狂笑", categories=["第三方"]) == []
    assert [e.name for e in store.lookup(atlas.KIND_SPELL, "火球", categories=["第三方"])] == [
        "示例火球术"
    ]
    assert store.lookup(atlas.KIND_SPELL, "") == []


@pytest.mark.asyncio
async def test_store_save_and_load_roundtrip(tmp_path) -> None:
    """缓存往返：保存后新实例可加载，条目与构建时间保持。"""
    store = _make_store(tmp_path, {})
    store.merge_and_save({atlas.KIND_SPELL: [_spell_entry("样例法术")]})

    fresh = _make_store(tmp_path, {})
    assert fresh.load() is True
    assert fresh.counts()[atlas.KIND_SPELL] == 1
    assert fresh.built_at is not None
    assert fresh.lookup(atlas.KIND_SPELL, "样例法术")[0].meta == "一环 · 惑控"


@pytest.mark.asyncio
async def test_store_keeps_old_when_build_shrinks(tmp_path) -> None:
    """自检：新构建条目数低于旧值一半时保留旧数据（不覆盖）。"""
    store = _make_store(tmp_path, {})
    store.merge_and_save(
        {atlas.KIND_SPELL: [_spell_entry(f"法术{i}") for i in range(10)]}
    )
    outcomes = store.merge_and_save({atlas.KIND_SPELL: [_spell_entry("法术0")]})
    assert outcomes == {atlas.KIND_SPELL: "kept"}
    assert store.counts()[atlas.KIND_SPELL] == 10


@pytest.mark.asyncio
async def test_store_load_missing_file(tmp_path) -> None:
    """无缓存文件时 load 返回 False（按未建立处理）。"""
    store = _make_store(tmp_path, {})
    assert store.load() is False
    assert store.ready is False
    assert store.counts()[atlas.KIND_SPELL] == 0
