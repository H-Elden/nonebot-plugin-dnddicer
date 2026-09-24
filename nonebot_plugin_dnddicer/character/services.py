"""DND5e 角色/检定业务服务。

- ``AbilityService.initialize``：把「等级/六属性/熟练项/额外加值」校验写入 AbilityInfo；
- ``AbilityService.perform_check``：按条目把 D20（可优势/劣势）+ 熟练 + 调整 + 加值
  拼成掷骰表达式交 ast_engine，返回 (hint 过程说明, result 掷骰过程文本, 数值)；
- ``CharacterService.parse``：把 ``.角色卡记录`` 的 ``$xxx$`` 模板文本解析为角色；
- ``gen_template_char``：生成示例模板（供 .角色卡模板 输出）。

只处理数据，不负责存储（存储见 data/characters.py）。
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Literal, Optional, Tuple

from ..engine.roll.ast_engine.adapter import exec_roll_exp_unified
from ..engine.roll.roll_utils import RollDiceError
from ..engine.roll.result import RollResult
from .constants import (
    ABILITY_LIST,
    ABILITY_NUM,
    ATTACK_ALL_KEY,
    ATTACK_LIST,
    ATTACK_PARENT_DICT,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_CLASS,
    CHAR_INFO_KEY_EXT,
    CHAR_INFO_KEY_HP,
    CHAR_INFO_KEY_HP_DICE,
    CHAR_INFO_KEY_LEVEL,
    CHAR_INFO_KEY_LIST,
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_PROF,
    CHAR_INFO_KEY_RACE,
    CHAR_INFO_KEY_SUBCLASS,
    CHAR_INFO_KEY_WEAPON,
    CHECK_ITEM_INDEX_DICT,
    CHECK_ITEM_LIST,
    CLASS_LIST,
    CLASS_SYNONYM_DICT,
    DAMAGE_TYPE_LIST,
    DAMAGE_TYPE_SYNONYM_DICT,
    EXT_ITEM_INDEX_DICT,
    EXT_ITEM_LIST,
    SAVING_ALL_KEY,
    SAVING_LIST,
    SAVING_PARENT_DICT,
    SKILL_LIST,
    SKILL_PARENT_DICT,
    SKILL_SYNONYM_DICT,
    SNEAK_ATTACK_CLASS,
    WEAPON_MAX_COUNT,
    WEAPON_NAME_FORBIDDEN_CHARS,
    WEAPON_NAME_FORBIDDEN_WORDS,
    WEAPON_NAME_MAX_LEN,
)
from .models import AbilityInfo, DNDCharacter, HPInfo, WeaponInfo


def _normalize_name(name: str) -> str:
    """把别名/俗称归一为正式条目名。"""
    return SKILL_SYNONYM_DICT.get(name, name)


def parse_template_to_dict(input_str: str) -> Dict[str, str]:
    """把角色卡模板文本（``$关键字$ 内容``）拆成 {关键字: 内容} 字典。

    ``$`` 为段落分隔符，内容中不应再出现 ``$``；未知关键字静默跳过。
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


# ── 自定义武器项 / 职业 / 偷袭骰（2026-09-24 新增）────────────────────────

#: 伤害表达式允许的形态：骰子项与常数项以 +- 连接（重击/副手后缀对表达式做
#: 确定性重写，禁用乘除与括号以免歧义；首项可带符号）
_WEAPON_DAMAGE_ITEM_RE = re.compile(r"^[+-]?(\d*[dD]\d+|\d+)([+-](\d*[dD]\d+|\d+))*$")

#: 命中加值 / 伤害临时加值片段允许的形态（必须以符号开头，随后为骰子/常数项以 +- 连接）
WEAPON_BONUS_RE = re.compile(r"^[+-](\d*[dD]\d+|\d+)([+-](\d*[dD]\d+|\d+))*$")

#: 兼职判定用分隔符号（复合写法直接提示「暂不支持兼职」）
_CLASS_MULTI_SEPARATORS = ("/", "、", "+", ",", "，", "兼")


def normalize_class_name(text: str) -> str:
    """把职业段文本归一为 12 职业规范名；不支持兼职（复合写法报错）。"""
    value = text.strip()
    name = CLASS_SYNONYM_DICT.get(value, value)
    if name in CLASS_LIST:
        return name
    if any(sep in value for sep in _CLASS_MULTI_SEPARATORS):
        raise AssertionError("当前版本暂不支持兼职，请填写单一职业名（如 游荡者）")
    raise AssertionError(f"职业无效: {value}，可用职业: {'/'.join(CLASS_LIST)}")


def normalize_damage_type(text: str) -> str:
    """伤害类型归一（别名 → 规范名）；未知类型返回空串（视为未填写）。"""
    if text in DAMAGE_TYPE_SYNONYM_DICT:
        return DAMAGE_TYPE_SYNONYM_DICT[text]
    return text if text in DAMAGE_TYPE_LIST else ""


def _validate_weapon_name(name: str) -> None:
    """武器名基础校验（解析与 .设置武器 共用；失败抛 AssertionError）。"""
    if not name:
        raise AssertionError("武器名称不能为空")
    if len(name) > WEAPON_NAME_MAX_LEN:
        raise AssertionError(f"武器名称过长（≤{WEAPON_NAME_MAX_LEN} 字）: {name}")
    for ch in WEAPON_NAME_FORBIDDEN_CHARS:
        if ch in name:
            raise AssertionError(f"武器名称不能包含符号「{ch}」: {name}")
    for word in WEAPON_NAME_FORBIDDEN_WORDS:
        if word in name:
            raise AssertionError(f"武器名称不能包含「{word}」字样: {name}")
    if name in CHECK_ITEM_LIST:
        raise AssertionError(f"武器名称不能与检定条目重名: {name}")


def validate_weapon_name(name: str, reserved_names: Iterable[str] = ()) -> None:
    """武器名完整校验（含插件命令名保留字；供解析与 .设置武器 共用）。"""
    _validate_weapon_name(name)
    lowered = {item.lower() for item in reserved_names}
    if name.lower() in lowered:
        raise AssertionError(f"武器名称不能与插件命令重名: {name}")


def parse_weapon_item(item: str, reserved_names: Iterable[str] = ()) -> WeaponInfo:
    """解析自定义武器项：``名称±命中加值,伤害表达式+类型``。

    例：``短剑+6,1d4+4穿刺``——名称段以首个 ± 切出命中加值（名称本身禁含
    ±）；伤害段尾部可带 13 种伤害类型之一（含「斩击→挥砍」容错），剩余为
    伤害表达式（骰子与常数的加减组合）。校验失败抛 AssertionError（消息面向用户）。

    兼容性（2026-09-24 补强）：逗号前后空格任意（``长剑+8, 1d8+5挥砍``）、
    全角逗号（``长剑+8，1d8+5挥砍``）、表达式与加值内部空白（``1d8 + 5``、
    ``+ 6``）均按等价处理。名称尾部可写 **x 标记**表示「不可进行攻击检定」
    （如 ``火球术x,8d6火焰``，纯伤害法术专用；x 仅在无命中加值时识别，
    且前一个字符须为非 ASCII 字母数字——英文武器名如 ``Box`` 不会误判）。
    """
    raw = item.strip()
    normalized = raw.replace("，", ",")
    if not normalized or "," not in normalized:
        raise AssertionError(f"武器条目不完整: {raw}（示例：短剑+6,1d4+4穿刺）")
    name_part, _, damage_part = normalized.partition(",")
    name_part, damage_part = name_part.strip(), damage_part.strip()
    if not name_part or not damage_part:
        raise AssertionError(f"武器条目不完整: {raw}（示例：短剑+6,1d4+4穿刺）")

    match = re.search(r"[+-]", name_part)
    if match:
        name = name_part[: match.start()].strip()
        bonus = re.sub(r"\s+", "", name_part[match.start():])
    else:
        name, bonus = name_part, ""

    # x 标记：名称最后一个字符为 x/X 且前一个字符非 ASCII 字母数字时视为
    # 「不可攻击检定」标记（中文名尾缀场景），并从名称中摘除
    no_attack = False
    if (
        len(name) > 1
        and name[-1] in ("x", "X")
        and not (name[-2].isascii() and name[-2].isalnum())
    ):
        if bonus:
            raise AssertionError(
                f"武器条目写法无效: {raw}（x 标记表示不可攻击检定，不要再写命中加值）"
            )
        no_attack = True
        name = name[:-1].strip()

    validate_weapon_name(name, reserved_names)
    # 注：命中加值与伤害表达式都用正则做静态校验（不调用引擎试掷）——试掷会
    # 真实消耗一次随机数、拖累文档取证与复现（表达式形态本就限定为加减组合）
    if bonus and not WEAPON_BONUS_RE.match(bonus):
        raise AssertionError(
            f"武器命中加值无效: {name}{bonus}（仅支持骰子与常数的加减组合，如 +6）"
        )

    damage_part = re.sub(r"\s+", "", damage_part)
    damage_type = ""
    damage_expr = damage_part
    for type_name in sorted(
        (*DAMAGE_TYPE_LIST, *DAMAGE_TYPE_SYNONYM_DICT), key=len, reverse=True
    ):
        if damage_part.endswith(type_name) and len(damage_part) > len(type_name):
            damage_expr = damage_part[: -len(type_name)].strip()
            damage_type = normalize_damage_type(type_name)
            break
    if not _WEAPON_DAMAGE_ITEM_RE.match(damage_expr):
        raise AssertionError(
            f"武器伤害表达式无效: {damage_expr}（仅支持骰子与常数的加减组合，如 1d4+4）"
        )
    return WeaponInfo(
        name=name,
        attack_bonus=bonus,
        damage_expr=damage_expr,
        damage_type=damage_type,
        no_attack=no_attack,
    )


def parse_weapon_list(content: str, reserved_names: Iterable[str] = ()) -> List[WeaponInfo]:
    """解析 ``$武器$`` 段全文（``/`` 分隔多项；名称卡内唯一、数量 ≤ 上限）。"""
    items = [item for item in content.split("/") if item.strip()]
    if len(items) > WEAPON_MAX_COUNT:
        raise AssertionError(f"武器数量最多 {WEAPON_MAX_COUNT} 件")
    weapons: List[WeaponInfo] = []
    seen: set[str] = set()
    for item in items:
        weapon = parse_weapon_item(item, reserved_names)
        if weapon.name in seen:
            raise AssertionError(f"武器名称重复: {weapon.name}")
        seen.add(weapon.name)
        weapons.append(weapon)
    return weapons


def get_sneak_attack_dice(level: int, char_class: str) -> int:
    """游荡者偷袭骰数量（颗 d6）：ceil(等级 / 2)，封顶 10；非游荡者返回 0。

    对应 5e/2024 游荡者特性表（1 级 1d6、3 级 2d6、……、19 级 10d6）。
    当前版本不支持兼职，等级取角色卡整体等级（简化偏差见设计文档记录）。
    """
    if char_class != SNEAK_ATTACK_CLASS or level <= 0:
        return 0
    return min(10, (level + 1) // 2)


def apply_critical_to_damage(expr: str) -> str:
    """重击：伤害表达式中所有骰子项骰数 ×2（固定加值只加一次、保持不变）。

    如 ``1d4+4`` → ``2d4+4``、``2d6+1d4+3`` → ``4d6+2d4+3``、``d6`` → ``2d6``。
    """
    def _double(matched: "re.Match[str]") -> str:
        count = int(matched.group(1)) if matched.group(1) else 1
        return f"{count * 2}{matched.group(2)}"

    return re.sub(r"(\d*)([dD]\d+)", _double, expr)


def strip_damage_constants(expr: str) -> str:
    """副手：剔除伤害表达式中所有常数项（保留骰子项）；无骰子时返回空串。

    如 ``1d4+4`` → ``1d4``、``2d6+1d4+3`` → ``2d6+1d4``；纯常数（如 ``1``）→ ""。
    """
    dice_items = re.findall(r"[+-]?\d*[dD]\d+", expr)
    if not dice_items:
        return ""
    return dice_items[0].lstrip("+") + "".join(dice_items[1:])


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

        # 熟练项：默认全部不熟练，$熟练$ 声明了哪些条目才熟练（修订：不做
        # 「默认所有攻击熟练」，与 PHB 不符——攻击检定加熟练仅限熟练的
        # 武器/法术攻击；支持 N*名称 多倍熟练与 0*名称 显式关闭）
        check_prof = [0] * len(CHECK_ITEM_LIST)
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
    ) -> Tuple[str, str, int, RollResult]:
        """执行一次条目检定（属性/技能/豁免/攻击通用）。

        Args:
            ability_info: 已初始化的属性信息。
            check_name: 条目名（可为同义词），如 力量/运动/敏捷豁免/力量攻击/先攻。
            advantage: 本次检定的临时优劣势（1/-1/0）。
            mod_str: 本次检定的临时加值表达式片段（如 "+d4"；"优势+2" 由调用方拆好）。

        Returns:
            (hint, result, value, roll_result)：过程说明 / 掷骰过程文本 / 结果数值 /
            完整掷骰结果对象（供调用方做 d20 大成功/大失败判定与多轮聚合，
            见 commands/text.py _d20_crit_counts；先攻检定由调用方忽略播报）。

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
        return hint, roll_result.get_complete_result(), roll_result.get_val(), roll_result


class CharacterService:
    """角色卡解析服务。"""

    @staticmethod
    def parse(
        input_str: str,
        group_id: str,
        user_id: str,
        reserved_names: Iterable[str] = (),
    ) -> DNDCharacter:
        """把 ``.角色卡记录`` 的模板文本解析为角色；失败抛 AssertionError。

        模板格式（.角色卡模板 可查看示例）：
        $姓名$ 伊丽莎白
        $种族$ 半精灵
        $职业$ 游荡者
        $子职$ 刺客
        $等级$ 5
        $生命值$ 5/10(4)
        $生命骰$ 4/10 D6
        $属性$ 10/11/12/15/12/8
        $熟练$ 力量/2*隐匿/奥秘
        $额外加值$ 运动:优势/隐匿:优势+2/游说:-2
        $武器$ 短剑+6,1d4+4穿刺/长弓+5,1d8+3穿刺

        ``reserved_names`` 为保留名集合（插件固定命令名），武器名不得与之
        冲突（由命令层传入；缺省不检查，供纯函数调用与单测）。
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

        # ── 种族/职业/子职/武器（可选段；职业与武器名有校验）──
        char_class = ""
        char_class_str = data.get(CHAR_INFO_KEY_CLASS, "").strip()
        if char_class_str:
            char_class = normalize_class_name(char_class_str)
        weapon_str = data.get(CHAR_INFO_KEY_WEAPON, "").strip()
        weapons = parse_weapon_list(weapon_str, reserved_names) if weapon_str else []

        return DNDCharacter(
            group_id=group_id,
            user_id=user_id,
            name=data.get(CHAR_INFO_KEY_NAME, ""),
            race=data.get(CHAR_INFO_KEY_RACE, "").strip(),
            char_class=char_class,
            subclass=data.get(CHAR_INFO_KEY_SUBCLASS, "").strip(),
            hp_info=hp_info,
            ability_info=ability_info,
            weapons=weapons,
            is_init=True,
        )


def gen_template_char(group_id: str = "", user_id: str = "") -> DNDCharacter:
    """生成一张示例角色卡（供 .角色卡模板 输出展示）。"""
    character = DNDCharacter(group_id=group_id, user_id=user_id, name="张三", is_init=True)
    character.race = "半精灵"
    character.char_class = "游荡者"  # 示例职业取游荡者（可用偷袭后缀）
    character.subclass = "刺客"
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
    # 示例武器与卡自洽：命中 +4 = 敏捷调整 +2 + 熟练 +2（4 级）；伤害 1d4+2（敏捷调整）
    character.weapons = [
        WeaponInfo(name="短剑", attack_bonus="+4", damage_expr="1d4+2", damage_type="穿刺"),
    ]
    return character


class HPService:
    """HP 相关服务（伤害/治疗结算、长休与生命骰）。"""

    @staticmethod
    def use_hp_dice(hp_info: HPInfo, num: int, con_mod: int) -> str:
        """使用生命骰恢复 HP，返回修改结果描述。"""
        if not hp_info.is_init or hp_info.hp_dice_type <= 0:
            return "尚未设置生命骰"
        if num <= 0 or num > 1000:
            return f"无效的生命骰数量({num})"
        if hp_info.hp_dice_num < num:
            return f"生命骰数量不足, 还有{hp_info.hp_dice_num}颗生命骰"

        roll_exp = f"1D{hp_info.hp_dice_type}+{con_mod}"

        roll_result_list = []
        roll_result_val = 0
        for _ in range(num):
            try:
                roll_result = exec_roll_exp_unified(roll_exp)
            except RollDiceError as e:
                return f"未知掷骰错误:{e.info}"
            if num > 1:
                roll_result_list.append(f"({roll_result.get_info()})")
            else:
                roll_result_list.append(roll_result.get_info())
            roll_val = roll_result.get_val()
            if roll_val < 0:
                roll_val = 0
                roll_result_list[-1] = f"({roll_result_list[-1]}->0)"
            roll_result_val += roll_val

        roll_result_str = f"{'+'.join(roll_result_list)}={roll_result_val}"
        mod_info = f"使用{num}颗D{hp_info.hp_dice_type}生命骰, 体质调整值为{con_mod}, 回复{roll_result_str}点生命值\n"
        hp_info_str_prev = hp_info.get_info()
        hp_info.hp_dice_num -= num
        hp_info.heal(roll_result_val)
        mod_info += f"{hp_info_str_prev} -> {hp_info.get_info()}"
        return mod_info

    @staticmethod
    def process_roll_result(
        hp_info: HPInfo,
        cmd_type: Literal["=", "+", "-"],
        hp_cur_mod_result: Optional[RollResult] = None,
        hp_max_mod_result: Optional[RollResult] = None,
        hp_temp_mod_result: Optional[RollResult] = None,
        short_feedback: bool = False,
        damage_factor: float = 1.0,
    ) -> str:
        """根据掷骰结果修改 HP，返回修改结果描述。

        Args:
            hp_info: HP 信息对象
            cmd_type: "=" 设置, "+" 增加, "-" 减少
            hp_cur_mod_result: 当前 HP 的掷骰结果
            hp_max_mod_result: 最大 HP 的掷骰结果
            hp_temp_mod_result: 临时 HP 的掷骰结果
            short_feedback: 是否使用短格式反馈（多目标时用）
            damage_factor: 目标承伤因子（DM 掷伤害用）——1.0 全额；0.5 抗性
                （伤害减半，向下取整、最少 1）；2.0 易伤（伤害加倍）。仅对
                "-" 生效，其余取值按全额处理。

        伤害/治疗值最低为 0：掷骰表达式可能算出负值（如 ``-d12-2`` 掷出 1），
        按 5e 语义伤害不为负——负值按 0 计并在反馈中标注（2026-09-21 修复：
        此前负伤害经 take_damage 会变成回血）。
        """
        mod_info = ""

        if cmd_type == "=":
            hp_info.is_init = True
            if hp_cur_mod_result:
                if hp_info.is_record_normal():
                    hp_info.is_alive = hp_cur_mod_result.get_val() > 0
                hp_info.hp_cur = hp_cur_mod_result.get_val()
                mod_info = f"HP={hp_cur_mod_result.get_result()}"
            if hp_max_mod_result:
                hp_info.hp_max = hp_max_mod_result.get_val()
                if hp_info.hp_cur > hp_info.hp_max:
                    hp_info.take_damage(hp_info.hp_cur - hp_info.hp_max)
                mod_info = f"HP={hp_cur_mod_result.get_result()}/{hp_max_mod_result.get_result()}"
            if hp_temp_mod_result:
                hp_info.hp_temp = hp_temp_mod_result.get_val()
                if "HP=" in mod_info:
                    mod_info += f" ({hp_temp_mod_result.get_result()})"
                else:
                    mod_info = f"临时HP={hp_temp_mod_result.get_result()}"
            mod_info += f"\n当前{hp_info.get_info()}"

        elif cmd_type == "+":
            hp_info_str_prev = hp_info.get_info()
            if hp_max_mod_result:
                hp_info.hp_max += hp_max_mod_result.get_val()
                mod_info += f"最大HP增加{hp_max_mod_result.get_result()}, "
            if hp_cur_mod_result:
                # 治疗同样最低为 0（负值按 0 计，避免「加血」变成掉血）；0 不调用 heal，
                # 以免把昏迷标记（is_alive）意外唤醒
                heal_value = hp_cur_mod_result.get_val()
                heal_suffix = ""
                if heal_value < 0:
                    heal_suffix = "（治疗最低为0）"
                    heal_value = 0
                if heal_value > 0:
                    hp_info.heal(heal_value)
                mod_info += f"当前HP增加{hp_cur_mod_result.get_result()}{heal_suffix}"
            if hp_temp_mod_result:
                hp_info.hp_temp += hp_temp_mod_result.get_val()
                if mod_info:
                    mod_info += ", "
                mod_info += f"临时HP增加{hp_temp_mod_result.get_result()}"
            mod_info += f"\n{hp_info_str_prev} -> {hp_info.get_info()}"

        else:  # cmd_type == "-"
            hp_info_str_prev = hp_info.get_info()
            if hp_temp_mod_result:
                hp_info.hp_temp = max(0, hp_info.hp_temp - hp_temp_mod_result.get_val())
                mod_info += f"临时HP减少{hp_temp_mod_result.get_result()}"
            if hp_max_mod_result:
                hp_info.hp_max -= hp_max_mod_result.get_val()
                if mod_info:
                    mod_info += ", "
                mod_info += f"最大HP减少{hp_max_mod_result.get_result()}"
                if hp_info.hp_cur > hp_info.hp_max:
                    hp_info.take_damage(hp_info.hp_cur - hp_info.hp_max)
            if hp_cur_mod_result:
                # 伤害最低为 0：负值（如 -d12-2 掷出 1）按 0 计，避免负伤害变回血
                damage = max(0, hp_cur_mod_result.get_val())
                damage_suffix = ""
                if damage == 0:
                    damage_suffix = "（伤害最低为0）"
                elif damage_factor == 0.5:
                    damage = max(1, int(damage // 2))
                    damage_suffix = f"（抗性减半→{damage}）"
                elif damage_factor == 2.0:
                    damage = int(damage) * 2
                    damage_suffix = f"（易伤加倍→{damage}）"
                hp_info.take_damage(damage)
                if mod_info:
                    mod_info += ", "
                mod_info += f"当前HP减少{hp_cur_mod_result.get_result()}{damage_suffix}"
            mod_info += f"\n{hp_info_str_prev} -> {hp_info.get_info()}"

        mod_info = mod_info.strip()
        if short_feedback:
            mod_info = mod_info.replace("\n", "; ")
        return mod_info
