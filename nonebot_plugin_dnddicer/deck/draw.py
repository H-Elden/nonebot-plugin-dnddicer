"""牌堆抽取：放回/不放回、嵌套引用、内联掷骰与图片标记。

语义（2026-11-02 计划）：

- 顶层默认不放回，命令结束即重置；嵌套 ``{}`` 不放回、``{%}`` 放回；
- 权重是相对概率，不视为多份；
- 顶层抽空即停止；嵌套不放回池抽空时重洗子牌组；
- ``[expr]`` 用本插件掷骰引擎求值，替换为 ``表达式=数值``；
- ``[img:images/...]`` 只产出相对路径，由命令层读取并校验。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Optional

from nonebot import logger

from ..engine.roll.ast_engine import exec_roll_exp_unified
from ..engine.roll.roll_utils import RollDiceError
from .errors import DeckCountOutOfRange, DeckEmpty
from .library import DeckLibrary
from .media import MAX_IMAGES_PER_DRAW, MAX_IMAGES_PER_ENTRY
from .models import (
    Deck,
    DeckImagePart,
    DeckItem,
    DeckTextPart,
    DrawResult,
    RenderedEntry,
    normalize_name,
)
from .runtime import DeckRuntime, get_runtime

#: 单次命令最多抽取次数
MAX_TIMES = 10

#: 嵌套深度与单次展开次数上限
MAX_DEPTH = 8
MAX_EXPANSIONS = 100

#: 图片 / 嵌套 / 表达式标记（图片优先，避免被表达式抢走）
_TOKEN_RE = re.compile(
    r"\[img:([^\]]+)\]|\{(%?)([^{}]+)\}|\[([^\[\]]+)\]"
)


@dataclass
class DrawContext:
    """一次顶层抽取的上下文（池子、递归栈与计数）。"""

    library: DeckLibrary
    runtime: DeckRuntime
    pools: dict[str, list[DeckItem]] = field(default_factory=dict)
    stack: list[str] = field(default_factory=list)
    expansions: int = 0
    image_count: int = 0


def _sanitize(text: str) -> str:
    """清洗文本：CQ 码转义为普通文本，去掉 NUL。"""
    return (
        text.replace("[CQ:", "［CQ:")
        .replace("[cq:", "［cq:")
        .replace("\x00", "")
    )


def _append_text(parts: list[object], text: str) -> None:
    if not text:
        return
    if parts and isinstance(parts[-1], DeckTextPart):
        previous = parts[-1]
        parts[-1] = DeckTextPart(previous.text + text)
    else:
        parts.append(DeckTextPart(text))


def _pick_item(
    ctx: DrawContext,
    deck: Deck,
    *,
    replace: bool,
    refill: bool,
) -> Optional[DeckItem]:
    """按权重抽一条；不放回时从上下文池中移除。"""
    if replace:
        pool = list(deck.items)
    else:
        key = normalize_name(deck.name)
        pool = ctx.pools.get(key)
        if pool is None:
            pool = list(deck.items)
            ctx.pools[key] = pool
        if not pool and refill:
            pool.clear()
            pool.extend(deck.items)

    if not pool:
        return None

    total = sum(max(1, item.weight) for item in pool)
    if total <= 0:  # pragma: no cover - parser 保证权重 >=1
        item = pool[0]
        if not replace:
            pool.remove(item)
        return item

    roll = ctx.runtime.randbelow(total)
    for index, item in enumerate(pool):
        roll -= max(1, item.weight)
        if roll < 0:
            if not replace:
                pool.pop(index)
            return item

    # 理论上不可达；兜底返回最后一条，避免死循环
    item = pool[-1]
    if not replace:
        pool.pop()
    return item


def _render_expr(expression: str) -> str:
    """执行 ``[expr]``；非法表达式保留原文并记日志。"""
    expression = expression.strip()
    if not expression:
        return "[]"
    try:
        result = exec_roll_exp_unified(expression)
        return result.get_exp_val()
    except RollDiceError as exc:
        logger.warning("DNDDicer 牌堆内联表达式无效：{}（{}）", expression, exc)
        return f"[{expression}]"


def _render_nested(
    ctx: DrawContext,
    name: str,
    *,
    replace: bool,
    depth: int,
) -> list[object]:
    """渲染嵌套引用；失败时返回占位文本。"""
    ctx.expansions += 1
    if ctx.expansions > MAX_EXPANSIONS:
        return [DeckTextPart("【嵌套过多，已省略】")]
    if depth > MAX_DEPTH:
        return [DeckTextPart("【嵌套过深，已省略】")]

    target = ctx.library.exact_any(name)
    if target is None:
        return [DeckTextPart(f"【未知牌组：{name}】")]

    key = normalize_name(target.name)
    if key in ctx.stack:
        return [DeckTextPart(f"【循环引用：{target.name}】")]

    ctx.stack.append(key)
    try:
        item = _pick_item(ctx, target, replace=replace, refill=True)
        if item is None:
            return [DeckTextPart(f"【牌组为空：{target.name}】")]
        entry = _render_item(ctx, target, item, depth + 1)
        return list(entry.parts)
    finally:
        ctx.stack.pop()


def _render_item(
    ctx: DrawContext,
    deck: Deck,
    item: DeckItem,
    depth: int,
) -> RenderedEntry:
    """渲染一条内容（文本 / 图片 / 嵌套 / 表达式按出现顺序）。"""
    if depth > MAX_DEPTH:
        return RenderedEntry([DeckTextPart("【嵌套过深，已省略】")])

    raw = _sanitize(item.raw)
    parts: list[object] = []
    entry_images = 0
    cursor = 0

    for match in _TOKEN_RE.finditer(raw):
        if match.start() > cursor:
            _append_text(parts, raw[cursor:match.start()])

        if match.group(1) is not None:
            rel_path = match.group(1).strip()
            filename = PurePosixPath(rel_path).name or rel_path
            if (
                entry_images >= MAX_IMAGES_PER_ENTRY
                or ctx.image_count >= MAX_IMAGES_PER_DRAW
            ):
                _append_text(parts, "【图片过多，已省略】")
            else:
                parts.append(DeckImagePart(rel_path=rel_path, filename=filename))
                entry_images += 1
                ctx.image_count += 1
        elif match.group(3) is not None:
            name = match.group(3).strip()
            parts.extend(
                _render_nested(
                    ctx,
                    name,
                    replace=bool(match.group(2)),
                    depth=depth,
                )
            )
        else:
            _append_text(parts, _render_expr(match.group(4)))

        cursor = match.end()

    if cursor < len(raw):
        _append_text(parts, raw[cursor:])

    # 单条最多 5 张图（嵌套展开后同样生效）；超出的图片改为占位文本
    image_indexes = [
        index for index, part in enumerate(parts) if isinstance(part, DeckImagePart)
    ]
    if len(image_indexes) > MAX_IMAGES_PER_ENTRY:
        removed = 0
        for index in image_indexes[MAX_IMAGES_PER_ENTRY:]:
            parts[index] = DeckTextPart("【图片过多，已省略】")
            removed += 1
        ctx.image_count = max(0, ctx.image_count - removed)

    if not parts:
        parts.append(DeckTextPart(""))
    return RenderedEntry(parts=parts)


def draw(
    library: DeckLibrary,
    deck: Deck,
    times: int = 1,
    *,
    replace: bool = False,
) -> DrawResult:
    """从牌组顶层抽取。

    Args:
        library: 牌堆库（嵌套引用用）。
        deck: 目标牌组。
        times: 抽取次数（1..MAX_TIMES）。
        replace: 顶层是否放回；默认 False。

    Raises:
        DeckCountOutOfRange: 次数越界。
        DeckEmpty: 牌组没有条目。
    """
    if not 1 <= times <= MAX_TIMES:
        raise DeckCountOutOfRange(times, MAX_TIMES)
    if not deck.items:
        raise DeckEmpty(deck.name)

    ctx = DrawContext(library=library, runtime=get_runtime())
    entries: list[RenderedEntry] = []
    for _ in range(times):
        item = _pick_item(ctx, deck, replace=replace, refill=False)
        if item is None:
            break
        entries.append(_render_item(ctx, deck, item, 0))
    return DrawResult(
        entries=entries,
        requested=times,
        exhausted=len(entries) < times,
    )


__all__ = [
    "DrawContext",
    "MAX_TIMES",
    "draw",
]
