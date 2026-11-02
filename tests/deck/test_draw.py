"""牌堆抽取：不放回、权重、嵌套、表达式与图片标记。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nonebot_plugin_dnddicer.deck.draw import draw
from nonebot_plugin_dnddicer.deck.errors import DeckCountOutOfRange, DeckEmpty
from nonebot_plugin_dnddicer.deck.library import DeckLibrary
from nonebot_plugin_dnddicer.deck.models import Deck, DeckImagePart, DeckItem, DeckMeta
from nonebot_plugin_dnddicer.deck.runtime import (
    SequenceDeckRuntime,
    reset_runtime,
    set_runtime,
)
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import (
    SequenceRuntime,
    reset_runtime as reset_dice_runtime,
    set_runtime as set_dice_runtime,
)


async def _library(tmp_path: Path, decks: dict) -> DeckLibrary:
    custom = tmp_path / "custom"
    custom.mkdir(parents=True, exist_ok=True)
    (custom / "decks.json").write_text(
        json.dumps(decks, ensure_ascii=False), encoding="utf-8"
    )
    library = DeckLibrary(custom_dir=custom)
    await library.reload()
    return library


@pytest.mark.asyncio
async def test_no_replacement_and_exhaustion(tmp_path: Path):
    library = await _library(tmp_path, {"A": ["1", "2", "3"]})
    deck = library.exact("A")
    assert deck is not None

    token = set_runtime(SequenceDeckRuntime([1, 1, 1]))
    try:
        result = draw(library, deck, 3)
    finally:
        reset_runtime(token)
    assert [entry.text for entry in result.entries] == ["1", "2", "3"]
    assert result.exhausted is False

    token = set_runtime(SequenceDeckRuntime([1, 1, 1, 1]))
    try:
        result = draw(library, deck, 4)
    finally:
        reset_runtime(token)
    assert result.count == 3
    assert result.exhausted is True


@pytest.mark.asyncio
async def test_replace_and_weight(tmp_path: Path):
    library = await _library(
        tmp_path,
        {"A": ["1", "2"], "W": ["::1::A", "::3::B"]},
    )
    deck = library.exact("A")
    token = set_runtime(SequenceDeckRuntime([1, 2, 1]))
    try:
        result = draw(library, deck, 3, replace=True)
    finally:
        reset_runtime(token)
    assert [entry.text for entry in result.entries] == ["1", "2", "1"]

    weighted = library.exact("W")
    token = set_runtime(SequenceDeckRuntime([1, 2, 3, 4]))
    try:
        result = draw(library, weighted, 4, replace=True)
    finally:
        reset_runtime(token)
    assert [entry.text for entry in result.entries] == ["A", "B", "B", "B"]


@pytest.mark.asyncio
async def test_nested_no_replacement_and_replace(tmp_path: Path):
    library = await _library(
        tmp_path,
        {
            "C": ["c1", "c2"],
            "N": ["{C}", "{C}"],
            "R": ["{%C}", "{%C}"],
        },
    )

    nested = library.exact("N")
    token = set_runtime(SequenceDeckRuntime([1, 1, 2, 2]))
    try:
        result = draw(library, nested, 2)
    finally:
        reset_runtime(token)
    assert [entry.text for entry in result.entries] == ["c1", "c2"]

    replace = library.exact("R")
    token = set_runtime(SequenceDeckRuntime([1, 1, 1, 1]))
    try:
        result = draw(library, replace, 2)
    finally:
        reset_runtime(token)
    assert [entry.text for entry in result.entries] == ["c1", "c1"]


@pytest.mark.asyncio
async def test_expression_image_and_placeholders(tmp_path: Path):
    library = await _library(
        tmp_path,
        {
            "E": ["[2d6]"],
            "I": ["文字\n[img:images/a.png]"],
            "X": ["{X}"],
            "U": ["{不存在}"],
        },
    )

    dice_token = set_dice_runtime(SequenceRuntime([3, 4]))
    try:
        expression = library.exact("E")
        result = draw(library, expression, 1)
    finally:
        reset_dice_runtime(dice_token)
    assert result.entries[0].text == "2D6=7"

    image = library.exact("I")
    result = draw(library, image, 1)
    assert result.has_image is True
    assert result.entries[0].text == "文字\n"
    assert any(
        isinstance(part, DeckImagePart) and part.rel_path == "images/a.png"
        for part in result.entries[0].parts
    )

    cycle = library.exact("X")
    assert "【循环引用：X】" in draw(library, cycle, 1).entries[0].text
    unknown = library.exact("U")
    assert "【未知牌组：不存在】" in draw(library, unknown, 1).entries[0].text


@pytest.mark.asyncio
async def test_empty_and_count_limits(tmp_path: Path):
    library = DeckLibrary(custom_dir=tmp_path / "custom")
    empty = Deck(
        name="空",
        items=[],
        file=tmp_path / "x.json",
        meta=DeckMeta(),
    )
    with pytest.raises(DeckEmpty):
        draw(library, empty, 1)

    deck = Deck(
        name="单条",
        items=[DeckItem("entry")],
        file=tmp_path / "x.json",
        meta=DeckMeta(),
    )
    with pytest.raises(DeckCountOutOfRange):
        draw(library, deck, 11)
