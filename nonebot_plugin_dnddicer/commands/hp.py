"""HP 管理命令：``.hp`` + 长休 ``.长休``。

迁移自 nonebot-dicepp ``module/character/dnd5e/hp_command.py``（commit 732ff74），
适配本插件 ``on_dnd_command`` 注册模式。

一期简化：不迁移 NPC 生命值与先攻列表联动（数据层尚未实现），
目标搜索仅覆盖群内 PC 角色卡。
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ..character.models import DNDCharacter
from ..character.services import HPService
from ..data.characters import (
    delete_character,
    get_character,
    list_characters_by_group,
    save_character,
)
from ..engine.roll.ast_engine.adapter import exec_roll_exp_unified
from ..engine.roll.result import RollResult
from ..engine.roll.roll_utils import RollDiceError
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
    "删除生命值: .hp del\n"
    "查看生命值: .hp -> 查看自己当前的生命值信息\n"
    "查看列表: .hp list -> 查看本群所有PC的生命值\n"
    "注意: 指定对象时只需名称中独一无二的一部分即可"
)
hp_matcher = base.on_dnd_command("hp", _HELP)


# =========================================================================
# .长休 命令
# =========================================================================

_HELP_LONG_REST = "进行一次长休：恢复生命值至上限、清除临时生命值、回复一半生命骰。"
long_rest_matcher = base.on_dnd_command("长休", _HELP_LONG_REST)


# =========================================================================
# 目标搜索（简化版：仅 PC 角色卡）
# =========================================================================


def _match_substring(substring: str, str_list: list[str]) -> list[str]:
    """找到所有包含输入字符串的字符串（对齐 DicePP utils/string.py match_substring）。"""
    return [s for s in str_list if substring in s]


async def _search_target(
    target_intent: str, group_id: int | str
) -> Tuple[str, str]:
    """在群内 PC 角色卡中模糊搜索目标。

    返回 (source_key, target_id)：
    - ("pc", user_id) 找到唯一匹配
    - ("multiple", "name1/name2") 多个匹配
    - ("", "") 未找到
    """
    chars = await list_characters_by_group(group_id)
    if not chars:
        return "", ""

    name_map: dict[str, str] = {}
    for char in chars:
        display = char.name or str(char.user_id)
        name_map[char.user_id] = display

    matches = _match_substring(target_intent, list(name_map.values()))
    if len(matches) == 1:
        for uid, name in name_map.items():
            if name == matches[0]:
                return "pc", uid
    elif len(matches) > 1:
        return "multiple", "/".join(matches)
    return "", ""


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
async def handle_hp(event: MessageEvent) -> None:
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

    # 列表
    if arg_str.startswith("list"):
        chars = await list_characters_by_group(event.group_id)
        feedback = ""
        for char in chars:
            if char.hp_info.is_init:
                name = char.name or str(char.user_id)
                feedback += f"{name} {char.hp_info.get_info()}\n"
        feedback = feedback.strip()
        if not feedback:
            feedback = text.TXT_HP_INFO_NONE
        await hp_matcher.finish(feedback)

    # 删除
    if arg_str.startswith("del") or arg_str.startswith("clr"):
        await delete_character(event.group_id, event.user_id)
        name = base.get_display_name(event)
        await hp_matcher.finish(text.TXT_HP_DEL.format(name=name))

    # 调整 HP（流程对齐 DicePP hp_command.process_msg：先定位操作符，
    # 再剥离目标前缀，最后解析调整表达式）
    cmd_type: str = "="
    max_len = 2 ** 20
    cmd_index_eq = arg_str.find("=") if "=" in arg_str else max_len
    cmd_index_add = arg_str.find("+") if "+" in arg_str else max_len
    cmd_index_sub = arg_str.find("-") if "-" in arg_str else max_len
    cmd_index_space = arg_str.find(" ") if " " in arg_str else max_len
    cmd_index = min(cmd_index_eq, cmd_index_add, cmd_index_sub, cmd_index_space)
    if cmd_index == max_len:
        cmd_index = -1
    elif cmd_index == cmd_index_eq or cmd_index == cmd_index_space:
        cmd_type = "="
    elif cmd_index == cmd_index_add:
        cmd_type = "+"
    elif cmd_index == cmd_index_sub:
        cmd_type = "-"

    target_list: list[Tuple[str, str]] = []
    if cmd_index == 0:
        # 直接以操作符开头，无目标指定
        arg_str = arg_str[1:].strip()
    elif cmd_index > 0:
        target_part = arg_str[:cmd_index].strip()
        # 本插件扩展：DicePP 会把 ".hp 10/30 (5)" 的 "10/30" 当目标搜索而报错；
        # 目标部分含 "/" 或 "(" 时视为表达式而非目标，不做剥离
        if target_part and "/" not in target_part and "(" not in target_part:
            arg_str = arg_str[cmd_index + 1:].strip()
            for target_intent in target_part.split(";"):
                target_intent = target_intent.strip()
                source_key, target_id = await _search_target(target_intent, event.group_id)
                if source_key == "pc":
                    target_list.append((source_key, target_id))
                elif source_key == "multiple":
                    names = target_id.split("/")
                    feedback = text.TXT_HP_INFO_MULTI.format(name_list=names)
                    await hp_matcher.finish(feedback)
                else:
                    feedback = text.TXT_HP_INFO_MISS.format(name=target_intent)
                    await hp_matcher.finish(feedback)

    if not target_list:
        target_list = [("pc", str(event.user_id))]

    # 解析调整表达式（arg_str 已剥离目标前缀与操作符）
    hp_cur, hp_max, hp_temp, error = _parse_hp_args(arg_str)
    if error:
        await hp_matcher.finish(text.TXT_HP_MOD_ERR.format(error=error))

    # 应用调整
    feedback = ""
    for source_key, target_id in target_list:
        character = await get_character(event.group_id, target_id)
        if character is None:
            character = DNDCharacter(group_id=str(event.group_id), user_id=target_id)

        mod_info = HPService.process_roll_result(
            character.hp_info, cmd_type, hp_cur, hp_max, hp_temp,
            short_feedback=(len(target_list) > 1),
        )
        character.is_init = True
        await save_character(character)

        if source_key == "pc":
            if target_id == str(event.user_id):
                name = character.name or base.get_display_name(event)
            else:
                name = character.name or target_id
        else:
            name = target_id
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
