"""纯函数：正文分块与避头尾折行（无第三方依赖，易测）。

分块规则（仿 5e 不全书站点正文结构，四类）：
- ``sub``：子标题行（如「三环 塑能」「优势」→ 站点同款紫色加粗）
- ``label``：标签行（如「施法时间：1 动作」→ 冒号前加粗）
- ``lead``：句首强调（如「升环施法。…」→ 句首加粗）
- ``para``：普通段落

避头尾折行：litehtml 无避头尾规则，自动折行会偶发行首标点（如一行以「。」
开头）。渲染前用 Python 按宽度折行、行以 ``pre-wrap`` 呈现，规避该问题；
超预算的长行仍由 litehtml 自动折行兜底。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Tuple

#: 行首禁则标点（不允许出现在行首）
_LINE_START_FORBIDDEN = set("。，、；：！？）」』】》…·")

#: 行尾禁则标点（不允许出现在行尾）
_LINE_END_FORBIDDEN = set("（「『【《")

#: 标签行：冒号前为标签名（如「施法时间：」「距离：」）
_LABEL_RE = re.compile(r"^([^：:]{1,12}[：:])\s*(.*)$")

#: 句首强调：短引导句 + 句末标点（如「升环施法。」），后接正文。
#: 长度与逗号双重限制——避免把普通段落的首个长句也当强调（站点上真正加粗的
#: 只有这类短语式引导，如法术条的「升环施法。」）
_LEAD_RE = re.compile(r"^([^。！？；，、]{1,10}[。！？；])\s*(.*)$")

#: 子标题行最大长度（超过视为普通段落）
_SUB_MAX_LENGTH = 40

#: 子标题行不得出现的行尾字符（句末标点/冒号 → 更像正文或标签）
_SUB_BANNED_TAIL = set("。！？…；：，、")


def to_blocks(body: str) -> List[Dict[str, str]]:
    """把正文拆分为分块列表。

    每块为 ``{"type": "sub"|"label"|"lead"|"para", "text": str}``。
    空行分段；连续非空行合并为同一段落（段落内保留原换行）。
    """
    blocks: List[Dict[str, str]] = []
    para_lines: List[str] = []

    def flush() -> None:
        if para_lines:
            blocks.append({"type": "para", "text": "\n".join(para_lines)})
            para_lines.clear()

    for raw_line in body.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            flush()
            continue

        # 三类特殊行只在「段首」（前面为空行或尚未开始段落）判定，
        # 段中的行一律并入当前段落——避免把正文句子的后半截误判。
        if not para_lines:
            kind = _classify(line)
            if kind is not None:
                blocks.append({"type": kind, "text": line})
                continue

        para_lines.append(line)

    flush()
    return blocks


def _classify(line: str) -> str | None:
    """判断段首行的类型；普通正文返回 None。"""
    # 子标题：短、无句末标点、非标签、非纯数字/符号行（表格行不做标题）
    if (
        len(line) <= _SUB_MAX_LENGTH
        and line[-1] not in _SUB_BANNED_TAIL
        and not _LABEL_RE.match(line)
        and _has_word_char(line)
    ):
        return "sub"
    if _LABEL_RE.match(line):
        return "label"
    lead = _LEAD_RE.match(line)
    if lead and lead.group(2):
        return "lead"
    return None


def _has_word_char(line: str) -> bool:
    """行内是否有文字字符（中日韩或拉丁字母）——纯数字/符号行（如表格行
    ``8 0 12 4``）不判子标题。"""
    return any(c.isalpha() for c in line)


def prepare_blocks(body: str) -> List[Dict[str, str]]:
    """分块 + 折行（渲染入参，供模板直接消费）。

    每块键：``type`` / ``prefix``（加粗前缀，label 与 lead 用，其余为空串）/
    ``text``（余下正文，已折行）。标签与句首强调的前后缀分别折行——前缀通常
    很短，不会跨行；正文部分单独按宽度预算折行。
    """
    out: List[Dict[str, str]] = []
    for block in to_blocks(body):
        kind = block["type"]
        raw = block["text"]
        if kind == "label":
            prefix, rest = _split_label(raw)
        elif kind == "lead":
            prefix, rest = _split_lead(raw)
        else:
            prefix, rest = "", raw
        out.append({"type": kind, "prefix": prefix, "text": wrap_cjk(rest)})
    return out


def _split_label(text: str) -> Tuple[str, str]:
    """拆出标签行的 (标签名含冒号, 余下内容)；非标签行返回 ("", text)。"""
    match = _LABEL_RE.match(text)
    if match:
        return match.group(1), match.group(2)
    return "", text


def _split_lead(text: str) -> Tuple[str, str]:
    """拆出句首强调的 (首句含标点, 余下内容)；不匹配返回 ("", text)。"""
    match = _LEAD_RE.match(text)
    if match and match.group(2):
        return match.group(1), match.group(2)
    return "", text


def _char_width(char: str, font_size: int) -> float:
    """估算单字符宽度（px）：全角 1em、半角 0.5em。"""
    if unicodedata.east_asian_width(char) in ("F", "W"):
        return float(font_size)
    return font_size * 0.5


def _text_width(text: str, font_size: int) -> float:
    """估算文本渲染宽度（px）。"""
    return sum(_char_width(c, font_size) for c in text)


def wrap_cjk(text: str, *, width_em: float = 39, font_size: int = 16) -> str:
    """按宽度折行，避免行首标点、行尾开括号与西文/数字拆词。

    Args:
        text: 待折行文本（可含换行——原换行保留）。
        width_em: 可用宽度（em）。
        font_size: 字号（px），用于 em→px 换算。

    Returns:
        折行后文本（行以 ``\\n`` 分隔，渲染时用 ``white-space: pre-wrap``）。
    """
    max_width = width_em * font_size
    out: List[str] = []
    for segment in text.split("\n"):
        if not segment:
            out.append("")
            continue
        out.extend(_wrap_line(segment, max_width, font_size))
    return "\n".join(out)


def _wrap_line(line: str, max_width: float, font_size: int) -> List[str]:
    """单行按宽度折行（贪心 + 避头尾 + 整词保护）。"""
    if _text_width(line, font_size) <= max_width:
        return [line]

    lines: List[str] = []
    start = 0
    total = len(line)
    while start < total:
        # 贪心累积到超宽为止
        width = 0.0
        end = start
        while end < total:
            w = _char_width(line[end], font_size)
            if width + w > max_width:
                break
            width += w
            end += 1
        if end == start:  # 单字符即超宽（极端宽度设置）→ 强制取一个
            end = start + 1

        # 行尾禁则：开括号不留在行尾（回退一个字符，让它随下行一起走）
        while end > start + 1 and line[end - 1] in _LINE_END_FORBIDDEN:
            end -= 1

        # 行首禁则：下一行首是禁则标点时，把它拉到本行（宁可略超宽）
        if end < total and line[end] in _LINE_START_FORBIDDEN and end > start:
            end -= 1

        # 西文/数字整词：断点落在词中时回退到词首
        if start < end < total:
            word_start = _word_start(line, start, end)
            if word_start > start:
                end = word_start

        lines.append(line[start:end])
        start = end

    return lines


def _word_start(line: str, begin: int, end: int) -> int:
    """断点 ``end`` 落在西文/数字词中时返回词首，否则原样返回。"""
    if not (line[end].isascii() and line[end].isalnum() and end > begin):
        return end
    if not (line[end - 1].isascii() and line[end - 1].isalnum()):
        return end
    k = end - 1
    while k > begin and line[k - 1].isascii() and line[k - 1].isalnum():
        k -= 1
    return k
