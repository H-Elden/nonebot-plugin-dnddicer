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


def char_width(char: str, font_size: int = FONT_SIZE) -> float:
    """单字符宽度估算（px）：全角 1em、半角按 ``ASCII_EM``。"""
    import unicodedata

    if unicodedata.east_asian_width(char) in ("F", "W"):
        return float(font_size)
    return font_size * ASCII_EM


def text_width(text: str, font_size: int = FONT_SIZE) -> float:
    """文本宽度估算（px）。"""
    return sum(char_width(char, font_size) for char in text)
