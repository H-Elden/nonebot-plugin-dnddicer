"""网页建卡器段语法清单的一致性测试。

四层断言：``spec.py`` 的段顺序 = ``CHAR_INFO_KEY_LIST``；入库的
``card-spec.json`` = ``spec.py`` 的序列化结果；每个示例 = 示例卡对应段，
且能作为单段卡文本被插件解析；``fixtures.json`` 的样例都真能被插件解析、
回写稳定（网页端 Node 校验再用同一份样例跑「解析 → 回写 → 再解析」）。
"""

from __future__ import annotations

import json
from pathlib import Path

from nonebot_plugin_dnddicer.character.constants import CHAR_INFO_KEY_LIST
from nonebot_plugin_dnddicer.character.services import (
    CharacterService,
    gen_template_char,
    parse_template_to_dict,
)
from nonebot_plugin_dnddicer.character.spec import CARD_SPEC

_SPEC_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / ".vitepress"
    / "theme"
    / "card-builder"
    / "card-spec.json"
)

_FIXTURES_PATH = _SPEC_PATH.with_name("fixtures.json")


def test_spec_segments_match_card_keys() -> None:
    """段清单顺序必须与角色卡解析顺序完全一致。"""
    keys = [segment["key"] for segment in CARD_SPEC["segments"]]
    assert keys == list(CHAR_INFO_KEY_LIST)


def test_spec_json_is_up_to_date() -> None:
    """站点读取的 JSON 必须与插件 spec.py 逐字一致（改语法后需重生成）。"""
    expected = json.dumps(CARD_SPEC, ensure_ascii=False, indent=2) + "\n"
    assert _SPEC_PATH.read_text(encoding="utf-8") == expected


def test_spec_examples_match_template_card() -> None:
    """每个段的示例必须与示例卡对应段逐字相同（防止示例与语法漂移）。"""
    template = parse_template_to_dict(gen_template_char().get_char_info())
    for segment in CARD_SPEC["segments"]:
        assert segment["example"] == template.get(segment["key"], ""), segment["key"]


def test_spec_examples_are_parseable() -> None:
    """每个示例拼成单段卡文本后都必须能被插件解析。"""
    base = "$姓名$ 测试\n$等级$ 5\n$属性$ 10/10/10/10/10/10\n"
    for segment in CARD_SPEC["segments"]:
        if not segment["example"]:
            continue
        text = base + f"{segment['key']} {segment['example']}\n"
        CharacterService.parse(text, "g", "u")


def test_spec_groups_and_fields() -> None:
    group_ids = {group["id"] for group in CARD_SPEC["groups"]}
    assert {segment["group"] for segment in CARD_SPEC["segments"]} <= group_ids
    for segment in CARD_SPEC["segments"]:
        assert segment["label"]
        assert segment["summary"]
        assert isinstance(segment["required"], bool)
    assert sum(1 for segment in CARD_SPEC["segments"] if segment["required"]) == 2


def test_spec_output_order_matches_template_card() -> None:
    """回写顺序必须与示例卡的段顺序一致（网页端据此逐字往返）。"""
    template = parse_template_to_dict(gen_template_char().get_char_info())
    assert list(template) == [
        key for key in CARD_SPEC["output_order"] if key in template
    ]


def test_spec_examples_build_template_card() -> None:
    """把各段示例按回写顺序拼起来，必须等于示例卡整卡文本。"""
    examples = {segment["key"]: segment["example"] for segment in CARD_SPEC["segments"]}
    text = "\n".join(
        f"{key} {examples[key]}"
        for key in CARD_SPEC["output_order"]
        if examples[key]
    )
    assert text == gen_template_char().get_char_info()


def test_spec_legacy_segments() -> None:
    """退役的派生段必须登记为旧段，网页端据此提示忽略而不是报未知段。"""
    legacy = {item["key"] for item in CARD_SPEC["legacy_segments"]}
    assert legacy == {"$属性值$", "$豁免$", "$技能$"}
    assert all(item["message"] for item in CARD_SPEC["legacy_segments"])


def test_fixtures_are_parseable_and_stable() -> None:
    """网页端往返样例必须是插件真能解析的卡，且回写后再次解析保持稳定。"""
    data = json.loads(_FIXTURES_PATH.read_text(encoding="utf-8"))
    fixtures = {item["name"]: item for item in data["fixtures"]}
    assert set(fixtures) == {"template", "legacy", "edge"}
    assert fixtures["template"]["text"] == gen_template_char().get_char_info()
    for name, fixture in fixtures.items():
        character = CharacterService.parse(fixture["text"], "g", "u")
        canonical = character.get_char_info()
        again = CharacterService.parse(canonical, "g", "u").get_char_info()
        assert again == canonical, name
