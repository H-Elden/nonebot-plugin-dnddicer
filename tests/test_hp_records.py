"""无卡 HP 记录数据层测试（hp_records.json，2026-10-23）。"""

from __future__ import annotations

import pytest

from nonebot_plugin_dnddicer.character.models import DNDCharacter, HPInfo
from nonebot_plugin_dnddicer.data import characters, hp_records


@pytest.fixture(autouse=True)
def _clean_store():
    from nonebot_plugin_dnddicer.data import get_data_file

    characters._cache = None
    hp_records._cache = None
    for name in ("cards.json", "hp_records.json"):
        path = get_data_file(name)
        if path.exists():
            path.write_text("{}", encoding="utf-8")
    yield
    characters._cache = None
    hp_records._cache = None


def _hp(cur: int, maximum: int = 0) -> HPInfo:
    info = HPInfo()
    info.initialize(cur, maximum)
    return info


@pytest.mark.asyncio
async def test_save_get_list_and_overwrite():
    await hp_records.save_hp_record("88", "99", _hp(20, 30))
    await hp_records.save_hp_record("88", "100", _hp(12, 12))
    await hp_records.save_hp_record("89", "99", _hp(5, 10))

    loaded = await hp_records.get_hp_record("88", "99")
    assert loaded is not None and loaded.get_info() == "HP:20/30"

    listed = await hp_records.list_hp_records("88")
    assert [(user_id, info.get_info()) for user_id, info in listed] == [
        ("99", "HP:20/30"),
        ("100", "HP:12/12"),
    ]

    await hp_records.save_hp_record("88", "99", _hp(18, 30))
    overwritten = await hp_records.get_hp_record("88", "99")
    assert overwritten is not None and overwritten.get_info() == "HP:18/30"


@pytest.mark.asyncio
async def test_delete_and_dirty_data():
    assert await hp_records.delete_hp_record("88", "99") is False
    await hp_records.save_hp_record("88", "99", _hp(20, 30))
    assert await hp_records.delete_hp_record("88", "99") is True
    assert await hp_records.get_hp_record("88", "99") is None

    # 脏数据在读取时按无记录处理，列表里跳过
    from nonebot_plugin_dnddicer.data import get_data_file

    path = get_data_file("hp_records.json")
    path.write_text(
        '{"schema_version": 1, "data": {"88:101": {"hp_cur": "坏数据"}}}',
        encoding="utf-8",
    )
    hp_records._cache = None
    assert await hp_records.get_hp_record("88", "101") is None
    assert await hp_records.list_hp_records("88") == []


@pytest.mark.asyncio
async def test_save_rolls_back_cache_when_dump_fails(monkeypatch):
    """落盘失败：内存缓存回滚，不留下写不进磁盘的新值。"""
    await hp_records.save_hp_record("88", "99", _hp(20, 30))

    async def _boom(_data):
        raise OSError("disk full")

    monkeypatch.setattr(hp_records, "_dump_locked", _boom)

    # 覆盖已有记录失败 → 缓存仍是旧值
    with pytest.raises(OSError):
        await hp_records.save_hp_record("88", "99", _hp(1, 30))
    loaded = await hp_records.get_hp_record("88", "99")
    assert loaded is not None and loaded.get_info() == "HP:20/30"

    # 新建记录失败 → 缓存里不留半成品
    with pytest.raises(OSError):
        await hp_records.save_hp_record("88", "100", _hp(1, 10))
    assert await hp_records.get_hp_record("88", "100") is None


@pytest.mark.asyncio
async def test_bind_card_discards_hp_record():
    await hp_records.save_hp_record("88", "99", _hp(20, 30))
    card_id = await characters.create_card(
        "99", "卡A", "88",
        DNDCharacter(group_id="88", user_id="99", name="老王", is_init=True),
    )
    assert await hp_records.get_hp_record("88", "99") is not None

    await characters.bind_card("88", "99", card_id)

    assert await hp_records.get_hp_record("88", "99") is None
    loaded = await characters.get_character("88", "99")
    assert loaded is not None and loaded.name == "老王"
