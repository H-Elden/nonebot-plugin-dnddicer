"""Dice! JSON 牌堆解析测试。"""

from __future__ import annotations

import json
from pathlib import Path

from nonebot_plugin_dnddicer.deck.parser import (
    MAX_TEXT_CHARS,
    MAX_WEIGHT,
    parse_deck_file,
)


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_parse_metadata_weights_and_hidden(tmp_path: Path):
    path = _write(
        tmp_path,
        "deck.json",
        {
            "_title": ["测试牌堆"],
            "_author": ["作者"],
            "_version": ["1.2"],
            "_license": ["MIT"],
            "_source": ["原创"],
            "_brief": ["简介"],
            "_export": ["主牌组"],
            "主牌组": ["::3::第一条", "第二条"],
            "_隐藏": ["隐藏条目"],
            "未导出": ["不应可见"],
        },
    )
    decks, errors = parse_deck_file(path)
    assert errors == []
    by_name = {deck.name: deck for deck in decks}
    assert set(by_name) == {"主牌组", "_隐藏", "未导出"}
    main = by_name["主牌组"]
    assert main.hidden is False
    assert main.count == 2
    assert main.items[0].weight == 3
    assert main.items[1].weight == 1
    assert main.meta.title == "测试牌堆"
    assert main.meta.author == "作者"
    assert by_name["_隐藏"].hidden is True
    assert by_name["未导出"].hidden is True


def test_parse_invalid_and_reserved(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    decks, errors = parse_deck_file(bad)
    assert decks == []
    assert errors and "JSON 解析失败" in errors[0].message

    reserved = _write(
        tmp_path,
        "reserved.json",
        {"搜索": ["条目"], "正常": ["条目"]},
    )
    decks, errors = parse_deck_file(reserved)
    assert [deck.name for deck in decks] == ["正常"]
    assert any("保留子命令" in error.message for error in errors)


def test_parse_limits(tmp_path: Path):
    long_text = "长" * (MAX_TEXT_CHARS + 10)
    path = _write(
        tmp_path,
        "limits.json",
        {
            "牌组": [
                f"::{MAX_WEIGHT + 1}::{long_text}",
            ]
        },
    )
    decks, errors = parse_deck_file(path)
    assert errors == []
    item = decks[0].items[0]
    assert item.weight == MAX_WEIGHT
    assert len(item.raw) == MAX_TEXT_CHARS


def test_parse_non_string_and_empty(tmp_path: Path):
    path = _write(
        tmp_path,
        "mixed.json",
        {
            "牌组": ["好条目", 42, "", "另一条"],
            "空牌组": [],
        },
    )
    decks, errors = parse_deck_file(path)
    assert [deck.name for deck in decks] == ["牌组"]
    assert decks[0].count == 2
    assert errors == []
