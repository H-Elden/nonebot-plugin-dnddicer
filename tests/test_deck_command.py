"""``.draw`` 牌堆命令测试（别名、解析、列表、详情、图片与重载）。"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebug import App

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.commands import deck as deck_command
from nonebot_plugin_dnddicer.commands.deck import deck_matcher, parse_draw_args
from nonebot_plugin_dnddicer.deck.errors import DeckCountOutOfRange, DeckIndexOutOfRange
from nonebot_plugin_dnddicer.deck.library import DeckLibrary
from nonebot_plugin_dnddicer.deck.runtime import (
    SequenceDeckRuntime,
    reset_runtime,
    set_runtime,
)

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nXQAAAAASUVORK5CYII="
)


@pytest.fixture
async def library(tmp_path: Path) -> DeckLibrary:
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "decks.json").write_text(
        json.dumps(
            {
                "甲": ["a1", "a2", "a3"],
                "乙": ["b1", "b2"],
                "图": ["文字\n[img:images/a.png]"],
                "图缺": ["[img:images/missing.png]"],
                "_隐藏": ["hidden"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    images = custom / "images"
    images.mkdir()
    (images / "a.png").write_bytes(PNG_1PX)
    lib = DeckLibrary(custom_dir=custom)
    await lib.reload()
    original = deck_command._library
    deck_command.set_library(lib)
    try:
        yield lib
    finally:
        deck_command.set_library(original)


@pytest.fixture
async def big_library(tmp_path: Path) -> DeckLibrary:
    """12 个同名前缀牌堆，用于分页与搜索截断。"""
    custom = tmp_path / "big"
    custom.mkdir()
    (custom / "decks.json").write_text(
        json.dumps(
            {f"牌堆{index:02d}": ["x"] for index in range(1, 13)},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    lib = DeckLibrary(custom_dir=custom)
    await lib.reload()
    original = deck_command._library
    deck_command.set_library(lib)
    try:
        yield lib
    finally:
        deck_command.set_library(original)


@pytest.fixture
async def numeric_library(tmp_path: Path) -> DeckLibrary:
    """牌堆名本身是数字时，精确名优先于列表编号。"""
    custom = tmp_path / "numeric"
    custom.mkdir()
    (custom / "decks.json").write_text(
        json.dumps({"1": ["数字一"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    lib = DeckLibrary(custom_dir=custom)
    await lib.reload()
    original = deck_command._library
    deck_command.set_library(lib)
    try:
        yield lib
    finally:
        deck_command.set_library(original)


def _event(text: str, *, private: bool = False):
    if private:
        return fake_private_message_event_v11(message=Message(text))
    return fake_group_message_event_v11(message=Message(text), group_id=87654383)


async def _expect(app: App, event, expected):
    async with app.test_matcher(deck_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_parse_draw_args(library: DeckLibrary):
    args = parse_draw_args(library, "甲")
    assert (args.deck.name, args.times, args.replace) == ("甲", 1, False)
    args = parse_draw_args(library, "甲 2")
    assert (args.times, args.replace) == (2, False)
    args = parse_draw_args(library, "2#甲")
    assert (args.times, args.replace) == (2, False)
    args = parse_draw_args(library, "甲 2 放回")
    assert (args.times, args.replace) == (2, True)
    args = parse_draw_args(library, "甲 不放回")
    assert (args.times, args.replace) == (1, False)
    args = parse_draw_args(library, "甲 2 放回 不放回")
    assert (args.times, args.replace) == (2, False)

    # 列表编号：按 visible() 排序 1-based
    args = parse_draw_args(library, "1")
    assert (args.deck.name, args.times) == ("乙", 1)
    args = parse_draw_args(library, "1 2")
    assert (args.deck.name, args.times) == ("乙", 2)
    args = parse_draw_args(library, "2#1")
    assert (args.deck.name, args.times) == ("乙", 2)
    args = parse_draw_args(library, "4 放回")
    assert (args.deck.name, args.replace) == ("甲", True)

    with pytest.raises(DeckIndexOutOfRange):
        parse_draw_args(library, "0")
    with pytest.raises(DeckIndexOutOfRange):
        parse_draw_args(library, "99")

    with pytest.raises(DeckCountOutOfRange):
        parse_draw_args(library, "甲 11")
    with pytest.raises(DeckCountOutOfRange):
        parse_draw_args(library, "甲 0")


@pytest.mark.asyncio
async def test_list_search_detail_and_errors(app: App, library: DeckLibrary):
    await _expect(
        app,
        _event(".draw"),
        "自定义牌堆（4）：\n"
        "- 1. 乙（2 条）\n"
        "- 2. 图（1 条）\n"
        "- 3. 图缺（1 条）\n"
        "- 4. 甲（3 条）\n"
        "用 .draw 编号 或 .draw 名称 [次数] 抽取；.draw 搜索 关键词 搜索。",
    )
    await _expect(
        app,
        _event(".牌堆"),
        "自定义牌堆（4）：\n"
        "- 1. 乙（2 条）\n"
        "- 2. 图（1 条）\n"
        "- 3. 图缺（1 条）\n"
        "- 4. 甲（3 条）\n"
        "用 .draw 编号 或 .draw 名称 [次数] 抽取；.draw 搜索 关键词 搜索。",
    )
    await _expect(
        app,
        _event(".draw 搜索 甲"),
        "搜索「甲」（1 个）：\n- 甲（3 条）",
    )
    await _expect(
        app,
        _event(".draw 详情 甲"),
        "牌堆：甲\n条目：3 条\n用 .draw 甲 [次数] 抽取。",
    )
    await _expect(
        app,
        _event(".draw 不存在"),
        "找不到牌堆「不存在」。",
    )
    await _expect(
        app,
        _event(".draw 甲 11"),
        "次数需要在 1 到 10 之间。",
    )
    await _expect(
        app,
        _event(".draw 详情 1"),
        "牌堆：乙\n条目：2 条\n用 .draw 乙 [次数] 抽取。",
    )
    await _expect(app, _event(".draw 列表 abc"), "用法：.draw 列表 [页码]")
    await _expect(app, _event(".draw 列表 2"), "牌堆列表共 1 页。")
    await _expect(app, _event(".draw 列表 0"), "牌堆列表共 1 页。")
    await _expect(app, _event(".draw 重载"), "仅骰主私聊可用。")
    await _expect(app, _event(".draw 重载", private=True), "仅骰主私聊可用。")


@pytest.mark.asyncio
async def test_draw_by_index(app: App, library: DeckLibrary):
    token = set_runtime(SequenceDeckRuntime([1]))
    try:
        await _expect(app, _event(".draw 1"), "从【乙】抽到：\nb1")
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceDeckRuntime([1, 1]))
    try:
        await _expect(
            app,
            _event(".draw 1 2"),
            "从【乙】抽了 2 条：\n1. b1\n2. b2",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceDeckRuntime([1, 1, 1]))
    try:
        await _expect(
            app,
            _event(".draw 3#1"),
            "从【乙】抽了 2 条：\n1. b1\n2. b2\n（牌堆已抽完，本次只抽到 2 条。）",
        )
    finally:
        reset_runtime(token)

    await _expect(
        app,
        _event(".draw 0"),
        "没有第 0 个牌堆（共 4 个）。用 .draw 列表 查看编号。",
    )
    await _expect(
        app,
        _event(".draw 99"),
        "没有第 99 个牌堆（共 4 个）。用 .draw 列表 查看编号。",
    )


@pytest.mark.asyncio
async def test_numeric_deck_name_beats_index(app: App, numeric_library: DeckLibrary):
    token = set_runtime(SequenceDeckRuntime([1]))
    try:
        await _expect(app, _event(".draw 1"), "从【1】抽到：\n数字一")
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_list_pagination(app: App, big_library: DeckLibrary):
    first_page = "\n".join(
        f"- {index}. 牌堆{index:02d}（1 条）" for index in range(1, 11)
    )
    await _expect(
        app,
        _event(".draw"),
        "自定义牌堆（12）：\n"
        f"{first_page}\n"
        "第 1/2 页，用 .draw 列表 页码 翻页。\n"
        "用 .draw 编号 或 .draw 名称 [次数] 抽取；.draw 搜索 关键词 搜索。",
    )
    await _expect(
        app,
        _event(".draw 列表 2"),
        "自定义牌堆（12）：\n"
        "- 11. 牌堆11（1 条）\n"
        "- 12. 牌堆12（1 条）\n"
        "第 2/2 页，用 .draw 列表 页码 翻页。\n"
        "用 .draw 编号 或 .draw 名称 [次数] 抽取；.draw 搜索 关键词 搜索。",
    )
    await _expect(app, _event(".draw 列表 3"), "牌堆列表共 2 页。")


@pytest.mark.asyncio
async def test_search_truncated_shows_total(app: App, big_library: DeckLibrary):
    expected = (
        "搜索「牌堆」（共 12 个，仅显示前 10 个）：\n"
        + "\n".join(f"- 牌堆{index:02d}（1 条）" for index in range(1, 11))
    )
    await _expect(app, _event(".draw 搜索 牌堆"), expected)


@pytest.mark.asyncio
async def test_ambiguous_candidates_truncated(app: App, big_library: DeckLibrary):
    expected = (
        "牌堆「牌堆」匹配到多个："
        + "、".join(f"牌堆{index:02d}" for index in range(1, 11))
        + "\n请写得更完整一些。\n"
        "（共 12 个匹配，仅显示前 10 个；用 .draw 搜索 关键词 缩小范围。）"
    )
    await _expect(app, _event(".draw 牌堆"), expected)


@pytest.mark.asyncio
async def test_draw_text_and_aliases(app: App, library: DeckLibrary):
    token = set_runtime(SequenceDeckRuntime([1]))
    try:
        await _expect(app, _event(".draw 甲"), "从【甲】抽到：\na1")
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceDeckRuntime([1, 1]))
    try:
        await _expect(
            app,
            _event(".抽牌 甲 2"),
            "从【甲】抽了 2 条：\n1. a1\n2. a2",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_draw_image_and_missing(app: App, library: DeckLibrary):
    token = set_runtime(SequenceDeckRuntime([1]))
    try:
        expected = Message()
        expected += MessageSegment.text("从【图】抽到：\n")
        expected += MessageSegment.text("文字\n")
        expected += MessageSegment.image(PNG_1PX)
        await _expect(app, _event(".draw 图"), expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceDeckRuntime([1]))
    try:
        missing = Message()
        missing += MessageSegment.text("从【图缺】抽到：\n")
        missing += MessageSegment.text("【图片缺失：missing.png】")
        await _expect(app, _event(".draw 图缺"), missing)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_draw_counts_replace_and_exhaust(app: App, library: DeckLibrary):
    token = set_runtime(SequenceDeckRuntime([1, 1]))
    try:
        await _expect(
            app,
            _event(".draw 2#乙"),
            "从【乙】抽了 2 条：\n1. b1\n2. b2",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceDeckRuntime([1, 1]))
    try:
        await _expect(
            app,
            _event(".draw 乙 2 放回"),
            "从【乙】抽了 2 条：\n1. b1\n2. b1",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceDeckRuntime([1, 1, 1]))
    try:
        await _expect(
            app,
            _event(".draw 乙 3"),
            "从【乙】抽了 2 条：\n1. b1\n2. b2\n"
            "（牌堆已抽完，本次只抽到 2 条。）",
        )
    finally:
        reset_runtime(token)

    await _expect(app, _event(".draw 乙 0"), "次数需要在 1 到 10 之间。")


@pytest.mark.asyncio
async def test_reload_as_master(app: App, library: DeckLibrary, monkeypatch):
    monkeypatch.setattr(deck_command.base, "is_superuser", lambda event: True)
    await _expect(
        app,
        _event(".draw 重载", private=True),
        "牌堆已重载：自定义 4 个。\n"
        f"自定义牌堆目录：{library.custom_dir}",
    )
