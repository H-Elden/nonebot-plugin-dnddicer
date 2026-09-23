# ---------------------------------------------------------------------------
# 移植自 nonebot-dicepp (https://github.com/pear-studio/nonebot-dicepp)
# Copyright (c) 2022 pear-studio, MIT License（许可全文见本项目 LICENSE）。
# 本地有意修订：2026-09-22 拦截「优势/劣势 后紧跟数字」的粘连输入（旧行为会
# 静默改写成 K120/KL120 的荒谬表达式，详见 _STICKY_ALIAS_PATTERN）。
# ---------------------------------------------------------------------------
"""
Roll Expression Preprocessor

Normalizes and expands user input before it reaches the Lark parser.
This handles two categories of transformations:

1. **Text normalization**: strip whitespace, uppercase, full-width → half-width
2. **Chinese alias expansion**: 优势/劣势/抗性/易伤 → standard dice notation

The preprocessor is engine-agnostic in principle, but lives inside ast_engine
so that every call through the AST engine automatically benefits from it.
"""

import re

from .._string_utils import to_english_str
from .errors import RollSyntaxError

#: 优势/劣势 后紧跟数字的粘连检测（2026-09-22 修订）：
#: 别名展开时 ``KL1`` 会与后续数字粘成 ``KL120``（``D劣势20+6`` →
#: ``2DKL120+6``），被引擎当作「保留最低 120 个」静默求值——结果值是两个骰
#: 求和，与 ``MIN{...}`` 展示自相矛盾。
#: 此类输入对应两种书写错误：面数错序（想写 d20劣势+6）或漏写 + 号
#: （想写 d劣势+2），直接拦截并给出可读指引，不再静默改写。
_STICKY_ALIAS_PATTERN = re.compile(r"(^|[^0-9])D[0-9]*?(?:优势|劣势)(?=[0-9])")


def preprocess(expression: str) -> str:
    """
    Preprocess a roll expression string before parsing.

    Applies text normalization and Chinese alias expansion in order:
    1. Strip leading/trailing whitespace
    2. Uppercase all characters
    3. Convert full-width characters to half-width (e.g. ＋→+, １→1)
    4. Expand Chinese dice aliases:
       - ``D20优势``  → ``2D20K1``   (advantage: roll 2, keep highest)
       - ``D20劣势``  → ``2D20KL1``  (disadvantage: roll 2, keep lowest)
       - ``...抗性``  → ``(...)/2``  (resistance: halve result)
       - ``...易伤``  → ``(...)*2``  (vulnerability: double result)

    Args:
        expression: Raw user input expression string

    Returns:
        Normalized expression ready for the Lark parser
    """
    result = expression.strip()
    result = result.upper()
    result = to_english_str(result)
    result = _expand_chinese_aliases(result)
    return result


def _expand_chinese_aliases(expression: str) -> str:
    """
    Expand Chinese-language dice aliases into standard notation.

    The expansion order matters:
    - 优势/劣势 are per-dice modifiers (applied first, inside the expression)
    - 抗性/易伤 are expression-level wrappers (applied last, wrap the whole expr)
    """
    result = expression

    # 粘连拦截（2026-09-22 修订，见模块级 _STICKY_ALIAS_PATTERN 说明）
    if _STICKY_ALIAS_PATTERN.search(result):
        raise RollSyntaxError(
            "优势/劣势 后不能直接跟数字：骰子面数请写在前面（如 d20劣势+6），"
            "加值请写成 +N（如 d劣势+2）",
            expression=result,
        )

    # Advantage: D20优势 → 2D20K1, D6优势 → 2D6K1
    # Matches an optional non-digit prefix, then D followed by optional digits, then 优势
    result = re.sub(
        r"(^|[^0-9])(D[0-9]*?)优势",
        lambda m: m.group(1) + "2" + m.group(2) + "K1",
        result,
    )

    # Disadvantage: D20劣势 → 2D20KL1
    result = re.sub(
        r"(^|[^0-9])(D[0-9]*?)劣势",
        lambda m: m.group(1) + "2" + m.group(2) + "KL1",
        result,
    )

    # Resistance: <expr>抗性 → (<expr>)/2  (must be at end of string)
    result = re.sub(
        r"^(.+)抗性$",
        lambda m: f"({m.group(1)})/2",
        result,
    )

    # Vulnerability: <expr>易伤 → (<expr>)*2  (must be at end of string)
    result = re.sub(
        r"^(.+)易伤$",
        lambda m: f"({m.group(1)})*2",
        result,
    )

    return result
