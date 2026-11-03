"""牌堆与随机表命令：``.draw``（中文别名 ``.抽牌`` / ``.牌堆``）。

一条命令承担全部入口：

- ``.draw``：列出牌堆第一页；
- ``.draw 列表 [页码]``：翻页，每页 10 个，列表项带全局编号；
- ``.draw 名称|编号 [次数] [放回]``：抽取，默认单次命令内不放回；
- ``.draw 搜索 关键词`` / ``.draw 详情 名称|编号``：搜索与详情；
- ``.draw 重载``：骰主私聊重载。

牌堆名精确优先，其次纯数字编号，未命中再按子串匹配；多候选列清单不猜。
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)

from ..deck import (
    Deck,
    DeckAmbiguous,
    DeckCountOutOfRange,
    DeckEmpty,
    DeckImageError,
    DeckImagePart,
    DeckIndexOutOfRange,
    DeckLibrary,
    DeckNotFound,
    DeckTextPart,
    DrawResult,
    MAX_TIMES,
    MAX_TOTAL_IMAGE_BYTES,
    RenderedEntry,
    draw as draw_cards,
    load_image,
)
from . import base, text

_HELP = (
    ".draw [名称|编号] [次数] [放回]\n"
    "  无参数列出牌堆；.draw 列表 [页码] 翻页\n"
    "  .抽牌 / .牌堆 等价\n"
    "  次数 1-10，默认不放回；放回 允许重复\n"
    "  .draw 搜索 关键词 / .draw 详情 名称|编号\n"
    "  骰主：.draw 重载"
)

#: 列表每页条数
_LIST_PAGE_SIZE = 10

#: 搜索与多候选最多展示条数
_LIST_SHOW_LIMIT = 10

deck_matcher = base.on_dnd_command(
    "draw",
    _HELP,
    aliases=("抽牌", "牌堆"),
    doc="guide/decks",
)

#: 牌堆库单例（测试可替换）
_library = DeckLibrary()


def set_library(library: DeckLibrary) -> None:
    """替换牌堆库单例（测试用）。"""
    global _library
    _library = library


async def get_library() -> DeckLibrary:
    """返回已加载的牌堆库（首次调用懒加载）。"""
    await _library.ensure_loaded()
    return _library


@dataclass(frozen=True)
class DrawArgs:
    """解析后的抽取参数。"""

    deck: Deck
    times: int
    replace: bool


# ── 解析 ────────────────────────────────────────────────────────────────


def _normalize(text_value: str) -> str:
    """全角转半角并去掉首尾空白。"""
    return unicodedata.normalize("NFKC", text_value or "").strip()


def _consume_replacement(value: str) -> tuple[bool, str]:
    """剥掉末尾连续的 放回 / 不放回；返回 (是否放回, 剩余文本)。

    两个都写时以最后一个为准；只处理末尾，避免误伤牌堆名中间的词。
    """
    parts = value.split()
    if not parts or parts[-1] not in ("放回", "不放回"):
        return False, value
    replace = parts[-1] == "放回"
    while parts and parts[-1] in ("放回", "不放回"):
        parts.pop()
    return replace, " ".join(parts)


def _check_times(times: int) -> None:
    if not 1 <= times <= MAX_TIMES:
        raise DeckCountOutOfRange(times, MAX_TIMES)


def _resolve_deck(library: DeckLibrary, name: str) -> Deck:
    """名称精确优先，其次纯数字编号，最后子串匹配。

    纯数字排在子串匹配之前，保证 ``.draw 12`` 始终指向列表第 12 项；
    名称恰好是数字的牌堆仍由精确匹配先命中。
    """
    exact = library.exact(name)
    if exact is not None:
        return exact
    if name.isdecimal():
        decks = library.visible()
        index = int(name)
        if 1 <= index <= len(decks):
            return decks[index - 1]
        raise DeckIndexOutOfRange(index, len(decks))
    resolution = library.resolve(name)
    if resolution.deck is not None:
        return resolution.deck
    if resolution.candidates:
        raise DeckAmbiguous(
            name, [candidate.name for candidate in resolution.candidates]
        )
    raise DeckNotFound(name)


def parse_draw_args(library: DeckLibrary, value: str) -> Optional[DrawArgs]:
    """解析 ``.draw`` 的抽取参数；空参数返回 None（列表入口）。

    Raises:
        DeckNotFound / DeckAmbiguous / DeckIndexOutOfRange / DeckCountOutOfRange
    """
    value = _normalize(value)
    if not value:
        return None

    # 整个参数精确命中牌堆名时，不拆次数（避免「示例牌堆22」被拆成 22 次）
    exact = library.exact(value)
    if exact is not None:
        return DrawArgs(deck=exact, times=1, replace=False)

    replace, core = _consume_replacement(value)
    if not core:
        return None

    exact = library.exact(core)
    if exact is not None:
        return DrawArgs(deck=exact, times=1, replace=replace)

    # N#名称
    match = re.match(r"^(\d+)#\s*(.+)$", core)
    if match:
        times = int(match.group(1))
        _check_times(times)
        name = match.group(2).strip()
        return DrawArgs(deck=_resolve_deck(library, name), times=times, replace=replace)

    # 名称 N
    match = re.match(r"^(.*?)\s+(\d+)$", core)
    if match:
        name = match.group(1).strip()
        times = int(match.group(2))
        _check_times(times)
        if not name:
            return None
        return DrawArgs(deck=_resolve_deck(library, name), times=times, replace=replace)

    return DrawArgs(deck=_resolve_deck(library, core), times=1, replace=replace)


# ── 展示 ────────────────────────────────────────────────────────────────


def _format_list_item(deck: Deck, index: int) -> str:
    return text.TXT_DECK_LIST_ITEM.format(
        index=index, name=deck.name, count=deck.count
    )


def _format_candidate(deck: Deck) -> str:
    return text.TXT_DECK_CANDIDATE.format(name=deck.name, count=deck.count)


def _list_pages(library: DeckLibrary) -> int:
    return max(1, (len(library.visible()) + _LIST_PAGE_SIZE - 1) // _LIST_PAGE_SIZE)


def _format_list(library: DeckLibrary, page: int = 1) -> str:
    decks = library.visible()
    pages = _list_pages(library)
    start = (page - 1) * _LIST_PAGE_SIZE
    shown = decks[start : start + _LIST_PAGE_SIZE]
    lines: list[str] = [text.TXT_DECK_LIST_CUSTOM.format(count=len(decks))]
    if shown:
        lines.extend(
            _format_list_item(deck, start + offset)
            for offset, deck in enumerate(shown, start=1)
        )
        if pages > 1:
            lines.append(text.TXT_DECK_LIST_PAGE.format(page=page, pages=pages))
    else:
        lines.append(text.TXT_DECK_LIST_EMPTY)

    lines.append(text.TXT_DECK_LIST_FOOTER)
    return "\n".join(lines)


def _format_detail(deck: Deck) -> str:
    lines = [text.TXT_DECK_DETAIL_HEADER.format(name=deck.name)]
    lines.append(text.TXT_DECK_DETAIL_LINE.format(label="条目", value=f"{deck.count} 条"))
    if deck.image_count:
        lines.append(
            text.TXT_DECK_DETAIL_LINE.format(label="图片", value=f"{deck.image_count} 张")
        )
    meta = deck.meta
    for label, value in (
        ("作者", meta.author),
        ("版本", meta.version),
        ("许可", meta.license),
        ("来源", meta.source),
        ("简介", meta.brief),
    ):
        if value:
            lines.append(text.TXT_DECK_DETAIL_LINE.format(label=label, value=value))
    lines.append(text.TXT_DECK_DETAIL_HINT.format(name=deck.name))
    return "\n".join(lines)


def _format_not_found(library: DeckLibrary, name: str) -> str:
    lines = [text.TXT_DECK_NOT_FOUND.format(name=name)]
    suggestions = library.suggestions(name)
    if suggestions:
        lines.append(text.TXT_DECK_SUGGEST.format(names="、".join(suggestions)))
    return "\n".join(lines)


def _format_ambiguous(name: str, candidates: list[str]) -> str:
    shown = candidates[:_LIST_SHOW_LIMIT]
    body = text.TXT_DECK_AMBIGUOUS.format(name=name, names="、".join(shown))
    if len(candidates) > len(shown):
        body += "\n" + text.TXT_DECK_AMBIGUOUS_MORE.format(
            total=len(candidates), shown=len(shown)
        )
    return body


def _format_search(library: DeckLibrary, keyword: str) -> str:
    matches = library.search(keyword, limit=None)
    if not matches:
        lines = [text.TXT_DECK_SEARCH_NONE.format(keyword=keyword)]
        suggestions = library.suggestions(keyword)
        if suggestions:
            lines.append(text.TXT_DECK_SUGGEST.format(names="、".join(suggestions)))
        return "\n".join(lines)
    shown = matches[:_LIST_SHOW_LIMIT]
    if len(matches) > len(shown):
        header = text.TXT_DECK_SEARCH_HEADER_MORE.format(
            keyword=keyword, total=len(matches), shown=len(shown)
        )
    else:
        header = text.TXT_DECK_SEARCH_HEADER.format(
            keyword=keyword, count=len(matches)
        )
    lines = [header]
    lines.extend(_format_candidate(deck) for deck in shown)
    return "\n".join(lines)


def _chunk_text(body: str, size: int = 20, max_chunks: int = 3) -> list[str]:
    """长文本按行分段（与 .查询 的 20 行 / 3 段约定一致）。"""
    lines = body.splitlines()
    if len(lines) <= size:
        return [body]
    chunks = [
        "\n".join(lines[index : index + size])
        for index in range(0, len(lines), size)
    ]
    if len(chunks) > max_chunks:
        chunks = chunks[:max_chunks]
        chunks[-1] = f"{chunks[-1]}\n{text.TXT_DECK_TRUNCATED}"
    return chunks


async def _send_text(body: str) -> None:
    """按分段规则发送纯文本并结束当前命令。"""
    chunks = _chunk_text(body)
    for chunk in chunks[:-1]:
        await deck_matcher.send(chunk)
    await deck_matcher.finish(chunks[-1])


def _header_for(entry_index: int, total: int, deck_name: str) -> str:
    if total == 1:
        return text.TXT_DECK_DRAW_HEADER.format(name=deck_name)
    return text.TXT_DECK_DRAW_MULTI_HEADER.format(
        name=deck_name, index=entry_index, total=total
    )


async def _build_image_message(
    header: str,
    entry: RenderedEntry,
    library: DeckLibrary,
    budget: dict[str, int],
) -> Message:
    """把一条含图片的结果组装为 OneBot Message。"""
    message = Message()
    message.append(MessageSegment.text(f"{header}\n"))
    last_text = f"{header}\n"
    for part in entry.parts:
        if isinstance(part, DeckTextPart):
            if part.text:
                message.append(MessageSegment.text(part.text))
                last_text = part.text
            continue
        if not isinstance(part, DeckImagePart):
            continue
        try:
            image = await asyncio.to_thread(
                load_image, part.rel_path, library.image_roots()
            )
        except DeckImageError as exc:
            placeholder = (
                text.TXT_DECK_IMAGE_MISSING
                if exc.missing
                else text.TXT_DECK_IMAGE_BAD
            )
            message.append(MessageSegment.text(placeholder.format(name=part.filename)))
            last_text = placeholder.format(name=part.filename)
            continue
        if budget["bytes"] + len(image.data) > MAX_TOTAL_IMAGE_BYTES:
            if not budget.get("warned"):
                message.append(
                    MessageSegment.text(text.TXT_DECK_IMAGE_TOTAL_TOO_LARGE)
                )
                last_text = text.TXT_DECK_IMAGE_TOTAL_TOO_LARGE
                budget["warned"] = True
            continue
        if not last_text.endswith("\n"):
            message.append(MessageSegment.text("\n"))
        message.append(MessageSegment.image(image.data))
        last_text = ""
        budget["bytes"] += len(image.data)
    return message


async def _send_draw_result(
    result: DrawResult,
    deck: Deck,
    library: DeckLibrary,
) -> None:
    """发送抽取结果：纯文字合并，含图片逐条发送。"""
    entries: list[RenderedEntry] = result.entries
    if not entries:
        await deck_matcher.finish(text.TXT_DECK_EMPTY.format(name=deck.name))

    if not result.has_image:
        if len(entries) == 1:
            body = (
                text.TXT_DECK_DRAW_HEADER.format(name=deck.name)
                + "\n"
                + entries[0].text
            )
        else:
            lines = [
                text.TXT_DECK_DRAW_MULTI_TITLE.format(
                    name=deck.name, count=len(entries)
                )
            ]
            lines.extend(
                text.TXT_DECK_DRAW_ITEM.format(index=index, text=entry.text)
                for index, entry in enumerate(entries, start=1)
            )
            body = "\n".join(lines)
        if result.exhausted:
            body += "\n" + text.TXT_DECK_EXHAUSTED.format(count=len(entries))
        await _send_text(body)
        return

    budget = {"bytes": 0}
    messages: list[Message] = []
    for index, entry in enumerate(entries, start=1):
        header = _header_for(index, len(entries), deck.name)
        messages.append(
            await _build_image_message(header, entry, library, budget)
        )
    if result.exhausted:
        messages[-1].append(
            MessageSegment.text(
                "\n" + text.TXT_DECK_EXHAUSTED.format(count=len(entries))
            )
        )
    for message in messages[:-1]:
        await deck_matcher.send(message)
    await deck_matcher.finish(messages[-1])


# ── 命令入口 ────────────────────────────────────────────────────────────


@deck_matcher.handle()
async def handle_draw(event: MessageEvent) -> None:
    """处理 .draw / .抽牌 / .牌堆。"""
    library = await get_library()
    rest = _normalize(base.get_command_rest(event) or "")

    if not rest:
        await _send_text(_format_list(library))

    first, _, tail = rest.partition(" ")
    tail = tail.strip()

    if first == "列表":
        page = 1
        if tail:
            if not tail.isdecimal():
                await deck_matcher.finish(text.TXT_DECK_LIST_PAGE_USAGE)
            page = int(tail)
            pages = _list_pages(library)
            if page < 1 or page > pages:
                await deck_matcher.finish(
                    text.TXT_DECK_LIST_PAGE_RANGE.format(pages=pages)
                )
        await _send_text(_format_list(library, page))
    if first == "搜索":
        if not tail:
            await deck_matcher.finish(text.TXT_DECK_USAGE)
        await _send_text(_format_search(library, tail))
    if first == "详情":
        if not tail:
            await deck_matcher.finish(text.TXT_DECK_USAGE)
        try:
            deck = _resolve_deck(library, tail)
        except DeckNotFound:
            await deck_matcher.finish(_format_not_found(library, tail))
        except DeckIndexOutOfRange as exc:
            await deck_matcher.finish(
                text.TXT_DECK_INDEX_RANGE.format(index=exc.index, total=exc.total)
            )
        except DeckAmbiguous as exc:
            await deck_matcher.finish(_format_ambiguous(exc.name, exc.candidates))
        await _send_text(_format_detail(deck))
    if first == "重载":
        if isinstance(event, GroupMessageEvent) or not base.is_superuser(event):
            await deck_matcher.finish(text.TXT_DECK_MASTER_ONLY)
        await library.reload()
        lines = [
            text.TXT_DECK_RELOAD_OK.format(custom=len(library.visible()))
        ]
        lines.append(text.TXT_DECK_RELOAD_DIR.format(path=library.custom_dir))
        errors = library.errors
        if errors:
            lines.append(text.TXT_DECK_RELOAD_ERRORS.format(count=len(errors)))
            for error in errors[:3]:
                lines.append(
                    text.TXT_DECK_RELOAD_ERROR_LINE.format(
                        file=error.file.name, message=error.message
                    )
                )
            if len(errors) > 3:
                lines.append(text.TXT_DECK_RELOAD_MORE)
        await _send_text("\n".join(lines))

    try:
        args = parse_draw_args(library, rest)
    except DeckCountOutOfRange:
        await deck_matcher.finish(text.TXT_DECK_COUNT_RANGE)
    except DeckNotFound as exc:
        await deck_matcher.finish(_format_not_found(library, exc.name))
    except DeckIndexOutOfRange as exc:
        await deck_matcher.finish(
            text.TXT_DECK_INDEX_RANGE.format(index=exc.index, total=exc.total)
        )
    except DeckAmbiguous as exc:
        await deck_matcher.finish(_format_ambiguous(exc.name, exc.candidates))

    if args is None:
        await deck_matcher.finish(text.TXT_DECK_USAGE)

    try:
        result = draw_cards(
            library, args.deck, args.times, replace=args.replace
        )
    except DeckEmpty:
        await deck_matcher.finish(text.TXT_DECK_EMPTY.format(name=args.deck.name))
    except DeckCountOutOfRange:
        await deck_matcher.finish(text.TXT_DECK_COUNT_RANGE)

    await _send_draw_result(result, args.deck, library)
