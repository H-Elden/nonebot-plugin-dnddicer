"""``.角色卡图`` 命令与卡面视图测试（全离线，假渲染器）。

覆盖：发图、开关关闭回退、渲染异常回退、@ 查看他人、无卡、私聊提示、
视图模型对完整字段/空段的处理。真实 htmlkit 渲染冒烟见 test_render_char_card.py。
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
from nonebot_plugin_dnddicer.commands import card_image as card_image_cmd
from nonebot_plugin_dnddicer.commands import text
from nonebot_plugin_dnddicer.data.characters import get_character, save_character

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
    """每个用例清空角色卡缓存与 JSON（主键 = 群 + QQ）。"""
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file

    _chars._cache = None
    path = get_data_file("characters.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")
    yield


@pytest.fixture(autouse=True)
def _reset_renderer():
    yield
    render.reset_renderer()


def _event(text: str, user_id: int = _USER):
    return fake_group_message_event_v11(
        message=Message(text), group_id=_GROUP, user_id=user_id
    )


async def _expect_text(app: App, event, expected: str) -> None:
    async with app.test_matcher(card_image_cmd.character_image_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _expect_image(app: App, event, png: bytes) -> None:
    async with app.test_matcher(card_image_cmd.character_image_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, MessageSegment.image(png))
        ctx.receive_event(bot, event)


async def _save_card(user_id: int = _USER, name: str = "伊瑟兰·晨星") -> None:
    char = gen_template_char(str(_GROUP), str(user_id))
    char.name = name
    await save_character(char)


@pytest.mark.asyncio
async def test_card_image_sends_png(app: App):
    """.角色卡图 → 调用渲染器并发送图片。"""
    await _save_card()
    calls = []

    async def fake_renderer(view):
        calls.append(view)
        return _PNG_1PX

    render.set_char_renderer(fake_renderer)
    await _expect_image(app, _event(".角色卡图"), _PNG_1PX)
    assert len(calls) == 1
    assert calls[0].name == "伊瑟兰·晨星"
    assert calls[0].combat_notes == ("法师护甲(8小时)",)


@pytest.mark.asyncio
async def test_card_image_off_falls_back_to_text(app: App):
    """渲染未启用 → 文字卡 + 回退提示。"""
    await _save_card()
    char = await get_character(_GROUP, _USER)
    expected = char.get_char_info() + "\n" + text.TXT_CARD_IMAGE_FALLBACK
    await _expect_text(app, _event(".角色卡图"), expected)


@pytest.mark.asyncio
async def test_card_image_render_error_falls_back(app: App):
    """渲染异常 → 不静默，回退文字卡。"""
    await _save_card()
    char = await get_character(_GROUP, _USER)

    async def boom(view):
        raise RuntimeError("boom")

    render.set_char_renderer(boom)
    expected = char.get_char_info() + "\n" + text.TXT_CARD_IMAGE_FALLBACK
    await _expect_text(app, _event(".角色卡图"), expected)


@pytest.mark.asyncio
async def test_card_image_other_by_at(app: App):
    """.角色卡图 @玩家 → 渲染他人的卡。"""
    await _save_card(_TARGET, name="薇拉")
    calls = []

    async def fake_renderer(view):
        calls.append(view)
        return _PNG_1PX

    render.set_char_renderer(fake_renderer)
    await _expect_image(
        app, _event(f".角色卡图 @{_TARGET}", user_id=_USER), _PNG_1PX
    )
    assert calls[0].name == "薇拉"


@pytest.mark.asyncio
async def test_card_image_embeds_saved_portrait(app: App, tmp_path, monkeypatch):
    """已设置立绘时，渲染视图带 data URI（原图字节）。"""
    from nonebot_plugin_dnddicer.data import portraits

    monkeypatch.setattr(portraits, "get_data_dir", lambda: tmp_path)
    char = gen_template_char(str(_GROUP), str(_USER))
    char.portrait = await portraits.save_portrait(str(_GROUP), str(_USER), _PNG_1PX)
    await save_character(char)
    calls = []

    async def fake_renderer(view):
        calls.append(view)
        return _PNG_1PX

    render.set_char_renderer(fake_renderer)
    await _expect_image(app, _event(".角色卡图"), _PNG_1PX)
    assert calls[0].has_portrait
    assert calls[0].portrait_data_uri.startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_card_image_no_card(app: App):
    await _expect_text(app, _event(".角色卡图", user_id=19999), text.TXT_CHAR_MISS)


@pytest.mark.asyncio
async def test_card_image_private_rejected(app: App):
    event = fake_private_message_event_v11(
        message=Message(".角色卡图"), user_id=_USER
    )
    await _expect_text(app, event, text.TXT_GROUP_ONLY)
