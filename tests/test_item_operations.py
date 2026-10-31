"""``$物品$`` 纯函数测试（2026-11-01）：解析、匹配、增减与边界。"""

import pytest

from nonebot_plugin_dnddicer.character.items import (
    ItemAmbiguous,
    ItemDuplicate,
    ItemInsufficient,
    ItemLimit,
    ItemNotFound,
    ItemOperation,
    apply_item_operation,
    find_item_index,
    format_item_candidates,
    format_item_list,
    parse_item_entry,
    parse_item_operation,
)
from nonebot_plugin_dnddicer.character.constants import (
    ITEM_MAX_COUNT,
    ITEM_QUANTITY_MAX,
)


def test_parse_item_entry_normalizes_quantity():
    assert parse_item_entry("箭矢x20").get_info() == "箭矢x20"
    assert parse_item_entry("巨斧").get_info() == "巨斧x1"
    assert parse_item_entry("箭矢×3").get_info() == "箭矢x3"
    assert parse_item_entry("长弓+1x2").get_info() == "长弓+1x2"


def test_parse_item_operation_add_and_remove():
    add = parse_item_operation("箭矢+3")
    assert (add.name, add.mode, add.quantity) == ("箭矢", "add", 3)
    add_one = parse_item_operation("箭矢+")
    assert (add_one.name, add_one.mode, add_one.quantity) == ("箭矢", "add", 1)
    remove = parse_item_operation("箭矢-3")
    assert (remove.name, remove.mode, remove.quantity) == ("箭矢", "remove", 3)
    remove_one = parse_item_operation("巨斧 -")
    assert (remove_one.name, remove_one.mode, remove_one.quantity) == (
        "巨斧", "remove", 1
    )
    # 全角数字与减号
    fullwidth = parse_item_operation("箭矢－３")
    assert (fullwidth.name, fullwidth.mode, fullwidth.quantity) == (
        "箭矢", "remove", 3
    )
    # 名称自带 + / -，只认最右侧操作符
    tricky = parse_item_operation("长弓+1-1")
    assert (tricky.name, tricky.mode, tricky.quantity) == (
        "长弓+1", "remove", 1
    )
    spaced = parse_item_operation("巨斧 - 3")
    assert (spaced.name, spaced.mode, spaced.quantity) == ("巨斧", "remove", 3)
    # 名称里的全角数字不被改写
    fullwidth_name = parse_item_operation("药水２+1")
    assert (fullwidth_name.name, fullwidth_name.mode) == ("药水２", "add")


def test_parse_item_operation_rejects_invalid():
    with pytest.raises(AssertionError, match="物品写法无效"):
        parse_item_operation("箭矢")
    with pytest.raises(AssertionError, match="正整数"):
        parse_item_operation("箭矢-0")
    with pytest.raises(AssertionError, match="最多"):
        parse_item_operation(f"箭矢-{ITEM_QUANTITY_MAX + 1}")
    with pytest.raises(AssertionError, match="不能包含符号"):
        parse_item_operation("箭矢;+1")
    with pytest.raises(AssertionError, match="名称过长"):
        parse_item_operation("长" * 31 + "+1")


def test_find_item_exact_prefers_and_substring_lists():
    items = ["治疗药水x2", "强效治疗药水x1", "箭矢x20"]
    entries = [parse_item_entry(raw) for raw in items]

    index, candidates, duplicate = find_item_index(entries, "治疗药水")
    assert index == 0 and not candidates and not duplicate

    index, candidates, duplicate = find_item_index(entries, "药水")
    assert index is None and not duplicate
    assert [entry.name for entry in candidates] == ["治疗药水", "强效治疗药水"]

    index, candidates, duplicate = find_item_index(entries, "不存在")
    assert index is None and not candidates and not duplicate


def test_find_item_duplicate():
    entries = [parse_item_entry("箭矢x2"), parse_item_entry("箭矢x3")]
    index, candidates, duplicate = find_item_index(entries, "箭矢")
    assert index is None and duplicate
    assert len(candidates) == 2


def test_apply_add_new_and_existing():
    created = apply_item_operation(["箭矢x20"], ItemOperation("治疗药水", "add", 2))
    assert created.kind == "add_new"
    assert created.items == ("箭矢x20", "治疗药水x2")

    added = apply_item_operation(["箭矢x20"], ItemOperation("箭矢", "add", 3))
    assert added.kind == "add"
    assert (added.old_quantity, added.new_quantity) == (20, 23)
    assert added.items == ("箭矢x23",)


def test_apply_remove_and_remove_zero():
    removed = apply_item_operation(["箭矢x20"], ItemOperation("箭矢", "remove", 3))
    assert removed.kind == "remove"
    assert (removed.old_quantity, removed.new_quantity) == (20, 17)
    assert removed.items == ("箭矢x17",)

    one = apply_item_operation(["巨斧x3"], ItemOperation("巨斧", "remove", 1))
    assert one.kind == "remove"
    assert one.items == ("巨斧x2",)

    zero = apply_item_operation(["箭矢x3"], ItemOperation("箭矢", "remove", 3))
    assert zero.kind == "remove_zero"
    assert zero.items == ()

    last_one = apply_item_operation(
        ["巨斧x1", "箭矢x2"], ItemOperation("巨斧", "remove", 1)
    )
    assert last_one.kind == "remove_zero"
    assert last_one.items == ("箭矢x2",)


def test_apply_errors():
    with pytest.raises(ItemNotFound):
        apply_item_operation(["箭矢x2"], ItemOperation("短剑", "remove", 1))
    with pytest.raises(ItemInsufficient) as info:
        apply_item_operation(["箭矢x2"], ItemOperation("箭矢", "remove", 3))
    assert (info.value.current, info.value.requested) == (2, 3)
    with pytest.raises(ItemAmbiguous) as ambiguous:
        apply_item_operation(
            ["治疗药水x2", "强效治疗药水x1"],
            ItemOperation("药水", "remove", 1),
        )
    assert len(ambiguous.value.candidates) == 2
    with pytest.raises(ItemDuplicate):
        apply_item_operation(
            ["箭矢x2", "箭矢x3"], ItemOperation("箭矢", "remove", 1)
        )
    with pytest.raises(ItemLimit) as limit:
        apply_item_operation(
            ["箭矢x999"], ItemOperation("箭矢", "add", 1)
        )
    assert limit.value.kind == "quantity"


def test_apply_item_count_limit():
    items = [f"物品{i}x1" for i in range(ITEM_MAX_COUNT)]
    with pytest.raises(ItemLimit) as limit:
        apply_item_operation(items, ItemOperation("新物品", "add", 1))
    assert limit.value.kind == "count"


def test_format_helpers_hide_single_quantity():
    assert format_item_list(["治疗药水x2", "巨斧x1"]) == ["治疗药水 ×2", "巨斧"]
    assert format_item_candidates([
        parse_item_entry("治疗药水x2"),
        parse_item_entry("强效治疗药水x1"),
    ]) == "治疗药水 ×2、强效治疗药水"
