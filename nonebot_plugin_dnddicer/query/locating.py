"""条目级定位：把「章节页正文」切成「词条正文」。

背景：在线查询服务以**章节页**为粒度返回整页文本（如《玩家手册2024》法术按环阶
成页），而玩家要的是单个词条（如「镜影术」）。本模块在页面文本内定位词条边界：

1. **条目头定位**（首选）：页面内词条以 ``名称｜English``（2024 版，竖线分隔）或
   ``名称 English``（2014 版，空格分隔）开头；命中后截取到**下一个条目头**为止；
2. **命中段落回退**：找不到条目头时，取首个包含关键词的段落（上下以空行为界）；
3. **页面片段回退**：仍失败时给页面开头若干行（命令层会加「未精确定位」提示）。

定位失败不等于查询失败——页面片段对用户仍有价值，故三级回退都返回文本，
由 ``located`` 标记是否走了回退（供命令层提示）。

除命令层使用外，本模块的条目定位也用于**候选排序**（``query/source.py``）：
同样命中条目头时，正文充实的页面（真词条页）优先于只有一行索引条目的
列表页（如各类「速查表」——实测这类页面在服务端排序里往往靠前）。
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

#: 条目头行的最大长度（超过视为正文，避免把含英文的长句当条目头）
_HEAD_MAX_LENGTH = 60

#: 条目头中「名称」部分的最大长度
_HEAD_NAME_MAX = 30

#: 条目头英文名部分：必须是纯西文（字母开头，允许字母/数字/空格/常见符号）
_LATIN_TAIL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\s'’\-·:.,()]*$")

#: 名称部分：中文（含间隔号）或纯西文
_CJK_NAME_RE = re.compile(r"^[\u4e00-\u9fa5·]{1,30}$")

#: 「中文名 + 英文名」结构（分隔可有可无：``借机攻击Opportunity Attack``）
_CJK_LATIN_RE = re.compile(r"^([\u4e00-\u9fa5·]{1,30})\s*([A-Za-z].*)$")

#: 判断「上一块已收束」的行尾字符（条目头的前一行应满足其一，或为空行）
_BLOCK_END_CHARS = "。！？…；：”’）》」】"

#: 截断省略号
_ELLIPSIS = "…"

#: 词条正文的标准窗口（行数 / 字符数）。
#: 命令层据此分段发送（20 行一段、最多 3 段），排序层据此判断「正文是否充实」
#: （真词条页 vs 只有一行条目的索引页），两处共用同一口径。
BODY_MAX_LINES = 60
BODY_MAX_CHARS = 3600


def _normalize_lines(content: str) -> List[str]:
    """统一换行并按行拆分（去掉行尾空白，保留行内缩进）。"""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return [line.rstrip() for line in normalized.split("\n")]


def split_entry_head(line: str) -> Optional[Tuple[str, str]]:
    """把一行拆成条目头的 (名称, 英文名)；不是条目头返回 None。

    真实语料里条目头有三种形态（2026-09-25 实测《5e不全书》）：

    - ``镜影术｜Mirror Image``（2024 版，竖线分隔）；
    - ``借机攻击 Opportunity Attacks``（2014 版，空格分隔）；
    - ``借机攻击Opportunity Attack``（无分隔，中文名后直接接英文名）。

    判定要求「名称 + 纯西文尾」结构完整（尾段不得再出现中文/中文标点），
    否则像 ``火球术fireball，流星爆meteor swarm`` 这类**列表行**会被误判为
    条目头——实测踩过这个坑。
    """
    stripped = line.strip()
    if not stripped or len(stripped) > _HEAD_MAX_LENGTH:
        return None

    # ① 竖线分隔（2024 版）
    for delimiter in ("｜", "|"):
        if delimiter in stripped:
            name, _, tail = stripped.partition(delimiter)
            name = name.strip()
            tail = tail.strip()
            if (
                name
                and len(name) <= _HEAD_NAME_MAX
                and _LATIN_TAIL_RE.match(tail or "")
            ):
                return name, tail
            return None

    # ② 中文名 + 英文名（空格可有可无）
    match = _CJK_LATIN_RE.match(stripped)
    if match:
        name, tail = match.group(1), match.group(2).strip()
        if _LATIN_TAIL_RE.match(tail):
            return name, tail
    return None


def _closes_block(line: Optional[str]) -> bool:
    """判断某行是否「收束」了上一块：空行、或行尾为句末标点。

    条目头一定出现在块首——实测《贤者谏言2025》这类 Q&A 页面存在**硬换行**，
    句子被拆成多行后，某一行恰好形如 ``借机攻击Opportunity Attack``（句中被
    拆出的片段），若不看上下文就会被误判成条目头（实测踩坑，见诊断记录）。
    """
    if line is None:
        return True
    stripped = line.strip()
    if not stripped:
        return True
    return stripped[-1] in _BLOCK_END_CHARS


def head_at(lines: List[str], index: int) -> Optional[Tuple[str, str]]:
    """行 ``index`` 为**块首条目头**时返回 (名称, 英文名)，否则 None。"""
    if index < 0 or index >= len(lines):
        return None
    previous = lines[index - 1] if index > 0 else None
    if not _closes_block(previous):
        return None
    return split_entry_head(lines[index])


def _head_matches_keyword(lines: List[str], index: int, keyword: str):
    """判断第 ``index`` 行是否为**指定关键词**的块首条目头。

    返回 ``(是否名称精确, 是否名称前缀命中)`` 二元组。
    """
    head = head_at(lines, index)
    if head is None:
        return False, False
    name = head[0].casefold()
    wanted = keyword.casefold()
    if name == wanted:
        return True, True
    return False, name.startswith(wanted)


def _find_head_index(lines: List[str], keyword: str) -> Optional[int]:
    """在行列表中找到该关键词的条目头行号（名称精确优先，其次前缀命中）。"""
    prefix_index: Optional[int] = None
    for index in range(len(lines)):
        exact, matched = _head_matches_keyword(lines, index, keyword)
        if exact:
            return index
        if matched and prefix_index is None:
            prefix_index = index
    return prefix_index


def _slice_until_next_head(lines: List[str], start: int) -> List[str]:
    """从 start 行起截取，直到出现下一个块首条目头（不含）或文本结束。"""
    collected: List[str] = []
    for index in range(start, len(lines)):
        if head_at(lines, index) is not None:
            break
        collected.append(lines[index])
    return collected


def _find_paragraph(lines: List[str], keyword: str) -> Optional[List[str]]:
    """找到关键词命中的段落（上下以空行为界），返回其行列表。

    两级：① 段落首行以关键词开头（小标题式段落，优先）；② 首个包含关键词的
    段落。均跳过**页面首行**（章节页首行通常是页面标题本身）与条目头行。
    """
    keyword_lower = keyword.lower()
    fallback: Optional[List[str]] = None
    for index, line in enumerate(lines):
        if index == 0 or head_at(lines, index) is not None:
            continue
        if keyword_lower not in line.lower():
            continue
        begin = index
        while begin > 0 and lines[begin - 1].strip():
            begin -= 1
        end = index
        while end + 1 < len(lines) and lines[end + 1].strip():
            end += 1
        paragraph = lines[begin : end + 1]
        if lines[begin].strip().lower().startswith(keyword_lower):
            return paragraph
        if fallback is None:
            fallback = paragraph
    return fallback


def _truncate(lines: List[str], max_lines: int, max_chars: int) -> str:
    """按行/字符上限截断，并去掉首尾空行。"""
    # 去首部空行
    while lines and not lines[0].strip():
        lines = lines[1:]
    # 去尾部空行
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    if not lines:
        return ""

    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
        truncated = True
    if truncated:
        text += _ELLIPSIS
    return text


def locate_entry(
    content: str,
    keyword: str,
    *,
    max_lines: int = BODY_MAX_LINES,
    max_chars: int = BODY_MAX_CHARS,
) -> Tuple[str, bool]:
    """在页面正文中定位关键词对应的词条正文。

    Args:
        content: 页面整页文本（查询服务响应 ``content`` 字段）。
        keyword: 用户输入的关键词。
        max_lines: 返回正文的最大行数。
        max_chars: 返回正文的最大字符数。

    Returns:
        (正文文本, 是否精确定位到条目头)；Text 为空串表示页面无可用内容。
    """
    lines = _normalize_lines(content)
    head_index = _find_head_index(lines, keyword)
    if head_index is not None:
        body = _slice_until_next_head(lines, head_index + 1)
        text = _truncate(body, max_lines, max_chars)
        if text:
            return text, True
        # 条目头下无正文时退回该行本身
        return _truncate([lines[head_index]], max_lines, max_chars), True

    # 关键词即页面标题（首行）时，页面开头就是该词条的正文
    if lines and lines[0].strip().lower().startswith(keyword.lower()):
        return _truncate(lines, max_lines, max_chars), False

    paragraph = _find_paragraph(lines, keyword)
    if paragraph:
        return _truncate(paragraph, max_lines, max_chars), False

    return _truncate(lines, max_lines, max_chars), False
