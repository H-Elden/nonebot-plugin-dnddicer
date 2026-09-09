"""数据层 schema_version 版本化测试（data/schema.py + 各存储模块）。

覆盖：v0 裸字典自动读取并随首次写入升级 v1、未来主版本拒绝读取、
损坏文件按空处理、v1 包装结构正确。
"""

import json

import pytest

from fake_event import fake_group_message_event_v11

from nonebot_plugin_dnddicer.character.models import DNDCharacter
from nonebot_plugin_dnddicer.data import get_data_file


@pytest.fixture(autouse=True)
def _clean_stores():
    """每个用例前清空各 JSON 存储（缓存 + 文件）。"""
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import group_config as _gc
    from nonebot_plugin_dnddicer.data import initiative as _init

    for module in (_chars, _gc, _init):
        module._cache = None
    for name in ("characters.json", "group_config.json", "initiative.json"):
        path = get_data_file(name)
        if path.exists():
            path.write_text("{}", encoding="utf-8")
    yield


def _write_raw(filename: str, document) -> None:
    get_data_file(filename).write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )


def _read_document(filename: str) -> dict:
    return json.loads(get_data_file(filename).read_text(encoding="utf-8"))


# =========================================================================
# 角色卡存储 characters.json
# =========================================================================


async def _sample_char() -> DNDCharacter:
    return DNDCharacter(group_id="88", user_id="99", name="老王", is_init=True)


@pytest.mark.asyncio
async def test_characters_legacy_v0_read_and_upgrade():
    """v0 裸字典可读；再次写入后文件自动升级为 v1 包装。"""
    from nonebot_plugin_dnddicer.data import characters as chars

    char = await _sample_char()
    # 先正常保存（得到合法条目），再手工把文件退化为 v0 裸字典形态
    await chars.save_character(char)
    document = _read_document("characters.json")
    raw_v0 = document["data"]
    _write_raw("characters.json", raw_v0)
    chars._cache = None

    loaded = await chars.get_character("88", "99")
    assert loaded is not None and loaded.name == "老王"

    # 再次写入 → v1 包装，且数据可继续读出
    await chars.save_character(char)
    upgraded = _read_document("characters.json")
    assert upgraded["schema_version"] == 1
    assert "88:99" in upgraded["data"]
    chars._cache = None
    assert (await chars.get_character("88", "99")).name == "老王"


@pytest.mark.asyncio
async def test_characters_future_version_rejected():
    """未知未来主版本 → 按空数据处理（拒绝降级写入读取）。"""
    from nonebot_plugin_dnddicer.data import characters as chars

    _write_raw("characters.json", {"schema_version": 99, "data": {"x": 1}})
    chars._cache = None
    assert await chars.get_character("88", "99") is None


@pytest.mark.asyncio
async def test_characters_corrupt_file_empty():
    """损坏 JSON → 空数据不崩溃。"""
    from nonebot_plugin_dnddicer.data import characters as chars

    get_data_file("characters.json").write_text("{not json", encoding="utf-8")
    chars._cache = None
    assert await chars.get_character("88", "99") is None


# =========================================================================
# 群配置 group_config.json
# =========================================================================


@pytest.mark.asyncio
async def test_group_config_legacy_upgrade_and_structure():
    """v0 裸字典读取 + 写入升级 v1（含 set 后字段仍可读）。"""
    from nonebot_plugin_dnddicer.data import group_config as gc

    _write_raw("group_config.json", {"12345": {"default_dice": "D20"}})
    gc._cache = None
    assert await gc.get_group_config(12345) == {"default_dice": "D20"}

    await gc.set_group_config_field(12345, "default_dice", "D100")
    document = _read_document("group_config.json")
    assert document["schema_version"] == 1
    assert document["data"]["12345"]["default_dice"] == "D100"
    gc._cache = None
    assert await gc.get_group_config("12345") == {"default_dice": "D100"}


# =========================================================================
# 先攻表 initiative.json（新存储直接 v1）
# =========================================================================


@pytest.mark.asyncio
async def test_initiative_schema_wrapper():
    """initiative.json 存取为 v1 包装结构。"""
    from nonebot_plugin_dnddicer.data.initiative import (
        clear_init_list,
        get_init_list,
        save_init_list,
    )
    from nonebot_plugin_dnddicer.initiative.models import InitList

    init = InitList(group_id="55")
    init.add_entity("地精", "", 12)
    await save_init_list(init)

    document = _read_document("initiative.json")
    assert document["schema_version"] == 1
    assert "55" in document["data"]

    loaded = await get_init_list("55")
    assert loaded is not None and loaded.entities[0].name == "地精"
    await clear_init_list("55")
    assert await get_init_list("55") is None
