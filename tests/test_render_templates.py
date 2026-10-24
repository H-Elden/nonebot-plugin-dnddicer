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


def _render_char(view) -> str:
    """渲染角色卡图模板（需要可选的渲染依赖）。"""
    template = engine._get_env().get_template("char_card.html")  # pyright: ignore[reportPrivateUsage]
    return template.render(
        view=view,
        css=engine._css_text("char_card.css"),  # pyright: ignore[reportPrivateUsage]
        font_rule='.card { font-family: "Noto Sans CJK SC"; }',
    )


def test_char_card_template_renders_with_production_env() -> None:
    """单页角色卡模板可渲染完整 HTML，且不引用任何外部资源。"""
    pytest.importorskip("jinja2", reason="模板渲染需要可选的 [render] 依赖（含 Jinja2）")
    from nonebot_plugin_dnddicer.character.card_view import build_card_view
    from nonebot_plugin_dnddicer.character.services import gen_template_char

    html = _render_char(build_card_view(gen_template_char()))
    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert 'class="sheet card"' in html
    for title in (
        "武器与伤害",
        "种族特性",
        "职业特性",
        "专长",
        "限定资源",
        "魔法物品",
        "装备",
        "背景与个性",
        "戏法与已准备法术",
    ):
        assert f'<div class="panel-title">{title}</div>' in html, title
    assert "伊瑟兰·晨星" in html
    assert "生命值" in html and "死亡豁免" in html and "英雄激励" in html
    assert "1级" in html and "5级" in html
    assert "战法师魔杖 +1" in html and "此外，你在进行法术攻击检定时无视半身掩护。" in html
    assert "http://" not in html and "https://" not in html
    assert "&#34;" not in html


def test_char_card_story_keeps_paragraph_lines() -> None:
    """多段故事按行渲染，换行不丢（卡面「背景故事」面板）。"""
    pytest.importorskip("jinja2", reason="模板渲染需要可选的 [render] 依赖（含 Jinja2）")
    from nonebot_plugin_dnddicer.character.card_view import build_card_view
    from nonebot_plugin_dnddicer.character.services import gen_template_char

    html = _render_char(build_card_view(gen_template_char()))
    assert html.count('class="story-line"') == 3
    assert "此后伊瑟兰离开书斋" in html


def test_char_card_layout_panel_order() -> None:
    """右栏：武器表 → 两列（左限定资源/装备/魔法物品/钱币/背景与个性，
    右专长/种族特性/职业特性）→ 背景故事；熟练与语言、战斗记录留在左栏。"""
    pytest.importorskip("jinja2", reason="模板渲染需要可选的 [render] 依赖（含 Jinja2）")
    from nonebot_plugin_dnddicer.character.card_view import build_card_view
    from nonebot_plugin_dnddicer.character.services import gen_template_char

    html = _render_char(build_card_view(gen_template_char()))
    left_at = html.index('<td class="left-col">')
    right_at = html.index('<td class="right-col">')
    order = (
        "武器与伤害",
        "限定资源",
        "装备",
        "魔法物品",
        "钱币",
        "背景与个性",
        "专长",
        "种族特性",
        "职业特性",
        "背景故事",
    )
    positions = [
        html.index(f'<div class="panel-title">{title}</div>') for title in order
    ]
    assert positions == sorted(positions), positions
    # 两条表格留在左栏，装备与背景与个性都进了右栏
    for title in ("熟练与语言", "战斗记录"):
        at = html.index(f'<div class="panel-title">{title}</div>')
        assert left_at < at < right_at, title
    assert html.index('<div class="panel-title">装备</div>') > right_at
    assert html.index('<div class="panel-title">背景与个性</div>') > right_at
    # 两个子列：左列是资源/装备/魔法物品/钱币/背景与个性，右列是专长/特性
    left_sub = html[html.index('<td class="sub-col sub-col-left">') : positions[6]]
    for title in ("限定资源", "装备", "魔法物品", "钱币", "背景与个性"):
        assert f'<div class="panel-title">{title}</div>' in left_sub, title
    for title in ("专长", "种族特性", "职业特性"):
        assert f'<div class="panel-title">{title}</div>' not in left_sub, title


def test_char_card_items_two_columns() -> None:
    """装备清单两列排版（每行两个格，奇数条补空格）。"""
    pytest.importorskip("jinja2", reason="模板渲染需要可选的 [render] 依赖（含 Jinja2）")
    from nonebot_plugin_dnddicer.character.card_view import build_card_view
    from nonebot_plugin_dnddicer.character.services import gen_template_char

    html = _render_char(build_card_view(gen_template_char()))
    assert '<table class="item-grid">' in html
    assert '<td class="item-line">法术书</td><td class="item-line">长棍</td>' in html
    # 示例卡 9 件装备 → 5 行 × 2 格
    assert html.count('class="item-line"') == 10


def test_char_card_background_pairs_two_columns() -> None:
    """背景与个性整行两列：每行两对键值，与背景故事同宽。"""
    pytest.importorskip("jinja2", reason="模板渲染需要可选的 [render] 依赖（含 Jinja2）")
    from nonebot_plugin_dnddicer.character.card_view import build_card_view
    from nonebot_plugin_dnddicer.character.services import gen_template_char

    html = _render_char(build_card_view(gen_template_char()))
    assert '<table class="bg-grid">' in html
    assert (
        '<td><span class="bg-key">背景</span>智者</td>'
        '<td><span class="bg-key">阵营</span>中立善良</td>'
    ) in html
    assert html.count('<span class="bg-key">') == 7
    # 七项背景 → 四行（末行右侧补空格）
    assert html.count("<tr><td><span class=\"bg-key\">") == 4


def test_char_card_template_hides_empty_panels() -> None:
    """空段不画空面板，但页眉与 HP 五行保留。"""
    pytest.importorskip("jinja2", reason="模板渲染需要可选的 [render] 依赖（含 Jinja2）")
    from nonebot_plugin_dnddicer.character.card_view import build_card_view
    from nonebot_plugin_dnddicer.character.models import DNDCharacter

    empty = DNDCharacter(group_id="g", user_id="u", name="空卡", is_init=True)
    html = _render_char(build_card_view(empty))
    for title in (
        "武器与伤害",
        "种族特性",
        "职业特性",
        "专长",
        "限定资源",
        "魔法物品",
        "装备",
        "背景与个性",
        "戏法与已准备法术",
    ):
        assert f'<div class="panel-title">{title}</div>' not in html, title
    assert "生命值" in html and "英雄激励" in html
    assert 'class="weapon-panel"' not in html


def test_char_card_panels_follow_content() -> None:
    """只有装备时画装备面板；只有种族特性时画种族特性面板。"""
    pytest.importorskip("jinja2", reason="模板渲染需要可选的 [render] 依赖（含 Jinja2）")
    from nonebot_plugin_dnddicer.character.card_view import build_card_view
    from nonebot_plugin_dnddicer.character.models import DNDCharacter

    items_only = DNDCharacter(group_id="g", user_id="u", name="测试", is_init=True)
    items_only.items = ["火把x3"]
    html = _render_char(build_card_view(items_only))
    assert '<div class="panel-title">装备</div>' in html
    assert '<div class="panel-title">种族特性</div>' not in html

    traits_only = DNDCharacter(group_id="g", user_id="u", name="测试", is_init=True)
    traits_only.race_traits = ["黑暗视觉:60 尺内微光"]
    html = _render_char(build_card_view(traits_only))
    assert '<div class="panel-title">种族特性</div>' in html
    assert '<div class="panel-title">装备</div>' not in html

def test_char_card_stylesheet_geometry() -> None:
    """角色卡图样式：940 单页、146 方框、表格布局、字体栈中文优先。"""
    css = engine._css_text("char_card.css")  # pyright: ignore[reportPrivateUsage]
    assert engine.CHAR_CARD_WIDTH == 940
    assert "padding: 14px 16px 10px 16px;" in css
    assert "width: 146px;" in css and "height: 146px;" in css
    assert "width: 158px;" in css
    assert "table-layout: fixed;" in css
    assert css.index('"Noto Sans CJK SC"') < css.index('"Microsoft YaHei"')
    assert "Georgia" not in css
    assert ".story-line {" in css and "text-indent: 2em;" in css
    assert "white-space: pre-wrap;" in css
    assert ".m-tag" in css and ".bg-grid" in css and ".item-grid" in css
    # 故事折行预算与样式表的故事区宽度同源
    assert card_geometry.CHAR_CARD_RIGHT_COL_WIDTH == 679
    assert card_geometry.STORY_FONT_SIZE == 10.5
    assert card_geometry.story_budget() < (
        card_geometry.CHAR_CARD_RIGHT_COL_WIDTH
        - (card_geometry.STORY_PANEL_BORDER + card_geometry.STORY_PADDING_X) * 2
    )


def test_budget_leaves_margin_below_content_width() -> None:
    """折行预算必须留出余量：越界会触发 litehtml 二次折行（孤字行）。"""
    content = card_geometry.content_width()
    assert card_geometry.flat_budget() < content
    assert card_geometry.list_budget() < card_geometry.flat_budget()
    # 余量至少 5%（字体度量差异的实测上界）
    assert card_geometry.flat_budget() <= content * 0.95


def test_char_card_inspiration_states_and_label() -> None:
    """激励行：未记录画「—」、无画空框、有画勾选框；2014 称呼为「激励」。"""
    pytest.importorskip("jinja2", reason="模板渲染需要可选的 [render] 依赖（含 Jinja2）")
    from nonebot_plugin_dnddicer.character.card_view import build_card_view
    from nonebot_plugin_dnddicer.character.models import DNDCharacter

    character = DNDCharacter(
        group_id="g", user_id="u", name="空卡", is_init=True
    )
    html = _render_char(build_card_view(character, version_2024=False))
    assert '<td class="hp-label">激励</td><td>—</td>' in html

    character.progress = {"激励": "无"}
    html = _render_char(build_card_view(character, version_2024=False))
    assert '<td class="hp-label">激励</td><td><span class="box"></span></td>' in html

    character.progress = {"激励": "有"}
    html = _render_char(build_card_view(character, version_2024=True))
    assert (
        '<td class="hp-label">英雄激励</td>'
        '<td><span class="box filled"></span></td>' in html
    )
