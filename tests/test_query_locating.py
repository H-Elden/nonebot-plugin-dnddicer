"""文字模式显示用的「段内合并」单测（离线）。

检索服务的整页正文多数条目已是完整行，少数条目仍带源文档的硬折行
（实测「…操纵距离你 / 60 / 尺内…」）。合并判据取最保守的信号：**上一行以空格
结尾**（在空白处断行）且两行都不是结构行（标签 / 条目头 / 列表项）。
"""

from __future__ import annotations

from nonebot_plugin_dnddicer.query import locating


def test_join_merges_wrap_at_space() -> None:
    """尾随空格的断行合并成一段（保留中文/数字间的既有空格风格）。"""
    text = "在你的每个回合内，你可以使用一个附赠动作操纵距离你 \n60 \n尺内的生物。"
    assert locating.join_wrapped_lines(text) == (
        "在你的每个回合内，你可以使用一个附赠动作操纵距离你 60 尺内的生物。"
    )


def test_join_keeps_label_lines() -> None:
    """标签行不与正文合并（站点正文里标签是独立行）。"""
    text = "施法时间：动作\n施法距离：60尺\n你打断正在施法的生物。"
    assert locating.join_wrapped_lines(text) == text


def test_join_keeps_lines_without_wrap_signal() -> None:
    """没有尾随空格就不合并（避免把刻意分行的内容粘成一行）。"""
    text = "第1行\n第2行\n第3行"
    assert locating.join_wrapped_lines(text) == text


def test_join_keeps_entry_head_and_bullets() -> None:
    """条目头与列表项自成一块，不参与合并（行尾空白另行折叠）。"""
    text = "火球术｜Fireball \n· 一项 \n· 二项"
    assert locating.join_wrapped_lines(text) == "火球术｜Fireball\n· 一项\n· 二项"


def test_join_keeps_blank_line_separation() -> None:
    """空行分段保留（段落之间仍空一行）。"""
    text = "第一段 \n续行。\n\n第二段。"
    assert locating.join_wrapped_lines(text) == "第一段续行。\n\n第二段。"


def test_join_does_not_change_text_content() -> None:
    """合并只动换行与空白，不改动任何文字。"""
    text = "升环施法。使用 \n法术位每高一环，伤害增加 1d6。"
    joined = locating.join_wrapped_lines(text)
    strip = lambda value: "".join(value.split())  # noqa: E731
    assert strip(joined) == strip(text)
