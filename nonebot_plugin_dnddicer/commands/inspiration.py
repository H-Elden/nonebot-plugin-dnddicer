"""英雄激励（``.激励``，2026-10-24 新增）。

记录仍存放在 ``DNDCharacter.progress["激励"]``（``有`` / ``无``；键缺失 =
未记录），不新增字段、不改卡面段语法。称呼按群级规则版本区分：2024 / 5r
为「英雄激励」，2014 / 5e 为「激励」；数据键不随版本改名。

命令面：

- ``.激励`` / ``.激励 状态``：查看本人状态（有 / 无 / 未记录）；
- ``.激励 +``：获得；已有则提示不能叠加；
- ``.激励 -``：消耗；本来没有则提示；
- ``.激励 给予 目标``：转赠给 ``@玩家`` 或本群角色名（精确优先 → 子串）。

改激励直接改 ``progress`` 字典后保存整卡，不走整段覆盖，避免清掉经验。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent

from ..character import rules as char_rules
from ..character.models import DNDCharacter
from ..data.characters import (
    get_character,
    list_characters_by_group,
    save_character,
)
from ..platform import onebot_v11
from . import base, text

_HELP = (
    ".激励 [状态|+|-|给予 目标]\n"
    "  查看 / 获得 / 消耗英雄激励（2014 称激励）\n"
    "  给予：转赠给 @玩家 或本群角色名\n"
    "  示例：.激励 + ｜ .激励 给予 @阿岩"
)
inspiration_matcher = base.on_dnd_command(
    "激励", _HELP, doc="guide/character-card"
)


def inspiration_label(version: str) -> str:
    """规则版本对应的称呼：2024 / 5r → 英雄激励；2014 / 5e → 激励。"""
    if version == char_rules.RULES_2024:
        return "英雄激励"
    return "激励"


def _state(character: DNDCharacter) -> str:
    """读取当前状态：有 / 无 / 未记录。"""
    value = character.progress.get("激励", "")
    if value == "有":
        return text.TXT_INSPIRE_STATE_YES
    if value == "无":
        return text.TXT_INSPIRE_STATE_NO
    return text.TXT_INSPIRE_STATE_UNRECORDED


def _has_inspiration(character: DNDCharacter) -> bool:
    return character.progress.get("激励") == "有"


async def _match_group_chars(
    group_id: int | str, query: str
) -> List[DNDCharacter]:
    """按角色名匹配本群已绑定卡：精确优先，其次子串。"""
    lowered = query.strip().lower()
    chars = await list_characters_by_group(group_id)
    if not lowered:
        return []
    exact = [
        char for char in chars
        if (char.name or "").strip().lower() == lowered
    ]
    if exact:
        return exact
    return [
        char for char in chars
        if lowered in (char.name or "").strip().lower()
    ]


async def _resolve_give_target(
    event: GroupMessageEvent, target_text: str
) -> Tuple[Optional[DNDCharacter], Optional[str], Optional[str]]:
    """解析转赠目标 → (角色卡, 展示名, 错误类型)。

    错误类型：``self``（目标是自己）/ ``at_miss``（@ 无卡）/ ``multiple`` /
    ``miss``；成功时两项为 None。
    """
    mention_qq = onebot_v11.parse_mention_token(target_text)
    if mention_qq is not None:
        if mention_qq == str(event.user_id):
            return None, None, "self"
        character = await get_character(event.group_id, mention_qq)
        if character is None or not character.is_init:
            return None, None, "at_miss"
        return character, character.name, None

    matches = await _match_group_chars(event.group_id, target_text)
    if len(matches) > 1:
        return None, "/".join(char.name for char in matches), "multiple"
    if not matches:
        return None, None, "miss"
    character = matches[0]
    if str(character.user_id) == str(event.user_id):
        return None, None, "self"
    return character, character.name, None


@inspiration_matcher.handle()
async def handle_inspiration(bot: Bot, event: MessageEvent) -> None:
    """处理 .激励：状态 / 获得 / 消耗 / 转赠。"""
    if not isinstance(event, GroupMessageEvent):
        await inspiration_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await inspiration_matcher.finish(text.TXT_CHAR_MISS)

    label = inspiration_label(
        await char_rules.rules_version(event.group_id)
    )
    name = await base.resolve_display_name(
        bot, event, char_name=character.name
    )

    # 转赠
    if rest.startswith("给予"):
        target_text = rest[2:].strip()
        if not target_text:
            await inspiration_matcher.finish(text.TXT_INSPIRE_USAGE)
        if not _has_inspiration(character):
            await inspiration_matcher.finish(
                text.TXT_INSPIRE_GIVE_NONE.format(label=label)
            )
        target, target_name, error = await _resolve_give_target(
            event, target_text
        )
        if error == "self":
            await inspiration_matcher.finish(
                text.TXT_INSPIRE_GIVE_SELF.format(label=label)
            )
        if error == "at_miss":
            qq = onebot_v11.parse_mention_token(target_text)
            await inspiration_matcher.finish(
                onebot_v11.at_reply(qq, text.TXT_MENTION_NO_CHAR)
            )
        if error == "multiple":
            await inspiration_matcher.finish(
                text.TXT_TARGET_CARD_MULTI.format(
                    name=target_text, names=target_name
                )
            )
        if error == "miss" or target is None:
            await inspiration_matcher.finish(
                text.TXT_CHAR_TARGET_MISS.format(name=target_text)
            )
        if _has_inspiration(target):
            target_display = await base.resolve_display_name(
                bot, event, target.user_id, char_name=target.name
            )
            await inspiration_matcher.finish(
                text.TXT_INSPIRE_GIVE_HAS.format(
                    target=target_display, label=label
                )
            )

        character.progress["激励"] = "无"
        target.progress["激励"] = "有"
        await save_character(character)
        await save_character(target)
        target_display = await base.resolve_display_name(
            bot, event, target.user_id, char_name=target.name
        )
        await inspiration_matcher.finish(
            text.TXT_INSPIRE_GIVE.format(
                giver=name, target=target_display, label=label
            )
        )

    if not rest or rest == "状态":
        await inspiration_matcher.finish(
            text.TXT_INSPIRE_STATE.format(
                name=name, label=label, state=_state(character)
            )
        )

    if rest in ("+", "＋"):
        if _has_inspiration(character):
            await inspiration_matcher.finish(
                text.TXT_INSPIRE_GAIN_ALREADY.format(name=name, label=label)
            )
        character.progress["激励"] = "有"
        await save_character(character)
        await inspiration_matcher.finish(
            text.TXT_INSPIRE_GAIN.format(name=name, label=label)
        )

    if rest in ("-", "－"):
        if not _has_inspiration(character):
            await inspiration_matcher.finish(
                text.TXT_INSPIRE_SPEND_NONE.format(name=name, label=label)
            )
        character.progress["激励"] = "无"
        await save_character(character)
        await inspiration_matcher.finish(
            text.TXT_INSPIRE_SPEND.format(name=name, label=label)
        )

    await inspiration_matcher.finish(text.TXT_INSPIRE_USAGE)
