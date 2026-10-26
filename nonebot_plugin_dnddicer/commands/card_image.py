"""角色卡图片：卡面渲染辅助与 ``.立绘`` 命令。

- ``render_card_png``：供 ``.角色卡`` 调用，角色卡图开关开启且渲染依赖可用时
  返回 PNG 字节，不可用或渲染异常返回 ``None``（调用方回退文字卡）；
- ``.立绘 [卡名]``：群聊设置本群绑定卡、私聊按卡名设置本人卡；
- 立绘按 ``card_id`` 落盘；旧路径若存在继续可读，不做文件迁移。
"""

from __future__ import annotations

from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
)

from ..character import rules as char_rules
from ..character.card_view import build_card_view
from ..character.models import DNDCharacter
from ..data import portraits
from ..data.characters import save_card
from ..platform import onebot_v11
from ..render import char_card_available, render_char_card
from . import base, card_helpers, text

_HELP_PORTRAIT = (
    ".立绘 [卡名]\n"
    "  发送图片并附带本命令，设置当前卡立绘\n"
    "  私聊多张卡需带卡名；群聊设置本群绑定卡\n"
    "  原图保存，建议方形；仅支持 PNG/JPG/WebP，≤4 MB"
)
portrait_matcher = base.on_dnd_command(
    "立绘", _HELP_PORTRAIT, doc="guide/character-card"
)


async def render_card_png(
    event: MessageEvent, character: DNDCharacter
) -> bytes | None:
    """渲染角色卡 PNG；开关关闭、依赖不可用或渲染失败时返回 None。"""
    if not char_card_available():
        return None
    try:
        portrait_data = b""
        portrait_mime = ""
        if character.portrait:
            loaded = await portraits.load_portrait(character.portrait)
            if loaded is not None:
                portrait_data, portrait_mime = loaded
        version = (
            await char_rules.rules_version(event.group_id)
            if isinstance(event, GroupMessageEvent)
            else char_rules.default_rules_version()
        )
        return await render_char_card(
            build_card_view(
                character,
                portrait_data,
                portrait_mime,
                version_2024=version == char_rules.RULES_2024,
            )
        )
    except Exception:
        logger.exception("DNDDicer 角色卡图片渲染失败，已回退文字输出")
        return None


@portrait_matcher.handle()
async def handle_portrait(bot: Bot, event: MessageEvent) -> None:
    """``.立绘``：取本条消息第一张图片，原图保存为当前卡立绘。"""
    rest = (base.get_command_rest(event) or "").strip()
    if isinstance(event, GroupMessageEvent):
        if rest:
            await portrait_matcher.finish(text.TXT_PORTRAIT_USAGE)
        _card_id, _card_name, character = await card_helpers.resolve_group_bound(
            event.group_id, event.user_id, portrait_matcher
        )
    else:
        if rest.startswith("@"):
            await portrait_matcher.finish(text.TXT_CHAR_PRIVATE_TARGET_UNSUPPORTED)
        _card_id, _card_name, character = await card_helpers.resolve_private_current(
            event.user_id, rest, portrait_matcher
        )

    images = onebot_v11.image_segments(event)
    if not images:
        await portrait_matcher.finish(text.TXT_PORTRAIT_USAGE)

    try:
        data = await portraits.fetch_image_bytes(bot, images[0])
        name = await portraits.save_portrait(
            character.card_id, data, character.portrait
        )
    except portraits.PortraitTooLarge:
        await portrait_matcher.finish(text.TXT_PORTRAIT_TOO_LARGE)
    except portraits.PortraitBadFormat:
        await portrait_matcher.finish(text.TXT_PORTRAIT_BAD_FORMAT)
    except portraits.PortraitError:
        await portrait_matcher.finish(text.TXT_PORTRAIT_FETCH_FAILED)

    character.portrait = name
    await save_card(character.card_id, character)
    feedback = text.TXT_PORTRAIT_SET
    if len(images) > 1:
        feedback += text.TXT_PORTRAIT_MULTI
    await portrait_matcher.finish(feedback)
