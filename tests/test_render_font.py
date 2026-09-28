"""卡片字体方案单测（离线）。

2026-09-27 实机取证：服务器上拉丁字母回退到 DejaVu Sans、汉字回退到
Noto Sans CJK JP，同一行两套字体导致字重与基线不一致。方案是字体栈**中文优先且
中西文同源**（Noto Sans CJK SC / 思源黑体自带完整拉丁），并留一个配置项供
服务器换字（留空用内置栈）。
"""

from __future__ import annotations

from nonebot_plugin_dnddicer.render import engine

CSS_FILES = ("rich_card.css", "rule_card.css", "books_card.css")


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
