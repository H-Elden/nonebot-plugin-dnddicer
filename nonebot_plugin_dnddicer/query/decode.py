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

from .. import card_geometry

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
_HEADING_RE = re.compile(r"<H([1-6])\b[^>]*>(.*?)</H\1\s*>", re.I | re.S)
_RED_FONT_RE = re.compile(r"<FONT\s+color=#800000[^>]*>", re.I)
_RED_BLOCK_RE = re.compile(r"<FONT\s+color=#800000[^>]*>(.{0,300}?)</FONT>", re.I | re.S)
_STAT_BLOCK_RE = re.compile(r'<div[^>]*\bclass="[^"]*\bstat-block\b[^"]*"', re.I)
_TAG_RE = re.compile(r"<[^>]+>")

#: 红标题前可回退到的块起始标签（让切片包含段首标签）
_BLOCK_START_TAGS = ("<p", "<div", "<li", "<strong", "<h1", "<h2", "<h3", "<h4", "<h5", "<h6")


def _zh_part(text: str) -> str:
    """取「中文名 English」的中文部分（首个 ASCII 字母之前）。"""
    match = re.search(r"[A-Za-z]", text)
    if match is None:
        return text.strip()
    return text[: match.start()].strip(" ·：:")


def _find_heading(html: str, name: str):
    """按文字找**页面级**标题（H1~H6）：精确中文名优先，其次前缀/包含。

    职业 / 起源等条目即整页（站点以 ``<H1>野蛮人 Barbarian</H1>`` 为页题），
    此规则先于红标题形态匹配（后者用于专长 / 单位小节这类页内条目）。
    """
    fallback = None
    for match in _HEADING_RE.finditer(html):
        text = _clean_text(match.group(2))
        zh = _zh_part(text)
        if not zh:
            continue
        if zh == name:
            return match, text
        if fallback is None and (zh.startswith(name) or name in zh):
            fallback = match, text
    return fallback


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
    #: 片段内是否还需去掉开头的第一个标题标签（数据卡容器分支：条目头在容器内）
    drop_first_head: bool = False


def _head_end(html: str, open_end: int) -> int:
    """标题标签（``<H?>`` 已匹配到开标签）的内容结束位置（``</H?>`` 之后）。"""
    close = re.search(r"</H[1-6]\s*>", html[open_end:], re.I)
    return open_end + close.end() if close else open_end


def _strip_first_heading(fragment: str) -> str:
    """去掉片段开头的第一个标题标签（含其文字与闭合标签）。"""
    match = re.search(r"<H[1-6]\b[^>]*>.*?</H[1-6]\s*>", fragment, re.I | re.S)
    if match is None:
        return fragment
    return fragment[: match.start()] + fragment[match.end() :]


def _enclosing_stat_block(html: str, position: int) -> Optional[Tuple[int, int]]:
    """标题所在的 2024 数据卡容器区间；不在任何容器内返回 ``None``。

    判据必须是「标题落在容器**内部**」——只看「标题之前出现过数据卡」会把排在
    任意数据卡之后的词条全切成那张卡（实测 4 环页 20/41 条切错，见专项分析文档）。
    """
    found: Optional[Tuple[int, int]] = None
    for match in _STAT_BLOCK_RE.finditer(html, 0, position):
        end = _div_end(html, match.start())
        if match.start() < position < end:
            found = (match.start(), end)  # 取最靠后的那个（嵌套时取内层）
    return found


def _find_heading_by_anchor(html: str, anchor: str):
    """按锚点找标题**开标签**（返回 ``re.Match`` 或 ``None``）。"""
    return re.search(
        rf"<H([1-6])\b[^>]*\bid=\"{re.escape(anchor)}\"[^>]*>", html, re.I
    )


def _match_heading(
    html: str, *, anchor: str = "", name: str = ""
) -> Tuple[Optional["re.Match"], int, str]:
    """定位条目标题：返回 ``(标题匹配, 正文起点, 标题文字)``。

    锚点优先（在开标签上匹配，正文起点取 ``</H?>`` 之后）；无锚点或锚点未命中时
    按标题文字匹配（此时匹配已含闭合标签，正文起点就是匹配末尾）。
    """
    if anchor:
        match = _find_heading_by_anchor(html, anchor)
        if match is not None:
            return match, _head_end(html, match.end()), _head_text(html, match)
    if name:
        found = _find_heading(html, name)
        if found is not None:
            return found[0], found[0].end(), found[1]
    return None, 0, ""


def _slice_from_heading(
    html: str, match: "re.Match", body_start: int, title: str
) -> Slice:
    """普通标题分支：切到下一个**同级或更高级**标题（或页尾）。

    口径必须与名字分支一致：2024 召唤类法术自带的数据卡，其名称是低一级的
    ``<H5>``，若按「下一个任意标题」截断就会把法术自带的生物卡丢掉。
    """
    level = int(match.group(1))
    end = len(html)
    for nxt in _HEADING_RE.finditer(html, body_start):
        if int(nxt.group(1)) <= level:
            end = nxt.start()
            break
    return Slice(body_start, end, title, True)


def slice_entry(
    html: str, *, anchor: str = "", name: str = ""
) -> Slice:
    """按锚点 / 数据卡容器 / 红标题切出条目区间。

    三级判据（2026-09-27 修订）：

    1. **数据卡容器**：锚点或条目名命中的标题落在某个 ``stat-block`` 容器内部
       （2024 怪物卡、召唤生物卡）时整块切出，并**保留卡内名称行**（站点卡片本来
       就带名字，删掉会让读者不知道这是谁的卡）；
    2. **普通标题**：切到下一个同级或更高级标题，因此召唤类法术的「法术正文 +
       它自带的生物卡」会一起带出（正文里写着「参考下面的生物卡」）；
    3. **红标题块**：专长 / 单位小节这类页内条目（仅名字分支）。

    Args:
        html: 整页 HTML。
        anchor: 条目锚点（如 ``Orb_of_Dragonkind``）；优先使用。
        name: 条目名（无锚点页面用；红标题形态匹配）。

    Returns:
        ``Slice``；未命中时返回整页区间且 ``located=False``。
    """
    match, body_start, text = _match_heading(html, anchor=anchor, name=name)
    if match is not None:
        container = _enclosing_stat_block(html, match.start())
        if container is not None:
            start, end = container
            return Slice(start, end, text or _head_text(html, match), True)
        return _slice_from_heading(html, match, body_start, text)

    if name:
        # ③ 页内条目（专长 / 单位小节）：紫红加粗标题块
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

#: 中文标点（硬折行落在标点旁时不留空格）
_CJK_PUNCT = set("。，、；：！？（）「」『』【】《》〈〉…·—～")

#: 空白串（含换行/全角空格）
_WHITESPACE_RE = re.compile(r"[ \t\r\n\u3000]+")


def _is_cjk(char: str) -> bool:
    """是否全角字符（汉字、中文标点、全角符号）。"""
    import unicodedata

    return bool(char) and unicodedata.east_asian_width(char) in ("F", "W")


def collapse_soft_wraps(data: str) -> str:
    """折叠文本节点里的空白，并合并「站内硬折行」。

    - 普通空格（不含换行）原样折叠成一个空格（站内用「四环 塑能」这种空格
      分隔，不能吃掉）；
    - **含换行的空白串**是站内按固定列硬折行的产物：两侧都是中文时直接连起来
      （「本\\n法术」→「本法术」），有一侧是中文标点时直接丢掉（「…）\\n。」
      →「…）。」），其余情形折叠成一个空格（「不过 1 \\n尺」→「不过 1 尺」）。
    """
    out: List[str] = []
    index = 0
    length = len(data)
    while index < length:
        match = _WHITESPACE_RE.match(data, index)
        if match is None:
            out.append(data[index])
            index += 1
            continue
        run = match.group(0)
        before = data[index - 1] if index > 0 else ""
        after = data[match.end()] if match.end() < length else ""
        has_newline = "\n" in run or "\r" in run
        if has_newline and (before in _CJK_PUNCT or after in _CJK_PUNCT):
            pass  # 标点旁的硬折行：不留空格
        elif has_newline and _is_cjk(before) and _is_cjk(after):
            pass  # 中文词被折开：直接连起来
        else:
            out.append(" ")
        index = match.end()
    return "".join(out)


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
        # 折叠源 HTML 的原始空白（缩进/换行）：渲染侧用 pre-wrap 呈现我们
        # 自己插入的折行，若保留原始换行会到处多出空行。
        # 站内正文按固定列硬折行，换行常落在句子中间甚至词中间：这类**含换行的
        # 空白**在中文之间直接连起来、在标点旁直接丢掉（否则会留下「本 法术」
        # 这类词中空格与行首缩进）。
        data = collapse_soft_wraps(data)
        if not data:
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
    cleaned = "".join(parser.out).strip()
    # 标签之间的空白（源缩进/换行）直接删除，避免 pre-wrap 下多出空行
    return re.sub(r">[ \t\r\n\u3000]+<", "><", cleaned)


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


# ── 富文本折行（Python 侧避头尾；litehtml 无避头尾规则）──────────────

#: 行首禁则标点（不允许出现在行首；与 render/layout.py 同口径）
_LINE_START_FORBIDDEN = set("。，、；：！？）」』】》…·")

#: 块级标签（出现即视为新行开始；折行宽度重新累计）
_BLOCK_TAGS = {
    "p", "div", "li", "ul", "ol", "table", "tr", "td", "th", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
}

#: 块边界标签（切「折行块」用：块内折行 + 尾行再平衡；与 _BLOCK_TAGS 同口径 + br）
_TOKEN_RE = re.compile(r"<[^>]+>|\n|.", re.S)
_BLOCK_BOUNDARY_RE = re.compile(
    r"</?(?:p|div|li|ul|ol|table|tr|td|th|hr|blockquote|h[1-6])\b|^<br\s*/?>$", re.I
)


def _char_width_px(char: str, font_size: int) -> float:
    """单字符宽度估算（px）——口径集中在 ``card_geometry``。"""
    return card_geometry.char_width(char, font_size)


class _FragmentWrapper(HTMLParser):
    """在文本节点内插入换行实现避头尾（标签原样保留、不占宽度）。

    litehtml 无避头尾规则（实测 ``white-space: nowrap`` 不生效），行首标点
    （如一行以「。」开头）需在 Python 侧规避：按可见宽度累计折行，行首禁则
    标点拉回上一行（宁可略超宽），ASCII 词整体不拆。

    预算由调用方给出（**小于**卡片内容宽，见 ``card_geometry``）：越界会让
    litehtml 再折一次、把末尾一两个字挤成孤行；列表项内另给更窄的预算。
    """

    def __init__(self, *, budget: float, font_size: int) -> None:
        super().__init__(convert_charrefs=True)
        self.out: List[str] = []
        self.budget = budget
        self.font_size = font_size
        self.line_width = 0.0

    def _emit_text(self, text: str) -> None:
        index = 0
        length = len(text)
        while index < length:
            char = text[index]
            if char == " " and self.line_width == 0:
                index += 1  # 行首空格不输出（标签间残留的空白）
                continue
            if char.isascii() and (char.isalnum() or char in "-'"):
                end = index
                while (
                    end < length
                    and text[end].isascii()
                    and (text[end].isalnum() or text[end] in "-'")
                ):
                    end += 1
                word = text[index:end]
                width = sum(_char_width_px(c, self.font_size) for c in word)
                if self.line_width > 0 and self.line_width + width > self.budget:
                    self.out.append("\n")
                    self.line_width = 0.0
                self.out.append(word)
                self.line_width += width
                index = end
                continue
            width = _char_width_px(char, self.font_size)
            if (
                self.line_width > 0
                and self.line_width + width > self.budget
                and char not in _LINE_START_FORBIDDEN
            ):
                self.out.append("\n")
                self.line_width = 0.0
            self.out.append(char)
            self.line_width += width
            index += 1

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "br":
            self.out.append("<br>")
            self.line_width = 0.0
            return
        if tag in _BLOCK_TAGS:
            self.line_width = 0.0
        self.out.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br":
            self.out.append("<br>")
            self.line_width = 0.0
        else:
            self.out.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag.lower() in _BLOCK_TAGS:
            self.line_width = 0.0
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self._emit_text(data)


def _split_segments(fragment: str) -> List[Tuple[str, str]]:
    """把片段切成「块级标签」与「文本块」（文本块内含行内标签）。"""
    segments: List[Tuple[str, str]] = []
    buffer: List[str] = []
    for token in _TOKEN_RE.findall(fragment):
        if token.startswith("<") and _BLOCK_BOUNDARY_RE.match(token):
            if buffer:
                segments.append(("text", "".join(buffer)))
                buffer = []
            segments.append(("tag", token))
        else:
            buffer.append(token)
    if buffer:
        segments.append(("text", "".join(buffer)))
    return segments


def _wrap_once(chunk: str, *, budget: float, font_size: int) -> str:
    wrapper = _FragmentWrapper(budget=budget, font_size=font_size)
    wrapper.feed(chunk)
    wrapper.close()
    return "".join(wrapper.out)


def _plain_lines(wrapped: str) -> List[str]:
    return re.sub(r"<[^>]+>", "", wrapped).split("\n")


def _has_tiny_tail(wrapped: str) -> bool:
    """末行不足 ``MIN_TAIL_CHARS`` 字、且上一行够长（不是标题式短行）。"""
    lines = _plain_lines(wrapped)
    if len(lines) < 2:
        return False
    tail = lines[-1].strip()
    return (
        0 < len(tail) < card_geometry.MIN_TAIL_CHARS
        and len(lines[-2].strip()) >= card_geometry.TAIL_PREV_MIN_CHARS
    )


def _wrap_block(chunk: str, *, budget: float, font_size: int) -> str:
    """块内折行；末行过短时逐次收紧预算重折（只让行更短，不会越界）。"""
    best = _wrap_once(chunk, budget=budget, font_size=font_size)
    for step in range(1, card_geometry.MAX_TAIL_SHIFT + 1):
        if not _has_tiny_tail(best):
            break
        candidate = _wrap_once(
            chunk, budget=budget - step * font_size, font_size=font_size
        )
        if len(_plain_lines(candidate)) > len(_plain_lines(best)) + 1:
            break  # 收紧过头（多出一行以上）就回退到上一次结果
        best = candidate
    return best


def wrap_fragment(
    fragment: str,
    *,
    width_em: Optional[float] = None,
    font_size: int = card_geometry.FONT_SIZE,
) -> str:
    """对清洗后的片段做「Python 侧折行」（跨标签、避头尾、整词保护、列表感知）。

    渲染侧以 ``white-space: pre-wrap`` 呈现（换行即所见）。预算：

    - 默认取 ``card_geometry`` 的「内容宽 × 0.93」（列表项内再扣缩进与行标记）；
    - 显式传入 ``width_em`` 时按 ``width_em × font_size`` 作为普通段落预算
      （供测试与特殊版式使用），列表内仍额外扣缩进。
    """
    if width_em is None:
        flat = card_geometry.flat_budget(font_size=font_size)
        listed = card_geometry.list_budget(font_size=font_size)
    else:
        flat = float(width_em) * font_size
        indent = (card_geometry.LIST_INDENT_EM + card_geometry.LIST_MARKER_EM) * font_size
        listed = max(1.0, flat - indent)

    out: List[str] = []
    depth = 0
    for kind, chunk in _split_segments(fragment):
        if kind == "tag":
            low = chunk.lower()
            if re.match(r"<(ul|ol)\b", low):
                depth += 1
            elif re.match(r"</(ul|ol)\b", low):
                depth = max(0, depth - 1)
            out.append(chunk)
            continue
        budget = listed if depth > 0 else flat
        out.append(_wrap_block(chunk, budget=budget, font_size=font_size))
    return "".join(out)


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
    fragment_html = html[sliced.start : sliced.end]
    if sliced.drop_first_head:
        fragment_html = _strip_first_heading(fragment_html)
    # 清洗只做一次：文字用**未折行**的清洗结果，图片用折行结果。
    # 文字消息里不能带图片排版的折行（客户端会按气泡宽度自己折，硬换行会
    # 在句中留下一两个字独占一行的残行，2026-09-27 用户实测反馈）。
    cleaned = sanitize_html(fragment_html, highlight=keyword)
    return DecodedEntry(
        title=sliced.title or name,
        fragment=wrap_fragment(cleaned),
        text=fragment_to_text(cleaned),
        located=sliced.located,
    )
