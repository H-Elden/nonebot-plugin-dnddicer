"""卡片版式与折行几何的**单一来源**（CSS 与 Python 折行共用，纯常量无依赖）。

规则查询的图片卡片由 litehtml 渲染，它没有避头尾规则，因此正文折行在 Python 侧
完成（`query/decode.py` 的 ``wrap_fragment`` 与 ``render/layout.py`` 的 ``wrap_cjk``）。
折行宽度必须**小于**卡片内容宽，否则 litehtml 会把我们折好的行再折一次，末尾
一两个字被挤到下一行（实测：644px 容器里 41 个汉字即触发，`<ul>` 内 39 个即触发）。

本模块集中这些数字，模板样式表里的对应值必须与之保持一致（有测试断言）：

- 卡片宽 700px、左右内边距 28px（``rich_card.css`` 的 ``.card`` padding）；
- 正文 16px、行高 1.75；
- 列表缩进 1.4em（``.content ul`` 的 padding-left）、行标记另占约 0.5em；
- 折行预算 = 可用宽 × 0.93（留 7% 余量抵消字体度量差异）；
- 西文/数字按 0.6em 估算（实测 Microsoft YaHei 约 0.54em、Noto Sans CJK 约 0.50em、
  DejaVu 数字最大 0.64em，取偏大值保守估计）。
"""

from __future__ import annotations

#: 卡片总宽（px）——与 `render/engine.py` 的 `html_to_pic(max_width=...)` 一致
CARD_WIDTH = 700

#: 卡片左右内边距（px）——与模板样式表的 `.card` padding 一致
CARD_PADDING_X = 28

#: 正文字号（px）与行高倍数
FONT_SIZE = 16
LINE_HEIGHT = 1.75

#: 折行预算比例（可用宽 × 该比例；越小越安全、行越短）
BUDGET_RATIO = 0.93

#: 西文/数字的宽度估算（em）
ASCII_EM = 0.6

#: 列表项缩进（em，对应 `.content ul { padding-left: 1.4em }`）
LIST_INDENT_EM = 1.4

#: 列表行标记的占位（em，litehtml 每行都会预留标记宽度）
LIST_MARKER_EM = 0.5

#: 尾行再平衡：末行少于该字数且上一行足够长时，收紧预算重折
MIN_TAIL_CHARS = 4
#: 判定「上一行足够长」的下限（字）
TAIL_PREV_MIN_CHARS = 8
#: 尾行再平衡最多收紧几次（每次 1 个汉字宽）
MAX_TAIL_SHIFT = 3

# ── 角色卡图（940px 单页版式）的「背景故事」折行几何 ──────────────────────
#: 角色卡图宽度（px）——与 `render/engine.py` 的 `CHAR_CARD_WIDTH` 一致
CHAR_CARD_WIDTH = 940

#: 卡面右栏内容宽（px）——武器表与下方两列面板的外框宽度（实测 679px，
#: 由 940 − 页边距 32 − 边框 2 − 左栏 220 − 两栏间距 7 得到）
CHAR_CARD_RIGHT_COL_WIDTH = 679

#: 故事面板的边框与左右内边距（px）——对应 `char_card.css` 的 `.panel`
#: 边框与 `.story-text` 的左右 padding
STORY_PANEL_BORDER = 1
STORY_PADDING_X = 7

#: 故事正文字号（px）与首行缩进（em）——对应 `char_card.css` 的 `.story-text`
STORY_FONT_SIZE = 10.5
STORY_INDENT_EM = 2.0


def content_width(padding_x: int = CARD_PADDING_X, card_width: int = CARD_WIDTH) -> float:
    """卡片内容区宽度（px）。"""
    return float(card_width - padding_x * 2)


def flat_budget(
    *, font_size: int = FONT_SIZE, padding_x: int = CARD_PADDING_X
) -> float:
    """普通段落的折行预算（px）。"""
    return content_width(padding_x) * BUDGET_RATIO


def list_budget(
    *, font_size: int = FONT_SIZE, padding_x: int = CARD_PADDING_X
) -> float:
    """列表项内的折行预算（px）：再扣掉列表缩进与行标记占位。"""
    indent = (LIST_INDENT_EM + LIST_MARKER_EM) * font_size
    return max(1.0, content_width(padding_x) - indent) * BUDGET_RATIO


def char_width(char: str, font_size: float = FONT_SIZE) -> float:
    """单字符宽度估算（px）：全角 1em、半角按 ``ASCII_EM``。"""
    import unicodedata

    if unicodedata.east_asian_width(char) in ("F", "W"):
        return float(font_size)
    return font_size * ASCII_EM


def text_width(text: str, font_size: float = FONT_SIZE) -> float:
    """文本宽度估算（px）。"""
    return sum(char_width(char, font_size) for char in text)


def story_budget() -> float:
    """角色卡「背景故事」的折行预算（px）。

    首行有 2em 缩进，litehtml 计算折行时不把 ``text-indent`` 计入可用宽，
    故预算按**首行可用宽**算（其余行沿用同一预算，右侧略留白）。
    """
    text_width_px = CHAR_CARD_RIGHT_COL_WIDTH - (STORY_PANEL_BORDER + STORY_PADDING_X) * 2
    first_line = text_width_px - STORY_INDENT_EM * STORY_FONT_SIZE
    return first_line * BUDGET_RATIO
