"""Dice! JSON 牌堆解析（安全子集）。

只读取「牌组名 → 字符串数组」与少量元数据；不执行脚本、不联网、不支持 CQ
图片。解析失败按文件隔离，错误交给 ``DeckLibrary`` 汇总给骰主。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from nonebot import logger

from .models import Deck, DeckFileError, DeckItem, DeckMeta

#: 单文件 / 单牌组 / 单条限制
MAX_FILE_BYTES = 1024 * 1024
MAX_DECKS_PER_FILE = 200
MAX_ITEMS_PER_DECK = 500
MAX_TEXT_CHARS = 1000
MAX_NAME_CHARS = 40
MAX_WEIGHT = 1000

#: 管理子命令保留词：可见牌组不得与之同名，避免无法直接抽取
RESERVED_DECK_NAMES = frozenset({"列表", "搜索", "详情", "重载"})

#: 已知元数据键（值为字符串或字符串数组，不当作牌组）
_META_KEYS = frozenset(
    {
        "_title",
        "_author",
        "_date",
        "_updateDate",
        "_version",
        "_brief",
        "_license",
        "_source",
        "_export",
        "_exports",
        "_keys",
    }
)

_WEIGHT_RE = re.compile(r"^::(\d+)::(.*)$", re.S)


def _join_text(value: Any, sep: str = " / ") -> str:
    """把元数据值（字符串或字符串数组）拼成展示文本。"""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return sep.join(str(item).strip() for item in value if str(item).strip())
    return ""


def _string_list(value: Any) -> tuple[str, ...]:
    """把元数据值（字符串或字符串数组）规整为字符串元组。"""
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _parse_meta(data: dict[str, Any]) -> DeckMeta:
    return DeckMeta(
        title=_join_text(data.get("_title")),
        author=_join_text(data.get("_author")),
        version=_join_text(data.get("_version")),
        license=_join_text(data.get("_license")),
        source=_join_text(data.get("_source")),
        brief=_join_text(data.get("_brief"), sep="\n"),
        date=_join_text(data.get("_date")),
        update_date=_join_text(data.get("_updateDate")),
        export=_string_list(data.get("_export", data.get("_exports"))),
        keys=_string_list(data.get("_keys")),
    )


def _parse_item(raw: str, line: int) -> tuple[Optional[DeckItem], list[str]]:
    """解析单条文本：返回 (条目, 警告)；空条目返回 (None, [])。"""
    warnings: list[str] = []
    text = raw.strip()
    if not text:
        return None, warnings

    weight = 1
    match = _WEIGHT_RE.match(text)
    if match:
        try:
            weight = int(match.group(1))
        except ValueError:  # pragma: no cover - 正则已保证是数字
            weight = 1
        text = match.group(2).strip()
        if not text:
            return None, warnings
        if weight <= 0:
            weight = 1
        elif weight > MAX_WEIGHT:
            weight = MAX_WEIGHT
            warnings.append(f"权重超过 {MAX_WEIGHT}，已按 {MAX_WEIGHT} 处理")

    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
        warnings.append(f"条目超过 {MAX_TEXT_CHARS} 字，已截断")

    return DeckItem(raw=text, weight=weight, line=line), warnings


def _parse_deck(
    name: str,
    values: Any,
    *,
    meta: DeckMeta,
    file: Path,
    hidden: bool,
    line: int,
) -> tuple[Optional[Deck], list[str]]:
    """解析一个牌组；返回 (牌组, 警告)，不可用时牌组为 None。"""
    warnings: list[str] = []
    if not isinstance(values, list):
        return None, [f"牌组「{name}」不是字符串数组，已跳过"]

    items: list[DeckItem] = []
    for index, value in enumerate(values, start=1):
        if not isinstance(value, str):
            warnings.append(f"牌组「{name}」第 {index} 条不是字符串，已跳过")
            continue
        item, item_warnings = _parse_item(value, index)
        warnings.extend(f"牌组「{name}」{msg}" for msg in item_warnings)
        if item is not None:
            items.append(item)
        if len(items) >= MAX_ITEMS_PER_DECK:
            if index < len(values):
                warnings.append(
                    f"牌组「{name}」超过 {MAX_ITEMS_PER_DECK} 条，后续条目已忽略"
                )
            break

    if not items:
        return None, [f"牌组「{name}」没有可抽取的条目，已跳过"]

    return (
        Deck(name=name, items=items, file=file, meta=meta, hidden=hidden),
        warnings,
    )


def parse_deck_file(path: Path) -> tuple[list[Deck], list[DeckFileError]]:
    """解析单个 Dice! JSON 文件。

    Args:
        path: 文件路径。

    Returns:
        (牌组列表, 错误列表)。错误可按文件隔离，不应抛到命令层。
    """
    errors: list[DeckFileError] = []

    def error(message: str) -> None:
        errors.append(DeckFileError(file=path, message=message))

    try:
        size = path.stat().st_size
    except OSError as exc:
        error(f"无法读取文件：{exc}")
        return [], errors
    if size > MAX_FILE_BYTES:
        error(f"文件超过 {MAX_FILE_BYTES // 1024 // 1024} MB，已跳过")
        return [], errors

    try:
        raw_text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        error(f"读取失败：{exc}")
        return [], errors

    duplicates: list[str] = []

    def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                duplicates.append(key)
            result[key] = value
        return result

    try:
        data = json.loads(raw_text, object_pairs_hook=_pairs_hook)
    except json.JSONDecodeError as exc:
        error(f"JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}")
        return [], errors

    if not isinstance(data, dict):
        error("顶层必须是 JSON 对象（牌组名 → 字符串数组）")
        return [], errors

    meta = _parse_meta(data)
    visible_filter: Optional[set[str]] = None
    if meta.export:
        visible_filter = set(meta.export)
    elif meta.keys:
        visible_filter = set(meta.keys)

    for duplicate in dict.fromkeys(duplicates):
        if duplicate in _META_KEYS:
            logger.warning("DNDDicer 牌堆文件 {}：元数据键「{}」重复，后写入的值生效", path, duplicate)
        else:
            logger.warning("DNDDicer 牌堆文件 {}：牌组「{}」重复，后写入的值生效", path, duplicate)

    decks: list[Deck] = []
    for name, values in data.items():
        if name in _META_KEYS:
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()
        if len(name) > MAX_NAME_CHARS:
            error(f"牌组名「{name[:20]}…」超过 {MAX_NAME_CHARS} 字，已跳过")
            continue

        hidden = name.startswith("_")
        if visible_filter is not None and name not in visible_filter:
            hidden = True
        if not hidden and name in RESERVED_DECK_NAMES:
            error(f"牌组名「{name}」是保留子命令，已跳过；请改名后重试")
            continue

        deck, warnings = _parse_deck(
            name,
            values,
            meta=meta,
            file=path,
            hidden=hidden,
            line=0,
        )
        for warning in warnings:
            logger.warning("DNDDicer 牌堆文件 {}：{}", path, warning)
        if deck is not None:
            decks.append(deck)

        if len(decks) >= MAX_DECKS_PER_FILE:
            error(f"文件超过 {MAX_DECKS_PER_FILE} 个牌组，后续牌组已忽略")
            break

    if not decks and not errors:
        error("没有找到可用的牌组")
    return decks, errors


__all__ = [
    "MAX_DECKS_PER_FILE",
    "MAX_FILE_BYTES",
    "MAX_ITEMS_PER_DECK",
    "MAX_NAME_CHARS",
    "MAX_TEXT_CHARS",
    "MAX_WEIGHT",
    "RESERVED_DECK_NAMES",
    "parse_deck_file",
]
