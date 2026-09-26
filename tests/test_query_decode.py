"""正文层（query/decode.py）的单元测试（全离线：自写合成 HTML 夹具）。

覆盖：三条切分规则（锚点标题 / 数据卡容器 / 紫红标题）、未精确定位回退、
清洗白名单（保留样式标签与站点类名、丢弃脚本链接图片）、关键词高亮、
以及文字块提取（段落 / 列表 / 表格）。

夹具说明：结构照站点形态（2024 竖线式条目头、stat-block 数据卡、紫红加粗
标题、表格底色属性），内容为自写样例。
"""

from __future__ import annotations

from nonebot_plugin_dnddicer.query import decode

_SPELL_PAGE = """<html><body>
<h2>法术详述</h2>
<H4 id="Sample_Spell">样例法术｜Sample Spell</H4>
<P><EM>一环 惑控</EM><BR><STRONG>施法时间：</STRONG>动作<BR>一段自写说明，样例二字出现于此。</P>
<H4 id="Other_Spell">另一个法术｜Other Spell</H4>
<P>其它内容。</P>
</body></html>"""

_MONSTER_PAGE = """<html><body>
<h2>样例怪物 Sample Monster</h2>
<div class="stat-block">
<H5 id="Sample_Monster">样例怪物Sample Monster</H5>
<div class="sub-line">大型巨人，混乱邪恶</div>
<table><tr><td><strong>AC </strong>11</td><td><strong>先攻 </strong>-1（9）</td></tr></table>
<table class="stat-abilities"><tr><td class="c1"><strong>力量</strong></td><td class="c1">19</td></tr></table>
<p>怪物动作段落。</p>
</div>
<P>页面其它内容。</P>
</body></html>"""

_FEAT_PAGE = """<html><body>
<p><b><FONT color=#800000>专长描述 Feat Descriptions</FONT></b></p>
<p><b><FONT color=#800000>冲锋手 <BR>Charger</FONT></b></p>
<i>通用专长（先决：等级4+）</i><BR>你获得以下增益。
<UL><LI><DIV><b>属性值提升Ability Score Increase。</b>你的力量或敏捷提升1。</DIV></LI></UL>
<p><b><FONT color=#800000>大厨 <BR>Chef</FONT></b></p>
<P>厨子内容。</P>
</body></html>"""

_UNIT_PAGE = """<html><body>
<P>导言。</P>
<STRONG><FONT color=#800000 size=5>长度单位</FONT></STRONG>
<P>1尺=12寸</P>
<STRONG><FONT color=#800000 size=5>货币</FONT></STRONG>
<P>1金币(GP)=10银币(SP)</P>
</body></html>"""


# ── 切分 ───────────────────────────────────────────────────────────────


def test_slice_by_anchor() -> None:
    """锚点标题：切到下一个标题，标题取条目头文字（片段从标题之后开始）。"""
    sliced = decode.slice_entry(_SPELL_PAGE, anchor="Sample_Spell")
    assert sliced.located is True
    assert "样例法术" in sliced.title

    fragment = decode.sanitize_html(_SPELL_PAGE[sliced.start : sliced.end])
    assert "施法时间：" in fragment
    assert "另一个法术" not in fragment


def test_slice_stat_block_container() -> None:
    """数据卡容器：条目在 stat-block 内时整块切出（含属性表与动作段落）。"""
    sliced = decode.slice_entry(_MONSTER_PAGE, anchor="Sample_Monster")
    assert sliced.located is True
    fragment = decode.sanitize_html(_MONSTER_PAGE[sliced.start : sliced.end])
    assert 'class="stat-block"' in fragment
    assert "AC " in fragment and "力量" in fragment and "怪物动作段落" in fragment
    assert "页面其它内容" not in fragment


def test_slice_by_red_title() -> None:
    """紫红标题：无锚点页面按条目标题匹配（专长页形态）。"""
    sliced = decode.slice_entry(_FEAT_PAGE, name="冲锋手")
    assert sliced.located is True
    fragment = decode.sanitize_html(_FEAT_PAGE[sliced.start : sliced.end])
    assert "冲锋手" in fragment
    assert "属性值提升" in fragment
    assert "大厨" not in fragment


def test_slice_page_level_heading() -> None:
    """页面级条目（职业）：H1 标题文字匹配，切片为整页内容。"""
    html = (
        "<H1>样例职业 Sample Class</H1>"
        "<P>开头段落。</P>"
        "<H3>样例职业特性 Class Features</H3>"
        "<P>正文。</P>"
    )
    sliced = decode.slice_entry(html, name="样例职业")
    assert sliced.located is True
    assert "样例职业" in sliced.title
    fragment = decode.sanitize_html(html[sliced.start : sliced.end])
    # 匹配 H1（若误配「包含同名」的 H3 会丢掉开头段落）
    assert "开头段落。" in fragment
    assert "正文。" in fragment


def test_slice_unit_section() -> None:
    """紫红小节标题：单位页按小节切分。"""
    sliced = decode.slice_entry(_UNIT_PAGE, name="货币")
    assert sliced.located is True
    fragment = decode.sanitize_html(_UNIT_PAGE[sliced.start : sliced.end])
    assert "1金币(GP)=10银币(SP)" in fragment
    assert "1尺=12寸" not in fragment


def test_slice_not_located_returns_page() -> None:
    """锚点与标题都未命中：整页回退并标记未定位。"""
    sliced = decode.slice_entry(_SPELL_PAGE, anchor="Missing", name="不存在")
    assert sliced.located is False
    assert sliced.start == 0 and sliced.end == len(_SPELL_PAGE)


# ── 清洗与高亮 ─────────────────────────────────────────────────────────


def test_sanitize_keeps_styles_drops_active_content() -> None:
    """清洗：保留样式标签与站点类名；丢弃脚本、链接标签（留文字）、图片。"""
    html = (
        '<div class="stat-block other-class"><p>'
        '<a href="x.htm">链接文字</a>'
        "<script>bad()</script><img src=\"x.png\">"
        "<STRONG>粗体</STRONG><FONT color=#008000>绿色术语</FONT>"
        "</p></div>"
    )
    fragment = decode.sanitize_html(html)
    assert "链接文字" in fragment
    assert "bad()" not in fragment
    assert "x.png" not in fragment
    assert "<strong>粗体</strong>" in fragment
    assert 'style="color:#008000"' in fragment
    assert 'class="stat-block"' in fragment
    assert "other-class" not in fragment


def test_sanitize_table_keeps_bgcolor_outside_stat_block() -> None:
    """普通表格（非数据卡）：表头底色以内联背景保留（表格行底色）。"""
    fragment = decode.sanitize_html(
        '<table><tr><td bgcolor=#f5c589>表头</td><td>值</td></tr></table>'
    )
    assert 'class="rt-table"' in fragment
    assert 'style="background-color:#f5c589"' in fragment


def test_sanitize_highlight_wraps_keyword() -> None:
    """高亮：关键词在文本节点内包上 dx-hl 标记（大小写不敏感）。"""
    fragment = decode.sanitize_html("<p>样例法术说明</p>", highlight="样例")
    assert '<span class="dx-hl">样例</span>' in fragment
    fragment_en = decode.sanitize_html("<p>Sample Spell</p>", highlight="sample")
    assert '<span class="dx-hl">Sample</span>' in fragment_en


# ── 文字块 ─────────────────────────────────────────────────────────────


def test_fragment_to_text_blocks() -> None:
    """文字块：段落空行分隔、列表 `· `、表格 ` | ` 连接。"""
    fragment = (
        "<p>第一段。</p><p>第二段。</p>"
        "<ul><li>一项</li><li>二项</li></ul>"
        "<table><tr><td>法术</td><td>充能</td></tr>"
        "<tr><td>侦测魔法</td><td>0</td></tr></table>"
    )
    text = decode.fragment_to_text(fragment)
    assert "第一段。" in text
    assert "\n\n" in text  # 段落之间有空行
    assert "· 一项" in text and "· 二项" in text
    assert "法术 | 充能" in text
    assert "侦测魔法 | 0" in text


def test_decode_entry_end_to_end() -> None:
    """decode_entry：切分 + 清洗 + 高亮 + 文字块一次完成。"""
    entry = decode.decode_entry(_FEAT_PAGE, name="冲锋手", keyword="冲锋")
    assert entry.located is True
    assert entry.title.startswith("冲锋手")
    assert "冲锋" in entry.fragment
    assert '<span class="dx-hl">冲锋</span>' in entry.fragment
    assert "· 属性值提升" in entry.text
    assert "大厨" not in entry.text
