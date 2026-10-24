"""限定资源命令：``.能力`` / ``.设置能力`` / ``.删除能力``。

命令面（2026-10-20 批②新增）：
- ``.能力``：列出卡上全部限定资源（当前/上限与恢复档）；
- ``.能力 名称``：查看单个限定资源详情；
- ``.能力 名称 -N`` / ``+N``：消耗 / 恢复 N 次（N 缺省 1），不会越过 0 与上限；
- ``.设置能力 名称:当前/上限恢复档``：录入或覆盖（多项用 ``;`` 分隔）；
- ``.删除能力 名称``：删除（支持模糊匹配，多个用 ``/`` 分隔）。

恢复档（``短休`` / ``长休`` / ``两者`` / ``手动``，可后缀 ``+N`` 或 ``满``）
短休 / 长休时由休息服务自动恢复。名称匹配沿用武器与目标搜索的两级口径：
精确优先，其次子串，多候选列清单、不猜。
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent

from ..character.constants import FEATURE_MAX_COUNT
from ..character.models import CharacterFeature, DNDCharacter
from ..character.services import match_features, parse_feature_list
from ..data.characters import (
    get_character,
    list_characters_by_group,
    save_character,
)
from ..platform import onebot_v11
from . import base, card_helpers, text

_HELP = (
    ".能力 [目标] [名称[±N]]\n"
    "  无参数：列出卡上限定资源与恢复档\n"
    "  目标：@玩家 或角色名，可代看 / 代改\n"
    "  写名称：详情；名称 -N 消耗、+N 恢复\n"
    "  示例：.能力 薇拉 引导神力 -1"
)
ability_matcher = base.on_dnd_command("能力", _HELP, doc="guide/resources")

_HELP_SET_FEATURE = (
    ".设置能力 名称:当前/上限恢复档\n"
    "  恢复档：短休/长休/两者/手动，可加 +N 或 满\n"
    "  多项用 ; 分隔；同名覆盖\n"
    "  示例：.设置能力 引导神力:2/2短休+1,长休"
)
set_feature_matcher = base.on_dnd_command(
    "设置能力", _HELP_SET_FEATURE, doc="guide/resources"
)

_HELP_DEL_FEATURE = (
    ".删除能力 名称 （多个用 / 分隔）\n"
    "  删除卡上限定资源，名称支持模糊匹配\n"
    "  未找到或名称不明确时逐项回报"
)
del_feature_matcher = base.on_dnd_command(
    "删除能力", _HELP_DEL_FEATURE, doc="guide/resources"
)

#: 名称 + 可选 ±N 后缀（名称本身禁含 ±，可安全按尾部符号切分）
_FEATURE_ACTION_RE = re.compile(r"^(.*?)\s*([+-])\s*(\d*)$")


def _format_feature_lines(features: List[CharacterFeature]) -> str:
    """限定资源清单的编号多行展示（清单 / 设置 / 删除反馈共用）。"""
    return "\n".join(
        text.TXT_FEATURE_ITEM.format(
            index=index,
            name=feature.name,
            cur=feature.uses_cur,
            max=feature.uses_max,
            recover=feature.get_recover_display(),
        )
        for index, feature in enumerate(features, start=1)
    )


def _parse_feature_action(rest: str) -> Optional[Tuple[str, str, int]]:
    """解析 ``名称 ±N`` → (名称, 符号, 次数)；不是增减写法时返回 None。"""
    matched = _FEATURE_ACTION_RE.match(rest)
    if matched is None:
        return None
    name = matched.group(1).strip()
    if not name:
        return None
    amount = int(matched.group(3)) if matched.group(3) else 1
    return name, matched.group(2), amount


def _find_feature(
    features: List[CharacterFeature], name: str
) -> Tuple[Optional[CharacterFeature], List[CharacterFeature]]:
    """精确优先 → 子串；返回 (唯一命中, 全部候选)。"""
    candidates = match_features(features, name)
    if len(candidates) == 1:
        return candidates[0], candidates
    return None, candidates


async def _resolve_ability_target(
    bot: Bot, event: GroupMessageEvent, rest: str
) -> Tuple[Optional[DNDCharacter], str, str]:
    """拆出 ``.能力`` 开头的目标 → (目标卡, 剩余参数, 展示名)。

    没有目标时返回 ``(None, 原参数, "")``，由调用方按本人卡处理。
    ``@`` 直连 QQ；名称按本群已绑定卡「精确优先 → 子串」，多候选列清单、
    不猜（含与本人能力名同名的边界，见文档）。
    目标无卡 / 多候选会直接回复并结束命令。
    """
    mentions = onebot_v11.iter_mentions(rest)
    if mentions:
        target_qq = mentions[0]
        character = await get_character(event.group_id, target_qq)
        if character is None or not character.is_init:
            await ability_matcher.finish(
                onebot_v11.at_reply(target_qq, text.TXT_MENTION_NO_CHAR)
            )
        remaining = onebot_v11.strip_mentions(rest).strip()
        display = await base.resolve_display_name(
            bot, event, target_qq, char_name=character.name
        )
        return character, remaining, display

    if not rest:
        return None, rest, ""

    chars = await list_characters_by_group(event.group_id)
    full_matches = await card_helpers.find_group_characters(
        event.group_id, rest
    )
    if len(full_matches) > 1:
        await ability_matcher.finish(
            text.TXT_TARGET_CARD_MULTI.format(
                name=rest,
                names="/".join(char.name or char.user_id for char in full_matches),
            )
        )
    if len(full_matches) == 1 and (
        (full_matches[0].name or "").strip().lower() == rest.lower()
    ):
        display = await base.resolve_display_name(
            bot, event, full_matches[0].user_id,
            char_name=full_matches[0].name,
        )
        return full_matches[0], "", display

    # 名称可能含空格：优先取最长的「完整名称 + 空白」前缀
    for character in sorted(chars, key=lambda item: len(item.name or ""), reverse=True):
        name = (character.name or "").strip()
        if not name or not rest.startswith(name):
            continue
        if len(rest) > len(name) and rest[len(name)].isspace():
            display = await base.resolve_display_name(
                bot, event, character.user_id, char_name=character.name
            )
            return character, rest[len(name):].strip(), display

    # 否则把首个空白前的文本当目标名做模糊匹配；匹配不到就整段按本人能力名
    token, separator, tail = rest.partition(" ")
    matches = await card_helpers.find_group_characters(
        event.group_id, token
    )
    if len(matches) > 1:
        await ability_matcher.finish(
            text.TXT_TARGET_CARD_MULTI.format(
                name=token,
                names="/".join(char.name or char.user_id for char in matches),
            )
        )
    if len(matches) == 1:
        display = await base.resolve_display_name(
            bot, event, matches[0].user_id, char_name=matches[0].name
        )
        return matches[0], tail.strip() if separator else "", display
    return None, rest, ""


@ability_matcher.handle()
async def handle_ability(bot: Bot, event: MessageEvent) -> None:
    """处理 .能力：清单 / 详情 / 消耗与恢复（支持 @ 与角色名目标）。"""
    if not isinstance(event, GroupMessageEvent):
        await ability_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    target, rest, target_name = await _resolve_ability_target(
        bot, event, rest
    )
    if target is None:
        character = await get_character(event.group_id, event.user_id)
        if character is None or not character.is_init:
            await ability_matcher.finish(text.TXT_CHAR_MISS)
    else:
        character = target

    if not rest:
        if not character.features:
            template = (
                text.TXT_FEATURE_LIST_EMPTY_TARGET
                if target is not None
                else text.TXT_FEATURE_LIST_EMPTY
            )
            await ability_matcher.finish(
                template.format(name=target_name)
            )
        template = (
            text.TXT_FEATURE_LIST_TARGET
            if target is not None
            else text.TXT_FEATURE_LIST
        )
        await ability_matcher.finish(
            template.format(
                name=target_name,
                count=len(character.features),
                items=_format_feature_lines(character.features),
            )
        )

    action = _parse_feature_action(rest)
    if action is None:
        # 只写了符号（如 .能力 +1）：给用法，不当成名称去查
        if rest[0] in "+-":
            await ability_matcher.finish(text.TXT_FEATURE_USAGE)
        feature, candidates = _find_feature(character.features, rest)
        if feature is None:
            if candidates:
                await ability_matcher.finish(
                    text.TXT_FEATURE_VAGUE.format(
                        name=rest,
                        names="/".join(item.name for item in candidates),
                    )
                )
            await ability_matcher.finish(
                text.TXT_FEATURE_NOT_FOUND.format(name=rest)
            )
        if target is not None:
            await ability_matcher.finish(
                text.TXT_FEATURE_DETAIL_TARGET.format(
                    name=target_name,
                    feature=feature.name,
                    cur=feature.uses_cur,
                    max=feature.uses_max,
                    recover=feature.get_recover_display(),
                )
            )
        await ability_matcher.finish(
            text.TXT_FEATURE_DETAIL.format(
                name=feature.name,
                cur=feature.uses_cur,
                max=feature.uses_max,
                recover=feature.get_recover_display(),
            )
        )

    name, sign, amount = action
    if amount < 1:
        await ability_matcher.finish(text.TXT_FEATURE_AMOUNT_INVALID)
    feature, candidates = _find_feature(character.features, name)
    if feature is None:
        if candidates:
            await ability_matcher.finish(
                text.TXT_FEATURE_VAGUE.format(
                    name=name,
                    names="/".join(item.name for item in candidates),
                )
            )
        await ability_matcher.finish(text.TXT_FEATURE_NOT_FOUND.format(name=name))

    old = feature.uses_cur
    if sign == "-" and old == 0:
        await ability_matcher.finish(
            text.TXT_FEATURE_ALREADY_EMPTY.format(
                name=feature.name, max=feature.uses_max
            )
        )
    note = ""
    if sign == "-":
        feature.uses_cur = max(0, old - amount)
        if feature.uses_cur == 0 and old > 0:
            note = text.TXT_FEATURE_MOD_EXHAUSTED
    else:
        feature.uses_cur = min(feature.uses_max, old + amount)
        if feature.uses_cur == feature.uses_max and old < feature.uses_max:
            note = text.TXT_FEATURE_MOD_FULL
    if feature.uses_cur != old:
        await save_character(character)
    if target is not None:
        await ability_matcher.finish(
            text.TXT_FEATURE_MOD_TARGET.format(
                name=target_name,
                feature=feature.name,
                old=old,
                max=feature.uses_max,
                new=feature.uses_cur,
                note=note,
            )
        )
    await ability_matcher.finish(
        text.TXT_FEATURE_MOD.format(
            name=feature.name,
            old=old,
            max=feature.uses_max,
            new=feature.uses_cur,
            note=note,
        )
    )


@set_feature_matcher.handle()
async def handle_set_feature(event: MessageEvent) -> None:
    """处理 .设置能力：录入或覆盖（仅操作本人角色卡）。"""
    if not isinstance(event, GroupMessageEvent):
        await set_feature_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    if not rest:
        await set_feature_matcher.finish(text.TXT_FEATURE_SET_USAGE)
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await set_feature_matcher.finish(text.TXT_CHAR_MISS)

    try:
        new_features = parse_feature_list(rest)
    except AssertionError as exc:
        await set_feature_matcher.finish(str(exc))

    merged: List[CharacterFeature] = list(character.features)
    set_names: List[str] = []
    for feature in new_features:
        # 名称完全一致才算覆盖（子串命中不用于覆盖判定，避免误盖同名片段）
        existing = next(
            (
                item for item in merged
                if item.name.lower() == feature.name.lower()
            ),
            None,
        )
        if existing is not None:
            merged[merged.index(existing)] = feature
        else:
            merged.append(feature)
        set_names.append(feature.name)
    if len(merged) > FEATURE_MAX_COUNT:
        await set_feature_matcher.finish(f"限定资源数量最多 {FEATURE_MAX_COUNT} 项")

    character.features = merged
    await save_character(character)
    await set_feature_matcher.finish(
        text.TXT_FEATURE_SET.format(
            names="/".join(set_names),
            count=len(merged),
            items=_format_feature_lines(merged),
        )
    )


@del_feature_matcher.handle()
async def handle_del_feature(event: MessageEvent) -> None:
    """处理 .删除能力（支持 / 与 ; 分隔多个；名称可只写一部分）。"""
    if not isinstance(event, GroupMessageEvent):
        await del_feature_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    if not rest:
        await del_feature_matcher.finish(text.TXT_FEATURE_DEL_USAGE)
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await del_feature_matcher.finish(text.TXT_CHAR_MISS)

    names = [
        item.strip()
        for item in re.split(r"[/;；]", rest)
        if item.strip()
    ]
    remained: List[CharacterFeature] = list(character.features)
    deleted: List[str] = []
    missing: List[str] = []
    vague: List[str] = []
    for name in names:
        candidates = match_features(remained, name)
        if not candidates:
            missing.append(name)
        elif len(candidates) > 1:
            vague.append(
                text.TXT_FEATURE_DEL_VAGUE_ITEM.format(
                    name=name,
                    names="/".join(item.name for item in candidates),
                )
            )
        else:
            remained.remove(candidates[0])
            deleted.append(candidates[0].name)

    lines: List[str] = []
    if deleted:
        if missing:
            lines.append(
                text.TXT_FEATURE_DEL_PARTIAL.format(
                    deleted="/".join(deleted), missing="/".join(missing)
                )
            )
        else:
            lines.append(text.TXT_FEATURE_DEL.format(deleted="/".join(deleted)))
    elif missing:
        lines.append(text.TXT_FEATURE_DEL_MISS.format(missing="/".join(missing)))
    if vague:
        lines.append(
            text.TXT_FEATURE_DEL_VAGUE.format(items="；".join(vague))
        )
    if not lines:  # 理论不可达（names 非空时必有结论），防御性兜底
        lines.append(text.TXT_FEATURE_DEL_MISS.format(missing="/".join(names)))

    if deleted:
        character.features = remained
        await save_character(character)
    await del_feature_matcher.finish("\n".join(lines))
