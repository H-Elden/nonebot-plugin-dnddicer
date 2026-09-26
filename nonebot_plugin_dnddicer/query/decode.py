"""正文层：站点 HTML → 条目片段（切分 / 清洗 / 高亮 / 文字块）（2026-09-26）。

规则查询的正文来源从「服务端纯文本 content」升级为「站点页面 HTML」（样式
在索引阶段已被剥离，只有 HTML 才带加粗、颜色、表格底色等信息）。本模块：

1. **切分**（三条规则，按页面类型收敛）：
   - 锚点标题：``<H1~H6 id="…">``，切到下一个标题标签（法术 / 物品 / 术语页）；
   - 数据卡容器：``<div class="stat-block">`` 整块（div 配对；2024 怪物页）；
   - 紫红标题块：``<FONT color=#800000>``（专长条目标题、单位小节标题）；
   - 都失败时按「未精确定位」处理（给页面片段 + 高亮关键词）。
2. **清洗**：标签与属性白名单（保留加粗 / 斜体 / 颜色 / 色块表格 / 列表 /
   站点数据卡类名），丢弃脚本、样式、链接（保留文字）、图片；站点语义配色
   由渲染侧的样式表复刻（不复制站点 CSS 资产）。
3. **高亮**：用户关键词在文本节点内加 ``dx-hl`` 标记（图片模式带底色）；
4. **文字块**：``fragment_to_text`` 把清洗结果转为结构化文本（文字模式用：
   标题 / 段落 / 列表 ``·`` / 表格行）。

纯函数、离线可测；不发起网络请求。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Sequence, Tuple

# ── 白名单 ─────────────────────────────────────────────────────────────

#: 保留的标签（其余标签去掉、保留其文字）
_ALLOWED_TAGS = {
    "p", "br", "b", "strong", "i", "em", "u", "span", "div", "hr",
    "table", "tr", "td", "th", "thead", "tbody",
    "ul", "ol", "li", "sub", "sup", "blockquote",
}

#: 整个丢弃内容的标签（含结束标签，按嵌套计数跳过）
_SKIP_TAGS = {
    "script", "style", "link", "meta", "title", "head", "iframe", "form",
    "nav", "audio", "video", "svg", "noscript", "button",
}

#: 只丢弃标签本身、不影响后续内容的标签（自闭合/无内容型）
_DROP_TAGS = {"img", "input", "source", "track", "embed", "object", "base", "area"}

#: 保留的类名（站点数据卡等；其余类名丢弃，样式由卡片侧给出）
_KEEP_CLASSES = {
    "stat-block", "stat-abilities", "sub-line", "little-paper",
    "c1", "c2", "c3", "c4",
}

#: 高亮标记的类名（渲染侧样式表定义底色）
HIGHLIGHT_CLASS = "dx-hl"

# ── 标题点（切分边界）─────────────────────────────────────────────────

_HEAD_TAG_RE = re.compile(r"<H[1-6]\b", re.I)
_RED_FONT_RE = re.compile(r"<FONT\s+color=#800000[^>]*>", re.I)
_RED_BLOCK_RE = re.compile(r"<FONT\s+color=#800000[^>]*>(.{0,300}?)</FONT>", re.I | re.S)
_STAT_BLOCK_RE = re.compile(r'<div[^>]*\bclass="[^"]*\bstat-block\b[^"]*"', re.I)
_TAG_RE = re.compile(r"<[^>]+>")

#: 红标题前可回退到的块起始标签（让切片包含段首标签）
_BLOCK_START_TAGS = ("<p", "<div", "<li", "<strong", "<h1", "<h2", "<h3", "<h4", "<h5", "<h6")


def _clean_text(fragment: str) -> str:
    """去标签、折叠空白（全角空格按空格处理）。"""
    text = _TAG_RE.sub(" ", fragment).replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


def _div_end(html: str, start: int) -> int:
    """从 ``<div…>`` 起始处找容器结束位置（div 配对）。"""
    depth = 0
    for match in re.finditer(r"<div\b|</div>", html[start:], re.I):
        if match.group(0).lower().startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return start + match.end()
    return len(html)


@dataclass
class Slice:
    """切分结果：条目在整页 HTML 中的区间与标题。"""

    start: int
    end: int
    title: str
    located: bool


def slice_entry(
    html: str, *, anchor: str = "", name: str = ""
) -> Slice:
    """按锚点 / 数据卡容器 / 红标题切出条目区间。

    Args:
        html: 整页 HTML。
        anchor: 条目锚点（如 ``Orb_of_Dragonkind``）；优先使用。
        name: 条目名（无锚点页面用；红标题形态匹配）。

    Returns:
        ``Slice``；未命中时返回整页区间且 ``located=False``。
    """
    if anchor:
        match = re.search(
            rf"<H[1-6]\b[^>]*\bid=\"{re.escape(anchor)}\"[^>]*>", html, re.I
        )
        if match is not None:
            # 2024 怪物数据卡：条目在 stat-block 容器内，整块切出
            containers = list(_STAT_BLOCK_RE.finditer(html, 0, match.start()))
            if containers:
                start = containers[-1].start()
                end = _div_end(html, start)
                return Slice(start, end, _head_text(html, match), True)
            start = match.end()
            end = len(html)
            nxt = _HEAD_TAG_RE.search(html, start)
            if nxt is not None:
                end = nxt.start()
            return Slice(start, end, _head_text(html, match), True)

    if name:
        for match in _RED_BLOCK_RE.finditer(html):
            text = _clean_text(match.group(1))
            if name not in text:
                continue
            start = _retreat_to_block_start(html, match.start())
            end = len(html)
            for pattern in (_RED_FONT_RE, _HEAD_TAG_RE):
                nxt = pattern.search(html, match.end())
                if nxt is not None:
                    end = min(end, nxt.start())
            return Slice(start, end, text, True)

    return Slice(0, len(html), name, False)


def _head_text(html: str, match: "re.Match") -> str:
    """取标题标签内的文字（作为条目名）。"""
    close = re.search(r"</H[1-6]\s*>", html[match.end() :], re.I)
    inner = html[match.end() : match.end() + close.start()] if close else ""
    return _clean_text(inner) or _clean_text(_TAG_RE.sub(" ", match.group(0)))


def _retreat_to_block_start(html: str, position: int) -> int:
    """从红标题匹配点向前回退到所在块的起始标签（<p>/<div>/<strong> 等）。"""
    best = position
    for tag in _BLOCK_START_TAGS:
        index = html.rfind(tag, 0, position)
        if index > best - 1 and index < position:
            # 取最靠后的块起始
            if index > best:
                best = index
    return best if best < position else position


# ── 清洗器 ─────────────────────────────────────────────────────────────


class _Sanitizer(HTMLParser):
    """把条目 HTML 清洗为卡片可渲染的片段（保留语义标签与站点类名）。"""

    def __init__(self, *, highlight: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.skip = 0
        self.div_stack: List[bool] = []
        self.highlight = highlight.strip()
        self._hl_re = (
            re.compile(re.escape(self.highlight), re.I) if self.highlight else None
        )

    # -- 工具 -----------------------------------------------------------

    def _in_stat_block(self) -> bool:
        return bool(self.div_stack and self.div_stack[-1])

    def _class_attr(self, attrs: Dict[str, str]) -> str:
        kept = [c for c in attrs.get("class", "").split() if c in _KEEP_CLASSES]
        return f' class="{" ".join(kept)}"' if kept else ""

    # -- HTMLParser 回调 -------------------------------------------------

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in _DROP_TAGS:
            return
        attrs = {k.lower(): v for k, v in attrs}
        if tag == "br":
            self.out.append("<br>")
            return
        if tag == "hr":
            self.out.append("<hr>")
            return
        if tag == "div":
            inside = self._in_stat_block() or "stat-block" in attrs.get("class", "")
            self.div_stack.append(inside)
            self.out.append(f"<div{self._class_attr(attrs)}>")
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append('<div class="rt-h">')
            return
        if tag == "font":
            color = attrs.get("color")
            style = f' style="color:{color}"' if color else ""
            self.out.append(f"<span{style}>")
            return
        if tag == "table":
            self.out.append('<table class="rt-table">')
            return
        if tag in ("td", "th"):
            span_attr = ""
            if attrs.get("colspan"):
                span_attr += f' colspan="{attrs["colspan"]}"'
            if attrs.get("rowspan"):
                span_attr += f' rowspan="{attrs["rowspan"]}"'
            if self._in_stat_block():
                self.out.append(f"<{tag}{self._class_attr(attrs)}{span_attr}>")
            else:
                bg = attrs.get("bgcolor")
                style = f' style="background-color:{bg}"' if bg else ""
                self.out.append(f"<{tag}{span_attr}{style}>")
            return
        if tag == "p":
            align = attrs.get("align")
            style = ' style="text-align:center"' if align == "center" else ""
            self.out.append(f"<p{style}>")
            return
        if tag in _ALLOWED_TAGS:
            self.out.append(f"<{tag}{self._class_attr(attrs)}>")

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br":
            self.out.append("<br>")
        elif tag.lower() == "hr":
            self.out.append("<hr>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "div":
            if self.div_stack:
                self.div_stack.pop()
            self.out.append("</div>")
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.out.append("</div>")
            return
        if tag == "font":
            self.out.append("</span>")
            return
        if tag in _ALLOWED_TAGS:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if self.skip:
            return
        if self._hl_re is None:
            self.out.append(data)
            return
        index = 0
        for match in self._hl_re.finditer(data):
            self.out.append(data[index : match.start()])
            self.out.append(
                f'<span class="{HIGHLIGHT_CLASS}">{match.group(0)}</span>'
            )
            index = match.end()
        self.out.append(data[index:])


def sanitize_html(fragment: str, *, highlight: str = "") -> str:
    """清洗条目 HTML 片段（保留样式标签与站点类名；可选关键词高亮）。"""
    parser = _Sanitizer(highlight=highlight)
    parser.feed(fragment)
    parser.close()
    return "".join(parser.out).strip()


# ── 文字模式：片段 → 结构化文本 ───────────────────────────────────────

_TABLE_RE = re.compile(r"<table\b.*?</table>", re.I | re.S)
_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)


def _table_to_text(table_html: str) -> str:
    """表格 → 文本行（单元以 ` | ` 连接，每行一条）。"""
    rows: List[str] = []
    for row in _ROW_RE.finditer(table_html):
        cells = [_clean_text(cell) for cell in _CELL_RE.findall(row.group(1))]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(" | ".join(cells))
    return "\n" + "\n".join(rows) + "\n" if rows else "\n"


def fragment_to_text(fragment: str) -> str:
    """把清洗后的 HTML 片段转成结构化文本（文字模式用）。

    规则：表格单元以 `` | `` 连接、每行一条；段与段之间空行分隔；列表项以
    ``· `` 起头；水平线渲染为一行 ``……``。颜色与加粗在文本消息里不可用，
    按内容完整优先。
    """
    text = _TABLE_RE.sub(lambda m: _table_to_text(m.group(0)), fragment)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<hr\b[^>]*>", "\n……\n", text, flags=re.I)
    text = re.sub(r"</(?:p|div|li|h[1-6])\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<li\b[^>]*>", "\n· ", text, flags=re.I)
    text = _TAG_RE.sub("", text)

    out: List[str] = []
    for raw in text.split("\n"):
        line = re.sub(r"[ \t\u3000]+", " ", raw).strip()
        if line:
            out.append(line)
        elif out and out[-1] != "":
            out.append("")
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


# ── 对外主入口 ─────────────────────────────────────────────────────────


@dataclass
class DecodedEntry:
    """正文层产物：条目标题 + 富文本片段 + 文字块 + 是否精确定位。"""

    title: str
    fragment: str
    text: str
    located: bool


def decode_entry(
    html: str, *, anchor: str = "", name: str = "", keyword: str = ""
) -> DecodedEntry:
    """从整页 HTML 切出条目并清洗（含关键词高亮）。

    Args:
        html: 整页 HTML（``query/fetch.py`` 抓取）。
        anchor: 条目锚点（速查索引提供；优先）。
        name: 条目名（无锚点页面用）。
        keyword: 用户关键词（高亮用；可与 name 不同）。

    Returns:
        ``DecodedEntry``（``located=False`` 表示未精确定位、给的是页面片段）。
    """
    sliced = slice_entry(html, anchor=anchor, name=name)
    fragment = sanitize_html(html[sliced.start : sliced.end], highlight=keyword)
    return DecodedEntry(
        title=sliced.title or name,
        fragment=fragment,
        text=fragment_to_text(fragment),
        located=sliced.located,
    )
