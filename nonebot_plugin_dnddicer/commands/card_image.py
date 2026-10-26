"""角色卡图片：卡面渲染辅助与 ``.立绘`` 命令。

- ``render_card_png``：供 ``.角色卡`` 调用，角色卡图开关开启且渲染依赖可用时
  返回 PNG 字节，不可用或渲染异常返回 ``None``（调用方回退文字卡）；
- ``.立绘`` 不带图片：查看立绘——群聊看本群绑定卡，``@玩家`` / 角色名看他人；
  私聊按卡名看本人卡（卡库仅一张可省略）；
- ``.立绘 [卡名]`` + 图片：设置立绘——群聊只能改本群绑定卡，私聊按卡名改本人卡；
- 立绘按 ``card_id`` 落盘；旧路径若存在继续可读，不做文件迁移。
"""

from __future__ import annotations

from typing import List

from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    MessageSegment,
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
    ".立绘 / .立绘 @玩家 / .立绘 角色名\n"
    "  查看立绘（群聊看本群绑定卡，@ 或角色名看他人）\n"
    "  私聊 .立绘 [卡名] 看本人卡（单张可省略）\n"
    "  设置：发送图片并附带 .立绘 [卡名]\n"
    "  群聊只能改本群绑定卡；私聊多张卡需带卡名\n"
    "  原图保存，建议方形；PNG/JPG/WebP，≤4 MB"
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


async def _view_portrait(
    bot: Bot, event: MessageEvent, rest: str
) -> None:
    """``.立绘``：查看自己或他人的立绘（目标解析与 ``.角色卡`` 同口径）。"""
    character, target_name = await card_helpers.resolve_view_target(
        bot, event, portrait_matcher, rest
    )
    loaded = await portraits.load_portrait(character.portrait)
    if loaded is None:
        if character.portrait:
            # 卡上记了文件名但文件缺失/损坏：与「未设置」区分，提示重新上传
            await portrait_matcher.finish(text.TXT_PORTRAIT_LOAD_FAILED)
        if character.user_id == str(event.user_id):
            await portrait_matcher.finish(text.TXT_PORTRAIT_NONE_SELF)
        await portrait_matcher.finish(
            text.TXT_PORTRAIT_NONE_TARGET.format(
                name=target_name or character.name
            )
        )
    data, _mime = loaded
    await portrait_matcher.finish(MessageSegment.image(data))


async def _set_portrait(
    bot: Bot, event: MessageEvent, rest: str, images: List[dict]
) -> None:
    """``.立绘 [卡名]`` + 图片：校验目标并原图保存。"""
    if rest.startswith("@") or len(rest.split()) > 1:
        await portrait_matcher.finish(text.TXT_PORTRAIT_SET_USAGE)
    if isinstance(event, GroupMessageEvent):
        card_id, card_name, character = await card_helpers.resolve_group_bound(
            event.group_id, event.user_id, portrait_matcher
        )
        if rest and rest.casefold() != card_name.casefold():
            await portrait_matcher.finish(
                text.TXT_CHAR_MODIFY_GROUP_MISMATCH.format(name=card_name)
            )
    elif rest:
        card_id, card_name, character = await card_helpers.resolve_private_manage(
            event.user_id, rest, portrait_matcher
        )
    else:
        card_id, card_name, character = await card_helpers.resolve_private_current(
            event.user_id, "", portrait_matcher
        )

    try:
        data = await portraits.fetch_image_bytes(bot, images[0])
        name = await portraits.save_portrait(
            card_id, data, character.portrait
        )
    except portraits.PortraitTooLarge:
        await portrait_matcher.finish(text.TXT_PORTRAIT_TOO_LARGE)
    except portraits.PortraitBadFormat:
        await portrait_matcher.finish(text.TXT_PORTRAIT_BAD_FORMAT)
    except portraits.PortraitError:
        await portrait_matcher.finish(text.TXT_PORTRAIT_FETCH_FAILED)

    character.portrait = name
    await save_card(card_id, character)
    feedback = text.TXT_PORTRAIT_SET.format(name=card_name)
    if len(images) > 1:
        feedback += text.TXT_PORTRAIT_MULTI
    await portrait_matcher.finish(feedback)


@portrait_matcher.handle()
async def handle_portrait(bot: Bot, event: MessageEvent) -> None:
    """``.立绘``：带图片设置立绘，不带图片查看立绘。"""
    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    images = onebot_v11.image_segments(event)
    if images:
        await _set_portrait(bot, event, rest, images)
        return
    await _view_portrait(bot, event, rest)
