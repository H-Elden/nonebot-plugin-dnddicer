"""DND5e 角色数据模型（Pydantic，纯数据与基础展示方法）。

存储/检定等复杂业务见 data/characters.py 与 character/services.py。
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .constants import (
    ABILITY_NUM,
    CHECK_ITEM_INDEX_DICT,
    CHECK_ITEM_LIST,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_CLASS,
    CHAR_INFO_KEY_EXT,
    CHAR_INFO_KEY_HP,
    CHAR_INFO_KEY_HP_DICE,
    CHAR_INFO_KEY_LEVEL,
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_PROF,
    CHAR_INFO_KEY_RACE,
    CHAR_INFO_KEY_SUBCLASS,
    CHAR_INFO_KEY_WEAPON,
    EXT_ITEM_INDEX_DICT,
    EXT_ITEM_LIST,
)


class HPInfo(BaseModel):
    """生命值信息（当前/最大/临时 HP 与生命骰）。"""

    is_init: bool = False
    is_alive: bool = True
    hp_cur: int = 0       # 当前生命值
    hp_max: int = 0       # 最大生命值
    hp_temp: int = 0      # 临时生命值
    hp_dice_type: int = 0  # 生命骰面数
    hp_dice_num: int = 0   # 当前生命骰数量
    hp_dice_max: int = 0   # 生命骰最大数量

    def initialize(
        self,
        hp_cur: int,
        hp_max: int = 0,
        hp_temp: int = 0,
        hp_dice_type: int = 0,
        hp_dice_num: int = 0,
        hp_dice_max: int = 0,
    ) -> None:
        """按模板字符串解析结果初始化 HP。"""
        assert 0 <= hp_cur <= hp_max, f"无效的生命值信息: {hp_cur}/{hp_max}"
        assert hp_temp >= 0, f"无效的临时生命值信息: {hp_temp}"
        assert 0 <= hp_dice_type <= 100 and 0 <= hp_dice_max <= 1000, \
            f"无效的生命骰信息: {hp_dice_max}颗{hp_dice_type}面骰"
        self.is_init = True
        self.is_alive = True
        self.hp_cur = hp_cur
        self.hp_max = hp_max
        self.hp_temp = hp_temp
        self.hp_dice_type = hp_dice_type
        self.hp_dice_num = hp_dice_num
        self.hp_dice_max = hp_dice_max

    def is_record_normal(self) -> bool:
        """当前是否正常记录生命值（拥有 HP 值，而非单纯记录受损）。"""
        return self.hp_cur > 0 or (self.hp_cur == 0 and not self.is_alive)

    def is_record_damage(self) -> bool:
        """当前是否是记录受损生命值的情况。"""
        return not self.is_record_normal()

    def take_damage(self, value: int) -> None:
        """受到伤害：临时 HP 先吸收，溢出扣当前 HP；降至 0 昏迷。"""
        if self.hp_temp > 0:
            if self.hp_temp >= value:
                self.hp_temp -= value
                return
            else:
                value -= self.hp_temp
                self.hp_temp = 0
        if self.is_alive:
            if self.hp_cur > 0:
                if self.hp_cur > value:
                    self.hp_cur -= value
                else:
                    self.hp_cur = 0
                    self.is_alive = False
            else:
                self.hp_cur -= value

    def heal(self, value: int) -> None:
        """治疗：不超过最大 HP；受损模式下向 0 恢复。"""
        if self.is_record_normal():
            if self.hp_max == 0:
                self.hp_cur += value
            else:
                self.hp_cur = min(self.hp_max, self.hp_cur + value)
        else:
            self.hp_cur = min(0, self.hp_cur + value)
        self.is_alive = True

    def long_rest(self) -> str:
        """长休：恢复 HP 至上限、清除临时 HP、回复一半生命骰（至少 1）。"""
        info = ""
        if self.hp_max != 0:
            info = f"生命值回复至上限({self.hp_max})"
            self.hp_cur = self.hp_max
        if self.hp_temp != 0:
            info += f" {self.hp_temp}点临时生命值失效"
            self.hp_temp = 0
        if self.hp_dice_max != 0 and self.hp_dice_type != 0:
            prev_num = self.hp_dice_num
            self.hp_dice_num = int(max(1, min(
                self.hp_dice_max,
                self.hp_dice_num + self.hp_dice_max // 2
            )))
            info += f"\n回复{self.hp_dice_num - prev_num}个生命骰, "
            info += f"当前拥有{self.hp_dice_num}/{self.hp_dice_max}个D{self.hp_dice_type}生命骰"
        return info.strip()

    def get_info(self) -> str:
        """HP 摘要，如 ``HP:5/10 (4)`` 或 ``损失HP:3``。"""
        temp_info = f" ({self.hp_temp})" if self.hp_temp != 0 else ""
        if self.is_record_normal():
            max_info = f"/{self.hp_max}" if self.hp_max != 0 else ""
            info = f"HP:{self.hp_cur}{max_info}{temp_info}"
            if not self.is_alive:
                info += " 昏迷"
        else:
            info = f"损失HP:{-self.hp_cur}{temp_info}"
        return info

    def get_char_info(self) -> str:
        """角色卡段落，如 ``$生命值$ 5/10 (4)``。"""
        if not self.is_init:
            return ""
        info = f"{CHAR_INFO_KEY_HP} {self.hp_cur}"
        if self.hp_max > 0:
            info += f"/{self.hp_max}"
        if self.hp_temp > 0:
            info += f" ({self.hp_temp})"
        if self.hp_dice_type > 0:
            info += f"\n{CHAR_INFO_KEY_HP_DICE} {self.hp_dice_num}/{self.hp_dice_max} D{self.hp_dice_type}"
        return info


class AbilityInfo(BaseModel):
    """属性与检定信息。

    - ``ability``：六属性原始值（力量~魅力）；
    - ``check_prof``：每个检定条目的熟练系数（0=未熟练，1=熟练，2=双倍熟练……）；
    - ``check_ext``：每个检定条目的额外加值表达式片段（可含全局豁免键）；
    - ``check_adv``：每个条目自带优劣势（1 优势 / -1 劣势 / 0 无）。
    """

    is_init: bool = False
    version: int = 1
    level: int = 0
    ability: List[int] = Field(default_factory=lambda: [0] * ABILITY_NUM)
    check_prof: List[int] = Field(default_factory=lambda: [0] * len(CHECK_ITEM_LIST))
    check_ext: List[str] = Field(default_factory=lambda: [""] * len(EXT_ITEM_LIST))
    check_adv: List[int] = Field(default_factory=lambda: [0] * len(EXT_ITEM_LIST))

    def get_prof_bonus(self) -> int:
        """熟练加值：2 + (等级-1)//4（5e 规则）。"""
        return 2 + (self.level - 1) // 4

    def get_modifier(self, ability_index: int) -> int:
        """属性调整值：(值-10)//2（5e 向下取整）。"""
        return (self.ability[ability_index] - 10) // 2

    def get_char_info(self) -> str:
        """角色卡属性段落（可直接复制再记录，用于自行保存多卡）。"""
        info = f"{CHAR_INFO_KEY_LEVEL} {self.level}\n"
        info += f"{CHAR_INFO_KEY_ABILITY} {'/'.join(str(v) for v in self.ability)}\n"

        prof_parts = []
        for index, scale in enumerate(self.check_prof):
            if scale <= 0:
                continue
            name = CHECK_ITEM_LIST[index]
            prof_parts.append(name if scale == 1 else f"{scale}*{name}")
        if prof_parts:
            info += f"{CHAR_INFO_KEY_PROF} {'/'.join(prof_parts)}\n"

        adv_dict = {
            EXT_ITEM_LIST[i]: flag
            for i, flag in enumerate(self.check_adv) if flag != 0
        }
        ext_parts = []
        for index, ext_str in enumerate(self.check_ext):
            if not ext_str:
                continue
            name = EXT_ITEM_LIST[index]
            prefix = ""
            if name in adv_dict:
                prefix = "优势" if adv_dict[name] > 0 else "劣势"
            ext_parts.append(f"{name}:{prefix}{ext_str}")
        if ext_parts:
            info += f"{CHAR_INFO_KEY_EXT} {'/'.join(ext_parts)}\n"

        return info.strip()


class WeaponInfo(BaseModel):
    """自定义武器/法术项（玩家自行填写，机器人不做规则判断）。

    录入格式与展示格式一致（可复制回 ``$武器$`` 段）：
    ``名称±命中加值,伤害表达式+类型``，如 ``短剑+6,1d4+4穿刺``；
    名称尾部 ``x`` 为「不可攻击检定」标记（如 ``火球术x,8d6火焰``）。
    解析与校验见 ``character/services.py`` 的 ``parse_weapon_item``。
    """

    name: str                 # 武器/法术名（卡内唯一，命令匹配用）
    attack_bonus: str = ""    # 命中加值表达式片段（如 "+6"；空 = 不加）
    damage_expr: str = ""     # 伤害表达式（骰子与常数的加减组合，如 "1d4+4"）
    damage_type: str = ""     # 伤害类型（规范名，如 "穿刺"；空 = 不提示类型）
    no_attack: bool = False   # x 标记：不可进行攻击检定（纯伤害法术，如 火球术）

    def get_info(self) -> str:
        """展示/回写文本，如 ``短剑+6,1d4+4穿刺``、``火球术x,8d6火焰``。"""
        mark = "x" if self.no_attack else ""
        text = f"{self.name}{mark}{self.attack_bonus},{self.damage_expr}"
        if self.damage_type:
            text += self.damage_type
        return text


class NPCHealth(BaseModel):
    """NPC/怪物血量条目（群级、按名称索引）。

    名称即主键（同一群内 NPC 名唯一），血量复用 HPInfo（与 PC 同款结构）。
    条目在 ``.hp 目标 ...`` 且目标经先攻表解析时按需创建——即 NPC 需先
    ``.ri`` 入先攻表（或已存在血量记录）。

    ``persistent``：血量跨战斗保持（``.npc 持久`` 设置）——``.ri`` 再次以
    新条目入先攻表时不自动回满；默认 False 时每次新入表都会回满（同名条目
    在同一场战斗中重掷不触发，见 commands/initiative.py）。
    """

    group_id: str
    name: str
    hp_info: HPInfo = Field(default_factory=HPInfo)
    persistent: bool = False


class DNDCharacter(BaseModel):
    """DND5e 角色卡（每人在每群一张，键 = 群 + QQ）。"""

    group_id: str
    user_id: str
    name: str = ""
    race: str = ""        # 种族（$种族$；本批次仅记录展示）
    char_class: str = ""  # 职业（$职业$；12 职业规范名之一，偷袭骰计算依据）
    subclass: str = ""    # 子职（$子职$；本批次仅记录展示）
    hp_info: HPInfo = Field(default_factory=HPInfo)
    ability_info: AbilityInfo = Field(default_factory=AbilityInfo)
    weapons: List[WeaponInfo] = Field(default_factory=list)  # 自定义武器/法术项
    is_init: bool = False

    def get_char_info(self) -> str:
        """完整角色卡文本（$xxx$ 段落格式，可再次 .角色卡记录）。"""
        parts = []
        if self.name:
            parts.append(f"{CHAR_INFO_KEY_NAME} {self.name}")
        if self.race:
            parts.append(f"{CHAR_INFO_KEY_RACE} {self.race}")
        if self.char_class:
            parts.append(f"{CHAR_INFO_KEY_CLASS} {self.char_class}")
        if self.subclass:
            parts.append(f"{CHAR_INFO_KEY_SUBCLASS} {self.subclass}")
        hp_part = self.hp_info.get_char_info()
        if hp_part:
            parts.append(hp_part)
        ability_part = self.ability_info.get_char_info()
        if ability_part:
            parts.append(ability_part)
        if self.weapons:
            weapon_str = "/".join(weapon.get_info() for weapon in self.weapons)
            parts.append(f"{CHAR_INFO_KEY_WEAPON} {weapon_str}")
        return "\n".join(parts)
