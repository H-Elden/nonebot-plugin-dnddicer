"""``$物品$`` 的查看与增删（纯函数，无 IO）。

卡面条目保持 ``名称x数量``，本模块只做解析、名称匹配与增减，不改模型与
存储格式。命令层见 ``commands/items.py``。

写法：

- ``名称+`` / ``名称+3``：增加 1 个 / 3 个，没有该物品时新建；
- ``名称-`` / ``名称-3``：扣减 1 个 / 3 个，扣到 0 时移除；
- 只认最右侧的 ``+`` / ``-``，名称本身可以含这两个符号；
- 名称精确优先，未命中再按子串匹配，大小写不敏感。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from .constants import ITEM_MAX_COUNT, ITEM_NAME_MAX_LEN, ITEM_QUANTITY_MAX

#: 卡面条目：``名称`` / ``名称x数量``（兼容卡面展示用的 ×）
_ITEM_RE = re.compile(r"^(?P<name>.+?)(?:[xX×](?P<qty>\d+))?$")
#: 命令操作：最右侧的 + / -，数量可省略（兼容全角符号与数字）
_OP_RE = re.compile(
    r"^(?P<name>.+?)\s*(?P<op>[+\-＋－])\s*(?P<qty>[0-9０-９]*)$"
)
#: 全角加号、减号 → 半角
_OP_MAP = str.maketrans("＋－", "+-")
#: 全角数字 → 半角
_DIGIT_MAP = str.maketrans("０１２３４５６７８９", "0123456789")

#: 卡格式 v2 的分隔符，物品名称不得包含
_NAME_FORBIDDEN_CHARS = ("$", ";", "|")


@dataclass(frozen=True)
class ItemEntry:
    """一条背包物品。"""

    name: str
    quantity: int = 1

    def get_info(self) -> str:
        """回写为卡面格式。"""
        return f"{self.name}x{self.quantity}"

    def get_display(self) -> str:
        """列表展示：数量大于 1 时带 ``×N``。"""
        if self.quantity > 1:
            return f"{self.name} ×{self.quantity}"
        return self.name


@dataclass(frozen=True)
class ItemOperation:
    """一条物品操作：增加 / 扣减。"""

    name: str
    mode: str  # add / remove
    quantity: int = 1


@dataclass(frozen=True)
class ItemChange:
    """一次操作的结果（新条目列表由 ``items`` 回写）。"""

    kind: str  # add_new / add / remove / remove_zero
    name: str
    old_quantity: int
    new_quantity: int
    items: Tuple[str, ...]


class ItemError(Exception):
    """物品操作失败（消息面向用户）。"""


class ItemNotFound(ItemError):
    """名称未命中。"""

    def __init__(self, name: str):
        super().__init__(f"背包里没有物品「{name}」")
        self.name = name


class ItemAmbiguous(ItemError):
    """子串命中多项。"""

    def __init__(self, name: str, candidates: Sequence[ItemEntry]):
        super().__init__(f"物品「{name}」匹配到多项")
        self.name = name
        self.candidates = tuple(candidates)


class ItemDuplicate(ItemError):
    """卡上存在多条同名物品。"""

    def __init__(self, name: str, candidates: Sequence[ItemEntry]):
        super().__init__(f"物品「{name}」在卡上出现了多次")
        self.name = name
        self.candidates = tuple(candidates)


class ItemInsufficient(ItemError):
    """扣减数量超过当前数量。"""

    def __init__(self, name: str, current: int, requested: int):
        super().__init__(f"物品「{name}」只有 {current} 个")
        self.name = name
        self.current = current
        self.requested = requested


class ItemLimit(ItemError):
    """条目数或单项数量超过上限。"""

    def __init__(self, kind: str, limit: int, name: str = ""):
        super().__init__(f"物品上限：{kind}={limit}")
        self.kind = kind
        self.limit = limit
        self.name = name


def normalize_item_name(name: str) -> str:
    """校验并返回物品名称；失败抛 ``AssertionError``（消息面向用户）。"""
    normalized = (name or "").strip()
    if not normalized:
        raise AssertionError("物品名称不能为空")
    if len(normalized) > ITEM_NAME_MAX_LEN:
        raise AssertionError(
            f"物品名称过长（≤{ITEM_NAME_MAX_LEN} 字）: {normalized}"
        )
    for char in _NAME_FORBIDDEN_CHARS:
        if char in normalized:
            raise AssertionError(f"物品名称不能包含符号「{char}」: {normalized}")
    return normalized


def parse_item_entry(raw: str) -> ItemEntry:
    """解析卡面条目 ``名称x数量``；异常数据按名称原样、数量 1 处理。"""
    text = (raw or "").strip()
    matched = _ITEM_RE.match(text)
    if matched is None:
        return ItemEntry(name=text, quantity=1)
    name = matched.group("name").strip()
    quantity = int(matched.group("qty") or "1")
    return ItemEntry(name=name, quantity=quantity)


def parse_item_operation(rest: str) -> ItemOperation:
    """解析命令参数；写法不合法时抛 ``AssertionError``（消息面向用户）。"""
    text = (rest or "").strip()
    matched = _OP_RE.match(text)
    if matched is None:
        raise AssertionError(
            "物品写法无效"
            "（写成 名称+数量、名称-数量 或 名称-；例：.物品 箭矢-3）"
        )
    name = normalize_item_name(matched.group("name"))
    operator = matched.group("op").translate(_OP_MAP)
    qty_text = matched.group("qty").translate(_DIGIT_MAP)
    quantity = 1
    if qty_text:
        quantity = int(qty_text)
        if quantity < 1:
            raise AssertionError("物品数量必须为正整数")
        if quantity > ITEM_QUANTITY_MAX:
            raise AssertionError(f"物品数量最多 {ITEM_QUANTITY_MAX} 个")
    if operator == "+":
        return ItemOperation(name=name, mode="add", quantity=quantity)
    return ItemOperation(name=name, mode="remove", quantity=quantity)


def find_item_index(
    entries: Sequence[ItemEntry], name: str
) -> Tuple[Optional[int], Tuple[ItemEntry, ...], bool]:
    """按名称查条目 → (唯一序号, 候选, 是否同名重复)。

    精确命中优先；未命中再按子串匹配。唯一命中返回序号，多候选返回候选
    列表，同名重复返回 ``duplicate=True``。
    """
    query = name.casefold()
    exact = [
        index
        for index, entry in enumerate(entries)
        if entry.name.casefold() == query
    ]
    if len(exact) == 1:
        return exact[0], (), False
    if len(exact) > 1:
        return None, tuple(entries[index] for index in exact), True
    partial = [
        index
        for index, entry in enumerate(entries)
        if query in entry.name.casefold()
    ]
    if len(partial) == 1:
        return partial[0], (), False
    return None, tuple(entries[index] for index in partial), False


def apply_item_operation(
    raw_items: Iterable[str], operation: ItemOperation
) -> ItemChange:
    """在条目列表上执行一条操作，返回新列表；失败抛 ``ItemError`` 子类。

    不修改传入列表；调用方成功后再整卡保存。
    """
    entries = [parse_item_entry(raw) for raw in raw_items]
    index, candidates, duplicate = find_item_index(entries, operation.name)

    if index is None:
        if duplicate:
            raise ItemDuplicate(operation.name, candidates)
        if candidates:
            raise ItemAmbiguous(operation.name, candidates)
        if operation.mode != "add":
            raise ItemNotFound(operation.name)
        if len(entries) >= ITEM_MAX_COUNT:
            raise ItemLimit("count", ITEM_MAX_COUNT)
        entry = ItemEntry(operation.name, operation.quantity)
        entries.append(entry)
        return ItemChange(
            kind="add_new",
            name=entry.name,
            old_quantity=0,
            new_quantity=entry.quantity,
            items=tuple(item.get_info() for item in entries),
        )

    entry = entries[index]
    if operation.mode == "remove":
        if operation.quantity > entry.quantity:
            raise ItemInsufficient(
                entry.name, entry.quantity, operation.quantity
            )
        new_quantity = entry.quantity - operation.quantity
        if new_quantity == 0:
            entries.pop(index)
            return ItemChange(
                kind="remove_zero",
                name=entry.name,
                old_quantity=entry.quantity,
                new_quantity=0,
                items=tuple(item.get_info() for item in entries),
            )
        entries[index] = ItemEntry(entry.name, new_quantity)
        return ItemChange(
            kind="remove",
            name=entry.name,
            old_quantity=entry.quantity,
            new_quantity=new_quantity,
            items=tuple(item.get_info() for item in entries),
        )

    new_quantity = entry.quantity + operation.quantity
    if new_quantity > ITEM_QUANTITY_MAX:
        raise ItemLimit("quantity", ITEM_QUANTITY_MAX, entry.name)
    entries[index] = ItemEntry(entry.name, new_quantity)
    return ItemChange(
        kind="add",
        name=entry.name,
        old_quantity=entry.quantity,
        new_quantity=new_quantity,
        items=tuple(item.get_info() for item in entries),
    )


def format_item_list(raw_items: Iterable[str]) -> List[str]:
    """把卡面条目转成列表展示行（不含序号）。"""
    return [
        parse_item_entry(raw).get_display()
        for raw in raw_items
    ]


def format_item_candidates(candidates: Sequence[ItemEntry]) -> str:
    """多候选的统一展示：``名称 ×数量`` 以顿号连接。"""
    return "、".join(entry.get_display() for entry in candidates)
