"""卡片字体方案单测（离线）。

2026-09-27 实机取证：服务器上拉丁字母回退到 DejaVu Sans、汉字回退到
Noto Sans CJK JP，同一行两套字体导致字重与基线不一致。方案是字体栈**中文优先且
中西文同源**（Noto Sans CJK SC / 思源黑体自带完整拉丁），并留一个配置项供
服务器换字（留空用内置栈）。
"""

from __future__ import annotations

import asyncio

from nonebot_plugin_dnddicer.render import engine

CSS_FILES = ("rich_card.css", "rule_card.css", "books_card.css")
HTML_FILES = ("rich_card.html", "rule_card.html", "books_card.html")


def _render_template(name: str) -> str:
    """渲染任一卡片模板（传入全部模板变量，多余的会被 Jinja 忽略）。"""
    template = engine._get_env().get_template(name)  # pyright: ignore[reportPrivateUsage]
    return asyncio.run(
        template.render_async(
            title="T",
            category="C",
            body_html="<p>直</p>",
            blocks=[],
            sections=[],
            hint="",
            footer="",
            fallback_note="",
            source_path="p.htm",
            css=engine._css_text(name.replace(".html", ".css")),  # pyright: ignore[reportPrivateUsage]
            font_rule='.card { font-family: "Noto Sans CJK SC"; }',
        )
    )


def test_stylesheets_prefer_cjk_family_first() -> None:
    """三个样式表的字体栈都以中文字体开头（中西文同源）。"""
    for css_name in CSS_FILES:
        css = engine._css_text(css_name)  # pyright: ignore[reportPrivateUsage]
        assert css.index('"Noto Sans CJK SC"') < css.index('"Microsoft YaHei"'), css_name
        assert "sans-serif" in css, css_name


def test_font_rule_from_config(monkeypatch) -> None:
    """自定义字体家族：合法值注入一条 CSS 规则，非法值忽略。"""
    from nonebot_plugin_dnddicer.config import get_config

    config = get_config()
    monkeypatch.setattr(config, "dnddicer_query_image_font_family", "", raising=False)
    assert engine.font_rule() == ""

    monkeypatch.setattr(
        config,
        "dnddicer_query_image_font_family",
        '"Noto Sans CJK SC", sans-serif',
        raising=False,
    )
    assert engine.font_rule() == '.card { font-family: "Noto Sans CJK SC", sans-serif; }'

    monkeypatch.setattr(
        config,
        "dnddicer_query_image_font_family",
        "x; } body { display: none",
        raising=False,
    )
    assert engine.font_rule() == ""


def test_template_css_is_not_html_escaped() -> None:
    """模板渲染出的样式表不得被 autoescape 转义（2026-09-30 回归）。

    Jinja 的 autoescape 会把 CSS 里的 ``"`` 输出成 ``&#34;``，字体名随之变成
    ``&#34;Noto Sans CJK SC&#34;`` 这类查不到的家族，整个字体栈逐个失配、卡片回落到
    sans-serif（拉丁走 DejaVu Sans、汉字走 Noto Sans CJK JP），表现为日文字形与
    同一行中英文基线不一致；配置项注入的字体规则同样会失效。
    """
    for name in HTML_FILES:
        html = _render_template(name)
        assert "&#34;" not in html, name
        assert 'font-family: "Noto Sans CJK SC"' in html, name
        assert '.card { font-family: "Noto Sans CJK SC"; }' in html, name
