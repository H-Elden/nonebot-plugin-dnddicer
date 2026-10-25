"""``.角色卡`` 图片/文字输出与 ``.角色卡导出`` 测试（全离线，假渲染器）。

覆盖：角色卡图开启时 ``.角色卡`` 发图、关闭时发文字卡、渲染异常回退文字卡
并附联系骰主提示、@ 查看他人、私聊选卡；``.角色卡导出`` 始终输出文字卡
（即使图片开关开启）、多卡选名与他人卡标题行。
"""

from __future__ import annotations

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import (
    Adapter as OnebotV11Adapter,
    Bot,
    Message,
    MessageSegment,
)

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer import render
from nonebot_plugin_dnddicer.character.services import (
    gen_template_char,
)
from nonebot_plugin_dnddicer.commands import base, text
from nonebot_plugin_dnddicer.commands.character import char_matcher, export_matcher
from nonebot_plugin_dnddicer.config import get_config
from nonebot_plugin_dnddicer.data import characters
from nonebot_plugin_dnddicer.data.characters import get_character, save_card
from card_test_utils import create_bound_card

_GROUP = 87654321
_USER = 10001
_TARGET = 10002

_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


@pytest.fixture(autouse=True)
def _clear_store():
    """每个用例清空角色卡缓存与 JSON。"""
    from nonebot_plugin_dnddicer.data import get_data_file

    characters._cache = None
    path = get_data_file("cards.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")
    yield


@pytest.fixture(autouse=True)
def _reset_renderer():
    yield
    render.reset_renderer()


@pytest.fixture
def card_image_on():
    """临时开启角色卡图开关（用例结束后自动还原）。"""
    config = get_config()
    original = config.dnddicer_card_image_enabled
    config.dnddicer_card_image_enabled = True
    yield
    config.dnddicer_card_image_enabled = original


@pytest.fixture(autouse=True)
def _card_image_off():
    config = get_config()
    original = config.dnddicer_card_image_enabled
    config.dnddicer_card_image_enabled = False
    yield
    config.dnddicer_card_image_enabled = original


def _event(text_value: str, user_id: int = _USER):
    return fake_group_message_event_v11(
        message=Message(text_value), group_id=_GROUP, user_id=user_id
    )


def _private(text_value: str, user_id: int = _USER):
    return fake_private_message_event_v11(
        message=Message(text_value), user_id=user_id
    )


def _mention_event(*parts, user_id: int = _USER):
    message = Message()
    for part in parts:
        message += part
    return fake_group_message_event_v11(
        message=message, group_id=_GROUP, user_id=user_id
    )


async def _expect_text(app: App, matcher, event, expected: str) -> None:
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _expect_image(app: App, matcher, event, png: bytes) -> None:
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, MessageSegment.image(png))
        ctx.receive_event(bot, event)


async def _save_card(
    user_id: int = _USER, name: str = "伊瑟兰·晨星", card_name: str = "测试卡"
) -> str:
    char = gen_template_char(str(_GROUP), str(user_id))
    char.name = name
    return await create_bound_card(
        _GROUP, user_id, char, card_name=card_name
    )


# =========================================================================
# .角色卡：图片 / 文字分流
# =========================================================================


@pytest.mark.asyncio
async def test_card_renders_image_when_enabled(app: App, card_image_on):
    """角色卡图开启 → .角色卡 调用渲染器并发送图片。"""
    await _save_card()
    calls = []

    async def fake_renderer(view):
        calls.append(view)
        return _PNG_1PX

    render.set_char_renderer(fake_renderer)
    await _expect_image(app, char_matcher, _event(".角色卡"), _PNG_1PX)
    assert len(calls) == 1
    assert calls[0].name == "伊瑟兰·晨星"
    assert calls[0].combat_notes == ("法师护甲(8小时)",)


@pytest.mark.asyncio
async def test_card_text_when_disabled(app: App):
    """角色卡图关闭 → .角色卡 输出文字卡，不带回退提示。"""
    await _save_card()
    char = await get_character(_GROUP, _USER)
    assert char is not None
    await _expect_text(app, char_matcher, _event(".角色卡"), char.get_char_info())


@pytest.mark.asyncio
async def test_card_falls_back_on_render_error(app: App, card_image_on):
    """渲染异常 → 文字卡 + 联系骰主提示。"""
    await _save_card()
    char = await get_character(_GROUP, _USER)
    assert char is not None

    async def boom(view):
        raise RuntimeError("boom")

    render.set_char_renderer(boom)
    expected = char.get_char_info() + "\n" + text.TXT_CARD_IMAGE_FALLBACK
    await _expect_text(app, char_matcher, _event(".角色卡"), expected)


@pytest.mark.asyncio
async def test_card_render_unavailable_falls_back(app: App, card_image_on, monkeypatch):
    """开关开启但渲染器不可用 → 文字卡 + 联系骰主提示。"""
    from nonebot_plugin_dnddicer.commands import card_image

    await _save_card()
    char = await get_character(_GROUP, _USER)
    assert char is not None
    monkeypatch.setattr(card_image, "char_card_available", lambda: False)
    expected = char.get_char_info() + "\n" + text.TXT_CARD_IMAGE_FALLBACK
    await _expect_text(app, char_matcher, _event(".角色卡"), expected)


@pytest.mark.asyncio
async def test_card_other_by_at_renders_image(app: App, card_image_on):
    """.角色卡 @玩家 → 渲染他人本群绑定卡。"""
    await _save_card(_TARGET, name="薇拉")
    calls = []

    async def fake_renderer(view):
        calls.append(view)
        return _PNG_1PX

    render.set_char_renderer(fake_renderer)
    await _expect_image(
        app,
        char_matcher,
        _mention_event(".角色卡 ", MessageSegment.at(_TARGET)),
        _PNG_1PX,
    )
    assert calls[0].name == "薇拉"


@pytest.mark.asyncio
async def test_card_embeds_saved_portrait(app: App, card_image_on, tmp_path, monkeypatch):
    """已设置立绘时，渲染视图带 data URI（原图字节）。"""
    from nonebot_plugin_dnddicer.data import portraits

    monkeypatch.setattr(portraits, "get_data_dir", lambda: tmp_path)
    char = gen_template_char(str(_GROUP), str(_USER))
    card_id = await create_bound_card(_GROUP, _USER, char)
    char.portrait = await portraits.save_portrait(card_id, _PNG_1PX)
    await save_card(card_id, char)
    calls = []

    async def fake_renderer(view):
        calls.append(view)
        return _PNG_1PX

    render.set_char_renderer(fake_renderer)
    await _expect_image(app, char_matcher, _event(".角色卡"), _PNG_1PX)
    assert calls[0].has_portrait
    assert calls[0].portrait_data_uri.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_card_no_card_group(app: App):
    """群聊未绑定且卡库为空 → 引导建卡。"""
    expected = text.TXT_CHAR_VIEW_MISS_GROUP.format(url=text.TXT_CARD_BUILDER_URL)
    await _expect_text(app, char_matcher, _event(".角色卡", user_id=19999), expected)


@pytest.mark.asyncio
async def test_card_private_single_card(app: App, card_image_on):
    await _save_card()

    async def fake_renderer(view):
        return _PNG_1PX

    render.set_char_renderer(fake_renderer)
    await _expect_image(app, char_matcher, _private(".角色卡"), _PNG_1PX)


@pytest.mark.asyncio
async def test_card_private_no_card(app: App):
    expected = text.TXT_CHAR_VIEW_MISS_PRIVATE.format(url=text.TXT_CARD_BUILDER_URL)
    await _expect_text(app, char_matcher, _private(".角色卡"), expected)


# =========================================================================
# .角色卡导出：始终文字
# =========================================================================


@pytest.mark.asyncio
async def test_export_private_single_card_ignores_image(app: App, card_image_on):
    """图片开关开启时，.角色卡导出 仍只发文字卡。"""
    await _save_card()
    char = await get_character(_GROUP, _USER)
    assert char is not None
    calls = []

    async def fake_renderer(view):
        calls.append(view)
        return _PNG_1PX

    render.set_char_renderer(fake_renderer)
    await _expect_text(app, export_matcher, _private(".角色卡导出"), char.get_char_info())
    assert calls == []


@pytest.mark.asyncio
async def test_export_private_with_card_name(app: App):
    """私聊多卡时按卡名选中。"""
    first = gen_template_char("private", str(_USER))
    first.name = "甲"
    await characters.create_card(str(_USER), "卡甲", "private", first)
    second = gen_template_char("private", str(_USER))
    second.name = "乙"
    await characters.create_card(str(_USER), "卡乙", "private", second)

    await _expect_text(
        app,
        export_matcher,
        _private(".角色卡导出 卡乙"),
        second.get_char_info(),
    )


@pytest.mark.asyncio
async def test_export_private_multiple_cards_need_name(app: App):
    for name in ("卡甲", "卡乙"):
        char = gen_template_char("private", str(_USER))
        await characters.create_card(str(_USER), name, "private", char)
    await _expect_text(
        app,
        export_matcher,
        _private(".角色卡导出"),
        text.TXT_CHAR_NEED_NAME.format(count=2),
    )


@pytest.mark.asyncio
async def test_export_group_other_by_at(app: App):
    """.角色卡导出 @玩家 → 标题行 + 他人文字卡。"""
    await _save_card(_TARGET, name="薇拉")
    target = await get_character(_GROUP, _TARGET)
    assert target is not None
    expected = text.TXT_CHAR_TARGET_TITLE.format(name="薇拉") + "\n" + target.get_char_info()
    await _expect_text(
        app,
        export_matcher,
        _mention_event(".角色卡导出 ", MessageSegment.at(_TARGET)),
        expected,
    )


@pytest.mark.asyncio
async def test_export_spaced_form(app: App, card_image_on):
    """.角色卡 导出 → 同样走导出（不触发图片渲染）。"""
    await _save_card()
    char = await get_character(_GROUP, _USER)
    assert char is not None
    calls = []

    async def fake_renderer(view):
        calls.append(view)
        return _PNG_1PX

    render.set_char_renderer(fake_renderer)
    await _expect_text(app, char_matcher, _event(".角色卡 导出"), char.get_char_info())
    assert calls == []


@pytest.mark.asyncio
async def test_export_private_no_card(app: App):
    expected = text.TXT_CHAR_VIEW_MISS_PRIVATE.format(url=text.TXT_CARD_BUILDER_URL)
    await _expect_text(app, export_matcher, _private(".角色卡导出"), expected)


def test_card_image_command_removed():
    """``.角色卡图`` 已删除，``.角色卡导出`` 已注册。"""
    commands = base.get_registered_commands(include_hidden=True)
    assert "角色卡图" not in commands
    assert "角色卡导出" in commands
