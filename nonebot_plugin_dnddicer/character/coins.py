"""``$钱币$`` 的收支结算（纯函数，无 IO）。

紧凑写法 ``+20GP-5SP`` 按书写顺序逐条结算：

- **加法**只加指定币种，不做汇率换算；
- **减法**先扣指定币种，不足时按「最接近的更高币种优先」破开
  （CP←SP/EP/GP/PP、SP←EP/GP/PP、EP←GP/PP、GP←PP），
  更高币种破完仍不足才用更低币种按面值抵扣（大面额优先）；
- 整条命令原子：任意一条减法失败就整体拒绝，不产生部分扣款。

换算率固定为 ``1 PP = 10 GP``、``1 GP = 10 SP = 100 CP``、
``1 EP = 5 SP = 50 CP``；内部统一用 CP 校验总价值。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .constants import COIN_KEY_LIST

#: 各币种折合 CP 的面值（校验总价值与计算换算率用）
COIN_VALUES: Dict[str, int] = {
    "CP": 1,
    "SP": 10,
    "EP": 50,
    "GP": 100,
    "PP": 1000,
}

#: 破币顺序：最接近目标面额的更高币种优先
HIGHER_COINS: Dict[str, Tuple[str, ...]] = {
    "CP": ("SP", "EP", "GP", "PP"),
    "SP": ("EP", "GP", "PP"),
    "EP": ("GP", "PP"),
    "GP": ("PP",),
    "PP": (),
}

#: 更高币种不足后，用更低币种按面值抵扣（大面额优先）
LOWER_COINS: Dict[str, Tuple[str, ...]] = {
    "CP": (),
    "SP": ("CP",),
    "EP": ("SP", "CP"),
    "GP": ("EP", "SP", "CP"),
    "PP": ("GP", "EP", "SP", "CP"),
}

#: 全角数字、加号与减号 → 半角（与其它命令的输入容错一致）
_FULLWIDTH_MAP = str.maketrans("０１２３４５６７８９＋－", "0123456789+-")

_COIN_OP_RE = re.compile(r"\s*([+-])\s*(\d+)\s*(CP|SP|EP|GP|PP)", re.IGNORECASE)


@dataclass(frozen=True)
class CoinOperation:
    """一条收支：``+20GP`` / ``-5SP``。"""

    sign: str
    amount: int
    unit: str

    def get_info(self) -> str:
        """紧凑写法的规范展示（币种统一大写）。"""
        return f"{self.sign}{self.amount}{self.unit}"


@dataclass(frozen=True)
class CoinResult:
    """一次结算的结果（原钱包、新钱包、换算明细与触及的币种顺序）。"""

    old_coins: Dict[str, int]
    coins: Dict[str, int]
    details: Tuple[str, ...]
    touched: Tuple[str, ...]


class CoinInsufficient(Exception):
    """总价值不足（整条命令拒绝）。"""

    def __init__(self, amount: int, unit: str, need_cp: int, total_cp: int):
        super().__init__(f"钱币不足：{amount}{unit}")
        self.amount = amount
        self.unit = unit
        self.need_cp = need_cp
        self.total_cp = total_cp


def parse_coin_operations(text: str) -> List[CoinOperation]:
    """解析紧凑收支串；写法不合法时抛 ``AssertionError``（消息面向用户）。"""
    normalized = (text or "").translate(_FULLWIDTH_MAP).strip()
    if not normalized:
        raise AssertionError("请写收支，如 +20GP-5SP")

    operations: List[CoinOperation] = []
    position = 0
    while position < len(normalized):
        matched = _COIN_OP_RE.match(normalized, position)
        if matched is None:
            raise AssertionError(
                f"钱币写法无效：{text.strip()}"
                "（格式：+20GP-5SP，币种 CP/SP/EP/GP/PP）"
            )
        amount = int(matched.group(2))
        if amount <= 0:
            raise AssertionError(f"钱币数量必须为正整数：{matched.group(0).strip()}")
        operations.append(
            CoinOperation(
                sign=matched.group(1),
                amount=amount,
                unit=matched.group(3).upper(),
            )
        )
        position = matched.end()
    return operations


def _normalize(coins: Dict[str, int]) -> Dict[str, int]:
    """只保留五种币值并转成整数（旧卡缺币种按 0，未知键丢弃）。"""
    return {
        key: max(0, int(coins.get(key, 0) or 0))
        for key in COIN_KEY_LIST
    }


def total_cp(coins: Dict[str, int]) -> int:
    """钱包折合 CP 的总价值。"""
    return sum(COIN_VALUES[key] * int(coins.get(key, 0) or 0) for key in COIN_KEY_LIST)


def _deduct(
    coins: Dict[str, int], amount: int, unit: str
) -> Tuple[bool, List[str], List[str]]:
    """从钱包扣除 ``amount`` 个 ``unit``（就地修改），返回 (是否成功, 明细, 触及币种)。"""
    details: List[str] = []
    touched: List[str] = [unit]
    remain = amount

    # ① 先扣指定币种
    direct = min(coins.get(unit, 0), remain)
    if direct:
        coins[unit] = coins.get(unit, 0) - direct
        remain -= direct

    # ② 不足时破开更高币种（最接近面额优先）
    for higher in HIGHER_COINS[unit]:
        if remain <= 0:
            break
        have = coins.get(higher, 0)
        if have <= 0:
            continue
        rate = COIN_VALUES[higher] // COIN_VALUES[unit]
        need_count = -(-remain // rate)
        take = min(have, need_count)
        coins[higher] = have - take
        gained = take * rate
        coins[unit] = coins.get(unit, 0) + gained
        paid = min(remain, gained)
        coins[unit] -= paid
        remain -= paid
        line = (
            f"{unit} 不足：拆 {take} {higher} → +{gained} {unit}，"
            f"扣 {paid} {unit}"
        )
        if gained > paid:
            line += f"，余 {gained - paid} {unit}"
        details.append(line)
        touched.append(higher)

    # ③ 更高币种仍不足时，用更低币种按面值抵扣（大面额优先）
    remain_cp = remain * COIN_VALUES[unit]
    for lower in LOWER_COINS[unit]:
        if remain_cp <= 0:
            break
        have = coins.get(lower, 0)
        if have <= 0:
            continue
        lower_value = COIN_VALUES[lower]
        need_count = -(-remain_cp // lower_value)
        take = min(have, need_count)
        coins[lower] = have - take
        paid_cp = min(remain_cp, take * lower_value)
        remain_cp -= paid_cp
        # 折算量能整除就按目标币种写，否则写多少 CP（如 1 EP 只折半 GP）
        if paid_cp % COIN_VALUES[unit] == 0:
            paid_text = f"{paid_cp // COIN_VALUES[unit]} {unit}"
        else:
            paid_text = f"{paid_cp} CP"
        line = f"{unit} 不足：用 {take} {lower} 折算 {paid_text}，扣 {take} {lower}"
        if coins[lower] > 0:
            line += f"，余 {coins[lower]} {lower}"
        details.append(line)
        touched.append(lower)

    return remain_cp <= 0, details, touched


def apply_coin_operations(
    coins: Dict[str, int], operations: Iterable[CoinOperation]
) -> CoinResult:
    """按顺序结算全部收支；任一减法总价值不足时抛 ``CoinInsufficient``。

    失败时不修改传入字典；成功返回新钱包（未触及且原本不存在的零值币种不写入）。
    """
    original = _normalize(coins)
    working = dict(original)
    original_keys = {key for key in coins if key in COIN_VALUES}

    details: List[str] = []
    touched: List[str] = []
    for operation in operations:
        if operation.sign == "+":
            working[operation.unit] = working.get(operation.unit, 0) + operation.amount
            if operation.unit not in touched:
                touched.append(operation.unit)
            continue
        ok, op_details, op_touched = _deduct(
            working, operation.amount, operation.unit
        )
        if not ok:
            raise CoinInsufficient(
                operation.amount,
                operation.unit,
                operation.amount * COIN_VALUES[operation.unit],
                total_cp(original),
            )
        details.extend(op_details)
        for key in op_touched:
            if key not in touched:
                touched.append(key)

    new_coins = {
        key: value
        for key, value in working.items()
        if value != 0 or key in original_keys
    }
    return CoinResult(
        old_coins=original,
        coins=new_coins,
        details=tuple(details),
        touched=tuple(touched),
    )
