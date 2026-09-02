"""DND5e 角色数据模型（Pydantic，纯数据与基础展示方法）。

字段与计算语义对齐 nonebot-dicepp（core/data/models/character.py，参考实现）；
存储/检定等复杂业务见 data/characters.py 与 character/services.py。

一期范围：角色卡记录/查看/状态与检定所需字段；生命骰消耗、伤害/治疗、长休等
行为逻辑在 T1「HP 管理」模块落地时补充（本模型字段已预留）。
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .constants import (
    ABILITY_NUM,
    CHECK_ITEM_INDEX_DICT,
    CHECK_ITEM_LIST,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_EXT,
    CHAR_INFO_KEY_HP,
    CHAR_INFO_KEY_HP_DICE,
    CHAR_INFO_KEY_LEVEL,
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_PROF,
    EXT_ITEM_INDEX_DICT,
    EXT_ITEM_LIST,
)


class HPInfo(BaseModel):
    """生命值信息（字段兼容 DicePP；行为逻辑 T1 补全）。"""

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

    def get_info(self) -> str:
        """HP 摘要，如 ``HP:5/10 (4)``。"""
        temp_info = f" ({self.hp_temp})" if self.hp_temp != 0 else ""
        if self.is_init:
            max_info = f"/{self.hp_max}" if self.hp_max != 0 else ""
            info = f"HP:{self.hp_cur}{max_info}{temp_info}"
            if not self.is_alive:
                info += " 昏迷"
            return info
        return ""

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
    - ``check_ext``：每个检定条目的额外加值表达式片段（可含全局豁免/攻击键）；
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


class DNDCharacter(BaseModel):
    """DND5e 角色卡（每人在每群一张，键 = 群 + QQ）。"""

    group_id: str
    user_id: str
    name: str = ""
    hp_info: HPInfo = Field(default_factory=HPInfo)
    ability_info: AbilityInfo = Field(default_factory=AbilityInfo)
    is_init: bool = False

    def get_char_info(self) -> str:
        """完整角色卡文本（$xxx$ 段落格式，可再次 .角色卡记录）。"""
        parts = []
        if self.name:
            parts.append(f"{CHAR_INFO_KEY_NAME} {self.name}")
        hp_part = self.hp_info.get_char_info()
        if hp_part:
            parts.append(hp_part)
        ability_part = self.ability_info.get_char_info()
        if ability_part:
            parts.append(ability_part)
        return "\n".join(parts)
