"""卡片模板与版式几何的不变量（离线，不需要渲染依赖）。

覆盖两条纪律（2026-09-27 实机问题修复后固化）：

1. **容器内不留模板空白**：``rich_card.css`` 的 ``.content`` 设了
   ``white-space: pre-wrap``，模板自身的换行/缩进会被当成内容各占一个空行
   （实测每张卡多出 140+px 空白带），三个模板统一按「容器内无裸空白」写；
2. **版式常量与样式表一致**：卡片宽、左右内边距、列表缩进在
   ``card_geometry`` 与样式表里必须是同一组数字（折行预算据此推算，改一边就错位）。

第 1 条断言在**模板源码**上（不需渲染依赖），另有一条装了可选 ``[render]``
依赖才跑的真实渲染冒烟，保证模板在 CI 与本地都被检查到。
"""

from __future__ import annotations

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


def _template_text(name: str) -> str:
    """模板源码文本（不经 Jinja，因而与是否装了可选渲染依赖无关）。"""
    return (engine._TEMPLATE_DIR / name).read_text(  # pyright: ignore[reportPrivateUsage]
        encoding="utf-8"
    )


def _content_inner(html: str) -> str:
    """取 ``<div class="content">`` 与其**配对** ``</div>`` 之间的片段。

    容器内还有嵌套 ``<div>``（note / row / para 等），按「第一个 ``</div>``」截断
    会停在嵌套元素上，故用深度计数找配对闭合标签。
    """
    marker = '<div class="content">'
    opening = html.index(marker) + len(marker)
    depth = 1
    cursor = opening
    while depth:
        open_at = html.find("<div", cursor)
        close_at = html.find("</div>", cursor)
        assert close_at >= 0, '<div class="content"> 没有配对闭合标签'
        if 0 <= open_at < close_at:
            depth += 1
            cursor = open_at + len("<div")
        else:
            depth -= 1
            if depth == 0:
                return html[opening:close_at]
            cursor = close_at + len("</div>")
    raise AssertionError("不可达：深度计数未收敛")


def _render(template_name: str, css_name: str, context: dict) -> str:
    """用**生产 Jinja 环境**同步渲染模板（需要可选的渲染依赖）。"""
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
    """正文容器开标签之后、配对闭合标签之前不得有模板换行/缩进（pre-wrap 下会变成空行）。

    查的是**模板源码**：容器里的空白是模板自己写出来的，与渲染依赖装没装无关
    （2026-09-30 修订：原实现断言在 Jinja 渲染结果上，而 Jinja2 随可选依赖
    ``[render]`` 提供，CI 不装该可选依赖时会 ModuleNotFoundError，纪律在 CI 失守）。
    """
    inner = _content_inner(_template_text(template_name))
    assert inner, template_name
    assert not inner[0].isspace(), f"{template_name}: 容器开标签后紧跟模板空白"
    assert not inner[-1].isspace(), f"{template_name}: 容器闭合标签前还有模板空白"


def test_templates_render_with_production_env() -> None:
    """三个模板能被生产 Jinja 环境渲染出完整 HTML（装了可选渲染依赖时才跑）。"""
    pytest.importorskip("jinja2", reason="模板渲染需要可选的 [render] 依赖（含 Jinja2）")
    for template_name, css_name, context in CARDS:
        html = _render(template_name, css_name, context)
        assert html.lstrip().startswith("<!DOCTYPE html>"), template_name
        assert '<div class="content">' in html, template_name


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
