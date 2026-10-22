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
    BACKGROUND_KEY_MAX_LEN,
    BACKGROUND_MAX_COUNT,
    BACKGROUND_VALUE_MAX_LEN,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_BACKGROUND,
    CHAR_INFO_KEY_CLASS,
    CHAR_INFO_KEY_COINS,
    CHAR_INFO_KEY_COMBAT,
    CHAR_INFO_KEY_COMBAT_NOTES,
    CHAR_INFO_KEY_EXT,
    CHAR_INFO_KEY_FEATURE,
    CHAR_INFO_KEY_FEATS,
    CHAR_INFO_KEY_HP,
    CHAR_INFO_KEY_HP_DICE,
    CHAR_INFO_KEY_ITEMS,
    CHAR_INFO_KEY_LEVEL,
    CHAR_INFO_KEY_LIST,
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_PROF,
    CHAR_INFO_KEY_PROGRESS,
    CHAR_INFO_KEY_RACE,
    CHAR_INFO_KEY_SPELL,
    CHAR_INFO_KEY_SPELL_SLOTS,
    CHAR_INFO_KEY_STORY,
    CHAR_INFO_KEY_SUBCLASS,
    CHAR_INFO_KEY_TRAITS,
    CHAR_INFO_KEY_WEAPON,
    CHECK_ITEM_INDEX_DICT,
    CHECK_ITEM_LIST,
    CLASS_LIST,
    CLASS_SYNONYM_DICT,
    COIN_KEY_LIST,
    COIN_VALUE_MAX,
    COMBAT_KEY_LIST,
    COMBAT_NOTE_MAX_COUNT,
    COMBAT_NOTE_MAX_LEN,
    COMBAT_SPEED_MAX_LEN,
    DAMAGE_TYPE_LIST,
    DAMAGE_TYPE_SYNONYM_DICT,
    EXT_ITEM_INDEX_DICT,
    EXT_ITEM_LIST,
    FEAT_MAX_COUNT,
    FEAT_NAME_MAX_LEN,
    FEAT_TEXT_MAX_LEN,
    FEATURE_MAX_COUNT,
    FEATURE_NAME_FORBIDDEN_CHARS,
    FEATURE_NAME_FORBIDDEN_WORDS,
    FEATURE_NAME_MAX_LEN,
    FEATURE_RECOVER_MODES,
    FEATURE_TEXT_MAX_LEN,
    ITEM_MAX_COUNT,
    ITEM_NAME_MAX_LEN,
    ITEM_QUANTITY_MAX,
    LEGACY_CHAR_INFO_KEY_LIST,
    PREPARED_CASTERS_2014,
    PROFICIENCY_GROUP_ITEM_MAX,
    PROFICIENCY_GROUP_ITEM_MAX_LEN,
    PROFICIENCY_GROUP_LIST,
    REST_LONG,
    REST_SHORT,
    SAVING_ALL_KEY,
    SAVING_LIST,
    SAVING_PARENT_DICT,
    SKILL_LIST,
    SKILL_PARENT_DICT,
    SKILL_SYNONYM_DICT,
    SNEAK_ATTACK_CLASS,
    SPELLCASTING_ABILITY_KEY,
    SPELLCASTING_CLASSES_2024,
    SPELL_ATTACK_KEY,
    SPELL_DC_KEY,
    SPELL_DC_MAX,
    SPELL_DETAIL_KEYS,
    SPELL_LEVEL_MAX,
    SPELL_MAX_COUNT,
    SPELL_NAME_FORBIDDEN_CHARS,
    SPELL_NAME_MAX_LEN,
    SPELL_NOTE_MAX_LEN,
    SPELL_RANGE_MAX_LEN,
    SPELL_SLOT_MAX,
    SPELL_TIME_MAX_LEN,
    STORY_MAX_LEN,
    TRAIT_ITEM_MAX_LEN,
    TRAIT_MAX_COUNT,
    TRAIT_TEXT_MAX_LEN,
    WEAPON_MAX_COUNT,
    WEAPON_NAME_FORBIDDEN_CHARS,
    WEAPON_NAME_FORBIDDEN_WORDS,
    WEAPON_NAME_MAX_LEN,
    WEAPON_NOTE_MAX_LEN,
    XP_VALUE_MAX,
)
from .models import (
    AbilityInfo,
    CharacterFeature,
    DNDCharacter,
    HPInfo,
    SpellEntry,
    SpellSlots,
    WeaponInfo,
)


def _normalize_name(name: str) -> str:
    """把别名/俗称归一为正式条目名。"""
    return SKILL_SYNONYM_DICT.get(name, name)


def parse_template_to_dict(input_str: str) -> Dict[str, str]:
    """把角色卡模板文本（``$关键字$ 内容``）拆成 {关键字: 内容} 字典。

    ``$`` 为段落分隔符，内容中不应再出现 ``$``；未知关键字静默跳过。
    旧卡里的 ``$属性值$`` / ``$豁免$`` / ``$技能$`` 仍会被识别（便于整卡
    重录时静默忽略），但它们已不再输出、也不接受单独录入。
    """
    known_keys = set(CHAR_INFO_KEY_LIST) | set(LEGACY_CHAR_INFO_KEY_LIST)
    result: Dict[str, str] = {}
    parts = input_str.split("$")
    for index in range(len(parts) - 1):
        key = f"${parts[index]}$"
        if key not in known_keys:
            continue
        content = parts[index + 1].strip()
        if content and content not in known_keys:
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

    卡面备注（2026-10-21 批②）：第三个逗号字段，如
    ``匕首+5,1d4+2穿刺,灵巧·轻型``，只用于出图，最长 30 字、不含分隔符号。
    """
    raw = item.strip()
    normalized = raw.replace("，", ",")
    if not normalized or "," not in normalized:
        raise AssertionError(f"武器条目不完整: {raw}（示例：短剑+6,1d4+4穿刺）")
    parts = normalized.split(",")
    if len(parts) > 3:
        raise AssertionError(
            f"武器条目最多三段: {raw}（名称+命中,伤害+类型,备注）"
        )
    name_part, damage_part = parts[0].strip(), parts[1].strip()
    note = parts[2].strip() if len(parts) == 3 else ""
    if not name_part or not damage_part:
        raise AssertionError(f"武器条目不完整: {raw}（示例：短剑+6,1d4+4穿刺）")
    if note:
        if len(note) > WEAPON_NOTE_MAX_LEN:
            raise AssertionError(
                f"武器备注过长（≤{WEAPON_NOTE_MAX_LEN} 字）: {note}"
            )
        for ch in ("/", ";", "；", "$", "|", "｜"):
            if ch in note:
                raise AssertionError(f"武器备注不能包含符号「{ch}」: {note}")

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
        note=note,
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


# ── 能力次数 / 法术清单 / 法术位（2026-10-20 批②）────────────────────────


def _split_semicolon_items(content: str) -> List[str]:
    """按半角/全角分号切分段内容（新增三段统一口径）。"""
    return [item.strip() for item in re.split(r"[;；]", content) if item.strip()]


def validate_feature_name(name: str) -> None:
    """能力名基础校验（解析与 .设置能力 共用；失败抛 AssertionError）。"""
    if not name:
        raise AssertionError("能力名称不能为空")
    if len(name) > FEATURE_NAME_MAX_LEN:
        raise AssertionError(f"能力名称过长（≤{FEATURE_NAME_MAX_LEN} 字）: {name}")
    for ch in FEATURE_NAME_FORBIDDEN_CHARS:
        if ch in name:
            raise AssertionError(f"能力名称不能包含符号「{ch}」: {name}")
    for word in FEATURE_NAME_FORBIDDEN_WORDS:
        if word in name:
            raise AssertionError(f"能力名称不能包含「{word}」字样: {name}")


def _parse_recover_amount(text: str) -> str:
    """解析恢复量后缀：空 / ``满`` → 回满（规范化后留空），``+N`` → ``+N``。"""
    value = text.strip()
    if not value or value == "满":
        return ""
    matched = re.fullmatch(r"\+(\d+)", value)
    if not matched:
        raise AssertionError(
            f"能力恢复量无效: {text}（可写 +N 或 满，如 短休+1、长休满）"
        )
    count = int(matched.group(1))
    if count <= 0:
        raise AssertionError(f"能力恢复量必须大于 0: {text}")
    return f"+{count}"


def normalize_feature_recover(spec: str) -> str:
    """规范化能力恢复档串，返回如 ``短休+1,长休``。

    合法档位：``短休`` / ``长休`` / ``两者`` / ``手动``，多个用逗号连接；
    可后缀 ``+N``（恢复 N 次）或 ``满``（回满，默认，输出省略）。
    ``两者`` 表示短休与长休都回满，不得再与 ``短休`` / ``长休`` 同时写。
    输出按固定顺序排列，便于卡面稳定回写。
    """
    raw = (spec or "").strip()
    if not raw:
        raise AssertionError(
            "能力恢复方式不能为空"
            "（可选：短休/长休/两者/手动，可加 +N 或 满）"
        )
    amounts: Dict[str, str] = {}
    for piece in re.split(r"[,，]", raw):
        token = piece.strip()
        if not token:
            continue
        mode = next(
            (item for item in FEATURE_RECOVER_MODES if token.startswith(item)),
            None,
        )
        if mode is None:
            raise AssertionError(
                f"能力恢复方式无效: {token}"
                "（可选：短休/长休/两者/手动，可加 +N 或 满）"
            )
        tail = token[len(mode):]
        if mode == "手动" and tail.strip():
            raise AssertionError(f"「手动」不能带恢复量: {token}")
        if mode in amounts:
            raise AssertionError(f"能力恢复方式重复: {token}")
        amounts[mode] = _parse_recover_amount(tail)
    if not amounts:
        raise AssertionError("能力恢复方式不能为空")
    if "两者" in amounts and ("短休" in amounts or "长休" in amounts):
        raise AssertionError("「两者」已含短休与长休，不要再分别写")
    return ",".join(
        f"{mode}{amounts[mode]}"
        for mode in FEATURE_RECOVER_MODES
        if mode in amounts
    )


def parse_feature_item(item: str) -> CharacterFeature:
    """解析单条能力：``名称:当前/上限恢复档[|说明]``。

    例：``引导神力:2/2短休+1,长休``、``圣疗:25/25长休``、``狂暴:3/3两者``。
    恢复档可省略后缀（默认回满）；``|`` 之后是卡面说明（2026-10-21 批②，
    只展示、不参与结算）。校验失败抛 AssertionError（消息面向用户）。
    """
    raw = item.strip()
    normalized = raw.replace("：", ":")
    body, pipe, text = normalized.partition("|")
    text = text.strip()
    if pipe and not text:
        raise AssertionError(f"能力说明不能为空: {raw}")
    if "|" in text:
        raise AssertionError(f"能力说明不能包含符号「|」: {raw}")
    if len(text) > FEATURE_TEXT_MAX_LEN:
        raise AssertionError(
            f"能力说明过长（≤{FEATURE_TEXT_MAX_LEN} 字）: {raw}"
        )
    name_part, separator, value_part = body.partition(":")
    if not separator:
        raise AssertionError(
            f"能力条目不完整: {raw}（示例：引导神力:2/2短休+1,长休）"
        )
    name = name_part.strip()
    validate_feature_name(name)
    matched = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*(.*)$", value_part)
    if not matched:
        raise AssertionError(
            f"能力次数无效: {raw}（写法：当前/上限恢复档，如 2/2短休+1,长休）"
        )
    uses_cur = int(matched.group(1))
    uses_max = int(matched.group(2))
    if uses_max <= 0:
        raise AssertionError(f"能力上限必须大于 0: {raw}")
    if uses_cur > uses_max:
        raise AssertionError(f"能力当前次数不能超过上限: {raw}")
    recover = normalize_feature_recover(matched.group(3))
    return CharacterFeature(
        name=name,
        uses_cur=uses_cur,
        uses_max=uses_max,
        recover=recover,
        text=text,
    )


def parse_feature_list(content: str) -> List[CharacterFeature]:
    """解析 ``$能力$`` 段全文（分号分条；名称卡内唯一、数量 ≤ 上限）。"""
    items = _split_semicolon_items(content)
    if len(items) > FEATURE_MAX_COUNT:
        raise AssertionError(f"能力数量最多 {FEATURE_MAX_COUNT} 项")
    features: List[CharacterFeature] = []
    seen: set[str] = set()
    for item in items:
        feature = parse_feature_item(item)
        if feature.name in seen:
            raise AssertionError(f"能力名称重复: {feature.name}")
        seen.add(feature.name)
        features.append(feature)
    return features


def validate_spell_name(name: str) -> None:
    """法术名基础校验（解析与 .设置法术 共用；失败抛 AssertionError）。"""
    if not name:
        raise AssertionError("法术名称不能为空")
    if len(name) > SPELL_NAME_MAX_LEN:
        raise AssertionError(f"法术名称过长（≤{SPELL_NAME_MAX_LEN} 字）: {name}")
    for ch in SPELL_NAME_FORBIDDEN_CHARS:
        if ch in name:
            raise AssertionError(f"法术名称不能包含符号「{ch}」: {name}")


def _parse_spell_flag(value: str, label: str) -> bool:
    """解析法术的专注/仪式/材料标记（是/否，兼容 有/无、1/0）。"""
    text = value.strip()
    if text in ("是", "有", "1"):
        return True
    if text in ("否", "无", "0"):
        return False
    raise AssertionError(f"法术「{label}」只能写 是 或 否: {value}")


def _parse_spell_details(text: str) -> Dict[str, object]:
    """解析法术条目 ``|`` 之后的详情：``时间=1动作,距离=150尺,专注=是``。

    键固定为时间/距离/专注/仪式/材料/备注，顺序不限、缺项不写；返回可直接
    展开给 ``SpellEntry`` 的字段字典。校验失败抛 AssertionError。
    """
    result: Dict[str, object] = {}
    seen: set[str] = set()
    for piece in text.split(","):
        piece = piece.strip()
        if not piece:
            raise AssertionError(
                "法术详情中有空项（用逗号分隔，如 时间=1动作,距离=150尺）"
            )
        key, separator, value = piece.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or key not in SPELL_DETAIL_KEYS:
            raise AssertionError(
                f"法术详情写法无效: {piece}"
                f"（可用：{'/'.join(SPELL_DETAIL_KEYS)}，如 时间=1动作）"
            )
        if key in seen:
            raise AssertionError(f"法术详情重复: {key}")
        seen.add(key)
        if key == "时间":
            if not 1 <= len(value) <= SPELL_TIME_MAX_LEN:
                raise AssertionError(
                    f"法术施法时间过长（≤{SPELL_TIME_MAX_LEN} 字）: {value}"
                )
            result["cast_time"] = value
        elif key == "距离":
            if not 1 <= len(value) <= SPELL_RANGE_MAX_LEN:
                raise AssertionError(
                    f"法术施法距离过长（≤{SPELL_RANGE_MAX_LEN} 字）: {value}"
                )
            result["range"] = value
        elif key == "专注":
            result["concentration"] = _parse_spell_flag(value, key)
        elif key == "仪式":
            result["ritual"] = _parse_spell_flag(value, key)
        elif key == "材料":
            result["material"] = _parse_spell_flag(value, key)
        else:  # 备注
            if not 1 <= len(value) <= SPELL_NOTE_MAX_LEN:
                raise AssertionError(
                    f"法术备注过长（≤{SPELL_NOTE_MAX_LEN} 字）: {value}"
                )
            for ch in (",", "，", ";", "；", "|", "｜", "$"):
                if ch in value:
                    raise AssertionError(f"法术备注不能包含符号「{ch}」: {value}")
            result["note"] = value
    return result


def parse_spell_item(item: str) -> SpellEntry:
    """解析单条法术：``名称:环阶[*已准备][|详情]``。

    例：``火球术:3*``、``火焰箭:0``、``火球术:3*|时间=1动作,距离=150尺,材料=是``。
    环阶 0 = 戏法；``*`` = 今日已准备；``|`` 之后为卡面展示用的详情
    （时间/距离/专注/仪式/材料/备注，2026-10-21 批②）。校验失败抛 AssertionError。
    """
    raw = item.strip()
    normalized = raw.replace("：", ":")
    entry_text, pipe, detail_text = normalized.partition("|")
    name_part, separator, level_part = entry_text.partition(":")
    if not separator:
        raise AssertionError(f"法术条目不完整: {raw}（示例：火球术:3*）")
    name = name_part.strip()
    validate_spell_name(name)
    level_text = level_part.strip()
    prepared = False
    if level_text.endswith(("*", "＊")):
        prepared = True
        level_text = level_text[:-1].strip()
    if not level_text.isdigit():
        raise AssertionError(f"法术环阶无效: {raw}（写 0~9 的数字，0 = 戏法）")
    level = int(level_text)
    if level > SPELL_LEVEL_MAX:
        raise AssertionError(f"法术环阶无效: {raw}（写 0~9 的数字，0 = 戏法）")
    details = _parse_spell_details(detail_text) if pipe else {}
    return SpellEntry(name=name, level=level, prepared=prepared, **details)


def parse_spell_setting(
    content: str,
) -> Tuple[str, List[SpellEntry], str, str]:
    """解析 ``$法术$`` 段全文 → (施法属性, 法术列表, 豁免DC, 法术攻击)。

    首部可写三个保留键：``施法属性:智力``、``豁免DC:15``、``法术攻击:+7``；
    其余为 ``名称:环阶[*][|详情]``。分号分条；名称卡内唯一、数量 ≤ 上限。
    校验失败抛 AssertionError。
    """
    items = _split_semicolon_items(content)
    casting_ability = ""
    spell_dc = ""
    spell_attack = ""
    spells: List[SpellEntry] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.replace("：", ":")
        key, separator, value = normalized.partition(":")
        stripped_key = key.strip()
        if stripped_key == SPELLCASTING_ABILITY_KEY:
            if not separator:
                raise AssertionError(
                    f"施法属性写法无效: {item}（示例：施法属性:魅力）"
                )
            ability = value.strip()
            if ability not in ABILITY_LIST:
                raise AssertionError(
                    f"施法属性无效: {ability}（可选：{'/'.join(ABILITY_LIST)}）"
                )
            if casting_ability:
                raise AssertionError("施法属性只能写一条")
            casting_ability = ability
            continue
        if stripped_key == SPELL_DC_KEY:
            if not separator:
                raise AssertionError(
                    f"豁免DC写法无效: {item}（示例：豁免DC:15）"
                )
            text = value.strip()
            if not text.isdigit() or not 1 <= int(text) <= SPELL_DC_MAX:
                raise AssertionError(
                    f"豁免DC必须是 1~{SPELL_DC_MAX} 的整数: {text}"
                )
            if spell_dc:
                raise AssertionError("豁免DC只能写一条")
            spell_dc = str(int(text))
            continue
        if stripped_key == SPELL_ATTACK_KEY:
            if not separator:
                raise AssertionError(
                    f"法术攻击写法无效: {item}（示例：法术攻击:+7）"
                )
            if spell_attack:
                raise AssertionError("法术攻击只能写一条")
            spell_attack = _parse_signed_bonus(value, "法术攻击")
            continue
        spell = parse_spell_item(item)
        if spell.name in seen:
            raise AssertionError(f"法术名称重复: {spell.name}")
        seen.add(spell.name)
        spells.append(spell)
    if len(spells) > SPELL_MAX_COUNT:
        raise AssertionError(f"法术数量最多 {SPELL_MAX_COUNT} 条")
    return casting_ability, spells, spell_dc, spell_attack


def spell_slot_label(is_pact: bool, level: int) -> str:
    """法术位展示名：``3环`` / ``契约魔法（3环）``。"""
    return f"契约魔法（{level}环）" if is_pact else f"{level}环"


def parse_spell_slot_entries(
    content: str, *, allow_omitted_max: bool = False
) -> List[Tuple[bool, int, int, int]]:
    """解析法术位条目 → ``[(是否契约, 环阶, 当前, 上限), ...]``。

    ``allow_omitted_max=False``（卡面 ``$法术位$``）要求写全 ``当前/上限``；
    ``True``（``.法术位 set``）允许只写 ``环阶:当前``，此时上限 = 当前。
    分号或逗号分条；环阶 1~9、数量 0~99、当前 ≤ 上限。失败抛 AssertionError。
    """
    items = [
        item.strip()
        for item in re.split(r"[;；,，]", content)
        if item.strip()
    ]
    entries: List[Tuple[bool, int, int, int]] = []
    seen: set[Tuple[bool, int]] = set()
    for raw in items:
        normalized = raw.replace("：", ":")
        matched = re.match(
            r"^(契约)?\s*(\d+)\s*:\s*(\d+)(?:\s*/\s*(\d+))?$", normalized
        )
        if not matched:
            raise AssertionError(
                f"法术位条目不完整: {raw}"
                "（示例：1:4/4; 契约3:2/2）"
            )
        is_pact = matched.group(1) is not None
        level = int(matched.group(2))
        cur = int(matched.group(3))
        if matched.group(4) is None:
            if not allow_omitted_max:
                raise AssertionError(
                    f"法术位条目不完整: {raw}"
                    "（书写 当前/上限，如 1:4/4；契约写 契约3:2/2）"
                )
            max_value = cur
        else:
            max_value = int(matched.group(4))
        if not 1 <= level <= SPELL_LEVEL_MAX:
            raise AssertionError(f"法术位环阶无效: {raw}（1~9 环）")
        if not 0 <= cur <= SPELL_SLOT_MAX or not 0 <= max_value <= SPELL_SLOT_MAX:
            raise AssertionError(f"法术位数量无效: {raw}（0~{SPELL_SLOT_MAX}）")
        if cur > max_value:
            raise AssertionError(f"法术位当前值不能超过上限: {raw}")
        key = (is_pact, level)
        if key in seen:
            raise AssertionError(
                f"法术位重复: {spell_slot_label(is_pact, level)}"
            )
        seen.add(key)
        entries.append((is_pact, level, cur, max_value))
    if not entries:
        raise AssertionError("法术位内容不能为空（示例：1:4/4; 契约3:2/2）")
    return entries


def parse_spell_slots(content: str) -> SpellSlots:
    """解析 ``$法术位$`` 段全文为 ``SpellSlots``。"""
    slots = SpellSlots()
    for is_pact, level, cur, max_value in parse_spell_slot_entries(content):
        if is_pact:
            # 上限 0 等同未记录（不保留一个没有容量的契约位条目）
            if max_value > 0:
                slots.pact_level = level
                slots.pact_cur = cur
                slots.pact_max = max_value
        else:
            slots.slots_cur[level - 1] = cur
            slots.slots_max[level - 1] = max_value
    return slots


# ── 完整卡面扩展段（2026-10-21）────────────────────────────────────────


def _ensure_no_dollar(content: str, label: str, *, allow_newline: bool = False) -> None:
    """卡面段内容不得含 ``$``（模板解析按它分段）；默认也不得换行。

    ``allow_newline=True`` 只给 ``$故事$`` 使用：故事可以多行多段，其余段
    仍保持「一段一行」，避免与模板关键字切分混淆。
    """
    if "$" in content:
        raise AssertionError(f"{label}内容不能包含符号「$」")
    if not allow_newline and ("\n" in content or "\r" in content):
        raise AssertionError(f"{label}内容不能换行，多条请用分号分隔")


def _normalize_colon(text: str) -> str:
    """全角冒号归一为半角（新段统一口径）。"""
    return text.replace("：", ":")


def parse_prof_entries(content: str) -> Tuple[List[str], Dict[str, List[str]]]:
    """解析 ``$熟练$`` 段，拆成（检定条目列表, 扩展分组）。

    - 旧条目沿用 ``/`` 分隔，如 ``运动/2*隐匿/力量豁免``；
    - 新分组写成 ``护甲:轻甲·中甲``、``武器:军用武器``、``工具:盗贼工具``、
      ``语言:通用语·精灵语``，组内用 ``·``（也接受 ``、`` 与逗号）分隔；
    - 扩展分组只用于展示，不进入 ``check_prof``。
    """
    _ensure_no_dollar(content, "熟练")
    checks: List[str] = []
    groups: Dict[str, List[str]] = {}
    for raw_item in content.split("/"):
        item = raw_item.strip()
        if not item:
            continue
        normalized = _normalize_colon(item)
        prefix, separator, rest = normalized.partition(":")
        label = prefix.strip()
        if separator and label in PROFICIENCY_GROUP_LIST:
            values = [
                value.strip()
                for value in re.split(r"[·、,，]", rest)
                if value.strip()
            ]
            if not values:
                raise AssertionError(
                    f"熟练分组「{label}」不能为空（示例：{label}:轻甲·中甲）"
                )
            bucket = groups.setdefault(label, [])
            for value in values:
                if len(value) > PROFICIENCY_GROUP_ITEM_MAX_LEN:
                    raise AssertionError(
                        f"熟练分组「{label}」的条目长度不能超过"
                        f"{PROFICIENCY_GROUP_ITEM_MAX_LEN} 字: {value}"
                    )
                if value in bucket:
                    raise AssertionError(f"熟练分组「{label}」条目重复: {value}")
                bucket.append(value)
            continue
        checks.append(item)
    for label, values in groups.items():
        if len(values) > PROFICIENCY_GROUP_ITEM_MAX:
            raise AssertionError(
                f"熟练分组「{label}」最多 {PROFICIENCY_GROUP_ITEM_MAX} 项"
            )
    return checks, groups


def _parse_signed_bonus(value: str, label: str) -> str:
    """解析带符号加值（如 ``+7``、``-1``），返回规范化文本。"""
    text = value.strip().replace("＋", "+").replace("－", "-")
    if not re.fullmatch(r"[+-]?\d+", text):
        raise AssertionError(f"{label}加值无效: {value}（示例：+7）")
    number = int(text)
    if not -99 <= number <= 99:
        raise AssertionError(f"{label}加值超出范围: {value}")
    return f"{number:+d}"


def parse_combat(content: str) -> Dict[str, str]:
    """解析 ``$战斗$`` 段为固定键字典（AC / 先攻 / 速度 / 被动察觉）。"""
    _ensure_no_dollar(content, "战斗")
    result: Dict[str, str] = {}
    for item in _split_semicolon_items(content):
        normalized = _normalize_colon(item)
        key, separator, value = normalized.partition(":")
        key = key.strip()
        if key.lower() == "ac":
            key = "AC"
        value = value.strip()
        if not separator or key not in COMBAT_KEY_LIST:
            raise AssertionError(
                f"战斗条目不完整: {item}"
                f"（可用：{'/'.join(COMBAT_KEY_LIST)}）"
            )
        if key in result:
            raise AssertionError(f"战斗条目重复: {key}")
        if key == "速度":
            if not 1 <= len(value) <= COMBAT_SPEED_MAX_LEN:
                raise AssertionError(
                    f"速度写法无效: {value}（最长 {COMBAT_SPEED_MAX_LEN} 字）"
                )
        elif key == "先攻":
            value = _parse_signed_bonus(value, "先攻")
        else:
            if not value.isdigit() or not 0 <= int(value) <= 99:
                raise AssertionError(f"{key}必须是 0~99 的整数: {value}")
        result[key] = value
    return result


def parse_feats(content: str) -> List[str]:
    """解析 ``$专长$`` 段（``/`` 分条，可写 ``名称:说明``，名称唯一）。

    说明（2026-10-21 批②）只用于卡面，最长 60 字；不写说明时回写保持原名。
    """
    _ensure_no_dollar(content, "专长")
    items = [item.strip() for item in content.split("/") if item.strip()]
    if len(items) > FEAT_MAX_COUNT:
        raise AssertionError(f"专长最多 {FEAT_MAX_COUNT} 项")
    result: List[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _normalize_colon(item)
        name, _, text = normalized.partition(":")
        name, text = name.strip(), text.strip()
        if not name:
            raise AssertionError(f"专长名称不能为空: {item}")
        if len(name) > FEAT_NAME_MAX_LEN:
            raise AssertionError(
                f"专长名称过长（≤{FEAT_NAME_MAX_LEN} 字）: {name}"
            )
        if len(text) > FEAT_TEXT_MAX_LEN:
            raise AssertionError(
                f"专长说明过长（≤{FEAT_TEXT_MAX_LEN} 字）: {text}"
            )
        if name in seen:
            raise AssertionError(f"专长重复: {name}")
        seen.add(name)
        result.append(f"{name}:{text}" if text else name)
    return result


def parse_traits(content: str) -> List[str]:
    """解析 ``$特性$`` 段（``/`` 分条，可写 ``名称（来源）:说明``，名称唯一）。

    说明（2026-10-21 批②）只用于卡面，最长 80 字；不写说明时回写保持原名。
    """
    _ensure_no_dollar(content, "特性")
    items = [item.strip() for item in content.split("/") if item.strip()]
    if len(items) > TRAIT_MAX_COUNT:
        raise AssertionError(f"特性最多 {TRAIT_MAX_COUNT} 项")
    result: List[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _normalize_colon(item)
        name, _, text = normalized.partition(":")
        name, text = name.strip(), text.strip()
        if not name:
            raise AssertionError(f"特性名称不能为空: {item}")
        if len(name) > TRAIT_ITEM_MAX_LEN:
            raise AssertionError(
                f"特性名称过长（≤{TRAIT_ITEM_MAX_LEN} 字）: {name}"
            )
        if len(text) > TRAIT_TEXT_MAX_LEN:
            raise AssertionError(
                f"特性说明过长（≤{TRAIT_TEXT_MAX_LEN} 字）: {text}"
            )
        if name in seen:
            raise AssertionError(f"特性重复: {name}")
        seen.add(name)
        result.append(f"{name}:{text}" if text else name)
    return result


def parse_items(content: str) -> List[str]:
    """解析 ``$物品$`` 段（``;`` 分条，``名称x数量[装备]`` 规范化回写）。"""
    _ensure_no_dollar(content, "物品")
    items = _split_semicolon_items(content)
    if len(items) > ITEM_MAX_COUNT:
        raise AssertionError(f"物品最多 {ITEM_MAX_COUNT} 项")
    result: List[str] = []
    for item in items:
        raw = item.strip()
        equipped = False
        if raw.endswith("[装备]"):
            equipped = True
            raw = raw[: -len("[装备]")].strip()
        if "[" in raw or "]" in raw:
            raise AssertionError(
                f"物品条目写法无效: {item}（装备标记只支持 [装备]）"
            )
        matched = re.match(r"^(.+?)(?:[xX×](\d+))?$", raw)
        if matched is None:
            raise AssertionError(f"物品条目写法无效: {item}")
        name = matched.group(1).strip()
        quantity = int(matched.group(2)) if matched.group(2) else 1
        if not name:
            raise AssertionError(f"物品名称不能为空: {item}")
        if len(name) > ITEM_NAME_MAX_LEN:
            raise AssertionError(
                f"物品名称过长（≤{ITEM_NAME_MAX_LEN} 字）: {name}"
            )
        if not 1 <= quantity <= ITEM_QUANTITY_MAX:
            raise AssertionError(
                f"物品数量无效: {item}（1~{ITEM_QUANTITY_MAX}）"
            )
        text = f"{name}x{quantity}"
        if equipped:
            text += "[装备]"
        result.append(text)
    return result


def parse_background(content: str) -> Dict[str, str]:
    """解析 ``$背景$`` 段（``;`` 分条，``键:值``；未知键保留）。"""
    _ensure_no_dollar(content, "背景")
    items = _split_semicolon_items(content)
    if len(items) > BACKGROUND_MAX_COUNT:
        raise AssertionError(f"背景条目最多 {BACKGROUND_MAX_COUNT} 项")
    result: Dict[str, str] = {}
    for item in items:
        normalized = _normalize_colon(item)
        key, separator, value = normalized.partition(":")
        key = key.strip()
        value = value.strip()
        if not separator or not key or not value:
            raise AssertionError(
                f"背景条目不完整: {item}（示例：背景:士兵; 阵营:守序善良）"
            )
        if len(key) > BACKGROUND_KEY_MAX_LEN:
            raise AssertionError(
                f"背景键过长（≤{BACKGROUND_KEY_MAX_LEN} 字）: {key}"
            )
        if len(value) > BACKGROUND_VALUE_MAX_LEN:
            raise AssertionError(
                f"背景内容过长（≤{BACKGROUND_VALUE_MAX_LEN} 字）: {key}"
            )
        if key in result:
            raise AssertionError(f"背景条目重复: {key}")
        result[key] = value
    return result


def parse_combat_notes(content: str) -> List[str]:
    """解析 ``$战斗记录$`` 段（``;`` 分条，自由文本）。"""
    _ensure_no_dollar(content, "战斗记录")
    items = _split_semicolon_items(content)
    if len(items) > COMBAT_NOTE_MAX_COUNT:
        raise AssertionError(f"战斗记录最多 {COMBAT_NOTE_MAX_COUNT} 项")
    result: List[str] = []
    for item in items:
        if len(item) > COMBAT_NOTE_MAX_LEN:
            raise AssertionError(
                f"战斗记录条目过长（≤{COMBAT_NOTE_MAX_LEN} 字）: {item}"
            )
        result.append(item)
    return result


def _story_char_count(text: str) -> int:
    """故事字数：按码点计，换行不计（与网页建卡器的计数口径一致）。"""
    return sum(1 for char in text if char not in "\r\n")


def parse_story(content: str) -> str:
    """解析 ``$故事$`` 段（可多行多段，1~1000 字；换行不计入字数）。

    换行会原样保留，便于写多个段落；``$`` 仍不可出现（模板按它切段）。
    """
    _ensure_no_dollar(content, "故事", allow_newline=True)
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines).strip()
    if not text:
        raise AssertionError("故事内容不能为空")
    count = _story_char_count(text)
    if count > STORY_MAX_LEN:
        raise AssertionError(f"故事内容过长（≤{STORY_MAX_LEN} 字，换行不计）")
    return text


def parse_progress(content: str) -> Dict[str, str]:
    """解析 ``$进度$`` 段 → ``{经验: "6500/14000", 激励: "有"}``。

    ``经验`` 写 ``当前`` 或 ``当前/下一级``（0~9999999）；``激励`` 写 有/无。
    """
    _ensure_no_dollar(content, "进度")
    result: Dict[str, str] = {}
    for item in _split_semicolon_items(content):
        normalized = _normalize_colon(item)
        key, separator, value = normalized.partition(":")
        key, value = key.strip(), value.strip()
        if not separator or key not in ("经验", "激励"):
            raise AssertionError(
                f"进度条目不完整: {item}（示例：经验:6500/14000; 激励:有）"
            )
        if key in result:
            raise AssertionError(f"进度条目重复: {key}")
        if key == "经验":
            parts = value.split("/")
            if len(parts) > 2 or not all(part.strip().isdigit() for part in parts):
                raise AssertionError(
                    f"经验值写法无效: {item}（示例：经验:6500/14000）"
                )
            numbers = [int(part.strip()) for part in parts]
            if any(number > XP_VALUE_MAX for number in numbers):
                raise AssertionError(
                    f"经验值超出范围（0~{XP_VALUE_MAX}）: {item}"
                )
            result["经验"] = "/".join(str(number) for number in numbers)
            continue
        if value in ("有", "是", "1"):
            result["激励"] = "有"
        elif value in ("无", "否", "0"):
            result["激励"] = "无"
        else:
            raise AssertionError(f"激励只能写 有 或 无: {item}")
    return result


def parse_coins(content: str) -> Dict[str, int]:
    """解析 ``$钱币$`` 段 → ``{CP: 0, SP: 8, ...}``（键固定五种）。"""
    _ensure_no_dollar(content, "钱币")
    result: Dict[str, int] = {}
    for item in _split_semicolon_items(content):
        normalized = _normalize_colon(item)
        key, separator, value = normalized.partition(":")
        key = key.strip().upper()
        value = value.strip()
        if not separator or key not in COIN_KEY_LIST:
            raise AssertionError(
                f"钱币条目不完整: {item}"
                f"（可用：{'/'.join(COIN_KEY_LIST)}，示例：GP:18）"
            )
        if key in result:
            raise AssertionError(f"钱币条目重复: {key}")
        if not value.isdigit():
            raise AssertionError(f"钱币数值无效: {item}（写 0~999999 的整数）")
        number = int(value)
        if number > COIN_VALUE_MAX:
            raise AssertionError(
                f"钱币数值超出范围（0~{COIN_VALUE_MAX}）: {item}"
            )
        result[key] = number
    return result


def match_features(
    features: Iterable[CharacterFeature], name: str
) -> List[CharacterFeature]:
    """按名称匹配能力：精确（大小写不敏感）优先，其次子串模糊匹配。

    与武器/目标搜索同款两级；返回空 = 未找到、多项 = 歧义（调用方列候选、不猜）。
    """
    lowered = name.lower()
    for feature in features:
        if feature.name.lower() == lowered:
            return [feature]
    return [feature for feature in features if lowered in feature.name.lower()]


def match_spells(spells: Iterable[SpellEntry], name: str) -> List[SpellEntry]:
    """按名称匹配法术（精确优先 → 子串），口径同 ``match_features``。"""
    lowered = name.lower()
    for spell in spells:
        if spell.name.lower() == lowered:
            return [spell]
    return [spell for spell in spells if lowered in spell.name.lower()]


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
        prof_groups: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """校验并写入等级/六属性/熟练项/额外加值；失败抛 AssertionError（用户可见）。

        ``prof_groups`` 是 ``$熟练$`` 的扩展分组（护甲/武器/工具/语言），
        只展示、不参与检定计算；传空时四组一并清空。
        """
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

        # 熟练项：默认全部不熟练，$熟练$ 声明了哪些条目才熟练（支持 N*名称
        # 多倍熟练与 0*名称 显式关闭；攻击熟练不存在——攻击检定走武器项、
        # 命中加值由用户自填，见 commands/weapon.py）
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
        groups = prof_groups or {}
        ability_info.prof_armor = list(groups.get("护甲", []))
        ability_info.prof_weapons = list(groups.get("武器", []))
        ability_info.prof_tools = list(groups.get("工具", []))
        ability_info.prof_languages = list(groups.get("语言", []))

    @staticmethod
    def perform_check(
        ability_info: AbilityInfo,
        check_name: str,
        advantage: int,
        mod_str: str,
    ) -> Tuple[str, str, int, RollResult]:
        """执行一次条目检定（属性/技能/豁免通用）。

        Args:
            ability_info: 已初始化的属性信息。
            check_name: 条目名（可为同义词），如 力量/运动/敏捷豁免/先攻。
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

        hint_parts: List[str] = []
        check_index = CHECK_ITEM_INDEX_DICT[name]
        parent_name = ""
        if is_skill:
            parent_name = SKILL_PARENT_DICT[name]
        elif is_saving:
            parent_name = SAVING_PARENT_DICT[name]

        # 熟练加值
        scale = ability_info.check_prof[check_index]
        prof_bonus = scale * ability_info.get_prof_bonus()
        if scale == 0:
            hint_parts.append("无熟练加值")
        elif scale == 1:
            hint_parts.append(f"熟练加值:{prof_bonus}")
        else:
            hint_parts.append(f"熟练加值:{ability_info.get_prof_bonus()}*{scale}")

        # 属性调整值（技能/豁免取父属性）
        if parent_name:
            parent_index = ABILITY_LIST.index(parent_name)
            modifier = ability_info.get_modifier(parent_index)
            hint_parts.append(f"{parent_name}调整值:{modifier}")
        else:
            modifier = ability_info.get_modifier(check_index)
            hint_parts.append(f"{ABILITY_LIST[check_index]}调整值:{modifier}")

        # 额外加值（条目自身 + 父属性 + 全局豁免）
        ext_str = ability_info.check_ext[check_index]
        if parent_name:
            parent_index = ABILITY_LIST.index(parent_name)
            ext_str += ability_info.check_ext[EXT_ITEM_INDEX_DICT[ABILITY_LIST[parent_index]]]
        if is_saving:
            ext_str += ability_info.check_ext[EXT_ITEM_INDEX_DICT[SAVING_ALL_KEY]]
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
    def _merge_single_segment(
        existing: DNDCharacter,
        key: str,
        content: str,
        reserved_names: Iterable[str],
    ) -> DNDCharacter:
        """单段录入：把该段写回现有卡文本后按整卡重解析。

        走「卡文本 → 段字典 → 卡文本」的往返路径，保证单段更新与整卡记录
        使用同一套校验与规范化逻辑；其余段保持原有语义（格式按卡面规范回写）。
        """
        existing_data = parse_template_to_dict(existing.get_char_info())
        existing_data[key] = content
        merged_text = "\n".join(
            f"{name} {existing_data[name]}"
            for name in CHAR_INFO_KEY_LIST
            if name in existing_data
        )
        merged = CharacterService.parse(
            merged_text,
            existing.group_id,
            existing.user_id,
            reserved_names,
        )
        merged.portrait = existing.portrait
        return merged

    @staticmethod
    def parse(
        input_str: str,
        group_id: str,
        user_id: str,
        reserved_names: Iterable[str] = (),
        existing: Optional[DNDCharacter] = None,
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
        $能力$ 奥术回想:1/1短休
        $武器$ 短剑+6,1d4+4穿刺/长弓+5,1d8+3穿刺
        $法术$ 施法属性:智力; 火球术:3*; 火焰箭:0
        $法术位$ 1:4/4; 2:3/3; 契约3:2/2

        ``reserved_names`` 为保留名集合（插件固定命令名），武器名不得与之
        冲突（由命令层传入；缺省不检查，供纯函数调用与单测）。

        ``existing`` 为当前卡（分段录入用）：只带**一个** ``$段名$`` 时，
        把该段替换进现有卡文本后按整卡重解析，因此其余段保持原有语义；
        带两个及以上段时按整卡覆盖。无 ``existing`` 时行为与旧版一致。
        """
        data = parse_template_to_dict(input_str)
        # 属性值 / 豁免 / 技能自 2026-10-22 起由骰娘自动计算：旧卡整卡重录时
        # 静默忽略这三段；若只发了这三段，给出明确提示而不是「角色卡已设置」。
        if data and all(key in LEGACY_CHAR_INFO_KEY_LIST for key in data):
            raise AssertionError(
                "属性值、豁免与技能由骰娘按属性、等级与熟练自动计算，无需记录"
            )
        if existing is not None and len(data) == 1:
            key, content = next(iter(data.items()))
            if key in LEGACY_CHAR_INFO_KEY_LIST:
                raise AssertionError(
                    "属性值、豁免与技能由骰娘按属性、等级与熟练自动计算，无需记录"
                )
            return CharacterService._merge_single_segment(
                existing, key, content, reserved_names
            )

        hp_info = HPInfo()
        ability_info = AbilityInfo()

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
        prof_list, prof_groups = (
            parse_prof_entries(prof_str) if prof_str else ([], {})
        )
        ext_dict: Dict[str, str] = {}
        if ext_str:
            for item in ext_str.split("/"):
                if ":" not in item or item.endswith(":"):
                    raise AssertionError("必须使用冒号(:)分割额外加值条目和内容")
                key, _, content = item.partition(":")
                ext_dict[key] = content

        AbilityService.initialize(
            ability_info,
            level_str,
            ability_values,
            prof_list,
            ext_dict,
            prof_groups=prof_groups,
        )

        # ── 种族/职业/子职/武器（可选段；职业与武器名有校验）──
        char_class = ""
        char_class_str = data.get(CHAR_INFO_KEY_CLASS, "").strip()
        if char_class_str:
            char_class = normalize_class_name(char_class_str)
        weapon_str = data.get(CHAR_INFO_KEY_WEAPON, "").strip()
        weapons = parse_weapon_list(weapon_str, reserved_names) if weapon_str else []

        # ── 能力 / 法术 / 法术位（可选段，2026-10-20 批②）──
        feature_str = data.get(CHAR_INFO_KEY_FEATURE, "").strip()
        features = parse_feature_list(feature_str) if feature_str else []
        spell_str = data.get(CHAR_INFO_KEY_SPELL, "").strip()
        if spell_str:
            spellcasting_ability, spells, spell_dc, spell_attack = parse_spell_setting(
                spell_str
            )
        else:
            spellcasting_ability, spells = "", []
            spell_dc = spell_attack = ""
        slots_str = data.get(CHAR_INFO_KEY_SPELL_SLOTS, "").strip()
        spell_slots = parse_spell_slots(slots_str) if slots_str else SpellSlots()

        # ── 完整卡面扩展段（2026-10-21，全部可选）──
        background_str = data.get(CHAR_INFO_KEY_BACKGROUND, "").strip()
        combat_str = data.get(CHAR_INFO_KEY_COMBAT, "").strip()
        feats_str = data.get(CHAR_INFO_KEY_FEATS, "").strip()
        traits_str = data.get(CHAR_INFO_KEY_TRAITS, "").strip()
        items_str = data.get(CHAR_INFO_KEY_ITEMS, "").strip()
        notes_str = data.get(CHAR_INFO_KEY_COMBAT_NOTES, "").strip()
        story_str = data.get(CHAR_INFO_KEY_STORY, "").strip()
        progress_str = data.get(CHAR_INFO_KEY_PROGRESS, "").strip()
        coins_str = data.get(CHAR_INFO_KEY_COINS, "").strip()
        background = parse_background(background_str) if background_str else {}
        combat = parse_combat(combat_str) if combat_str else {}
        feats = parse_feats(feats_str) if feats_str else []
        traits = parse_traits(traits_str) if traits_str else []
        items = parse_items(items_str) if items_str else []
        combat_notes = parse_combat_notes(notes_str) if notes_str else []
        story = parse_story(story_str) if story_str else ""
        progress = parse_progress(progress_str) if progress_str else {}
        coins = parse_coins(coins_str) if coins_str else {}

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
            features=features,
            spells=spells,
            spell_slots=spell_slots,
            spellcasting_ability=spellcasting_ability,
            spell_dc=spell_dc,
            spell_attack=spell_attack,
            portrait=existing.portrait if existing is not None else "",
            combat=combat,
            feats=feats,
            traits=traits,
            items=items,
            background=background,
            combat_notes=combat_notes,
            story=story,
            progress=progress,
            coins=coins,
            is_init=True,
        )


def gen_template_char(group_id: str = "", user_id: str = "") -> DNDCharacter:
    """生成一张示例角色卡（供 .角色卡模板 输出展示）。

    示例为按 2024 规则完整建立的 5 级高等精灵法师（塑能师）：
    27 点购点、智者背景（+2 智力 / +1 体质）、4 级属性提升（+1 智力 / +1 感知），
    覆盖 ``$能力$`` / ``$法术$`` / ``$法术位$`` 与完整卡面各段。
    """
    character = DNDCharacter(
        group_id=group_id, user_id=user_id, name="伊瑟兰·晨星", is_init=True
    )
    character.race = "高等精灵"
    character.char_class = "法师"
    character.subclass = "塑能师"
    character.hp_info.initialize(
        hp_cur=37,
        hp_max=37,
        hp_temp=0,
        hp_dice_type=6,
        hp_dice_num=5,
        hp_dice_max=5,
    )
    character.ability_info.is_init = True
    character.ability_info.level = 5
    character.ability_info.ability = [8, 14, 16, 18, 11, 8]
    for name in ("奥秘", "历史", "洞悉", "察觉", "智力豁免", "感知豁免"):
        character.ability_info.check_prof[CHECK_ITEM_INDEX_DICT[name]] = 1
    character.ability_info.check_prof[CHECK_ITEM_INDEX_DICT["调查"]] = 2
    # 命中与伤害与卡自洽：法术攻击 +7 = 智力 +4 + 熟练 +3；匕首 +5 = 敏捷 +2 + 熟练 +3；
    # 长棍 +2 = 力量 -1 + 熟练 +3。
    character.weapons = [
        WeaponInfo(
            name="火焰箭", attack_bonus="+7", damage_expr="2d10",
            damage_type="火焰", note="法术攻击 · 120尺",
        ),
        WeaponInfo(
            name="冷冻射线", attack_bonus="+7", damage_expr="2d8",
            damage_type="寒冷", note="法术攻击 · 60尺 · 速度-10",
        ),
        WeaponInfo(
            name="匕首", attack_bonus="+5", damage_expr="1d4+2",
            damage_type="穿刺", note="灵巧 · 轻型",
        ),
        WeaponInfo(
            name="长棍", attack_bonus="+2", damage_expr="1d6-1",
            damage_type="钝击", note="奥术法器 · 两用(1d8)",
        ),
    ]
    character.features = [
        CharacterFeature(
            name="奥术回想",
            uses_cur=1,
            uses_max=1,
            recover="短休",
            text="短休时恢复总环阶不超过 3 的法术位（6 环以下），长休前一次",
        ),
        CharacterFeature(
            name="魔法学徒",
            uses_cur=1,
            uses_max=1,
            recover="长休",
            text="无需法术位施展一次护盾术，长休恢复",
        ),
    ]
    character.spellcasting_ability = "智力"
    character.spell_dc = "15"
    character.spell_attack = "+7"
    character.spells = [
        SpellEntry(
            name="火焰箭", level=0,
            cast_time="1动作", range="120尺", note="2d10 火焰 / 法术攻击",
        ),
        SpellEntry(
            name="冷冻射线", level=0,
            cast_time="1动作", range="60尺", note="2d8 寒冷 / 速度-10",
        ),
        SpellEntry(
            name="法师之手", level=0,
            cast_time="1动作", range="30尺", note="操控物件 / 1分钟",
        ),
        SpellEntry(
            name="次级幻象", level=0,
            cast_time="1动作", range="30尺", material=True,
            note="声音或影像 / 1分钟",
        ),
        SpellEntry(
            name="魔法伎俩", level=0,
            cast_time="1动作", range="10尺", note="无害小魔法 / 至多1小时",
        ),
        SpellEntry(
            name="光亮术", level=0,
            cast_time="1动作", range="触碰", material=True,
            note="20尺明亮光照 / 1小时",
        ),
        SpellEntry(
            name="心灵之楔", level=0,
            cast_time="1动作", range="60尺", note="2d6 心灵 / 智力豁免",
        ),
        SpellEntry(
            name="护盾术", level=1, prepared=True,
            cast_time="1反应", range="自身", note="+5 AC / 1轮 / 学徒免位1次",
        ),
        SpellEntry(
            name="魔法飞弹", level=1, prepared=True,
            cast_time="1动作", range="120尺", note="3d4+3 力场 / 升环+1飞镖",
        ),
        SpellEntry(
            name="法师护甲", level=1, prepared=True,
            cast_time="1动作", range="触碰", material=True,
            note="AC 13+敏捷 / 8小时",
        ),
        SpellEntry(
            name="侦测魔法", level=1, prepared=True,
            cast_time="1动作或仪式", range="自身",
            concentration=True, ritual=True, note="30尺灵光 / 血系免位1次",
        ),
        SpellEntry(
            name="羽落术", level=1, prepared=True,
            cast_time="1反应", range="60尺", material=True,
            note="至多5个生物 / 1分钟",
        ),
        SpellEntry(
            name="迷踪步", level=2, prepared=True,
            cast_time="1附赠动作", range="自身", note="传送30尺 / 血系免位1次",
        ),
        SpellEntry(
            name="蛛网术", level=2, prepared=True,
            cast_time="1动作", range="60尺", concentration=True, material=True,
            note="20尺立方 / 束缚",
        ),
        SpellEntry(
            name="镜影术", level=2, prepared=True,
            cast_time="1动作", range="自身", note="3个分身 / 1分钟",
        ),
        SpellEntry(
            name="火球术", level=3, prepared=True,
            cast_time="1动作", range="150尺", material=True,
            note="20尺半径 / 8d6 火焰 / 敏捷",
        ),
        SpellEntry(
            name="闪电束", level=3, prepared=True,
            cast_time="1动作", range="自身", material=True,
            note="100尺线 / 8d6 闪电 / 敏捷",
        ),
        SpellEntry(
            name="法术反制", level=3, prepared=True,
            cast_time="1反应", range="60尺", note="体质豁免 / 打断施法",
        ),
        SpellEntry(
            name="加速术", level=3, prepared=True,
            cast_time="1动作", range="30尺", concentration=True, material=True,
            note="速度翻倍 / +2 AC / 额外动作",
        ),
    ]
    character.spell_slots = SpellSlots(
        slots_cur=[4, 3, 2, 0, 0, 0, 0, 0, 0],
        slots_max=[4, 3, 2, 0, 0, 0, 0, 0, 0],
    )
    character.combat = {
        "AC": "15", "先攻": "+2", "速度": "30", "被动察觉": "13",
    }
    character.ability_info.prof_armor = []
    character.ability_info.prof_weapons = ["匕首", "长棍"]
    character.ability_info.prof_tools = ["书法工具"]
    character.ability_info.prof_languages = ["通用语", "精灵语", "龙语"]
    character.feats = [
        "魔法学徒（法师）:习得光亮术、心灵之楔与护盾术；护盾术可免法术位施展一次，长休恢复",
        "属性值提升:智力 +1、感知 +1",
    ]
    character.traits = [
        "黑暗视觉（种族）:60 尺内微光视为明亮，黑暗视为微光",
        "妖精血统（种族）:进行避免或结束魅惑状态的豁免时具有优势",
        "敏锐感官（种族）:获得察觉熟练",
        "出神（种族）:无需睡眠，魔法无法使你入睡；4 小时即可完成长休并保持清醒",
        "高等精灵血系（种族）:习得魔法伎俩；3 级习得侦测魔法、5 级习得迷踪步，"
        "始终准备，各可免法术位施展一次，长休恢复",
        "仪式学家（法师）:法术书中的仪式法术可直接以仪式施展，无需准备",
        "学者（法师）:获得调查专精",
        "塑能学者（法师）:法术书免费加入燃烧之手、粉碎音波与火球术",
        "强力戏法（塑能师）:伤害戏法攻击失手或目标豁免成功时，仍受一半伤害",
        "记忆法术（法师）:短休时可研究法术书，替换一道已准备的一环及以上法术",
    ]
    character.items = [
        "法术书x1[装备]", "长棍x1[装备]", "匕首x2[装备]", "长袍x1[装备]",
        "学者套组x1", "书法工具x1", "书籍（历史）x1", "羊皮纸x8",
        "治疗药水x1",
    ]
    character.background = {
        "背景": "智者", "阵营": "中立善良", "信仰": "密斯特拉", "体型": "中型",
        "年龄": "132", "外貌": "银发绿眼，深蓝法袍",
        "个性": "喜欢追问原理", "理想": "知识应当被分享",
        "羁绊": "导师的笔记", "缺点": "说话太直",
    }
    character.progress = {"经验": "6500/14000", "激励": "有"}
    character.coins = {"CP": 0, "SP": 0, "EP": 0, "GP": 13, "PP": 0}
    character.story = (
        "伊瑟兰出身于银月城的学者世家，少年时在塔中抄录古籍，一次偶然的星象记录"
        "让伊瑟兰看见奥术网络背后的裂隙。\n"
        "此后伊瑟兰离开书斋，以旅行者的身份追查那些被刻意抹去的法术痕迹；相信"
        "知识应当被分享，但也清楚有些门一旦打开就再难关上。\n"
        "如今伊瑟兰随商队来到边境，既是为了寻找失落的抄本，也是为了证明自己不只是"
        "导师笔记里的一个名字。"
    )
    character.combat_notes = ["法师护甲(8小时)"]
    return character


class HPService:
    """HP 相关服务（伤害/治疗结算、长休与生命骰）。"""

    @staticmethod
    def use_hp_dice(
        hp_info: HPInfo,
        num: int,
        con_mod: int,
        *,
        version_2024: bool = False,
    ) -> str:
        """使用生命骰恢复 HP，返回修改结果描述（旧接口，行为同默认 2014 口径）。"""
        _ok, text = HPService.use_hp_dice_ex(
            hp_info, num, con_mod, version_2024=version_2024
        )
        return text

    @staticmethod
    def use_hp_dice_ex(
        hp_info: HPInfo,
        num: int,
        con_mod: int,
        *,
        version_2024: bool = False,
    ) -> Tuple[bool, str]:
        """使用生命骰恢复 HP，返回 ``(是否成功, 描述)``。

        两版口径（2026-10-20 批③，规则原文见 doc30 §2.2）：

        - **2014**：逐粒掷 ``1D面数 + 体质调整值``，每粒最低 0，累加；
        - **2024**：掷 ``N D面数`` 的骰点总和（至少 1），再加
          ``投掷枚数 × 体质调整值``（最终治疗最低 0）。

        ``version_2024`` 由调用方按群级规则版本传入；默认 False 保留旧行为。
        掷骰失败、未设置生命骰、数量不足时返回 ``(False, 面向用户的提示)``；
        成功时已扣骰并治疗，返回 ``(True, 结算描述)``。
        """
        if not hp_info.is_init or hp_info.hp_dice_type <= 0:
            return False, "尚未设置生命骰"
        if num <= 0 or num > 1000:
            return False, f"无效的生命骰数量({num})"
        if hp_info.hp_dice_num < num:
            return False, f"生命骰数量不足, 还有{hp_info.hp_dice_num}颗生命骰"

        hp_info_str_prev = hp_info.get_info()
        dice_type = hp_info.hp_dice_type

        if version_2024:
            roll_exp = f"{num}D{dice_type}"
            try:
                roll_result = exec_roll_exp_unified(roll_exp)
            except RollDiceError as exc:
                return False, f"未知掷骰错误:{exc.info}"
            dice_total = max(1, roll_result.get_val())
            adjust = num * con_mod
            heal_total = max(0, dice_total + adjust)
            note = "（最低为0）" if dice_total + adjust <= 0 else ""
            mod_info = (
                f"使用{num}颗D{dice_type}生命骰, 体质调整值为{con_mod}, "
                f"骰点{roll_result.get_complete_result()}, "
                f"调整{num}×{con_mod}={adjust:+d}, "
                f"回复{heal_total}点生命值{note}\n"
            )
        else:
            # 2014 口径：逐粒「骰值 + 体质调整值」，每粒最低 0
            roll_exp = f"1D{dice_type}+{con_mod}"
            roll_result_list = []
            roll_result_val = 0
            for _ in range(num):
                try:
                    roll_result = exec_roll_exp_unified(roll_exp)
                except RollDiceError as exc:
                    return False, f"未知掷骰错误:{exc.info}"
                if num > 1:
                    roll_result_list.append(f"({roll_result.get_info()})")
                else:
                    roll_result_list.append(roll_result.get_info())
                roll_val = roll_result.get_val()
                if roll_val < 0:
                    roll_val = 0
                    roll_result_list[-1] = f"({roll_result_list[-1]}->0)"
                roll_result_val += roll_val
            heal_total = roll_result_val
            roll_result_str = f"{'+'.join(roll_result_list)}={roll_result_val}"
            mod_info = (
                f"使用{num}颗D{dice_type}生命骰, 体质调整值为{con_mod}, "
                f"回复{roll_result_str}点生命值\n"
            )

        hp_info.hp_dice_num -= num
        if heal_total > 0:
            hp_info.heal(heal_total)
        mod_info += f"{hp_info_str_prev} -> {hp_info.get_info()}"
        return True, mod_info

    @staticmethod
    def refresh_hp_status(
        hp_info: HPInfo, mod_info: str, *, short_feedback: bool = False
    ) -> str:
        """把结算描述里的「当前 HP 状态」换成最新的 ``get_info()``。

        ``process_roll_result`` 在描述最后一行写的是结算当下的 HP 状态（形如
        ``HP:20/30 -> HP:0/30 昏迷``，设置/治疗为 ``当前HP:20/30``）；若之后
        又改了 HP 状态（当前只有死亡豁免计数这一处：伤害结算完才记失败、转为
        稳定或死亡），那一行就会过期。本方法只重写**最后一段状态**：保留原有的
        ``旧 -> 新`` 形态（旧值那一侧原样留着做对照），中间的掷骰与折算过程
        也一并保留（``short_feedback`` 为多目标结算的 ``; `` 形态）。
        """
        status = hp_info.get_info()
        normalized = mod_info.replace("; ", "\n")
        lines = normalized.split("\n")
        if len(lines) > 1:
            head, arrow, _old_status = lines[-1].partition(" -> ")
            lines[-1] = f"{head}{arrow}{status}" if arrow else status
            normalized = "\n".join(lines)
        else:
            normalized = status
        return normalized.replace("\n", "; ") if short_feedback else normalized

    @staticmethod
    def apply_damage_factor(value: int, damage_factor: float = 1.0) -> int:
        """按承伤因子折算伤害：抗性减半（向下取整、最少 1）、易伤加倍、全额原样。

        伤害最低为 0（表达式算出负值按 0 计，避免负伤害变回血）。口径与
        ``process_roll_result`` 的伤害结算一致，供「.hp 武器伤害写法」的表头等复用。
        """
        damage = max(0, value)
        if damage == 0:
            return 0
        if damage_factor == 0.5:
            return max(1, int(damage // 2))
        if damage_factor == 2.0:
            return int(damage) * 2
        return damage

    @staticmethod
    def effective_damage(
        hp_cur_mod_result: Optional[RollResult], damage_factor: float = 1.0
    ) -> int:
        """本次伤害实际生效的数值（掷骰结果 → 最低 0 → 抗性/易伤折算）。

        供「表头显示的伤害」与「死亡豁免判定用的伤害」共用同一口径：调用方
        **不要**在 ``process_roll_result`` 之后再自行折算一次，否则会二次施加
        抗性/易伤（伤害翻倍或再减半）。
        """
        if hp_cur_mod_result is None:
            return 0
        return HPService.apply_damage_factor(hp_cur_mod_result.get_val(), damage_factor)

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
                damage = HPService.apply_damage_factor(
                    hp_cur_mod_result.get_val(), damage_factor
                )
                damage_suffix = ""
                if damage == 0:
                    damage_suffix = "（伤害最低为0）"
                elif damage_factor == 0.5:
                    damage_suffix = f"（抗性减半→{damage}）"
                elif damage_factor == 2.0:
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

    # ── 死亡豁免（2026-10-01，批①）───────────────────────────────────────
    # 全部为纯函数式结算（不掷骰、不落盘），由 commands/hp.py 在 HP 变动后调用；
    # NPC 血量不走这里（怪物不做死亡豁免）。

    #: ``apply_death_save_on_damage`` 的结果类型：本次伤害使目标进入濒死
    DEATH_TRANSITION_ENTERED = "entered"
    #: 同上：伤势稳定中受击，解除稳定并重新开始死亡豁免
    DEATH_TRANSITION_RESTART = "restart"
    #: 同上：濒死/稳定中受击（已记失败，附播报文本）
    DEATH_TRANSITION_DAMAGE = "damage"
    #: 同上：本次伤害致死（即死或失败满 3 次，附播报文本）
    DEATH_TRANSITION_DEATH = "death"
    #: 同上：无需处理（未初始化 / 已死亡）
    DEATH_TRANSITION_NONE = ""

    @staticmethod
    def apply_death_save_on_damage(
        hp_info: HPInfo,
        damage: int,
        *,
        critical: bool = False,
        was_unconscious: bool = False,
    ) -> Tuple[str, str]:
        """HP 伤害后的死亡豁免结算，返回 ``(结果类型, 播报文本)``。

        结果类型见 ``DEATH_TRANSITION_*`` 常量：``entered`` 本次伤害使目标进入
        濒死、``restart`` 稳定中受击重新开始死亡豁免（这两种的引导文案由调用方
        给），``damage`` 记失败（文本即播报），``death`` 本次伤害致死。

        覆盖三条规则（5e 与 5r 一致）：

        - **进入濒死**：HP 归 0 且未即死 → 昏迷并开始死亡豁免（计数清零）；
        - **0 HP 期间受伤**：失败 +1（武器重击 +2）；已稳定者先解除稳定并
          重新开始计数；伤害 ≥ HP 上限则直接死亡（先判即死，不看计数）；
        - **已死亡**：不再叠加失败（复活走 ``.死亡豁免 重置``）。

        Args:
            hp_info: 已结算完本次伤害的 HP 信息。
            damage: 实际生效的伤害（已过抗性/易伤折算，见 ``effective_damage``）。
            critical: 伤害是否来自武器重击（失败记 2 次）。
            was_unconscious: **本次伤害之前**目标是否已昏迷（由调用方在扣血前
                取 ``not hp_info.is_alive`` 传入）——「这一击打到 0」与「本来
                就在 0 HP 挨打」扣血后都是 0 HP，只有扣血前的状态能区分两者。
                已稳定者（``is_stable``）无论昏迷标记如何都按「重新开始」处理，
                故该参数只影响普通昏迷与「尚未昏迷」的区分。

        注：HP 上限未设置（``hp_max == 0``）时不做即死判定，避免拿
        「损失记录」当上限误杀。
        """
        if not hp_info.is_init or hp_info.is_dead:
            return HPService.DEATH_TRANSITION_NONE, ""
        if hp_info.hp_cur > 0 and not hp_info.is_stable:
            # 还有 HP 且不在稳定态：本次伤害没把人打倒，死亡豁免完全不涉及
            return HPService.DEATH_TRANSITION_NONE, ""
        if hp_info.hp_cur < 0:
            # 未设上限的「损失记录」模式被继续扣到负数：夹到 0（5e 的 HP 不为负）
            hp_info.hp_cur = 0
            hp_info.is_alive = False

        limit = hp_info.hp_max
        if limit > 0 and damage >= limit:
            hp_info.is_stable = False
            hp_info.is_dead = True
            return (
                HPService.DEATH_TRANSITION_DEATH,
                f"受到{damage}点伤害（≥生命值上限 {limit}）——死亡。",
            )

        if not was_unconscious or hp_info.is_stable:
            # 从「有 HP」或「已稳定」被打到 0：开始死亡豁免。进入濒死那一击
            # 本身不记失败（5e：只有「已在 0 HP 时受伤」才记）
            was_stable = hp_info.is_stable
            hp_info.clear_death_state(revive=False)
            kind = (
                HPService.DEATH_TRANSITION_RESTART if was_stable
                else HPService.DEATH_TRANSITION_ENTERED
            )
            return kind, ""

        fatal = hp_info.add_death_failure(2 if critical else 1)
        if fatal:
            return HPService.DEATH_TRANSITION_DEATH, "死亡豁免失败累计3次——死亡。"
        return (
            HPService.DEATH_TRANSITION_DAMAGE,
            "正在濒死中受到伤害：死亡豁免失败"
            f"+{2 if critical else 1}（成功{hp_info.ds_success} 失败{hp_info.ds_failure}）",
        )

    @staticmethod
    def roll_death_save(
        hp_info: HPInfo, advantage: int = 0, mod_str: str = ""
    ) -> Tuple[str, str, str, bool, bool]:
        """掷一次 d20 死亡豁免并按出目结算，返回 (过程文本, 播报行, 数值, 自然20, 自然1)。

        判定与属性无关（5e/5r 一致）：自然 20 → 回复 1 点 HP 并结束濒死；
        自然 1 → 记两次失败；出目 ≥10 → 成功 +1；≤9 → 失败 +1。
        成功累计 3 次即伤势稳定、失败累计 3 次即死亡。

        ``advantage`` 1 优势 / -1 劣势 / 0 无；``mod_str`` 为房规加值片段
        （如 ``"+2"`` / ``"-1"``），只影响出目、不影响自然 20/1 的判定
        （自然 20/1 看的是**保留的 d20 点数**）。

        Raises:
            AssertionError: 表达式无效或掷骰失败（消息面向用户）。
        """
        roll_exp = "D20优势" if advantage > 0 else ("D20劣势" if advantage < 0 else "D20")
        if mod_str:
            roll_exp += mod_str
        try:
            roll_result = exec_roll_exp_unified(roll_exp)
        except RollDiceError as exc:
            raise AssertionError(f"无效的死亡豁免加值:{mod_str}（{exc.info}）")

        natural = roll_result.d20_list[-1] if roll_result.d20_list else 0
        value = roll_result.get_val()
        result_str = roll_result.get_complete_result()

        if natural == 20:
            hp_info.revive_with_hp(1)
            return result_str, "死亡豁免·自然20：回复 1 点 HP，伤势脱离濒死！", value, True, False
        if natural == 1:
            if hp_info.add_death_failure(2):
                return result_str, "死亡豁免·自然1：失败 +2，累计 3 次——死亡。", value, False, True
            return (
                result_str,
                f"死亡豁免·自然1：失败 +2（成功{hp_info.ds_success} 失败{hp_info.ds_failure}）",
                value, False, True,
            )
        if value >= 10:
            if hp_info.add_death_success(1):
                return (
                    result_str,
                    "死亡豁免成功：伤势稳定，不再需要掷死亡豁免"
                    "（再受伤则重新开始死亡豁免）。",
                    value, False, False,
                )
            return (
                result_str,
                f"死亡豁免成功 +1（成功{hp_info.ds_success} 失败{hp_info.ds_failure}）",
                value, False, False,
            )
        if hp_info.add_death_failure(1):
            return result_str, "死亡豁免失败 +1，累计 3 次——死亡。", value, False, False
        return (
            result_str,
            f"死亡豁免失败 +1（成功{hp_info.ds_success} 失败{hp_info.ds_failure}）",
            value, False, False,
        )


class RestService:
    """休息结算：能力次数与法术位恢复、施法准备提醒判定（2026-10-20 批③）。

    只做内存对象上的纯结算（不掷骰、不落盘）；命令层负责读取卡、播报与保存。
    恢复档语义与 ``$能力$`` 录入一致：``短休`` / ``长休`` / ``两者`` +
    可选 ``+N``（``满`` 已在录入时规范化为无后缀）。
    """

    @staticmethod
    def feature_recovery_amount(recover: str, rest_kind: str) -> Optional[int]:
        """返回某能力在指定休息中的恢复量：None=不恢复，-1=回满，N=恢复 N 次。"""
        mapping: Dict[str, int] = {}
        for piece in (recover or "").split(","):
            token = piece.strip()
            if not token:
                continue
            for mode in FEATURE_RECOVER_MODES:
                if not token.startswith(mode):
                    continue
                tail = token[len(mode):].strip()
                try:
                    amount = -1 if not tail else int(tail[1:])
                except ValueError:
                    amount = -1
                if mode == "两者":
                    mapping[REST_SHORT] = amount
                    mapping[REST_LONG] = amount
                else:
                    mapping[mode] = amount
                break
        return mapping.get(rest_kind)

    @staticmethod
    def recover_features(
        features: Iterable[CharacterFeature], rest_kind: str
    ) -> List[Tuple[str, int, int, int]]:
        """按休息类型恢复能力次数，返回变更列表 ``(名称, 旧, 新, 上限)``。

        只返回真正发生变化的能力；已满或恢复档不匹配的条目不动。
        """
        changes: List[Tuple[str, int, int, int]] = []
        for feature in features:
            amount = RestService.feature_recovery_amount(
                feature.recover, rest_kind
            )
            if amount is None:
                continue
            old = feature.uses_cur
            new = (
                feature.uses_max
                if amount == -1
                else min(feature.uses_max, old + amount)
            )
            if new == old:
                continue
            feature.uses_cur = new
            changes.append((feature.name, old, new, feature.uses_max))
        return changes

    @staticmethod
    def restore_slots(
        slots: SpellSlots, rest_kind: str
    ) -> List[Tuple[str, int, int, int]]:
        """按休息类型恢复法术位，返回变更列表 ``(展示名, 旧, 新, 上限)``。

        - 短休：只恢复契约魔法法术位；
        - 长休：恢复全部已消耗的普通法术位与契约魔法法术位。
        """
        changes: List[Tuple[str, int, int, int]] = []

        def _restore(label: str, old: int, maximum: int) -> None:
            if maximum <= 0 or old >= maximum:
                return
            changes.append((label, old, maximum, maximum))

        if rest_kind == REST_SHORT:
            _restore(
                spell_slot_label(True, slots.pact_level) if slots.pact_max else "",
                slots.pact_cur,
                slots.pact_max,
            )
            if slots.pact_max > 0:
                slots.pact_cur = slots.pact_max
            return changes

        if rest_kind == REST_LONG:
            for level in range(1, SPELL_LEVEL_MAX + 1):
                index = level - 1
                _restore(
                    spell_slot_label(False, level),
                    slots.slots_cur[index],
                    slots.slots_max[index],
                )
                slots.slots_cur[index] = slots.slots_max[index]
            _restore(
                spell_slot_label(True, slots.pact_level) if slots.pact_max else "",
                slots.pact_cur,
                slots.pact_max,
            )
            slots.pact_cur = slots.pact_max
        return changes

    @staticmethod
    def should_remind_preparation(version_2024: bool, char_class: str) -> bool:
        """按群级规则版本与职业判定是否提醒「未标记准备」。

        2024：8 个施法职业都提醒；2014：只有牧师 / 德鲁伊 / 圣武士 / 法师
        这些准备型职业提醒（已知型施法者与无施法职业不提醒）。
        """
        if not char_class:
            return False
        if version_2024:
            return char_class in SPELLCASTING_CLASSES_2024
        return char_class in PREPARED_CASTERS_2014

    @staticmethod
    def available_slots_summary(slots: SpellSlots) -> str:
        """当前可用法术位摘要（只列还有剩余的法术位），如 ``3环 1/2、契约魔法（3环） 2/2``。"""
        parts: List[str] = []
        for level in range(1, SPELL_LEVEL_MAX + 1):
            index = level - 1
            if slots.slots_cur[index] <= 0:
                continue
            parts.append(
                f"{spell_slot_label(False, level)} "
                f"{slots.slots_cur[index]}/{slots.slots_max[index]}"
            )
        if slots.pact_max > 0 and slots.pact_cur > 0:
            parts.append(
                f"{spell_slot_label(True, slots.pact_level)} "
                f"{slots.pact_cur}/{slots.pact_max}"
            )
        return "、".join(parts) if parts else "无"

    @staticmethod
    def consume_spell_slot(
        slots: SpellSlots, level: int, *, allow_pact_upcast: bool = True
    ) -> Optional[Tuple[bool, int, int, int]]:
        """消耗一个指定环阶的法术位，返回 ``(是否契约, 实际环阶, 旧值, 上限)``。

        优先消耗同环阶的普通法术位；没有时若契约魔法的环阶 ≥ 请求环阶
        （``allow_pact_upcast``）且有剩余，则消耗契约位（魔契师用法术位）。
        无法消耗返回 None（不修改对象）。
        """
        if 1 <= level <= SPELL_LEVEL_MAX:
            index = level - 1
            if slots.slots_max[index] > 0 and slots.slots_cur[index] > 0:
                old = slots.slots_cur[index]
                slots.slots_cur[index] -= 1
                return False, level, old, slots.slots_max[index]
        if slots.pact_max > 0 and slots.pact_cur > 0:
            pact_ok = slots.pact_level == level or (
                allow_pact_upcast and slots.pact_level > level
            )
            if pact_ok:
                old = slots.pact_cur
                slots.pact_cur -= 1
                return True, slots.pact_level, old, slots.pact_max
        return None
