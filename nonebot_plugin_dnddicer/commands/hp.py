"""HP 管理命令：``.hp`` + 长休 ``.长休``。

迁移自 nonebot-dicepp ``module/character/dnd5e/hp_command.py``（commit 732ff74），
适配本插件 ``on_dnd_command`` 注册模式。

目标搜索覆盖三类（对齐 DicePP 优先级）：PC 角色卡 → NPC 血量条目 → 先攻表；
NPC 血量条目在目标经先攻表解析时按需创建——即 NPC 需先 ``.ri`` 入先攻表
（或已存在血量记录），与 DicePP 一致；先攻表联动（查看显示 / 清空与删除时
清理）见 commands/initiative.py。

DM 掷伤害扩展：目标名后可带 抗性/易伤 后缀（伤害减半/加倍，仅对 - 生效），
目标以 ;（半角/全角）分隔可一次对多个目标结算 AOE；伤害表达式只掷骰一次。
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent

from ..character.models import DNDCharacter, HPInfo
from ..character.services import HPService
from ..data.characters import (
    delete_character,
    get_character,
    list_characters_by_group,
    save_character,
)
from ..data.initiative import get_init_list
from ..data.npc_health import (
    delete_npc_health,
    get_npc_health,
    list_npc_health,
    save_npc_health,
)
from ..engine.roll.ast_engine.adapter import exec_roll_exp_unified
from ..engine.roll.result import RollResult
from ..engine.roll.roll_utils import RollDiceError
from ..platform.onebot_v11 import get_group_member_nickname
from . import base, text

# =========================================================================
# .hp 命令
# =========================================================================

_HELP = (
    "设置生命值: .hp [对象] [=, 或空格] [当前生命值/最大生命值] [(临时生命值)]\n"
    "示例:\n"
    ".hp 20/30 -> 将自己的当前生命值设为20, 最大生命值设为30\n"
    ".hp (10) -> 将自己的临时生命值设为10\n"
    ".hp 队友A 30/30 (10) -> 将队友A的当前和最大生命值都设为30, 临时生命值设为10\n"
    "调整生命值: .hp [对象] [+/-] [调整值]\n"
    "示例:\n"
    ".hp +2d10 -> 将自己的当前生命值增加2d10\n"
    ".hp +(10) -> 将自己的临时生命值增加10\n"
    ".hp +20/10 -> 先将最大HP增加10, 再将当前HP增加20\n"
    ".hp 队友A -4d6 -> 对队友A造成4d6点伤害\n"
    "NPC/怪物: 先 .ri 名称 加入先攻表后, 可用 .hp 名称 10/10 记录其血量"
    " (先攻列表中随条目一起展示)\n"
    "NPC 血量默认每次新入先攻表时自动回满, 需要跨战斗保持用 .npc 持久 名称\n"
    "删除生命值: .hp del [对象]\n"
    "查看生命值: .hp -> 查看自己当前的生命值信息\n"
    "查看列表: .hp list -> 查看本群所有PC与NPC的生命值\n"
    "注意: 指定对象时只需名称中独一无二的一部分即可"
)
hp_matcher = base.on_dnd_command("hp", _HELP)


# =========================================================================
# .长休 命令
# =========================================================================

_HELP_LONG_REST = "进行一次长休：恢复生命值至上限、清除临时生命值、回复一半生命骰。"
long_rest_matcher = base.on_dnd_command("长休", _HELP_LONG_REST)


# =========================================================================
# 目标搜索（PC 角色卡 → NPC 血量 → 先攻表，对齐 DicePP 优先级）
# =========================================================================

#: 目标名后缀 → 伤害折算因子（DM 掷伤害用）
_DAMAGE_MOD_SUFFIXES: Tuple[Tuple[str, float], ...] = (("抗性", 0.5), ("易伤", 2.0))


def _split_target_suffix(intent: str) -> Tuple[str, float]:
    """拆目标名后的 抗性/易伤 后缀 → (目标关键字, 伤害折算因子)。

    只对伤害（-）生效的语义由调用方校验（非伤害命令带后缀时报错）。
    """
    for suffix, factor in _DAMAGE_MOD_SUFFIXES:
        if intent.endswith(suffix):
            return intent[: -len(suffix)], factor
    return intent, 1.0


def _match_substring(substring: str, str_list: list[str]) -> list[str]:
    """找到所有包含输入字符串的字符串；存在完全匹配时只返回完全匹配。

    完全匹配优先（2026-09-21 修订）：先攻表/血量条目里同时有「地精」与
    「熊地精」时，``.hp 地精`` 应直接命中地精——与 ``.init`` 子指令的
    「精确 → 模糊 substring」两级匹配一致（DicePP 原版仅做 substring，
    会把两者都列为歧义）。
    """
    if substring in str_list:
        return [substring]
    return [s for s in str_list if substring in s]


async def search_target(
    target_intent: str, group_id: int | str
) -> Tuple[str, str]:
    """在群内 PC 角色卡 / NPC 血量 / 先攻列表中模糊搜索目标。

    返回 (source_key, target_id)：
    - ("pc", user_id) PC 角色卡
    - ("npc", 名称) NPC 血量条目（或无血量、但存在于先攻表的 NPC）
    - ("multiple", "name1/name2") 多个匹配
    - ("", "") 未找到

    优先级（对齐 DicePP）：精确匹配 角色卡 > NPC > 先攻表；部分匹配同序
    取先到者，但后续来源的**精确**匹配可覆盖前序部分匹配。
    """
    source, target_id = "", ""

    # 1. PC 角色卡
    chars = await list_characters_by_group(group_id)
    pc_name_map: dict[str, str] = {}
    for char in chars:
        pc_name_map[char.user_id] = char.name or str(char.user_id)
    matches = _match_substring(target_intent, list(pc_name_map.values()))
    if len(matches) > 1:
        return "multiple", "/".join(matches)
    if len(matches) == 1:
        for uid, name in pc_name_map.items():
            if name == matches[0]:
                source, target_id = "pc", uid
                if name == target_intent:
                    return source, target_id
                break

    # 2. NPC 血量条目
    npc_names = [npc.name for npc in await list_npc_health(group_id)]
    matches = _match_substring(target_intent, npc_names)
    if len(matches) > 1:
        return "multiple", "/".join(matches)
    if len(matches) == 1:
        if not source:
            source, target_id = "npc", matches[0]
        if matches[0] == target_intent:
            return "npc", matches[0]

    # 3. 先攻表（NPC 需先入表才能被 .hp 解析并创建血量，对齐 DicePP）
    init_data = await get_init_list(group_id)
    if init_data is not None:
        entity_map: dict[str, str] = {
            entity.name: entity.owner for entity in init_data.entities
        }
        matches = _match_substring(target_intent, list(entity_map.keys()))
        if len(matches) > 1:
            return "multiple", "/".join(matches)
        if len(matches) == 1:
            name = matches[0]
            owner = entity_map[name]
            resolved = ("pc", owner) if owner else ("npc", name)
            if not source:
                source, target_id = resolved
            if name == target_intent:
                return resolved

    return source, target_id


# =========================================================================
# 参数解析
# =========================================================================


def _parse_hp_args(arg_str: str) -> Tuple[
    Optional[RollResult],  # hp_cur
    Optional[RollResult],  # hp_max
    Optional[RollResult],  # hp_temp
    Optional[str],  # error
]:
    """解析调整表达式（不含目标前缀与操作符），返回 (cur, max, temp, error)。

    对齐 DicePP hp_command.process_msg 表达式解析段：末尾 ``(expr)`` 为临时 HP，
    其余按 ``/`` 拆为 当前/最大 HP。
    """
    # 临时 HP：末尾 (expr)
    hp_temp_result: Optional[RollResult] = None
    temp_match = re.search(r"\((.*?)\)$", arg_str)
    if temp_match:
        try:
            hp_temp_result = exec_roll_exp_unified(temp_match.group(1))
        except RollDiceError as e:
            return None, None, None, e.info
        arg_str = arg_str[:temp_match.span()[0]].strip()

    if not arg_str and not temp_match:
        return None, None, None, "没有给定调整值"

    hp_cur_result: Optional[RollResult] = None
    hp_max_result: Optional[RollResult] = None
    if arg_str:
        arg_list = arg_str.split("/", 1)
        try:
            if len(arg_list) == 2:
                hp_cur_result = exec_roll_exp_unified(arg_list[0])
                hp_max_result = exec_roll_exp_unified(arg_list[1])
            else:
                hp_cur_result = exec_roll_exp_unified(arg_str)
        except RollDiceError as e:
            return None, None, None, e.info

    return hp_cur_result, hp_max_result, hp_temp_result, None


# =========================================================================
# 处理器
# =========================================================================


@hp_matcher.handle()
async def handle_hp(bot: Bot, event: MessageEvent) -> None:
    """处理 .hp 命令。"""
    if not isinstance(event, GroupMessageEvent):
        await hp_matcher.finish(text.TXT_GROUP_ONLY)

    arg_str = (base.get_command_rest(event) or "").strip()

    # 查看自己
    if not arg_str:
        character = await get_character(event.group_id, event.user_id)
        if character and character.is_init and character.hp_info.is_init:
            name = character.name or base.get_display_name(event)
            feedback = text.TXT_HP_INFO.format(name=name, hp_info=character.hp_info.get_info())
        else:
            name = base.get_display_name(event)
            feedback = text.TXT_HP_INFO_MISS.format(name=name)
        await hp_matcher.finish(feedback)

    # 列表（无卡记录不再直接显示 QQ 号——名称回退链
    # 角色卡名 → 群名片 → QQ 昵称 → 「未知玩家」；无卡名成员需调
    # get_group_member_info，本插件放宽「离线可用」原则的唯一一处，
    # API 失败/异常由适配层吞掉、名称回退下一级，不影响列表主流程）
    if arg_str.startswith("list"):
        chars = await list_characters_by_group(event.group_id)
        feedback = ""
        for char in chars:
            if char.hp_info.is_init:
                name = char.name
                if not name:
                    name = await get_group_member_nickname(
                        bot, event.group_id, int(char.user_id)
                    )
                    name = name or text.TXT_HP_UNKNOWN_NAME
                feedback += f"{name} {char.hp_info.get_info()}\n"
        # NPC/怪物血量（对齐 DicePP：PC 在前、NPC 在后）
        for npc in await list_npc_health(event.group_id):
            feedback += f"{npc.name} {npc.hp_info.get_info()}\n"
        feedback = feedback.strip()
        if not feedback:
            feedback = text.TXT_HP_INFO_NONE
        await hp_matcher.finish(feedback)

    # 删除（.hp del [对象]：无对象删除自己；对齐 DicePP）
    if arg_str.startswith("del") or arg_str.startswith("clr"):
        del_arg = arg_str[3:].strip()
        if not del_arg:
            await delete_character(event.group_id, event.user_id)
            name = base.get_display_name(event)
            await hp_matcher.finish(text.TXT_HP_DEL.format(name=name))
        source_key, target_id = await search_target(del_arg, event.group_id)
        if source_key == "multiple":
            await hp_matcher.finish(text.TXT_HP_INFO_MULTI.format(
                name_list=target_id.split("/")
            ))
        if not source_key:
            await hp_matcher.finish(text.TXT_HP_INFO_MISS_HINT.format(name=del_arg))
        if source_key == "npc":
            await delete_npc_health(event.group_id, target_id)
            await hp_matcher.finish(text.TXT_HP_DEL.format(name=target_id))
        character = await get_character(event.group_id, target_id)
        await delete_character(event.group_id, target_id)
        name = character.name if character is not None and character.name else target_id
        await hp_matcher.finish(text.TXT_HP_DEL.format(name=name))

    # 调整 HP（流程对齐 DicePP hp_command.process_msg：先定位操作符，
    # 再剥离目标前缀，最后解析调整表达式）。操作符 = 首个 + / - / = ，
    # 或首个空格（设置目标 HP）；空格后紧跟 +/-/= 时按该符号识别
    # （如 ".hp 爱丽丝 -d8+3+d6" 的 - 是伤害操作符，空格不视为设置符）。
    cmd_type: str = "="
    max_len = 2 ** 20
    cmd_index_eq = arg_str.find("=") if "=" in arg_str else max_len
    cmd_index_add = arg_str.find("+") if "+" in arg_str else max_len
    cmd_index_sub = arg_str.find("-") if "-" in arg_str else max_len
    cmd_index_space = arg_str.find(" ") if " " in arg_str else max_len
    if cmd_index_space != max_len:
        next_non_space = arg_str[cmd_index_space + 1:].lstrip()
        if next_non_space and next_non_space[0] in "+-=":
            cmd_index_space = max_len  # 空格不是设置符，改由符号自身定位
    cmd_index = min(cmd_index_eq, cmd_index_add, cmd_index_sub, cmd_index_space)
    if cmd_index == max_len:
        cmd_index = -1
    elif cmd_index == cmd_index_eq or cmd_index == cmd_index_space:
        cmd_type = "="
    elif cmd_index == cmd_index_add:
        cmd_type = "+"
    elif cmd_index == cmd_index_sub:
        cmd_type = "-"

    target_list: list[Tuple[str, str, float]] = []
    if cmd_index == 0:
        # 直接以操作符开头，无目标指定
        arg_str = arg_str[1:].strip()
    elif cmd_index > 0:
        target_part = arg_str[:cmd_index].strip()
        # 本插件扩展：DicePP 会把 ".hp 10/30 (5)" 的 "10/30" 当目标搜索而报错；
        # 目标部分含 "/" 或 "(" 时视为表达式而非目标，不做剥离
        if target_part and "/" not in target_part and "(" not in target_part:
            arg_str = arg_str[cmd_index + 1:].strip()
            # 目标以 ;（半角/全角均可）分隔，实现 AOE 多目标一次结算
            for target_intent in re.split(r"[;；]", target_part):
                target_intent = target_intent.strip()
                target_name, damage_factor = _split_target_suffix(target_intent)
                if cmd_type != "-" and damage_factor != 1.0:
                    await hp_matcher.finish(text.TXT_HP_FACTOR_DMG_ONLY)
                source_key, target_id = await search_target(target_name, event.group_id)
                if source_key in ("pc", "npc"):
                    target_list.append((source_key, target_id, damage_factor))
                elif source_key == "multiple":
                    names = target_id.split("/")
                    feedback = text.TXT_HP_INFO_MULTI.format(name_list=names)
                    await hp_matcher.finish(feedback)
                else:
                    feedback = text.TXT_HP_INFO_MISS_HINT.format(name=target_name)
                    await hp_matcher.finish(feedback)

    if not target_list:
        target_list = [("pc", str(event.user_id), 1.0)]

    # 解析调整表达式（arg_str 已剥离目标前缀与操作符）
    hp_cur, hp_max, hp_temp, error = _parse_hp_args(arg_str)
    if error:
        await hp_matcher.finish(text.TXT_HP_MOD_ERR.format(error=error))

    # 应用调整
    feedback = ""
    for source_key, target_id, damage_factor in target_list:
        if source_key == "npc":
            # NPC/怪物：血量条目按需创建（目标经先攻表/已有记录解析而来）
            hp_info = await get_npc_health(event.group_id, target_id)
            if hp_info is None:
                hp_info = HPInfo()
            mod_info = HPService.process_roll_result(
                hp_info, cmd_type, hp_cur, hp_max, hp_temp,
                short_feedback=(len(target_list) > 1),
                damage_factor=damage_factor,
            )
            await save_npc_health(event.group_id, target_id, hp_info)
            feedback += text.TXT_HP_MOD.format(name=target_id, hp_mod=mod_info) + "\n"
            continue

        character = await get_character(event.group_id, target_id)
        if character is None:
            character = DNDCharacter(group_id=str(event.group_id), user_id=target_id)

        mod_info = HPService.process_roll_result(
            character.hp_info, cmd_type, hp_cur, hp_max, hp_temp,
            short_feedback=(len(target_list) > 1),
            damage_factor=damage_factor,
        )
        character.is_init = True
        await save_character(character)

        if target_id == str(event.user_id):
            name = character.name or base.get_display_name(event)
        else:
            name = character.name or target_id
        feedback += text.TXT_HP_MOD.format(name=name, hp_mod=mod_info) + "\n"

    await hp_matcher.finish(feedback.strip())


@long_rest_matcher.handle()
async def handle_long_rest(event: MessageEvent) -> None:
    """处理 .长休 命令。"""
    if not isinstance(event, GroupMessageEvent):
        await long_rest_matcher.finish(text.TXT_GROUP_ONLY)

    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        name = base.get_display_name(event)
        await long_rest_matcher.finish(text.TXT_LONG_REST_MISS.format(name=name))

    name = character.name or base.get_display_name(event)
    rest_info = character.hp_info.long_rest()
    if not rest_info:
        rest_info = "没有需要恢复的内容"
    result = f"{name}进行了一次长休\n{rest_info}"
    await save_character(character)
    await long_rest_matcher.finish(result)
