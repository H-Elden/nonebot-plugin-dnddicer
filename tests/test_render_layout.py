"""渲染纯函数单测：正文分块与避头尾折行（离线，无需渲染依赖）。

覆盖：
- 分块：sub / label / lead / para 四类判定、段落合并、空行处理；
- 折行：行首不出禁则标点、行尾不出开括号、西文/数字整词不拆、
  宽度预算内不产生超长行、空串与超长无空格串兜底。
"""

from __future__ import annotations

from nonebot_plugin_dnddicer.render.layout import (
    prepare_blocks,
    to_blocks,
    wrap_cjk,
)

#: 一张仿真实法术词条的正文
SPELL_BODY = """二环 幻术
施法时间：1 动作
距离：自身
成分：V、S
持续时间：1 分钟
三个镜像出现在你周围，用于迷惑攻击者。

升环施法。使用三环或更高的法术位施放时，法术位每高一环，镜像数量就增加一个。"""


# ── 分块 ────────────────────────────────────────────────────────────────


def test_to_blocks_types():
    """四类块判定：子标题 / 标签 / 句首强调 / 普通段落。"""
    blocks = to_blocks(SPELL_BODY)
    kinds = [b["type"] for b in blocks]
    assert kinds == ["sub", "label", "label", "label", "label", "para", "lead"]
    assert blocks[0]["text"] == "二环 幻术"
    assert blocks[1]["text"] == "施法时间：1 动作"
    assert blocks[6]["text"].startswith("升环施法。")


def test_to_blocks_merges_paragraph_lines():
    """段内连续行合并为一个段落块（保留原换行）。"""
    blocks = to_blocks("这是正文的第一行，\n它还没有结束，\n到这里才收束。\n\n新段落在这里。")
    assert len(blocks) == 2
    assert blocks[0]["type"] == "para"
    assert blocks[0]["text"] == "这是正文的第一行，\n它还没有结束，\n到这里才收束。"
    assert blocks[1]["type"] == "para"
    assert blocks[1]["text"] == "新段落在这里。"


def test_to_blocks_table_row_not_sub():
    """纯数字/符号行（表格行）不判子标题，归普通段落。"""
    blocks = to_blocks("8 0 12 4\n3 -4 12-13 +1\n\n正文收束。")
    assert blocks[0]["type"] == "para"
    assert blocks[0]["text"] == "8 0 12 4\n3 -4 12-13 +1"


def test_to_blocks_special_lines_only_at_block_start():
    """块中行不再判定特殊类型：正文句子里的「xx：」不会被当标签。"""
    blocks = to_blocks("这是一段正文开头，\n之后出现 说明：这里不是标签行。")
    assert len(blocks) == 1
    assert blocks[0]["type"] == "para"


def test_to_blocks_skips_empty_and_handles_crlf():
    """空行只作分段；CRLF 归一化；纯空白与空串不产生块。"""
    assert to_blocks("") == []
    assert to_blocks("\n\n  \n") == []
    blocks = to_blocks("甲\r\n\r\n乙")
    assert [b["text"] for b in blocks] == ["甲", "乙"]


def test_to_blocks_sub_not_label():
    """含冒号的行归 label（不是 sub）；短句无句末标点归 sub。"""
    blocks = to_blocks("优势\n持续时间：1 分钟")
    assert [b["type"] for b in blocks] == ["sub", "label"]


def test_to_blocks_long_first_line_is_para():
    """过长首行不判子标题（超过长度上限），归普通段落。"""
    long_line = "这是一行很长的正文内容，长到超过了子标题的长度上限，因此它应当被当作普通段落来处理。"
    blocks = to_blocks(long_line)
    assert blocks[0]["type"] == "para"


def test_to_blocks_long_lead_is_para():
    """句首强调的是短引导句：普通长句（首句很长）不加粗，仍为段落。"""
    blocks = to_blocks("三个镜像出现在你周围，用于迷惑攻击者。它们会模仿你的动作。")
    assert blocks[0]["type"] == "para"


def test_prepare_blocks_splits_prefix():
    """渲染入参：label/lead 拆出加粗前缀，sub/para 前缀为空串。"""
    prepared = prepare_blocks(SPELL_BODY)
    by_type = {}
    for block in prepared:
        by_type.setdefault(block["type"], []).append(block)
    assert by_type["label"][0]["prefix"] == "施法时间："
    assert by_type["label"][0]["text"] == "1 动作"
    assert by_type["lead"][0]["prefix"] == "升环施法。"
    assert by_type["lead"][0]["text"].startswith("使用三环")
    assert by_type["sub"][0]["prefix"] == ""
    assert by_type["para"][0]["prefix"] == ""


# ── 折行 ────────────────────────────────────────────────────────────────


def _width(text: str, font_size: int = 16) -> float:
    from nonebot_plugin_dnddicer.render.layout import _text_width

    return _text_width(text, font_size)


def test_wrap_short_text_untouched():
    """未超宽的文本原样返回（含空串与纯换行）。"""
    assert wrap_cjk("短文本") == "短文本"
    assert wrap_cjk("") == ""
    assert wrap_cjk("甲\n乙") == "甲\n乙"


def test_wrap_within_budget():
    """折行后每行都在宽度预算内（中文长文）。"""
    text = (
        "这是一段很长的中文文本，用来验证折行功能是否把每一行都控制在"
        "宽度预算之内；如果超宽就会溢出卡片边界，那样就不好看了。"
    )
    wrapped = wrap_cjk(text, width_em=20, font_size=16)
    lines = wrapped.split("\n")
    assert len(lines) > 1
    for line in lines:
        assert _width(line) <= 20 * 16


def test_wrap_no_forbidden_line_start():
    """行首不出现禁则标点（。，、；：！？）」等）。"""
    text = (
        "折行时不能让标点跑到行首，比如句号、逗号、顿号、分号、冒号、"
        "感叹号、问号、右括号等等都要避免，否则排版会很难看。"
    )
    wrapped = wrap_cjk(text, width_em=14, font_size=16)
    forbidden = set("。，、；：！？）」』】》…·")
    for line in wrapped.split("\n"):
        assert line[0] not in forbidden, f"行首出现禁则标点：{line!r}"


def test_wrap_no_forbidden_line_end():
    """行尾不出现开括号（（「『【《）——它应随下一行内容一起下移。"""
    text = "图示说明（这是一个很长的括号内容，需要跟着括号一起换行才行）。" * 2
    wrapped = wrap_cjk(text, width_em=12, font_size=16)
    forbidden = set("（「『【《")
    for line in wrapped.split("\n"):
        assert line[-1] not in forbidden, f"行尾出现开括号：{line!r}"


def test_wrap_keeps_latin_words_whole():
    """西文/数字整词不拆：单词与数字不被断行拆开。"""
    text = "Fireball 是一种三环塑能法术 damage 8d6 点火焰伤害 Scorching Ray 是二环法术。"
    wrapped = wrap_cjk(text, width_em=14, font_size=16)
    joined = wrapped.replace("\n", "")
    assert "Fireball" in joined and "Scorching" in joined and "8d6" in joined
    # 每一行内部不得出现「半个单词」：以空格切分后，首尾词应与原文词一致
    words = set(text.replace("。", " ").split())
    for line in wrapped.split("\n"):
        stripped = line.strip()
        for token in stripped.split():
            token_clean = token.strip("，。、；：！？（）")
            if token_clean and token_clean[0].isascii() and token_clean[0].isalpha():
                assert any(w.startswith(token_clean) or token_clean.startswith(w) for w in words), (
                    f"疑似拆词：{token_clean!r}"
                )


def test_wrap_long_unbroken_token_fallback():
    """超长无空格串兜底：仍按宽度硬切，不会死循环或丢字符。"""
    token = "A" * 200
    wrapped = wrap_cjk(token, width_em=10, font_size=16)
    lines = wrapped.split("\n")
    assert len(lines) > 1
    assert "".join(lines) == token
    for line in lines:
        assert _width(line) <= 10 * 16


def test_wrap_preserves_newlines_and_chars():
    """多段文本：原换行保留，字符无丢失（折行只增不删）。"""
    text = "第一段内容需要折行处理。\n\n第二段也要折行处理，内容更长一些以便触发折行。"
    wrapped = wrap_cjk(text, width_em=12, font_size=16)
    assert wrapped.replace("\n", "") == text.replace("\n", "")
