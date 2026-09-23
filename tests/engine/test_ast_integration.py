"""
Integration tests for the AST engine adapter.
"""

import pytest

from nonebot_plugin_dnddicer.engine.roll.ast_engine import (
    build_roll_result,
    exec_roll_exp_ast,
    exec_roll_exp_unified,
    RollExpressionResult,
)
from nonebot_plugin_dnddicer.engine.roll.ast_engine.errors import RollSyntaxError
from nonebot_plugin_dnddicer.engine.roll.ast_engine.evaluator import DiceRoll, DiceResult, EvalResult
from nonebot_plugin_dnddicer.engine.roll.result import RollResult


class MockDiceRoller:
    """Mock dice roller for deterministic testing."""

    def __init__(self, values):
        self._values = list(values)
        self._index = 0

    def __call__(self, sides):
        if self._index >= len(self._values):
            self._index = 0
        value = self._values[self._index]
        self._index += 1
        return value


class TestASTEngineAdapter:
    """Focused adapter integration test verifying full pipeline."""

    def test_full_pipeline_roll_dice(self):
        """Verify exec_roll_exp_unified produces correct RollExpressionResult fields."""
        roller = MockDiceRoller([10, 5])
        result = exec_roll_exp_unified("2D20K1+5", dice_roller=roller)
        assert result.get_val() == 15
        assert "15" in result.get_complete_result()
        assert result.get_exp() == "2D20K1+5"

    def test_full_pipeline_arithmetic(self):
        """Verify exec_roll_exp_unified for pure arithmetic."""
        result = exec_roll_exp_unified("1+2")
        assert result.get_val() == 3
        assert result.get_complete_result() == "1+2=3"

    def test_syntax_error_raises(self):
        from nonebot_plugin_dnddicer.engine.roll.roll_utils import RollDiceError
        with pytest.raises(RollDiceError):
            exec_roll_exp_unified("1+")


class TestUnifiedExecution:
    """Test the public AST-only execution API."""

    def test_unified_returns_roll_result(self):
        roller = MockDiceRoller([10])
        result = exec_roll_exp_unified("1D20", dice_roller=roller)
        assert isinstance(result, RollResult)
        assert result.get_val() == 10
        assert result.val_list == [10]

    def test_unified_wraps_arithmetic(self):
        result = exec_roll_exp_unified("1+2")
        assert result.get_val() == 3
        assert result.get_complete_result() == "1+2=3"


class TestResultInterface:
    """Test RollExpressionResult interface compatibility."""

    def test_get_val(self):
        result = RollExpressionResult(value=42, expression="1+41")
        assert result.get_val() == 42

    def test_get_info(self):
        result = RollExpressionResult(
            value=42,
            expression="1D20+22",
            info="[20]+22",
        )
        assert result.get_info() == "[20]+22"

    def test_get_exp(self):
        result = RollExpressionResult(
            value=42,
            expression="1D20+22",
            exp="1D20+22",
        )
        assert result.get_exp() == "1D20+22"


# ---------------------------------------------------------------------------
# Helpers for build_roll_result val_list tests
# ---------------------------------------------------------------------------

def _make_dice_result(*values: int, sides: int = 6) -> DiceResult:
    """Create a DiceResult where all rolls are kept."""
    rolls = [DiceRoll(value=v, sides=sides, kept=True) for v in values]
    return DiceResult(rolls=rolls, total=sum(values), count=len(values), sides=sides)


def _make_ast_result(value: int, *dice_results: DiceResult) -> RollExpressionResult:
    """Create a RollExpressionResult with pre-built DiceResults."""
    eval_result = EvalResult(value=value, dice_results=list(dice_results))
    return RollExpressionResult(
        value=value,
        expression="",
        info="",
        exp="",
        _eval_result=eval_result,
    )


class TestBuildRollResultValList:
    """val_list 正确性：多骰子 + 非加法因子不得丢失常量值。"""

    # ---- 单纯加法（应保留明细） ----

    def test_pure_two_dice_addition_keeps_detail(self):
        """1D20+1D6 → val_list=[15,4]"""
        result = _make_ast_result(19, _make_dice_result(15, sides=20), _make_dice_result(4))
        rr = build_roll_result(result)
        assert rr.val_list == [15, 4]
        assert rr.get_val() == 19

    def test_three_pure_dice_addition_keeps_detail(self):
        """1D20+1D6+1D4 → val_list=[15,4,3]"""
        result = _make_ast_result(22,
            _make_dice_result(15, sides=20),
            _make_dice_result(4),
            _make_dice_result(3, sides=4),
        )
        rr = build_roll_result(result)
        assert rr.val_list == [15, 4, 3]
        assert rr.get_val() == 22

    # ---- 有常量参与（应回退到 total） ----

    def test_dice_plus_constant_plus_dice(self):
        """1D6+5+1D4=14 → val_list=[14]"""
        result = _make_ast_result(14, _make_dice_result(5), _make_dice_result(4, sides=4))
        rr = build_roll_result(result)
        assert rr.val_list == [14]
        assert rr.get_val() == 14

    def test_constant_plus_two_dice(self):
        """5+1D20+1D6=24 → val_list=[24]"""
        result = _make_ast_result(24, _make_dice_result(15, sides=20), _make_dice_result(4))
        rr = build_roll_result(result)
        assert rr.val_list == [24]
        assert rr.get_val() == 24

    def test_two_dice_plus_constant(self):
        """1D20+1D6+5=24 → val_list=[24]"""
        result = _make_ast_result(24, _make_dice_result(15, sides=20), _make_dice_result(4))
        rr = build_roll_result(result)
        assert rr.val_list == [24]
        assert rr.get_val() == 24

    def test_two_dice_minus_constant(self):
        """1D20+1D4-5=10 → val_list=[10] (sum(5,4)=9≠10)"""
        result = _make_ast_result(10, _make_dice_result(5, sides=20), _make_dice_result(4, sides=4))
        rr = build_roll_result(result)
        assert rr.val_list == [10]
        assert rr.get_val() == 10

    # ---- 非加法运算（应回退到 total） ----

    def test_subtract_two_dice(self):
        """1D20-1D6=11 → val_list=[11] (15+4=19≠11)"""
        result = _make_ast_result(11, _make_dice_result(15, sides=20), _make_dice_result(4))
        rr = build_roll_result(result)
        assert rr.val_list == [11]
        assert rr.get_val() == 11

    def test_dice_times_constant_plus_dice(self):
        """1D20*2+1D6=34 → val_list=[34]"""
        result = _make_ast_result(34, _make_dice_result(15, sides=20), _make_dice_result(4))
        rr = build_roll_result(result)
        assert rr.val_list == [34]
        assert rr.get_val() == 34

    def test_two_dice_multiplication(self):
        """1D20*1D4=60 → val_list=[60]"""
        result = _make_ast_result(60, _make_dice_result(15, sides=20), _make_dice_result(4, sides=4))
        rr = build_roll_result(result)
        assert rr.val_list == [60]
        assert rr.get_val() == 60

    def test_two_dice_division(self):
        """1D20/1D4=3 → val_list=[3]"""
        result = _make_ast_result(3, _make_dice_result(15, sides=20), _make_dice_result(4, sides=4))
        rr = build_roll_result(result)
        assert rr.val_list == [3]
        assert rr.get_val() == 3

    # ---- 括号 + 常量（ParenNode 不产生 dice_result） ----

    def test_paren_with_constant_plus_dice(self):
        """(1D20+5)+1D6=24 → val_list=[24]"""
        result = _make_ast_result(24, _make_dice_result(15, sides=20), _make_dice_result(4))
        rr = build_roll_result(result)
        assert rr.val_list == [24]
        assert rr.get_val() == 24

    # ---- 边界：所有骰子均被弃用时的空列表回退 ----

    def test_all_dice_dropped_fallback_to_total(self):
        """所有 roll.kept=False → multi_kept=[] → val_list 回退为 [total]"""
        dr1 = DiceResult(
            rolls=[DiceRoll(value=15, sides=20, kept=False)],
            total=0, count=1, sides=20,
        )
        dr2 = DiceResult(
            rolls=[DiceRoll(value=4, sides=6, kept=False)],
            total=0, count=1, sides=6,
        )
        result = _make_ast_result(0, dr1, dr2)
        rr = build_roll_result(result)
        assert rr.val_list == [0]
        assert rr.get_val() == 0

    # ---- 端到端：exec_roll_exp_unified 验证 get_val() ----

    def test_end_to_end_dice_plus_constant_plus_dice(self):
        """1D6+5+1D4 全链路，mock 骰子为 5 和 4，验证 get_val()=14"""
        roller = MockDiceRoller([5, 4])
        result = exec_roll_exp_unified("1D6+5+1D4", dice_roller=roller)
        assert result.get_val() == 14
        assert result.val_list == [14]

    def test_end_to_end_two_dice_subtraction(self):
        """1D20-1D6 全链路，验证 get_val() 正确"""
        roller = MockDiceRoller([15, 4])
        result = exec_roll_exp_unified("1D20-1D6", dice_roller=roller)
        assert result.get_val() == 11
        assert result.val_list == [11]

    def test_end_to_end_complete_result(self):
        """1D6+5+1D4 complete result 中 val 应为 14"""
        roller = MockDiceRoller([5, 4])
        result = exec_roll_exp_unified("1D6+5+1D4", dice_roller=roller)
        complete = result.get_complete_result()
        assert "14" in complete
        # info 正确展示过程
        assert "[5]+5+[4]" in complete or "5+5+4" in complete


class TestCompoundOperandParentheses:
    """抗性/易伤等括号表达式渲染按优先级补括号（求值语义不变）。"""

    def test_resistance_additive_numerator(self):
        """5+2+3抗性 → 渲染补分子括号：(5+2+3)/2=5"""
        result = exec_roll_exp_unified("5+2+3抗性")
        assert result.get_val() == 5
        assert result.get_info() == "(5+2+3)/2"
        assert result.get_result() == "(5+2+3)/2=5"

    def test_vulnerability_additive_numerator(self):
        """5+2+3易伤 → 渲染补分子括号：(5+2+3)*2=20"""
        result = exec_roll_exp_unified("5+2+3易伤")
        assert result.get_val() == 20
        assert result.get_info() == "(5+2+3)*2"

    def test_resistance_dice_expression(self):
        """1D6+3抗性（骰 3）→ ([3]+3)/2=3"""
        roller = MockDiceRoller([3])
        result = exec_roll_exp_unified("1D6+3抗性", dice_roller=roller)
        assert result.get_val() == 3
        assert result.get_info() == "([3]+3)/2"

    def test_resistance_single_dice_no_parens(self):
        """12抗性（纯单操作数）→ 无需括号：12/2=6"""
        result = exec_roll_exp_unified("12抗性")
        assert result.get_val() == 6
        assert result.get_info() == "12/2"

    def test_explicit_parentheses_preserved_in_info(self):
        """(1+2)*2 → 渲染保留括号：(1+2)*2=6"""
        result = exec_roll_exp_unified("(1+2)*2")
        assert result.get_val() == 6
        assert result.get_info() == "(1+2)*2"

    def test_divide_by_parenthesized_sum(self):
        """12/(1+2) → 渲染保留括号：12/(1+2)=4"""
        result = exec_roll_exp_unified("12/(1+2)")
        assert result.get_val() == 4
        assert result.get_info() == "12/(1+2)"

    def test_multiply_by_parenthesized_sum(self):
        """2*(1+2) → 渲染保留括号：2*(1+2)=6"""
        result = exec_roll_exp_unified("2*(1+2)")
        assert result.get_val() == 6
        assert result.get_info() == "2*(1+2)"

    def test_left_associative_same_precedence_no_parens(self):
        """8/2/2 同级左结合 → 不补多余括号：8/2/2=2"""
        result = exec_roll_exp_unified("8/2/2")
        assert result.get_val() == 2
        assert result.get_info() == "8/2/2"


class TestConstantOperandRendering:
    """常量操作数与一元负号参与渲染：说明文字须与算式结构、四则运算一致。

    2026-09-23 修订：常量此前不产生渲染事件，纯常量子表达式（1D6+2*2 里的
    2*2）会被错配到其他层级的骰块上（曾显示 [4]*2+4），与四则运算不符。
    """

    def test_constant_mul_after_plus(self):
        """1D6+2*2 → [3]+2*2=7（乘号只作用于常量 2*2，不改写骰块）"""
        result = exec_roll_exp_unified("1D6+2*2", dice_roller=MockDiceRoller([3]))
        assert result.get_val() == 7
        assert result.get_info() == "[3]+2*2"

    def test_constant_mul_after_plus_multi_digit(self):
        """1D6+2*3 → [3]+2*3=9（常量两侧原样展示，不折叠成值）"""
        result = exec_roll_exp_unified("1D6+2*3", dice_roller=MockDiceRoller([3]))
        assert result.get_val() == 9
        assert result.get_info() == "[3]+2*3"

    def test_constant_mul_after_minus(self):
        """1D6-2*2 → [3]-2*2=-1"""
        result = exec_roll_exp_unified("1D6-2*2", dice_roller=MockDiceRoller([3]))
        assert result.get_val() == -1
        assert result.get_info() == "[3]-2*2"

    def test_constant_mul_between_dice_terms(self):
        """1D6*2+2*2 → [3]*2+2*2=10"""
        result = exec_roll_exp_unified("1D6*2+2*2", dice_roller=MockDiceRoller([3]))
        assert result.get_val() == 10
        assert result.get_info() == "[3]*2+2*2"

    def test_constant_mul_parenthesized_after_dice(self):
        """1D6+(2*2) → [3]+2*2=7（冗余括号不显示，运算顺序不变）"""
        result = exec_roll_exp_unified("1D6+(2*2)", dice_roller=MockDiceRoller([3]))
        assert result.get_val() == 7
        assert result.get_info() == "[3]+2*2"

    def test_unary_minus_operand_rendered(self):
        """1D6*-2 → [3]*(-2)=-6（负号操作数整体显示，不与骰块错位）"""
        result = exec_roll_exp_unified("1D6*-2", dice_roller=MockDiceRoller([3]))
        assert result.get_val() == -6
        assert result.get_info() == "[3]*(-2)"

    def test_unary_minus_before_dice(self):
        """-1D6+3 → -[3]+3=0"""
        result = exec_roll_exp_unified("-1D6+3", dice_roller=MockDiceRoller([3]))
        assert result.get_val() == 0
        assert result.get_info() == "-[3]+3"

    def test_double_minus_operand_parenthesized(self):
        """1D6--2 → [3]-(-2)=5（第二个减号为一元负号，渲染带括号防误读）"""
        result = exec_roll_exp_unified("1D6--2", dice_roller=MockDiceRoller([3]))
        assert result.get_val() == 5
        assert result.get_info() == "[3]-(-2)"

    def test_constant_mul_applies_to_adjacent_dice_only(self):
        """1D6+1D8*2 → [3]+[5]*2=13（*2 只作用于相邻的 d8，不整体翻倍）"""
        result = exec_roll_exp_unified("1D6+1D8*2", dice_roller=MockDiceRoller([3, 5]))
        assert result.get_val() == 13
        assert result.get_info() == "[3]+[5]*2"

    def test_parenthesized_dice_sum_times_two(self):
        """(1D6+1D8)*2 → ([3]+[5])*2=16（括号内整体乘 2，括号保留）"""
        result = exec_roll_exp_unified("(1D6+1D8)*2", dice_roller=MockDiceRoller([3, 5]))
        assert result.get_val() == 16
        assert result.get_info() == "([3]+[5])*2"

    def test_redundant_parens_around_dice_omitted(self):
        """1D6+(1D8)*2 与 1D6+(1D8*2) 同义 → [3]+[5]*2=13（冗余括号不显示）"""
        for exp in ("1D6+(1D8)*2", "1D6+(1D8*2)"):
            result = exec_roll_exp_unified(exp, dice_roller=MockDiceRoller([3, 5]))
            assert result.get_val() == 13
            assert result.get_info() == "[3]+[5]*2"

    def test_constant_after_keep_modifier(self):
        """2D6K1+2*2 → MAX{[6], [2]}+2*2=10（修饰符骰块与常量各就各位）"""
        result = exec_roll_exp_unified("2D6K1+2*2", dice_roller=MockDiceRoller([6, 2]))
        assert result.get_val() == 10
        assert result.get_info() == "MAX{[6], [2]}+2*2"
