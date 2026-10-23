"""角色卡库数据层与解析拆分测试（2026-10-23 卡库化）。"""

from __future__ import annotations

import pytest

from nonebot_plugin_dnddicer.character.models import DNDCharacter
from nonebot_plugin_dnddicer.character.services import (
    CharacterService,
    gen_template_char,
    parse_template_to_dict,
)
from nonebot_plugin_dnddicer.data import characters


@pytest.fixture(autouse=True)
def _clean_cards():
    from nonebot_plugin_dnddicer.data import get_data_file

    characters._cache = None
    path = get_data_file("cards.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")
    yield
    characters._cache = None


def _char(name: str = "老王") -> DNDCharacter:
    return DNDCharacter(group_id="", user_id="", name=name, is_init=True)


@pytest.mark.asyncio
async def test_create_bind_and_read():
    card_id = await characters.create_card("99", "卡A", "88", _char())
    assert await characters.get_card(card_id) is not None
    found = await characters.get_card_by_name("99", "卡A")
    assert found is not None and found[0] == card_id

    await characters.bind_card("88", "99", card_id)
    loaded = await characters.get_character("88", "99")
    assert loaded is not None and loaded.name == "老王"
    assert loaded.card_id == card_id

    grouped = await characters.list_characters_by_group("88")
    assert [item.name for item in grouped] == ["老王"]
    owned = await characters.list_cards_by_owner("99")
    assert [(name, character.name) for _cid, name, character in owned] == [
        ("卡A", "老王")
    ]


@pytest.mark.asyncio
async def test_owner_isolation_and_unbind():
    card_id = await characters.create_card("99", "卡A", "88", _char())
    await characters.bind_card("88", "99", card_id)

    assert await characters.get_character("88", "100") is None
    assert await characters.get_card_by_name("100", "卡A") is None
    with pytest.raises(characters.CardNotFound):
        await characters.bind_card("88", "100", card_id)

    assert await characters.unbind_card("88", "99") == card_id
    assert await characters.get_character("88", "99") is None
    assert await characters.get_bound_card_id("88", "99") is None
    assert await characters.unbind_card("88", "99") is None


@pytest.mark.asyncio
async def test_bind_replaces_previous_and_lists_groups():
    first = await characters.create_card("99", "卡A", "88", _char("甲"))
    second = await characters.create_card("99", "卡B", "88", _char("乙"))
    assert await characters.bind_card("88", "99", first) is None
    assert await characters.bind_card("88", "99", second) == first
    loaded = await characters.get_character("88", "99")
    assert loaded is not None and loaded.name == "乙"
    assert await characters.list_bound_groups(first) == []
    assert await characters.list_bound_groups(second) == ["88"]


@pytest.mark.asyncio
async def test_card_name_validation_and_duplicate():
    for bad in ("", " ", "卡" * 21, "带 空格", "带$符", "带@符", "列表"):
        with pytest.raises(characters.CardNameInvalid):
            await characters.create_card("99", bad, "88", _char())

    await characters.create_card("99", "卡A", "88", _char())
    with pytest.raises(characters.CardNameTaken):
        await characters.create_card("99", "卡A", "88", _char())


@pytest.mark.asyncio
async def test_card_limit():
    for index in range(10):
        await characters.create_card(
            "99", f"卡{index}", "88", _char(f"角色{index}")
        )
    assert await characters.count_cards("99") == 10
    with pytest.raises(characters.CardLimitReached):
        await characters.create_card("99", "第11张", "88", _char("溢出"))


@pytest.mark.asyncio
async def test_rename_and_delete_cleanup():
    card_id = await characters.create_card("99", "卡A", "88", _char())
    await characters.bind_card("88", "99", card_id)
    assert await characters.rename_card(card_id, "新卡名") == "新卡名"
    assert (await characters.get_card_by_name("99", "新卡名")) is not None

    other = await characters.create_card("99", "另一张", "88", _char("乙"))
    with pytest.raises(characters.CardNameTaken):
        await characters.rename_card(other, "新卡名")

    await characters.delete_card(card_id)
    assert await characters.get_card(card_id) is None
    assert await characters.get_character("88", "99") is None
    assert await characters.list_bound_groups(card_id) == []


@pytest.mark.asyncio
async def test_save_character_uses_card_id():
    template = gen_template_char("88", "99")
    card_id = await characters.create_card("99", "卡A", "88", template)
    await characters.bind_card("88", "99", card_id)

    loaded = await characters.get_character("88", "99")
    assert loaded is not None
    loaded.name = "改名后"
    await characters.save_character(loaded)

    reloaded = await characters.get_character("88", "99")
    assert reloaded is not None and reloaded.name == "改名后"

    orphan = DNDCharacter(group_id="99", user_id="100", name="无卡", is_init=True)
    with pytest.raises(characters.CardNotFound):
        await characters.save_character(orphan)


@pytest.mark.asyncio
async def test_find_cards_by_name_exact_and_substring():
    first = await characters.create_card("99", "精灵短剑", "88", _char("甲"))
    second = await characters.create_card("99", "短剑二号", "88", _char("乙"))
    exact = await characters.find_cards_by_name("99", "短剑二号")
    assert [cid for cid, _name, _char in exact] == [second]
    partial = await characters.find_cards_by_name("99", "短剑")
    assert {cid for cid, _name, _char in partial} == {first, second}


def test_parse_template_keep_empty():
    data = parse_template_to_dict("$物品$\n$姓名$ 甲", keep_empty=True)
    assert data["$物品$"] == ""
    assert data["$姓名$"] == "甲"
    data = parse_template_to_dict("$物品$\n$姓名$ 甲")
    assert "$物品$" not in data
    with pytest.raises(AssertionError, match="未知段"):
        parse_template_to_dict("$不存在$ 1", keep_empty=True)


def test_parse_full_requires_name():
    with pytest.raises(AssertionError, match="必须设定姓名"):
        CharacterService.parse_full(
            "$等级$ 1\n$属性$ 10/10/10/10/10/10", "88", "99"
        )


def test_merge_segments_never_full_overwrites():
    existing = CharacterService.parse_full(
        gen_template_char().get_char_info(), "88", "99"
    )
    merged = CharacterService.merge_segments(
        existing,
        {"$等级$": "6", "$属性$": "16/14/13/12/10/8"},
    )
    assert merged.ability_info.level == 6
    assert merged.name == existing.name
    assert merged.items == existing.items


def test_merge_segments_empty_clears_optional_segment():
    existing = CharacterService.parse_full(
        gen_template_char().get_char_info(), "88", "99"
    )
    assert existing.items
    merged = CharacterService.merge_segments(existing, {"$物品$": ""})
    assert merged.items == []


def test_merge_segments_rejects_required_clear_and_unknown():
    existing = CharacterService.parse_full(
        gen_template_char().get_char_info(), "88", "99"
    )
    with pytest.raises(AssertionError, match="等级不能清空"):
        CharacterService.merge_segments(existing, {"$等级$": ""})
    with pytest.raises(AssertionError, match="未知段"):
        CharacterService.merge_segments(existing, {"$不存在$": "1"})
