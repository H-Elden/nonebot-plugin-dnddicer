"""卡片模板与版式几何的不变量（离线，不需要渲染依赖）。

覆盖两条纪律（2026-09-27 实机问题修复后固化）：

1. **容器内不留模板空白**：``rich_card.css`` 的 ``.content`` 设了
   ``white-space: pre-wrap``，模板自身的换行/缩进会被当成内容各占一个空行
   （实测每张卡多出 140+px 空白带），三个模板统一按「容器内无裸空白」写；
2. **版式常量与样式表一致**：卡片宽、左右内边距、列表缩进在
   ``card_geometry`` 与样式表里必须是同一组数字（折行预算据此推算，改一边就错位）。
"""

from __future__ import annotations

import re

import pytest

from nonebot_plugin_dnddicer import card_geometry
from nonebot_plugin_dnddicer.render import engine

#: 三个卡片的 (模板文件, 样式表, 渲染参数)
CARDS = [
    (
        "rich_card.html",
        "rich_card.css",
        {
            "title": "样例｜Sample",
            "category": "玩家手册2024",
            "body_html": "<p>正文。</p>",
            "fallback_note": "",
            "source_path": "topics/样例.htm",
        },
    ),
    (
        "rule_card.html",
        "rule_card.css",
        {
            "title": "样例｜Sample",
            "category": "玩家手册2024",
            "blocks": [{"type": "para", "prefix": "", "text": "正文。"}],
            "fallback_note": "",
            "source_path": "topics/样例.htm",
        },
    ),
    (
        "books_card.html",
        "books_card.css",
        {
            "title": "可查询书目",
            "hint": "说明行",
            "footer": "底注",
            "sections": [{"title": "玩家手册2024", "rows": [{"key": "PHB24", "name": "玩家手册2024", "note": ""}]}],
        },
    ),
]


def _render(template_name: str, css_name: str, context: dict) -> str:
    """用**生产 Jinja 环境**同步渲染模板（与图片模式同一套配置）。"""
    template = engine._get_env().get_template(template_name)  # pyright: ignore[reportPrivateUsage]
    return template.render(
        css=engine._css_text(css_name),  # pyright: ignore[reportPrivateUsage]
        font_rule="",
        **context,
    )


@pytest.mark.parametrize("template_name, css_name, context", CARDS)
def test_content_container_has_no_template_whitespace(
    template_name: str, css_name: str, context: dict
) -> None:
    """正文容器开标签之后不得紧跟模板换行/缩进（pre-wrap 下会变成空行）。"""
    html = _render(template_name, css_name, context)
    opening = html.index('<div class="content">') + len('<div class="content">')
    # 容器内的第一个字符必须是内容（标签或文字），不能是换行/缩进
    assert html[opening] != "\n", template_name
    assert not html[opening:].startswith(" "), template_name
    inner_end = html.index("</div>", opening)
    assert not html[opening:inner_end].endswith("\n"), template_name
    assert not re.search(r"\n\s*$", html[opening:inner_end]), template_name


def test_card_geometry_matches_stylesheets() -> None:
    """折行预算依赖的版式数字必须与样式表一致。"""
    assert engine.CARD_WIDTH == card_geometry.CARD_WIDTH == 700
    for css_name in ("rich_card.css", "rule_card.css", "books_card.css"):
        css = engine._css_text(css_name)  # pyright: ignore[reportPrivateUsage]
        assert (
            f"padding: 22px {card_geometry.CARD_PADDING_X}px 16px "
            f"{card_geometry.CARD_PADDING_X}px;"
        ) in css, css_name
    rich = engine._css_text("rich_card.css")  # pyright: ignore[reportPrivateUsage]
    assert f"padding-left: {card_geometry.LIST_INDENT_EM}em" in rich


def test_budget_leaves_margin_below_content_width() -> None:
    """折行预算必须留出余量：越界会触发 litehtml 二次折行（孤字行）。"""
    content = card_geometry.content_width()
    assert card_geometry.flat_budget() < content
    assert card_geometry.list_budget() < card_geometry.flat_budget()
    # 余量至少 5%（字体度量差异的实测上界）
    assert card_geometry.flat_budget() <= content * 0.95
