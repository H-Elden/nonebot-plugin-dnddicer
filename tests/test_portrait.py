"""立绘：存储、魔数、体积、抓取与 .立绘 命令（2026-10-21）。"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import (
    Adapter as OnebotV11Adapter,
    Bot,
    Message,
    MessageSegment,
)

from fake_event import fake_group_message_event_v11

from nonebot_plugin_dnddicer.character.services import gen_template_char
from nonebot_plugin_dnddicer.commands import card_image as card_image_cmd
from nonebot_plugin_dnddicer.commands import text
from nonebot_plugin_dnddicer.commands.character import char_matcher
from nonebot_plugin_dnddicer.data import portraits
from nonebot_plugin_dnddicer.data.characters import get_character, save_character

_GROUP = 87654321
_USER = 10001

_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)
_JPEG_MIN = b"\xff\xd8\xff\xe0" + b"\x00" * 32
_WEBP_MIN = b"RIFF" + (16).to_bytes(4, "little") + b"WEBP" + b"\x00" * 32


@pytest.fixture(autouse=True)
def _portrait_dir(tmp_path, monkeypatch):
    """立绘目录指向临时目录，避免污染仓库 data/。"""
    monkeypatch.setattr(portraits, "get_data_dir", lambda: tmp_path)
    yield tmp_path


@pytest.fixture(autouse=True)
def _clear_characters():
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file

    _chars._cache = None
    path = get_data_file("characters.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")
    yield


def test_detect_image_types() -> None:
    assert portraits.detect_image_type(_PNG_1PX) == ("png", "image/png")
    assert portraits.detect_image_type(_JPEG_MIN) == ("jpg", "image/jpeg")
    assert portraits.detect_image_type(_WEBP_MIN) == ("webp", "image/webp")
    assert portraits.detect_image_type(b"not an image") is None


@pytest.mark.asyncio
async def test_save_load_delete_and_raw_bytes(tmp_path: Path) -> None:
    name = await portraits.save_portrait("g1", "u1", _PNG_1PX)
    assert name == "portraits/g1_u1.png"
    path = tmp_path / name
    assert path.read_bytes() == _PNG_1PX  # 原图逐字节保存，零后处理

    loaded = await portraits.load_portrait(name)
    assert loaded == (_PNG_1PX, "image/png")
    await portraits.delete_portrait(name)
    assert not path.exists()


@pytest.mark.asyncio
async def test_save_replaces_old_extension(tmp_path: Path) -> None:
    await portraits.save_portrait("g1", "u1", _PNG_1PX)
    jpg_name = await portraits.save_portrait("g1", "u1", _JPEG_MIN)
    assert jpg_name == "portraits/g1_u1.jpg"
    assert not (tmp_path / "portraits/g1_u1.png").exists()
    assert (tmp_path / "portraits/g1_u1.jpg").exists()


@pytest.mark.asyncio
async def test_save_rejects_bad_format_and_size() -> None:
    with pytest.raises(portraits.PortraitBadFormat):
        await portraits.save_portrait("g", "u", b"plain text")
    too_large = _PNG_1PX + b"\x00" * (portraits.MAX_PORTRAIT_BYTES + 1)
    with pytest.raises(portraits.PortraitTooLarge):
        await portraits.save_portrait("g", "u", too_large)


@pytest.mark.asyncio
async def test_load_missing_or_unsafe_name() -> None:
    assert await portraits.load_portrait("") is None
    assert await portraits.load_portrait("../../etc/passwd") is None
    assert await portraits.load_portrait("portraits/missing.png") is None


@pytest.mark.asyncio
async def test_fetch_local_file_and_base64(tmp_path: Path) -> None:
    path = tmp_path / "in.png"
    path.write_bytes(_PNG_1PX)
    assert await portraits.fetch_image_bytes(None, {"file": str(path)}) == _PNG_1PX
    encoded = "base64://" + base64.b64encode(_PNG_1PX).decode()
    assert await portraits.fetch_image_bytes(None, {"file": encoded}) == _PNG_1PX


@pytest.mark.asyncio
async def test_fetch_via_get_image(tmp_path: Path) -> None:
    path = tmp_path / "in.png"
    path.write_bytes(_PNG_1PX)

    class FakeBot:
        async def call_api(self, api: str, **kwargs):
            assert api == "get_image"
            return {"file": str(path)}

    data = await portraits.fetch_image_bytes(FakeBot(), {"file": "remote-id"})
    assert data == _PNG_1PX


def test_is_public_host(monkeypatch) -> None:
    monkeypatch.setattr(
        portraits.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )
    assert portraits._is_public_host("example.com")
    monkeypatch.setattr(
        portraits.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("10.0.0.1", 0))],
    )
    assert not portraits._is_public_host("internal.example")


@pytest.mark.asyncio
async def test_fetch_rejects_private_url(monkeypatch) -> None:
    monkeypatch.setattr(
        portraits.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 0))],
    )
    with pytest.raises(portraits.PortraitFetchFailed):
        await portraits.fetch_image_bytes(
            None, {"file": "x", "url": "http://internal.example/a.png"}
        )


@pytest.mark.asyncio
async def test_fetch_rejects_oversized_local(tmp_path: Path) -> None:
    path = tmp_path / "big.png"
    path.write_bytes(_PNG_1PX + b"\x00" * (portraits.MAX_PORTRAIT_BYTES + 1))
    with pytest.raises(portraits.PortraitTooLarge):
        await portraits.fetch_image_bytes(None, {"file": str(path)})


def _event_with_image(text: str, image_path: Path, user_id: int = _USER):
    message = Message(text) + MessageSegment.image(str(image_path))
    return fake_group_message_event_v11(
        message=message, group_id=_GROUP, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected: str) -> None:
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_portrait_command_sets_and_persists(app: App, tmp_path: Path) -> None:
    char = gen_template_char(str(_GROUP), str(_USER))
    await save_character(char)
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)

    await _expect(
        app, card_image_cmd.portrait_matcher,
        _event_with_image(".立绘", image), text.TXT_PORTRAIT_SET,
    )
    saved = await get_character(_GROUP, _USER)
    assert saved is not None and saved.portrait == "portraits/87654321_10001.png"
    assert (tmp_path / saved.portrait).read_bytes() == _PNG_1PX


@pytest.mark.asyncio
async def test_portrait_command_multi_image_hint(app: App, tmp_path: Path) -> None:
    await save_character(gen_template_char(str(_GROUP), str(_USER)))
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)
    message = Message(".立绘") + MessageSegment.image(str(image)) + MessageSegment.image(str(image))
    event = fake_group_message_event_v11(
        message=message, group_id=_GROUP, user_id=_USER
    )
    await _expect(
        app, card_image_cmd.portrait_matcher, event,
        text.TXT_PORTRAIT_SET + text.TXT_PORTRAIT_MULTI,
    )


@pytest.mark.asyncio
async def test_portrait_command_errors(app: App, tmp_path: Path) -> None:
    # 无卡
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)
    await _expect(
        app, card_image_cmd.portrait_matcher,
        _event_with_image(".立绘", image, user_id=19999), text.TXT_CHAR_MISS,
    )
    # 无图
    await save_character(gen_template_char(str(_GROUP), str(_USER)))
    await _expect(
        app, card_image_cmd.portrait_matcher,
        fake_group_message_event_v11(
            message=Message(".立绘"), group_id=_GROUP, user_id=_USER
        ),
        text.TXT_PORTRAIT_USAGE,
    )
    # 格式不支持
    bad = tmp_path / "bad.txt"
    bad.write_text("not an image", encoding="utf-8")
    await _expect(
        app, card_image_cmd.portrait_matcher,
        _event_with_image(".立绘", bad), text.TXT_PORTRAIT_BAD_FORMAT,
    )


@pytest.mark.asyncio
async def test_full_record_keeps_portrait(app: App, tmp_path: Path) -> None:
    """整卡重录（多段覆盖）不丢立绘。"""
    char = gen_template_char(str(_GROUP), str(_USER))
    char.portrait = await portraits.save_portrait(str(_GROUP), str(_USER), _PNG_1PX)
    await save_character(char)
    await _expect(
        app,
        char_matcher,
        fake_group_message_event_v11(
            message=Message(
                ".角色卡记录 $姓名$ 新名字\n$等级$ 5\n$属性$ 10/10/10/10/10/10"
            ),
            group_id=_GROUP,
            user_id=_USER,
        ),
        text.TXT_CHAR_SET,
    )
    saved = await get_character(_GROUP, _USER)
    assert saved is not None and saved.name == "新名字"
    assert saved.portrait == char.portrait
    assert (tmp_path / saved.portrait).exists()


@pytest.mark.asyncio
async def test_card_delete_removes_portrait(app: App, tmp_path: Path) -> None:
    char = gen_template_char(str(_GROUP), str(_USER))
    char.portrait = await portraits.save_portrait(str(_GROUP), str(_USER), _PNG_1PX)
    await save_character(char)
    path = tmp_path / char.portrait
    assert path.exists()
    await _expect(
        app,
        char_matcher,
        fake_group_message_event_v11(
            message=Message(".角色卡清除"), group_id=_GROUP, user_id=_USER
        ),
        text.TXT_CHAR_DEL,
    )
    assert not path.exists()
