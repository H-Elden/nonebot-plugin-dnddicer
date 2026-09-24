"""自定义武器/法术命令：``.X攻击`` / ``.X命中``（攻击检定）与 ``.X伤害``。

命令面（非固定命令名，按消息模式触发，与检定点命令同款机制）：

- ``.短剑攻击`` / ``.短剑命中``：以角色卡 ``$武器$`` 段中该武器的命中加值掷
  攻击检定（如 ``1D20+6``）；支持 ``N#`` 批量（``.2#短剑攻击``）、``优势`` /
  ``劣势``、``±`` 临时加值（可组合）与 ``@玩家``（DM 代掷）；
- ``.短剑伤害``：掷伤害骰并提示伤害类型（``造成了 8 点穿刺伤害``）；后缀
  ``副手`` / ``重击`` / ``偷袭`` 写在「伤害」之前、可任意组合
  （如 ``.短剑重击偷袭伤害``）——
  副手 = 剔除伤害表达式中全部常数项（不加任何加值）；重击 = 所有骰子项骰数
  ×2（固定加值不变、偷袭骰同样翻倍）；偷袭 = 按角色卡职业（游荡者）与整体
  等级自动附加 N 颗 d6（暂不支持兼职，见角色卡职业段校验）。

**机器人不做命中判断**（不判 AC，由玩家/DM 自行比较）；攻击检定 d20 出目
20/1 追加 DND 术语提示（``天然20：重击！`` 引导 ``.X重击伤害``、``天然1：必失``），
不使用 .r 的「大成功/大失败」文案。

匹配与让位：

- 固定命令（``match_command_name`` 命中，如 ``.角色卡攻击``）让位、不接管；
- 属性攻击检定点已退役（2026-09-24）：``.力量攻击`` 一类输入不再有检定点语义，
  按武器命令处理、落回「未找到武器」的默认提示（武器名经录入校验不得与检定
  条目重名，两者天然互斥）。

武器名对照发送者（或 @ 目标）当前角色卡的武器列表；查无该武器给出引导提示。
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher
from nonebot.plugin import on_message
from nonebot.rule import Rule

from ..character.constants import WEAPON_DAMAGE_SUFFIX_LIST, WEAPON_MAX_COUNT
from ..character.models import DNDCharacter, WeaponInfo
from ..character.services import (
    WEAPON_BONUS_RE,
    apply_critical_to_damage,
    get_sneak_attack_dice,
    parse_weapon_list,
    strip_damage_constants,
)
from ..config import get_config
from ..data.characters import get_character, save_character
from ..engine.roll.ast_engine.adapter import exec_roll_exp_unified
from ..engine.roll.roll_utils import RollDiceError
from ..engine.roll.result import RollResult
from ..platform import onebot_v11
from . import base, text

#: 攻击命令体模式：([1-9]#)? 武器名 (攻击|命中) 剩余(优劣势/加值/@)
_WEAPON_ATTACK_PATTERN = re.compile(r"^([1-9]#)?(.+?)(攻击|命中)(.*)$")
#: 伤害命令体模式：名称与后缀 伤害 剩余(@)
_WEAPON_DAMAGE_PATTERN = re.compile(r"^(.+?)伤害(.*)$")


def parse_weapon_attack_body(body: str) -> Optional[Tuple[int, str, str]]:
    """解析武器攻击命令体 → (次数, 武器名, 修正串)；无效返回 None。

    修正串可含 优势/劣势 前缀、±临时加值与 @ 标记（由 handler 处理）。
    """
    matched = _WEAPON_ATTACK_PATTERN.match(body)
    if not matched:
        return None
    time_part, name_part, _kind, tail = matched.groups()
    if not name_part.strip():
        return None
    times = int(time_part[:-1]) if time_part else 1
    return times, name_part.strip(), tail.strip()


def parse_weapon_attack_entry(body: str) -> Optional[Tuple[str, str]]:
    """识别「[N#]武器名(攻击|命中)…」形态 → (武器名, 关键词)；否则 None。

    供 ``.hp`` 伤害位置上的误用引导（攻击检定不是伤害掷骰，应改用
    「武器名伤害」，见 commands/hp.py）；与 parse_weapon_attack_body 共用
    同一模式，区别只在返回内容。
    """
    matched = _WEAPON_ATTACK_PATTERN.match(body)
    if not matched:
        return None
    _time_part, name_part, kind, _tail = matched.groups()
    if not name_part.strip():
        return None
    return name_part.strip(), kind


def parse_weapon_damage_body(body: str) -> Optional[Tuple[str, List[str], str]]:
    """解析武器伤害命令体 → (武器名, 后缀列表, 剩余文本)；无效返回 None。

    后缀（副手/重击/偷袭）写在「伤害」之前、可任意组合；名称段从右向左逐个
    剥后缀，且保证剥完名称非空（名为「重击」的武器不会被剥空误判）。
    「伤害」之后的剩余文本仅允许 @ 标记（由 handler 校验其余内容）。
    """
    matched = _WEAPON_DAMAGE_PATTERN.match(body)
    if not matched:
        return None
    entry_part, tail = matched.groups()
    suffixes: List[str] = []
    name = entry_part.strip()
    while name:
        for word in WEAPON_DAMAGE_SUFFIX_LIST:
            if name.endswith(word) and len(name) > len(word):
                name = name[: -len(word)].strip()
                suffixes.append(word)
                break
        else:
            break
    if not name:
        return None
    return name, suffixes, tail.strip()


def _is_weapon_body(body: str) -> bool:
    """命令体是否是武器命令（攻击/命中/伤害之一，供 rule 使用）。"""
    return (
        parse_weapon_attack_body(body) is not None
        or parse_weapon_damage_body(body) is not None
    )


def _weapon_command_rule() -> Rule:
    async def _checker(event: MessageEvent) -> bool:
        plain = event.get_plaintext().strip()
        if not plain:
            return False
        # 必须以本插件起始符开头，且非已注册固定命令（固定命令优先）
        starts = base.get_command_starts()
        matched_start = next((s for s in starts if plain.startswith(s)), None)
        if matched_start is None:
            return False
        body = plain[len(matched_start):]
        fixed_name, _ = base.match_command_name(body)
        if fixed_name is not None:
            return False
        return _is_weapon_body(body)

    # 群聊服务门禁（与固定命令一致：未开启服务的群不响应）
    return Rule(_checker) & base.group_service_rule()


def _make_weapon_matcher() -> Matcher:
    priority = get_config().dnddicer_command_priority
    return on_message(_weapon_command_rule(), priority=priority, block=True)


weapon_matcher = _make_weapon_matcher()


def find_weapon_in(
    weapons: List[WeaponInfo], name: str
) -> Optional[WeaponInfo]:
    """在武器列表中按名称查找（大小写不敏感）。"""
    for weapon in weapons:
        if weapon.name == name or weapon.name.lower() == name.lower():
            return weapon
    return None


def find_weapon(character: DNDCharacter, name: str) -> Optional[WeaponInfo]:
    """在角色卡武器列表中按名称查找（大小写不敏感）。"""
    return find_weapon_in(character.weapons, name)


def build_damage_expression(
    weapon: WeaponInfo,
    suffixes: List[str],
    level: int,
    char_class: str,
    tail: str = "",
) -> Tuple[str, Optional[str], int]:
    """按后缀（副手 / 重击 / 偷袭）把武器伤害项变换为最终掷骰表达式。

    2026-09-24 起由 ``.X伤害`` 与 ``.hp`` 的伤害位置共用，保证两处语义一致
    （临时加值并入表达式、参与后缀变换：重击时同样翻倍、副手时同样剔常数）。

    Returns:
        (表达式, 错误文案, 偷袭骰数)：错误文案非 None 时表达式不可用，
        由调用方直接回复给用户；偷袭骰数供 ``.X伤害`` 的读数标注使用。
    """
    expression = weapon.damage_expr + tail
    if "副手" in suffixes:
        expression = strip_damage_constants(expression)
        if not expression:
            return "", text.TXT_WEAPON_OFFHAND_NO_DICE.format(weapon=weapon.name), 0

    sneak_dice = 0
    if "偷袭" in suffixes:
        sneak_dice = get_sneak_attack_dice(level, char_class)
        if sneak_dice <= 0:
            error = (
                text.TXT_WEAPON_SNEAK_NO_CLASS.format(weapon=weapon.name)
                if not char_class
                else text.TXT_WEAPON_SNEAK_NOT_ROGUE.format(char_class=char_class)
            )
            return "", error, 0
        expression += f"+{sneak_dice}d6"

    if "重击" in suffixes:
        expression = apply_critical_to_damage(expression)
    return expression, None, sneak_dice


def _format_weapon_lines(weapons: List[WeaponInfo]) -> str:
    """武器列表的编号多行展示（.设置武器 反馈用，2026-09-24 用户要求格式化）。"""
    return "\n".join(
        f"{index}. {weapon.get_info()}"
        for index, weapon in enumerate(weapons, start=1)
    )


def build_damage_note(suffixes: List[str], sneak_dice: int, is_crit: bool) -> str:
    """伤害后缀的读数标注（如「（重击）」「（含偷袭3D6）」）；无后缀返回空串。

    由 ``.X伤害`` 与 ``.hp`` 武器伤害写法的表头共用（偷袭骰重击时同样翻倍）。
    """
    note_parts: List[str] = []
    if "副手" in suffixes:
        note_parts.append("副手：不加任何加值")
    if is_crit:
        note_parts.append("重击")
    if "偷袭" in suffixes:
        actual_dice = sneak_dice * (2 if is_crit else 1)
        note_parts.append(f"含偷袭{actual_dice}D6")
    return f"（{'，'.join(note_parts)}）" if note_parts else ""


async def _load_target_character(
    event: MessageEvent, target_qq: Optional[str]
) -> DNDCharacter:
    """取 @ 目标（无 @ 时取发送者）的角色卡；无卡给引导提示并终止本命令。"""
    if target_qq is not None:
        character = await get_character(event.group_id, target_qq)
        if character is None or not character.is_init:
            await weapon_matcher.finish(
                onebot_v11.at_reply(target_qq, text.TXT_MENTION_NO_CHAR)
            )
    else:
        character = await get_character(event.group_id, event.user_id)
        if character is None or not character.is_init:
            await weapon_matcher.finish(text.TXT_CHAR_MISS)
    return character


async def _handle_attack(
    bot: Bot, event: MessageEvent, times: int, weapon_name: str, mod_str: str
) -> None:
    """攻击检定：D20（可优劣势）+ 武器命中加值 + 临时加值。"""
    # 修正串中的 @ 目标（DM 代掷，与检定点同规则）
    target_qq, mod_str = base.split_target_mention(mod_str)
    character = await _load_target_character(event, target_qq)

    weapon = find_weapon(character, weapon_name)
    if weapon is None:
        await weapon_matcher.finish(text.TXT_WEAPON_NOT_FOUND.format(name=weapon_name))
    if weapon.no_attack:
        # x 标记：纯伤害法术（如 火球术），不做攻击检定
        await weapon_matcher.finish(
            text.TXT_WEAPON_NO_ATTACK.format(weapon=weapon.name)
        )

    # 解析临时优劣势（修正串开头的 优势/劣势；与检定点同款）
    advantage = 0
    if mod_str.startswith("优势"):
        advantage = 1
        mod_str = mod_str[2:]
    elif mod_str.startswith("劣势"):
        advantage = -1
        mod_str = mod_str[2:]
    mod_str = mod_str.strip()

    roll_exp = "D20"
    if advantage > 0:
        roll_exp += "优势"
    elif advantage < 0:
        roll_exp += "劣势"
    roll_exp += weapon.attack_bonus + mod_str

    # 注：不做「预校验掷骰」——那会额外消耗一次随机数；表达式问题走下面的
    # 正式掷骰错误路径（归因到用户输入的修正串或武器加值，给出可读提示）
    results: List[str] = []
    roll_results: List[RollResult] = []
    for _ in range(times):
        try:
            roll_result = exec_roll_exp_unified(roll_exp)
        except RollDiceError as exc:
            bad = mod_str if mod_str else weapon.attack_bonus
            await weapon_matcher.finish(
                text.TXT_WEAPON_BAD_MOD.format(mod=bad, reason=exc.info)
            )
        results.append(roll_result.get_complete_result())
        roll_results.append(roll_result)

    name = await base.resolve_display_name(
        bot, event, target_qq, char_name=character.name
    )
    hint_parts: List[str] = []
    hint_parts.append(
        f"武器命中加值:{weapon.attack_bonus}" if weapon.attack_bonus else "无命中加值"
    )
    if advantage > 0:
        hint_parts.append("优势")
    elif advantage < 0:
        hint_parts.append("劣势")
    display_check = f"{weapon.name}攻击检定"
    if times > 1:
        display_check = f"{times}次{display_check}"

    nat_state = text.format_nat_attack_state(roll_results, weapon.name)
    if nat_state:
        # 天然 20/1 提示单独成行（2026-09-24 用户要求）
        results.append(nat_state)

    await weapon_matcher.finish(
        text.TXT_WEAPON_ATTACK.format(
            name=name,
            check=display_check,
            hint=" ".join(hint_parts),
            result="\n".join(results),
        )
    )


async def _handle_damage(
    bot: Bot,
    event: MessageEvent,
    weapon_name: str,
    suffixes: List[str],
    tail: str,
) -> None:
    """伤害结算：伤害表达式 + 临时加值 + 后缀变换（副手 / 重击 / 偷袭）。"""
    # 「伤害」之后的剩余文本：允许 @ 标记与 ± 临时加值（如升环火球术 .火球术伤害+1d6）
    target_qq, mod_str = base.split_target_mention(tail)
    if mod_str and not WEAPON_BONUS_RE.match(mod_str):
        await weapon_matcher.finish(text.TXT_WEAPON_DAMAGE_TAIL.format(tail=mod_str))
    character = await _load_target_character(event, target_qq)

    weapon = find_weapon(character, weapon_name)
    if weapon is None:
        await weapon_matcher.finish(text.TXT_WEAPON_NOT_FOUND.format(name=weapon_name))

    is_off_hand = "副手" in suffixes
    is_crit = "重击" in suffixes
    is_sneak = "偷袭" in suffixes

    # 后缀变换与 .hp 的伤害位置共用同一实现（临时加值并入表达式、参与后缀变换）
    expression, error, sneak_dice = build_damage_expression(
        weapon, suffixes, character.ability_info.level, character.char_class, mod_str
    )
    if error:
        await weapon_matcher.finish(error)

    try:
        roll_result = exec_roll_exp_unified(expression)
    except RollDiceError as exc:
        await weapon_matcher.finish(
            text.TXT_WEAPON_BAD_MOD.format(mod=expression, reason=exc.info)
        )
    total = roll_result.get_val()

    note = build_damage_note(suffixes, sneak_dice, is_crit)

    name = await base.resolve_display_name(
        bot, event, target_qq, char_name=character.name
    )
    await weapon_matcher.finish(
        text.TXT_WEAPON_DAMAGE.format(
            name=name,
            weapon=weapon.name,
            total=total,
            type=weapon.damage_type,
            note=note,
            result=roll_result.get_complete_result(),
        )
    )


@weapon_matcher.handle()
async def handle_weapon(bot: Bot, event: MessageEvent) -> None:
    """处理 .X攻击 / .X命中 / .X伤害（rule 已确保命中且参数可解析）。"""
    if not isinstance(event, GroupMessageEvent):
        await weapon_matcher.finish(text.TXT_GROUP_ONLY)

    # 用带标记文本解析：@ 目标保留在修正串中（规则层仍基于纯文本）
    text_body = onebot_v11.strip_leading_mentions(
        onebot_v11.rebuild_text_with_mentions(event)
    ).strip()
    start = next(
        (s for s in base.get_command_starts() if text_body.startswith(s)), None
    )
    if start is None:  # 理论不可达（rule 已过滤），防御性兜底
        return
    body = text_body[len(start):]

    attack = parse_weapon_attack_body(body)
    if attack is not None:
        await _handle_attack(bot, event, *attack)
        return
    damage = parse_weapon_damage_body(body)
    if damage is not None:
        await _handle_damage(bot, event, *damage)
        return
    # 理论不可达（rule 已过滤）：不响应


# =========================================================================
# 武器管理命令（.设置武器 / .删除武器，2026-09-24 拍板新增）
# =========================================================================

_HELP_SET_WEAPON = (
    "设置/修改自定义武器（供 .X攻击 / .X命中 / .X伤害 使用）：\n"
    "用法：.设置武器 短剑+6,1d4+4穿刺（名称+命中加值,伤害表达式+类型；多项用 / 分隔）\n"
    "同名武器会被覆盖；无参数时查看当前武器列表"
)
set_weapon_matcher = base.on_dnd_command("设置武器", _HELP_SET_WEAPON)

_HELP_DEL_WEAPON = "删除自定义武器：.删除武器 短剑（多个用 / 分隔）"
del_weapon_matcher = base.on_dnd_command("删除武器", _HELP_DEL_WEAPON)


@set_weapon_matcher.handle()
async def handle_set_weapon(event: MessageEvent) -> None:
    """处理 .设置武器（增/改/列出；仅操作本人角色卡）。"""
    if not isinstance(event, GroupMessageEvent):
        await set_weapon_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await set_weapon_matcher.finish(text.TXT_CHAR_MISS)

    if not rest:
        if not character.weapons:
            await set_weapon_matcher.finish(text.TXT_WEAPON_LIST_EMPTY)
        await set_weapon_matcher.finish(
            text.TXT_WEAPON_LIST.format(
                count=len(character.weapons),
                items=_format_weapon_lines(character.weapons),
            )
        )

    try:
        new_weapons = parse_weapon_list(rest, tuple(base.get_registered_commands()))
    except AssertionError as exc:
        await set_weapon_matcher.finish(str(exc))

    merged: List[WeaponInfo] = list(character.weapons)
    set_names: List[str] = []
    for weapon in new_weapons:
        existing = find_weapon_in(merged, weapon.name)
        if existing is not None:
            merged[merged.index(existing)] = weapon
        else:
            merged.append(weapon)
        set_names.append(weapon.name)
    if len(merged) > WEAPON_MAX_COUNT:
        await set_weapon_matcher.finish(f"武器数量最多 {WEAPON_MAX_COUNT} 件")

    character.weapons = merged
    await save_character(character)
    await set_weapon_matcher.finish(
        text.TXT_WEAPON_SET.format(
            names="/".join(set_names),
            count=len(merged),
            items=_format_weapon_lines(merged),
        )
    )


@del_weapon_matcher.handle()
async def handle_del_weapon(event: MessageEvent) -> None:
    """处理 .删除武器（支持 / 分隔多个；仅操作本人角色卡）。"""
    if not isinstance(event, GroupMessageEvent):
        await del_weapon_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    if not rest:
        await del_weapon_matcher.finish(text.TXT_WEAPON_DEL_USAGE)
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await del_weapon_matcher.finish(text.TXT_CHAR_MISS)

    names = [item.strip() for item in rest.split("/") if item.strip()]
    remained: List[WeaponInfo] = list(character.weapons)
    deleted: List[str] = []
    missing: List[str] = []
    for name in names:
        target = find_weapon_in(remained, name)
        if target is None:
            missing.append(name)
        else:
            remained.remove(target)
            deleted.append(target.name)

    if not deleted:
        await del_weapon_matcher.finish(
            text.TXT_WEAPON_DEL_MISS.format(missing="/".join(missing))
        )
    character.weapons = remained
    await save_character(character)
    if missing:
        await del_weapon_matcher.finish(
            text.TXT_WEAPON_DEL_PARTIAL.format(
                deleted="/".join(deleted), missing="/".join(missing)
            )
        )
    await del_weapon_matcher.finish(
        text.TXT_WEAPON_DEL.format(deleted="/".join(deleted))
    )
