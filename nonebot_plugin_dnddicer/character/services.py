"""DND5e 角色/检定业务服务（自研；语义与提示对齐 nonebot-dicepp character/dnd5e/services.py）。

- ``AbilityService.initialize``：把「等级/六属性/熟练项/额外加值」校验写入 AbilityInfo；
- ``AbilityService.perform_check``：按条目把 D20（可优势/劣势）+ 熟练 + 调整 + 加值
  拼成掷骰表达式交 ast_engine，返回 (hint 过程说明, result 掷骰过程文本, 数值)；
- ``CharacterService.parse``：把 ``.角色卡记录`` 的 ``$xxx$`` 模板文本解析为角色；
- ``gen_template_char``：生成示例模板（供 .角色卡模板 输出）。

只处理数据，不负责存储（存储见 data/characters.py）。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from ..engine.roll.ast_engine.adapter import exec_roll_exp_unified
from ..engine.roll.roll_utils import RollDiceError
from .constants import (
    ABILITY_LIST,
    ABILITY_NUM,
    ATTACK_ALL_KEY,
    ATTACK_LIST,
    ATTACK_PARENT_DICT,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_EXT,
    CHAR_INFO_KEY_HP,
    CHAR_INFO_KEY_HP_DICE,
    CHAR_INFO_KEY_LEVEL,
    CHAR_INFO_KEY_LIST,
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_PROF,
    CHECK_ITEM_INDEX_DICT,
    CHECK_ITEM_LIST,
    EXT_ITEM_INDEX_DICT,
    EXT_ITEM_LIST,
    SAVING_ALL_KEY,
    SAVING_LIST,
    SAVING_PARENT_DICT,
    SKILL_LIST,
    SKILL_PARENT_DICT,
    SKILL_SYNONYM_DICT,
)
from .models import AbilityInfo, DNDCharacter, HPInfo


def _normalize_name(name: str) -> str:
    """把别名/俗称归一为正式条目名。"""
    return SKILL_SYNONYM_DICT.get(name, name)


def parse_template_to_dict(input_str: str) -> Dict[str, str]:
    """把角色卡模板文本（``$关键字$ 内容``）拆成 {关键字: 内容} 字典。

    ``$`` 为段落分隔符，内容中不应再出现 ``$``；与 DicePP 同款拆分语义。
    """
    result: Dict[str, str] = {}
    parts = input_str.split("$")
    for index in range(len(parts) - 1):
        key = f"${parts[index]}$"
        if key not in CHAR_INFO_KEY_LIST:
            continue
        content = parts[index + 1].strip()
        if content and content not in CHAR_INFO_KEY_LIST:
            result[key] = content
    return result


class AbilityService:
    """属性与检定服务。"""

    @staticmethod
    def initialize(
        ability_info: AbilityInfo,
        level_str: str,
        ability_values: List[int],
        prof_list: List[str],
        ext_dict: Dict[str, str],
    ) -> None:
        """校验并写入等级/六属性/熟练项/额外加值；失败抛 AssertionError（用户可见）。"""
        try:
            level = int(level_str)
            assert level > 0
        except (AssertionError, ValueError):
            raise AssertionError("等级必须为正整数")

        if len(ability_values) != ABILITY_NUM:
            raise AssertionError(f"必须设定全部的{ABILITY_NUM}项属性")
        ability = [0] * ABILITY_NUM
        for index, raw in enumerate(ability_values):
            try:
                val = int(raw)
                assert val > 0
            except (AssertionError, ValueError):
                raise AssertionError(f"{ABILITY_LIST[index]}属性值{raw}必须为正整数")
            ability[index] = val

        # 熟练项：默认所有攻击熟练；其余按清单逐项设定（支持 N*名称 多倍熟练）
        check_prof = [0] * len(CHECK_ITEM_LIST)
        for attack_name in ATTACK_LIST:
            check_prof[CHECK_ITEM_INDEX_DICT[attack_name]] = 1
        for raw in prof_list:
            scale = 1
            name = _normalize_name(raw)
            if "*" in raw:
                scale_str, name = raw.split("*", 1)
                try:
                    scale = int(scale_str)
                    assert scale >= 0
                except (AssertionError, ValueError):
                    raise AssertionError(f"{name}熟练加值倍数必须为非负整数")
                name = _normalize_name(name)
            if name not in CHECK_ITEM_LIST:
                raise AssertionError(
                    f"{name}为无效的检定条目, 可用条目:{CHECK_ITEM_LIST}"
                )
            check_prof[CHECK_ITEM_INDEX_DICT[name]] = scale

        # 额外加值：可含 优势/劣势 前缀 + +/- 表达式片段（校验可被引擎求值）
        check_ext = [""] * len(EXT_ITEM_LIST)
        check_adv = [0] * len(EXT_ITEM_LIST)
        for raw_name, ext_str in ext_dict.items():
            if not ext_str:
                continue
            name = _normalize_name(raw_name)
            if name not in EXT_ITEM_LIST:
                raise AssertionError(f"{name}为无效条目, 可用条目:\n{EXT_ITEM_LIST}")
            index = EXT_ITEM_INDEX_DICT[name]

            if ext_str.startswith(("优势", "劣势")):
                check_adv[index] = 1 if ext_str.startswith("优势") else -1
                ext_str = ext_str[2:]
            if not ext_str:
                continue
            if ext_str[0] not in ("+", "-"):
                raise AssertionError(
                    f"调整值无效: 必须以[优势/劣势]+/-开头\n{raw_name}:{ext_str}"
                )
            try:
                exec_roll_exp_unified("D20" + ext_str)
            except RollDiceError as exc:
                raise AssertionError(f"无效的调整值: {raw_name}:{ext_str} {exc.info}")
            check_ext[index] = ext_str

        ability_info.is_init = True
        ability_info.level = level
        ability_info.ability = ability
        ability_info.check_prof = check_prof
        ability_info.check_ext = check_ext
        ability_info.check_adv = check_adv

    @staticmethod
    def perform_check(
        ability_info: AbilityInfo,
        check_name: str,
        advantage: int,
        mod_str: str,
    ) -> Tuple[str, str, int]:
        """执行一次条目检定（属性/技能/豁免/攻击通用）。

        Args:
            ability_info: 已初始化的属性信息。
            check_name: 条目名（可为同义词），如 力量/运动/敏捷豁免/力量攻击/先攻。
            advantage: 本次检定的临时优劣势（1/-1/0）。
            mod_str: 本次检定的临时加值表达式片段（如 "+d4"；"优势+2" 由调用方拆好）。

        Returns:
            (hint, result, value)：过程说明 / 掷骰过程文本 / 结果数值。

        Raises:
            AssertionError: 条目无效或属性未初始化（消息面向用户）。
        """
        if not ability_info.is_init:
            raise AssertionError("未初始化属性值")

        name = _normalize_name(check_name)
        if name not in CHECK_ITEM_LIST:
            raise AssertionError(f"{name}无效, 可用检定条目:\n{CHECK_ITEM_LIST}")

        is_skill = name in SKILL_LIST
        is_saving = name in SAVING_LIST
        is_attack = name in ATTACK_LIST

        hint_parts: List[str] = []
        check_index = CHECK_ITEM_INDEX_DICT[name]
        parent_name = ""
        if is_skill:
            parent_name = SKILL_PARENT_DICT[name]
        elif is_saving:
            parent_name = SAVING_PARENT_DICT[name]
        elif is_attack:
            parent_name = ATTACK_PARENT_DICT[name]

        # 熟练加值
        scale = ability_info.check_prof[check_index]
        prof_bonus = scale * ability_info.get_prof_bonus()
        if scale == 0:
            hint_parts.append("无熟练加值")
        elif scale == 1:
            hint_parts.append(f"熟练加值:{prof_bonus}")
        else:
            hint_parts.append(f"熟练加值:{ability_info.get_prof_bonus()}*{scale}")

        # 属性调整值（技能/豁免/攻击取父属性）
        if parent_name:
            parent_index = ABILITY_LIST.index(parent_name)
            modifier = ability_info.get_modifier(parent_index)
            hint_parts.append(f"{parent_name}调整值:{modifier}")
        else:
            modifier = ability_info.get_modifier(check_index)
            hint_parts.append(f"{ABILITY_LIST[check_index]}调整值:{modifier}")

        # 额外加值（条目自身 + 父属性 + 全局豁免/攻击）
        ext_str = ability_info.check_ext[check_index]
        if parent_name:
            parent_index = ABILITY_LIST.index(parent_name)
            ext_str += ability_info.check_ext[EXT_ITEM_INDEX_DICT[ABILITY_LIST[parent_index]]]
        if is_saving:
            ext_str += ability_info.check_ext[EXT_ITEM_INDEX_DICT[SAVING_ALL_KEY]]
        if is_attack:
            ext_str += ability_info.check_ext[EXT_ITEM_INDEX_DICT[ATTACK_ALL_KEY]]
        if ext_str:
            hint_parts.append(f"额外加值:{ext_str}")
        if mod_str:
            hint_parts.append(f"临时加值:{mod_str}")

        # 优劣势（自带与本次叠加、抵消）
        adv_flag = ability_info.check_adv[check_index]
        parent_adv = 0
        if parent_name:
            parent_adv = ability_info.check_adv[
                EXT_ITEM_INDEX_DICT[ABILITY_LIST[ABILITY_LIST.index(parent_name)]]
            ]
        adv_flag = max(min(adv_flag + parent_adv, 1), -1)
        combined = max(min(adv_flag + advantage, 1), -1)
        if combined == 0 and (adv_flag != 0 or advantage != 0):
            hint_parts.append("优劣抵消")
        elif combined != 0 and advantage == 0:
            hint_parts.append("自带优势" if combined > 0 else "自带劣势")

        hint = " ".join(hint_parts).strip()

        # 拼表达式并掷骰
        if combined > 0:
            roll_exp = "D20优势"
        elif combined < 0:
            roll_exp = "D20劣势"
        else:
            roll_exp = "D20"

        prof_str = f"+{prof_bonus}" if prof_bonus > 0 else (str(prof_bonus) if prof_bonus < 0 else "")
        mod_str_clean = mod_str if (mod_str and mod_str[0] in "+-") else mod_str
        if modifier > 0:
            roll_exp += f"+{modifier}"
        elif modifier < 0:
            roll_exp += str(modifier)
        roll_exp += prof_str + ext_str + mod_str_clean

        try:
            roll_result = exec_roll_exp_unified(roll_exp)
        except RollDiceError as exc:
            raise AssertionError(f"Unexpected Code: {roll_exp}->{exc.info}")
        return hint, roll_result.get_complete_result(), roll_result.get_val()


class CharacterService:
    """角色卡解析服务。"""

    @staticmethod
    def parse(input_str: str, group_id: str, user_id: str) -> DNDCharacter:
        """把 ``.角色卡记录`` 的模板文本解析为角色；失败抛 AssertionError。

        模板格式（.角色卡模板 可查看示例）：
        $姓名$ 伊丽莎白
        $等级$ 5
        $生命值$ 5/10(4)
        $生命骰$ 4/10 D6
        $属性$ 10/11/12/15/12/8
        $熟练$ 力量/2*隐匿/奥秘
        $额外加值$ 运动:优势/隐匿:优势+2/游说:-2
        """
        hp_info = HPInfo()
        ability_info = AbilityInfo()
        data = parse_template_to_dict(input_str)

        # ── 生命值/生命骰（可选段）──
        hp_str = data.get(CHAR_INFO_KEY_HP, "")
        if hp_str:
            hp_cur_str, _, hp_max_str = hp_str.partition("/")
            hp_temp = 0
            if "(" in hp_str:
                # 形如 5/10(4) 或 5(4)
                if "(" in hp_cur_str:
                    hp_cur_str, temp_part = hp_cur_str.split("(", 1)
                    hp_max_str = hp_max_str or ""
                else:
                    hp_max_str, temp_part = hp_max_str.split("(", 1)
                hp_temp = int(temp_part.replace(")", "").strip())
            try:
                hp_cur = int(hp_cur_str.strip())
                hp_max = int(hp_max_str.strip()) if hp_max_str.strip() else 0
            except ValueError:
                raise AssertionError(f"无效的生命值信息:{hp_str}")

            hp_dice_type = hp_dice_num = hp_dice_max = 0
            hp_dice_str = data.get(CHAR_INFO_KEY_HP_DICE, "")
            if hp_dice_str:
                lowered = hp_dice_str.lower()
                if "d" not in lowered:
                    raise AssertionError(
                        f"生命骰信息不完整:{hp_dice_str}, 必须指定生命骰大小"
                    )
                head, _, type_str = lowered.partition("d")
                if "/" in head:
                    num_str, _, max_str = head.partition("/")
                else:
                    num_str, max_str = head, head
                try:
                    hp_dice_type = int(type_str.strip())
                    hp_dice_num = int(num_str.strip())
                    hp_dice_max = int(max_str.strip())
                except ValueError:
                    raise AssertionError(
                        f"生命骰信息不正确{hp_dice_str}, 示例: 8/10 D6"
                    )
            hp_info.initialize(hp_cur, hp_max, hp_temp, hp_dice_type, hp_dice_num, hp_dice_max)

        # ── 等级/属性/熟练/额外加值（必填：等级与属性）──
        level_str = data.get(CHAR_INFO_KEY_LEVEL, "")
        ability_str = data.get(CHAR_INFO_KEY_ABILITY, "")
        prof_str = data.get(CHAR_INFO_KEY_PROF, "")
        ext_str = data.get(CHAR_INFO_KEY_EXT, "")
        if not level_str or not ability_str:
            raise AssertionError("必须设定等级与属性")

        try:
            ability_values = [int(item) for item in ability_str.split("/")]
        except ValueError:
            raise AssertionError("属性值必须为正整数!")
        prof_list = prof_str.split("/") if prof_str else []
        ext_dict: Dict[str, str] = {}
        if ext_str:
            for item in ext_str.split("/"):
                if ":" not in item or item.endswith(":"):
                    raise AssertionError("必须使用冒号(:)分割额外加值条目和内容")
                key, _, content = item.partition(":")
                ext_dict[key] = content

        AbilityService.initialize(ability_info, level_str, ability_values, prof_list, ext_dict)

        return DNDCharacter(
            group_id=group_id,
            user_id=user_id,
            name=data.get(CHAR_INFO_KEY_NAME, ""),
            hp_info=hp_info,
            ability_info=ability_info,
            is_init=True,
        )


def gen_template_char(group_id: str = "", user_id: str = "") -> DNDCharacter:
    """生成一张示例角色卡（供 .角色卡模板 输出展示）。"""
    character = DNDCharacter(group_id=group_id, user_id=user_id, name="张三", is_init=True)
    character.hp_info.initialize(hp_cur=20, hp_max=30, hp_temp=5, hp_dice_type=8, hp_dice_num=3, hp_dice_max=4)
    character.ability_info.is_init = True
    character.ability_info.level = 4
    character.ability_info.ability = [10, 15, 12, 13, 8, 11]
    for name in ("敏捷攻击", "敏捷豁免", "体操"):
        character.ability_info.check_prof[CHECK_ITEM_INDEX_DICT[name]] = 1
    character.ability_info.check_prof[CHECK_ITEM_INDEX_DICT["隐匿"]] = 2
    character.ability_info.check_adv[EXT_ITEM_INDEX_DICT["隐匿"]] = 1
    character.ability_info.check_ext[EXT_ITEM_INDEX_DICT[SAVING_ALL_KEY]] = "+2"
    character.ability_info.check_ext[EXT_ITEM_INDEX_DICT["敏捷攻击"]] = "+1d4"
    return character
