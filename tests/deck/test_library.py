"""牌堆库加载、同名覆盖、搜索与错误汇总测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nonebot_plugin_dnddicer.deck.library import DeckLibrary


def _write(directory: Path, name: str, data: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_load_resolve_search_and_hidden(tmp_path: Path):
    custom = tmp_path / "custom"
    _write(
        custom,
        "decks.json",
        {"同名": ["A"], "同门": ["B"], "甲": ["A1"], "乙": ["B1"], "_隐藏": ["H"]},
    )

    library = DeckLibrary(custom_dir=custom)
    await library.reload()

    assert library.errors == []
    assert [deck.name for deck in library.visible()] == ["乙", "同名", "同门", "甲"]
    assert library.exact("同名").items[0].raw == "A"
    assert library.exact("_隐藏") is None
    assert library.exact_any("_隐藏") is not None

    resolution = library.resolve("同")
    assert resolution.deck is None
    assert {deck.name for deck in resolution.candidates} == {"同名", "同门"}

    # 精确优先：搜索「同名」只返回一条，且排在最前
    assert library.search("同名")[0].name == "同名"
    assert library.suggestions("同明")

    assert library.custom_dir == custom
    assert library.image_roots() == [custom / "images"]


@pytest.mark.asyncio
async def test_duplicate_name_in_later_file_wins(tmp_path: Path):
    custom = tmp_path / "custom"
    _write(custom, "a.json", {"同名": ["旧"]})
    _write(custom, "b.json", {"同名": ["新"]})

    library = DeckLibrary(custom_dir=custom)
    await library.reload()

    assert library.exact("同名").items[0].raw == "新"
    assert any("同名" in error.message for error in library.errors)


@pytest.mark.asyncio
async def test_errors_are_reported(tmp_path: Path):
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "bad.json").write_text("{bad", encoding="utf-8")

    library = DeckLibrary(custom_dir=custom)
    await library.reload()

    assert library.visible() == []
    assert library.errors
    assert library.errors[0].file.name == "bad.json"
