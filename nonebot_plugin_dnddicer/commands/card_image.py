"""角色卡图命令：``.角色卡图 [@玩家|角色名]``（2026-10-21）。

- 群聊限定（卡库化之前，私聊没有「本群角色卡」上下文）；
- 自己 / 他人与 ``.角色卡`` 同口径：@ 直连，角色名走「PC → NPC → 先攻表」
  三层搜索；查看开放、修改仍限本人；
- 渲染不可用或渲染异常时回退文字卡，并在末尾附一行「请联系骰主解决」；
- 渲染走 ``render.char_card_available()`` 与 ``render.render_char_card``，
  测试可注入假渲染器，CI 不需要 htmlkit。
"""

from __future__ import annotations

from typing import Optional

from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent,
    MessageSegment,
)
from nonebot.matcher import Matcher

from ..character.card_view import build_card_view
from ..character.models import DNDCharacter
from ..data import portraits
from ..data.characters import get_character, save_character
from ..platform import onebot_v11
from ..render import char_card_available, render_char_card
from . import base, text

_HELP = (
    ".角色卡图 [@玩家|角色名]\n"
    "  将本群角色卡渲染为图片\n"
    "  支持查看他人；需骰主开启图片渲染\n"
    "  示例：.角色卡图 ｜ .角色卡图 @阿茶"
)
character_image_matcher = base.on_dnd_command(
    "角色卡图", _HELP, doc="guide/card-image"
)

_HELP_PORTRAIT = (
    ".立绘\n"
    "  发送图片并附带本命令，设置当前卡立绘\n"
    "  原图保存，建议方形；仅支持 PNG/JPG/WebP，≤4 MB\n"
    "  示例：发图后输入 .立绘"
)
portrait_matcher = base.on_dnd_command(
    "立绘", _HELP_PORTRAIT, doc="guide/card-image"
)


def _fallback_text(character: DNDCharacter, target_name: str = "") -> str:
    """渲染不可用时的文字卡（他人带标题行）+ 一行回退提示。"""
    body = character.get_char_info()
    if target_name:
        body = text.TXT_CHAR_TARGET_TITLE.format(name=target_name) + "\n" + body
    return f"{body}\n{text.TXT_CARD_IMAGE_FALLBACK}"


async def _resolve_target(
    bot: Bot,
    event: GroupMessageEvent,
    matcher: Matcher,
    rest: str,
) -> Optional[tuple[DNDCharacter, str]]:
    """解析查看目标，返回 (角色卡, 展示名)；无法查看时已回复并返回 None。

    无参数 = 自己；有参数走与 ``.角色卡`` 相同的目标搜索与文案。
    """
    if not rest:
        character = await get_character(event.group_id, event.user_id)
        if character is None or not character.is_init:
            await matcher.finish(text.TXT_CHAR_MISS)
        return character, ""

    # 延迟导入：保持 commands 包的导入顺序（同 commands/character.py）
    from .hp import search_target

    source_key, target_id = await search_target(rest, event.group_id)
    if source_key == "at_miss":
        await matcher.finish(
            onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
        )
    if source_key == "multiple":
        await matcher.finish(
            text.TXT_HP_INFO_MULTI.format(name_list=target_id.split("/"))
        )
    if source_key == "npc":
        await matcher.finish(text.TXT_CHAR_NPC_NO_CARD.format(name=target_id))
    if source_key == "pc":
        character = await get_character(event.group_id, target_id)
        if character is None or not character.is_init:
            await matcher.finish(
                onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
            )
        name = await base.resolve_display_name(
            bot, event, target_id, char_name=character.name
        )
        return character, name

    await matcher.finish(text.TXT_CHAR_TARGET_MISS.format(name=rest))
    return None


@character_image_matcher.handle()
async def handle_character_image(bot: Bot, event: MessageEvent) -> None:
    """``.角色卡图``：渲染本群角色卡为图片，失败回退文字卡。"""
    if not isinstance(event, GroupMessageEvent):
        await character_image_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    resolved = await _resolve_target(bot, event, character_image_matcher, rest)
    if resolved is None:  # 理论不可达：_resolve_target 内已 finish
        return
    character, target_name = resolved

    if char_card_available():
        try:
            portrait_data = b""
            portrait_mime = ""
            if character.portrait:
                loaded = await portraits.load_portrait(character.portrait)
                if loaded is not None:
                    portrait_data, portrait_mime = loaded
            png = await render_char_card(
                build_card_view(character, portrait_data, portrait_mime)
            )
        except Exception:
            logger.exception("DNDDicer 角色卡图渲染失败，已回退文字输出")
        else:
            await character_image_matcher.finish(MessageSegment.image(png))

    await character_image_matcher.finish(_fallback_text(character, target_name))


@portrait_matcher.handle()
async def handle_portrait(bot: Bot, event: MessageEvent) -> None:
    """``.立绘``：取本条消息第一张图片，原图保存为当前卡立绘。"""
    if not isinstance(event, GroupMessageEvent):
        await portrait_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    if rest:
        await portrait_matcher.finish(text.TXT_PORTRAIT_USAGE)

    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await portrait_matcher.finish(text.TXT_CHAR_MISS)

    images = onebot_v11.image_segments(event)
    if not images:
        await portrait_matcher.finish(text.TXT_PORTRAIT_USAGE)

    try:
        data = await portraits.fetch_image_bytes(bot, images[0])
        name = await portraits.save_portrait(
            str(event.group_id), str(event.user_id), data
        )
    except portraits.PortraitTooLarge:
        await portrait_matcher.finish(text.TXT_PORTRAIT_TOO_LARGE)
    except portraits.PortraitBadFormat:
        await portrait_matcher.finish(text.TXT_PORTRAIT_BAD_FORMAT)
    except portraits.PortraitError:
        await portrait_matcher.finish(text.TXT_PORTRAIT_FETCH_FAILED)

    character.portrait = name
    await save_character(character)
    feedback = text.TXT_PORTRAIT_SET
    if len(images) > 1:
        feedback += text.TXT_PORTRAIT_MULTI
    await portrait_matcher.finish(feedback)
