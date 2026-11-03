"""法术战斗结算：攻击加值、豁免 DC、伤害段与升环加骰。

2026-11-02 新增。本模块只做纯计算与校验，不依赖命令层，供 ``.施法`` 与
``.X攻击`` / ``.X伤害`` 共用。法术的战斗数据全部来自角色卡 ``$法术$`` 段；
头键 ``法术攻击`` / ``豁免DC`` 作为条目未写时的默认值。

边界：

- 本期只自动应用"加骰"形态的升环（``+1d6`` / ``+1d4+1`` / ``+1d10钝击``）；
  ``+1束`` / ``+1枚`` / ``+1目标`` 与自由文本只返回提示，由玩家手动处理；
- 不判 AC、不掷目标豁免、不结算 HP；
- 伤害段已按 §5.2 校验过多段格式，这里只做乘法与拼接。
"""

from __future__ import annotations

import re
from typing import List, NamedTuple, Optional, Sequence, Tuple

from ..engine.roll.ast_engine.adapter import exec_roll_exp_unified
from ..engine.roll.result import RollResult
from ..engine.roll.roll_utils import RollDiceError
from .models import DNDCharacter, SpellDamagePart, SpellEntry
from .services import (
    apply_critical_to_damage,
    normalize_damage_type,
    split_spell_shots_upcast,
    split_spell_upcast,
)

#: 伤害表达式中的单项：``1d6`` / ``2d8`` / ``+3``（符号单独捕获）
_DAMAGE_ITEM_RE = re.compile(r"([+-]?)(\d*)[dD](\d+)|([+-]?)(\d+)")


class SpellCombatError(Exception):
    """法术战斗数据缺失或掷骰失败（消息面向用户，由命令层直接回复）。"""


class SpellDamagePartRoll(NamedTuple):
    """一段法术伤害的掷骰结果。"""

    expr: str
    damage_type: str
    result: RollResult
    total: int


def get_attack_bonus(character: DNDCharacter, spell: SpellEntry) -> str:
    """取法术攻击加值：条目 ``攻击`` 优先，其次头键 ``法术攻击``。"""
    bonus = spell.attack_bonus or character.spell_attack
    if not bonus:
        raise SpellCombatError(
            f"「{spell.name}」缺少法术攻击加值："
            "请在 .设置法术 写 法术攻击:+N，或在条目里写 攻击:+N。"
        )
    return bonus


def get_save_dc(character: DNDCharacter, spell: SpellEntry) -> str:
    """取豁免 DC：条目 ``DC`` 优先，其次头键 ``豁免DC``。"""
    dc = spell.save_dc or character.spell_dc
    if not dc:
        raise SpellCombatError(
            f"「{spell.name}」缺少豁免 DC："
            "请在 .设置法术 写 豁免DC:15，或在条目里写 DC:15。"
        )
    return dc


def scale_damage_expression(expr: str, times: int) -> str:
    """把伤害表达式整体放大 ``times`` 倍（升环加骰按次数叠加）。

    只支持骰子项与常数项的加减组合（与卡面校验一致）。骰数、常数都乘，
    如 ``1d4+1`` ×2 → ``2d4+2``、``1d6`` ×2 → ``2d6``。
    """
    if times <= 0:
        return ""
    items = re.findall(r"[+-]?[^+-]+", expr.strip())
    if not items:
        raise SpellCombatError(f"升环伤害表达式无效: {expr}")
    output: List[str] = []
    for item in items:
        matched = _DAMAGE_ITEM_RE.fullmatch(item)
        if matched is None:
            raise SpellCombatError(f"升环伤害表达式无效: {expr}")
        sign = matched.group(1) or matched.group(4) or ""
        if matched.group(3) is not None:
            count = int(matched.group(2) or 1) * times
            face = matched.group(3)
            output.append(f"{sign}{count}d{face}")
        else:
            value = int(matched.group(5)) * times
            output.append(f"{sign}{value}")
    text = "".join(output)
    return text[1:] if text.startswith("+") else text


def combine_damage_terms(expr: str) -> str:
    """合并同类项，让升环/临时加值后的表达式更短。

    ``8d6+1d6`` → ``9d6``、``3d4+3+2d4+2`` → ``5d4+5``；
    不同骰面与常数分别保留，如 ``1d8+1d6+2``。合并后为空时返回 ``0``。
    """
    items = re.findall(r"[+-]?[^+-]+", expr.strip())
    dice: dict[int, int] = {}
    constant = 0
    for item in items:
        matched = _DAMAGE_ITEM_RE.fullmatch(item)
        if matched is None:
            raise SpellCombatError(f"伤害表达式无效: {expr}")
        negative = (matched.group(1) or matched.group(4) or "") == "-"
        if matched.group(3) is not None:
            face = int(matched.group(3))
            count = int(matched.group(2) or 1) * (-1 if negative else 1)
            dice[face] = dice.get(face, 0) + count
        else:
            value = int(matched.group(5)) * (-1 if negative else 1)
            constant += value

    terms: List[Tuple[str, bool]] = []
    for face, count in dice.items():
        if count:
            terms.append((f"{abs(count)}d{face}", count < 0))
    if constant:
        terms.append((str(abs(constant)), constant < 0))
    if not terms:
        return "0"
    text = ("-" if terms[0][1] else "") + terms[0][0]
    for term, negative in terms[1:]:
        text += ("-" if negative else "+") + term
    return text


def resolve_spell_shots(spell: SpellEntry, cast_level: int) -> int:
    """实际发数：条目 ``多发`` + 升环 ``+N发`` 按环差叠加。"""
    shots = max(1, spell.shots)
    delta = max(0, cast_level - spell.level)
    if delta and spell.upcast:
        increase = split_spell_shots_upcast(spell.upcast)
        if increase:
            shots += increase * delta
    return shots


def build_damage_parts(
    spell: SpellEntry,
    cast_level: int,
    tail: str = "",
) -> Tuple[List[SpellDamagePart], str]:
    """按实际施法环阶生成伤害段 → ``(伤害段列表, 升环手动提示)``。

    ``tail`` 是 ``.X伤害`` 的 ``±`` 临时加值，并入第一段（保留其类型）。
    加骰型升环按 ``cast_level - spell.level`` 的次数叠加；非加骰型升环返回
    提示文本，由调用方附在回复末尾。
    """
    parts = [
        SpellDamagePart(expr=part.expr, damage_type=part.damage_type)
        for part in spell.damage_parts
    ]
    if not parts:
        return [], ""
    if tail:
        parts[0].expr += tail

    note = ""
    delta = max(0, cast_level - spell.level)
    if delta and spell.upcast and spell.upcast != "无":
        dice_upcast, text = split_spell_upcast(spell.upcast)
        if dice_upcast is None:
            if split_spell_shots_upcast(spell.upcast) is None:
                note = f"（升环效应：{text}，本期需手动处理）"
        else:
            up_expr, up_type_raw = dice_upcast
            up_type = normalize_damage_type(up_type_raw)
            scaled = scale_damage_expression(up_expr, delta)
            target: Optional[SpellDamagePart] = None
            if up_type:
                target = next(
                    (part for part in parts if part.damage_type == up_type), None
                )
            if target is None:
                target = parts[0]
            target.expr += scaled if scaled.startswith("-") else f"+{scaled}"
    for part in parts:
        part.expr = combine_damage_terms(part.expr)
    return parts, note


def format_damage_parts(parts: Sequence[SpellDamagePart]) -> str:
    """展示用伤害段，如 ``8d6 火焰`` / ``2d10 钝击 + 4d6 寒冷``。"""
    return " + ".join(
        f"{part.expr} {part.damage_type}".strip() for part in parts
    )


def format_type_summary(parts: Sequence[SpellDamagePart]) -> str:
    """伤害类型汇总（去重、保持出现顺序）；没有类型返回空串。"""
    types: List[str] = []
    for part in parts:
        if part.damage_type and part.damage_type not in types:
            types.append(part.damage_type)
    return "、".join(types)


def roll_damage_parts(
    parts: Sequence[SpellDamagePart], *, critical: bool = False
) -> List[SpellDamagePartRoll]:
    """逐段掷骰；``critical`` 时每段的骰子翻倍（固定加值不变）。"""
    rolls: List[SpellDamagePartRoll] = []
    for part in parts:
        expression = (
            apply_critical_to_damage(part.expr) if critical else part.expr
        )
        try:
            result = exec_roll_exp_unified(expression)
        except RollDiceError as exc:
            raise SpellCombatError(
                f"法术伤害掷骰失败: {expression}（{exc.info}）"
            ) from exc
        rolls.append(
            SpellDamagePartRoll(
                expr=expression,
                damage_type=part.damage_type,
                result=result,
                total=result.get_val(),
            )
        )
    return rolls


def roll_damage_shots(
    parts: Sequence[SpellDamagePart],
    shots: int,
    *,
    critical: bool = False,
) -> List[List[SpellDamagePartRoll]]:
    """按发数逐次掷骰；每一发都重新掷一次，而不是把骰数乘大发数。"""
    return [
        roll_damage_parts(parts, critical=critical)
        for _ in range(max(1, shots))
    ]


def roll_expression(expression: str) -> RollResult:
    """掷一条法术攻击表达式（如 ``D20+8``），失败转成用户可读错误。"""
    try:
        return exec_roll_exp_unified(expression)
    except RollDiceError as exc:
        raise SpellCombatError(
            f"法术攻击掷骰失败: {expression}（{exc.info}）"
        ) from exc
