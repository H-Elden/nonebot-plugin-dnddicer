"""零内置牌堆：发布包不携带任何牌堆文本或图片。"""

from __future__ import annotations

from pathlib import Path

import pytest

import nonebot_plugin_dnddicer
from nonebot_plugin_dnddicer.deck.library import DeckLibrary


def test_package_has_no_deck_data():
    data_dir = Path(nonebot_plugin_dnddicer.__file__).resolve().parent / "data"
    decks = data_dir / "decks"
    assert not decks.exists() or not any(path.is_file() for path in decks.rglob("*"))


@pytest.mark.asyncio
async def test_empty_library_has_no_decks(tmp_path: Path):
    library = DeckLibrary(custom_dir=tmp_path / "custom")
    await library.reload()
    assert library.visible() == []
    assert library.errors == []
