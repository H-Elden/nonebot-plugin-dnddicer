"""有使用次数的能力命令：``.能力`` / ``.设置能力`` / ``.删除能力``。

命令面（2026-10-20 批②新增）：

- ``.能力``：列出卡上全部能力（当前/上限与恢复档）；
- ``.能力 名称``：查看单个能力详情；
- ``.能力 名称 -N`` / ``+N``：消耗 / 恢复 N 次（N 缺省 1），不会越过 0 与上限；
- ``.设置能力 名称:当前/上限恢复档``：录入或覆盖（多项用 ``;`` 分隔）；
- ``.删除能力 名称``：删除（支持模糊匹配，多个用 ``/`` 分隔）。

恢复档（``短休`` / ``长休`` / ``两者`` / ``手动``，可后缀 ``+N`` 或 ``满``）
本批只做记录与展示；短休 / 长休的自动恢复在休息批次接入。名称匹配沿用
武器与目标搜索的两级口径：精确优先，其次子串，多候选列清单、不猜。
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ..character.constants import FEATURE_MAX_COUNT
from ..character.models import CharacterFeature
from ..character.services import match_features, parse_feature_list
from ..data.characters import get_character, save_character
from . import base, text

_HELP = (
    ".能力 [名称[±N]]\n"
    "  无参数：列出卡上能力与恢复档\n"
    "  写名称：查看详情；名称 -N 消耗、+N 恢复\n"
    "  录入：.设置能力 名称:当前/上限恢复\n"
    "  示例：.能力 引导神力 -1"
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
    "  删除卡上能力，名称支持模糊匹配\n"
    "  未找到或名称不明确时逐项回报"
)
del_feature_matcher = base.on_dnd_command(
    "删除能力", _HELP_DEL_FEATURE, doc="guide/resources"
)

#: 名称 + 可选 ±N 后缀（名称本身禁含 ±，可安全按尾部符号切分）
_FEATURE_ACTION_RE = re.compile(r"^(.*?)\s*([+-])\s*(\d*)$")


def _format_feature_lines(features: List[CharacterFeature]) -> str:
    """能力清单的编号多行展示（清单 / 设置 / 删除反馈共用）。"""
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


@ability_matcher.handle()
async def handle_ability(event: MessageEvent) -> None:
    """处理 .能力：清单 / 详情 / 消耗与恢复。"""
    if not isinstance(event, GroupMessageEvent):
        await ability_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await ability_matcher.finish(text.TXT_CHAR_MISS)

    if not rest:
        if not character.features:
            await ability_matcher.finish(text.TXT_FEATURE_LIST_EMPTY)
        await ability_matcher.finish(
            text.TXT_FEATURE_LIST.format(
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
        await set_feature_matcher.finish(f"能力数量最多 {FEATURE_MAX_COUNT} 项")

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
