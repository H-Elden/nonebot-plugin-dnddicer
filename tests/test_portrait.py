"""立绘：存储、魔数、体积、抓取与 ``.立绘`` 命令（2026-10-21 首版）。

命令面（2026-10-26 重做）：
- 群聊 ``.立绘`` 看本群绑定卡；``.立绘 @玩家|角色名`` 看他人本群绑定卡；
- 私聊 ``.立绘 [卡名]`` 看本人卡（卡库仅一张可省略卡名）；
- 消息带图片即设置：群聊 ``.立绘 [卡名]`` 只能改本群绑定卡，私聊按卡名改本人卡。
"""

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

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.character.services import gen_template_char
from nonebot_plugin_dnddicer.commands import card_image as card_image_cmd
from nonebot_plugin_dnddicer.commands import text
from nonebot_plugin_dnddicer.commands.character import char_matcher
from nonebot_plugin_dnddicer.data import characters, portraits
from nonebot_plugin_dnddicer.data.characters import (
    get_card_by_name,
    get_character,
    save_card,
)
from card_test_utils import create_bound_card

_GROUP = 87654321
_USER = 10001
_TARGET = 10002
_MISSING_USER = 19999

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
    from nonebot_plugin_dnddicer.data import get_data_file

    characters._cache = None
    path = get_data_file("cards.json")
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
    name = await portraits.save_portrait("card1", _PNG_1PX)
    assert name == "portraits/card1.png"
    path = tmp_path / name
    assert path.read_bytes() == _PNG_1PX  # 原图逐字节保存，零后处理

    loaded = await portraits.load_portrait(name)
    assert loaded == (_PNG_1PX, "image/png")
    await portraits.delete_portrait(name)
    assert not path.exists()


@pytest.mark.asyncio
async def test_save_replaces_old_extension(tmp_path: Path) -> None:
    await portraits.save_portrait("card1", _PNG_1PX)
    jpg_name = await portraits.save_portrait("card1", _JPEG_MIN)
    assert jpg_name == "portraits/card1.jpg"
    assert not (tmp_path / "portraits/card1.png").exists()
    assert (tmp_path / "portraits/card1.jpg").exists()


@pytest.mark.asyncio
async def test_save_rejects_bad_format_and_size() -> None:
    with pytest.raises(portraits.PortraitBadFormat):
        await portraits.save_portrait("card1", b"plain text")
    too_large = _PNG_1PX + b"\x00" * (portraits.MAX_PORTRAIT_BYTES + 1)
    with pytest.raises(portraits.PortraitTooLarge):
        await portraits.save_portrait("card1", too_large)


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


# =========================================================================
# 命令辅助
# =========================================================================


def _event(
    text_value: str,
    image_path: Path | None = None,
    user_id: int = _USER,
) -> object:
    message = Message(text_value)
    if image_path is not None:
        message += MessageSegment.image(str(image_path))
    return fake_group_message_event_v11(
        message=message, group_id=_GROUP, user_id=user_id
    )


def _private(
    text_value: str,
    image_path: Path | None = None,
    user_id: int = _USER,
) -> object:
    message = Message(text_value)
    if image_path is not None:
        message += MessageSegment.image(str(image_path))
    return fake_private_message_event_v11(message=message, user_id=user_id)


async def _expect(app: App, matcher, event, expected: str) -> None:
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


async def _bind_card(
    user_id: int = _USER,
    *,
    name: str = "伊瑟兰·晨星",
    card_name: str = "测试卡",
    group_id: int = _GROUP,
) -> str:
    char = gen_template_char(str(group_id), str(user_id))
    char.name = name
    return await create_bound_card(group_id, user_id, char, card_name=card_name)


async def _set_saved_portrait(card_id: str) -> str:
    """直接给卡落一张立绘（不经过命令），返回相对文件名。"""
    name = await portraits.save_portrait(card_id, _PNG_1PX)
    character = await characters.get_card(card_id)
    assert character is not None
    character.portrait = name
    await save_card(card_id, character)
    return name


# =========================================================================
# 群聊：设置立绘
# =========================================================================


@pytest.mark.asyncio
async def test_group_set_without_card_name(app: App, tmp_path: Path) -> None:
    char = gen_template_char(str(_GROUP), str(_USER))
    await create_bound_card(_GROUP, _USER, char)
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)

    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘", image),
        text.TXT_PORTRAIT_SET.format(name="测试卡"),
    )
    saved = await get_character(_GROUP, _USER)
    assert saved is not None and saved.portrait == f"portraits/{saved.card_id}.png"
    assert (tmp_path / saved.portrait).read_bytes() == _PNG_1PX


@pytest.mark.asyncio
async def test_group_set_with_matching_card_name(app: App, tmp_path: Path) -> None:
    await _bind_card()
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘 测试卡", image),
        text.TXT_PORTRAIT_SET.format(name="测试卡"),
    )
    saved = await get_character(_GROUP, _USER)
    assert saved is not None and saved.portrait


@pytest.mark.asyncio
async def test_group_set_rejects_other_card_name(app: App, tmp_path: Path) -> None:
    """群聊只能改本群绑定卡：写别的卡名直接拒绝。"""
    await _bind_card()
    other = gen_template_char(str(_GROUP), str(_USER))
    await characters.create_card(str(_USER), "另一张", _GROUP, other)
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)

    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘 另一张", image),
        text.TXT_CHAR_MODIFY_GROUP_MISMATCH.format(name="测试卡"),
    )
    saved = await get_character(_GROUP, _USER)
    assert saved is not None and not saved.portrait


@pytest.mark.asyncio
async def test_group_set_usage_errors(app: App, tmp_path: Path) -> None:
    await _bind_card()
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)
    # 卡名不能含空白：多段参数按用法错误处理
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘 测试卡 多余", image),
        text.TXT_PORTRAIT_SET_USAGE,
    )
    # 设置时不能 @ 别人
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        fake_group_message_event_v11(
            message=Message(".立绘 ") + MessageSegment.at(_TARGET)
            + MessageSegment.image(str(image)),
            group_id=_GROUP,
            user_id=_USER,
        ),
        text.TXT_PORTRAIT_SET_USAGE,
    )


@pytest.mark.asyncio
async def test_group_set_without_bound_card(app: App, tmp_path: Path) -> None:
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘", image, user_id=_MISSING_USER),
        text.TXT_CHAR_MISS,
    )


@pytest.mark.asyncio
async def test_group_set_multi_image_hint(app: App, tmp_path: Path) -> None:
    await _bind_card()
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)
    message = (
        Message(".立绘")
        + MessageSegment.image(str(image))
        + MessageSegment.image(str(image))
    )
    event = fake_group_message_event_v11(
        message=message, group_id=_GROUP, user_id=_USER
    )
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        event,
        text.TXT_PORTRAIT_SET.format(name="测试卡") + text.TXT_PORTRAIT_MULTI,
    )


@pytest.mark.asyncio
async def test_group_set_bad_format(app: App, tmp_path: Path) -> None:
    await _bind_card()
    bad = tmp_path / "bad.txt"
    bad.write_text("not an image", encoding="utf-8")
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘", bad),
        text.TXT_PORTRAIT_BAD_FORMAT,
    )


# =========================================================================
# 群聊：查看立绘
# =========================================================================


@pytest.mark.asyncio
async def test_group_view_self_with_portrait(app: App) -> None:
    card_id = await _bind_card()
    await _set_saved_portrait(card_id)
    await _expect_image(
        app, card_image_cmd.portrait_matcher, _event(".立绘"), _PNG_1PX
    )


@pytest.mark.asyncio
async def test_group_view_self_without_portrait(app: App) -> None:
    await _bind_card()
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘"),
        text.TXT_PORTRAIT_NONE_SELF,
    )


@pytest.mark.asyncio
async def test_group_view_other_by_at(app: App) -> None:
    card_id = await _bind_card(_TARGET, name="薇拉", card_name="薇拉卡")
    await _set_saved_portrait(card_id)
    event = fake_group_message_event_v11(
        message=Message(".立绘 ") + MessageSegment.at(_TARGET),
        group_id=_GROUP,
        user_id=_USER,
    )
    await _expect_image(app, card_image_cmd.portrait_matcher, event, _PNG_1PX)


@pytest.mark.asyncio
async def test_group_view_other_by_name(app: App) -> None:
    card_id = await _bind_card(_TARGET, name="薇拉", card_name="薇拉卡")
    await _set_saved_portrait(card_id)
    await _expect_image(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘 薇拉"),
        _PNG_1PX,
    )


@pytest.mark.asyncio
async def test_group_view_other_without_portrait(app: App) -> None:
    await _bind_card(_TARGET, name="薇拉", card_name="薇拉卡")
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘 薇拉"),
        text.TXT_PORTRAIT_NONE_TARGET.format(name="薇拉"),
    )


@pytest.mark.asyncio
async def test_group_view_unbound_cards(app: App) -> None:
    # 卡库为空：引导建卡
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘", user_id=_MISSING_USER),
        text.TXT_CHAR_VIEW_MISS_GROUP.format(url=text.TXT_CARD_BUILDER_URL),
    )


@pytest.mark.asyncio
async def test_group_view_unbound_with_library(app: App) -> None:
    # 有卡但本群未绑定：引导绑定
    char = gen_template_char(str(_GROUP), str(_MISSING_USER))
    await characters.create_card(str(_MISSING_USER), "测试卡", _GROUP, char)
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘", user_id=_MISSING_USER),
        text.TXT_CHAR_VIEW_MISS_BOUND,
    )


@pytest.mark.asyncio
async def test_group_view_unknown_name(app: App) -> None:
    await _bind_card()
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘 不存在"),
        text.TXT_CHAR_TARGET_MISS.format(name="不存在"),
    )


@pytest.mark.asyncio
async def test_group_view_missing_file(app: App) -> None:
    """卡上记了立绘但文件丢失：提示重新设置，不按「未设置」误导。"""
    card_id = await _bind_card()
    character = await characters.get_card(card_id)
    assert character is not None
    character.portrait = "portraits/missing.png"
    await save_card(card_id, character)
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _event(".立绘"),
        text.TXT_PORTRAIT_LOAD_FAILED,
    )


# =========================================================================
# 私聊：设置与查看
# =========================================================================


async def _create_private_card(name: str, card_name: str) -> str:
    char = gen_template_char("private", str(_USER))
    char.name = name
    return await characters.create_card(str(_USER), card_name, "private", char)


@pytest.mark.asyncio
async def test_private_set_single_card_without_name(app: App, tmp_path: Path) -> None:
    await _create_private_card("洛恩", "测试卡")
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _private(".立绘", image),
        text.TXT_PORTRAIT_SET.format(name="测试卡"),
    )
    found = await get_card_by_name(_USER, "测试卡")
    assert found is not None and found[1].portrait


@pytest.mark.asyncio
async def test_private_set_by_card_name(app: App, tmp_path: Path) -> None:
    await _create_private_card("甲", "卡甲")
    await _create_private_card("乙", "卡乙")
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _private(".立绘 卡乙", image),
        text.TXT_PORTRAIT_SET.format(name="卡乙"),
    )
    saved = await get_card_by_name(_USER, "卡乙")
    assert saved is not None and saved[1].portrait
    untouched = await get_card_by_name(_USER, "卡甲")
    assert untouched is not None and not untouched[1].portrait


@pytest.mark.asyncio
async def test_private_set_multiple_cards_need_name(app: App, tmp_path: Path) -> None:
    await _create_private_card("甲", "卡甲")
    await _create_private_card("乙", "卡乙")
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _private(".立绘", image),
        text.TXT_CHAR_NEED_NAME.format(count=2),
    )


@pytest.mark.asyncio
async def test_private_set_unknown_name(app: App, tmp_path: Path) -> None:
    await _create_private_card("甲", "卡甲")
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _private(".立绘 不存在", image),
        text.TXT_CHAR_NAME_MISS.format(name="不存在"),
    )


@pytest.mark.asyncio
async def test_private_set_at_not_supported(app: App, tmp_path: Path) -> None:
    await _create_private_card("甲", "卡甲")
    image = tmp_path / "in.png"
    image.write_bytes(_PNG_1PX)
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _private(".立绘 @10002", image),
        text.TXT_PORTRAIT_SET_USAGE,
    )


@pytest.mark.asyncio
async def test_private_view_single_card(app: App) -> None:
    card_id = await _create_private_card("洛恩", "测试卡")
    await _set_saved_portrait(card_id)
    await _expect_image(
        app, card_image_cmd.portrait_matcher, _private(".立绘"), _PNG_1PX
    )


@pytest.mark.asyncio
async def test_private_view_by_card_name(app: App) -> None:
    await _create_private_card("甲", "卡甲")
    second = await _create_private_card("乙", "卡乙")
    await _set_saved_portrait(second)
    await _expect_image(
        app,
        card_image_cmd.portrait_matcher,
        _private(".立绘 卡乙"),
        _PNG_1PX,
    )


@pytest.mark.asyncio
async def test_private_view_multiple_cards_need_name(app: App) -> None:
    await _create_private_card("甲", "卡甲")
    await _create_private_card("乙", "卡乙")
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _private(".立绘"),
        text.TXT_CHAR_NEED_NAME.format(count=2),
    )


@pytest.mark.asyncio
async def test_private_view_no_card(app: App) -> None:
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _private(".立绘"),
        text.TXT_CHAR_VIEW_MISS_PRIVATE.format(url=text.TXT_CARD_BUILDER_URL),
    )


@pytest.mark.asyncio
async def test_private_view_at_not_supported(app: App) -> None:
    await _expect(
        app,
        card_image_cmd.portrait_matcher,
        _private(".立绘 @10002"),
        text.TXT_CHAR_PRIVATE_TARGET_UNSUPPORTED,
    )


# =========================================================================
# 与角色卡生命周期的一致性
# =========================================================================


@pytest.mark.asyncio
async def test_full_record_keeps_portrait(app: App, tmp_path: Path) -> None:
    """整卡重录（多段覆盖）不丢立绘。"""
    char = gen_template_char(str(_GROUP), str(_USER))
    card_id = await create_bound_card(_GROUP, _USER, char)
    char.portrait = await portraits.save_portrait(card_id, _PNG_1PX)
    await save_card(card_id, char)
    await _expect(
        app,
        char_matcher,
        fake_group_message_event_v11(
            message=Message(
                ".角色卡修改 测试卡 $姓名$ 新名字\n$等级$ 5\n$属性$ 10/10/10/10/10/10"
            ),
            group_id=_GROUP,
            user_id=_USER,
        ),
        text.TXT_CHAR_MODIFY_OK.format(name="测试卡"),
    )
    saved = await get_character(_GROUP, _USER)
    assert saved is not None and saved.name == "新名字"
    assert saved.portrait == char.portrait
    assert (tmp_path / saved.portrait).exists()


@pytest.mark.asyncio
async def test_card_delete_removes_portrait(app: App, tmp_path: Path) -> None:
    char = gen_template_char(str(_GROUP), str(_USER))
    card_id = await create_bound_card(_GROUP, _USER, char)
    char.portrait = await portraits.save_portrait(card_id, _PNG_1PX)
    await save_card(card_id, char)
    path = tmp_path / char.portrait
    assert path.exists()
    await _expect(
        app,
        char_matcher,
        fake_group_message_event_v11(
            message=Message(".角色卡解绑"), group_id=_GROUP, user_id=_USER
        ),
        text.TXT_CHAR_UNBIND_OK,
    )
    await _expect(
        app,
        char_matcher,
        fake_group_message_event_v11(
            message=Message(".角色卡清除 测试卡 确认"), group_id=_GROUP, user_id=_USER
        ),
        text.TXT_CHAR_DELETE_OK.format(name="测试卡"),
    )
    assert not path.exists()
