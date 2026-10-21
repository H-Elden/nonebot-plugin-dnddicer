"""DND5e 角色数据模型（Pydantic，纯数据与基础展示方法）。

存储/检定等复杂业务见 data/characters.py 与 character/services.py。
"""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field

from .constants import (
    ABILITY_LIST,
    ABILITY_NUM,
    BACKGROUND_KEY_LIST,
    CHECK_ITEM_INDEX_DICT,
    CHECK_ITEM_LIST,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_ABILITY_DISPLAY,
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
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_PROF,
    CHAR_INFO_KEY_PROGRESS,
    CHAR_INFO_KEY_RACE,
    CHAR_INFO_KEY_SAVES,
    CHAR_INFO_KEY_SKILLS,
    CHAR_INFO_KEY_SPELL,
    CHAR_INFO_KEY_SPELL_SLOTS,
    CHAR_INFO_KEY_STORY,
    CHAR_INFO_KEY_SUBCLASS,
    CHAR_INFO_KEY_TRAITS,
    CHAR_INFO_KEY_WEAPON,
    COIN_KEY_LIST,
    COMBAT_KEY_LIST,
    EXT_ITEM_INDEX_DICT,
    EXT_ITEM_LIST,
    PROFICIENCY_GROUP_LIST,
    SKILL_LIST,
    SPELL_LEVEL_MAX,
)


class HPInfo(BaseModel):
    """生命值信息（当前/最大/临时 HP、生命骰与死亡豁免）。

    昏迷语义沿用 ``is_alive``：``False`` = HP 归 0 后昏迷。死亡豁免四字段
    （``ds_success`` / ``ds_failure`` / ``is_stable`` / ``is_dead``）在
    2026-10-01 加入，均有默认值——旧存档缺字段时按默认值读入，无需迁移。

    ``death_saves`` 区分「玩家角色卡」与「NPC 血量」：只有玩家走死亡豁免流程
    （濒死计数、稳定、死亡），NPC 的 0 HP 就是昏迷/倒下。NPC 血量条目
    （``NPCHealth``）用 ``npc_hp_info()`` 建默认值关掉它，怪物卡上便不会出现
    死亡豁免字样，也不会进濒死判定。
    """

    is_init: bool = False
    is_alive: bool = True
    hp_cur: int = 0       # 当前生命值
    hp_max: int = 0       # 最大生命值
    hp_temp: int = 0      # 临时生命值
    hp_dice_type: int = 0  # 生命骰面数
    hp_dice_num: int = 0   # 当前生命骰数量
    hp_dice_max: int = 0   # 生命骰最大数量
    ds_success: int = 0    # 死亡豁免成功次数（0~3）
    ds_failure: int = 0    # 死亡豁免失败次数（0~3）
    is_stable: bool = False  # 伤势已稳定（稳定后不再需要掷豁免）
    is_dead: bool = False    # 已死亡（治疗不自动复活，需 .死亡豁免 重置）
    death_saves: bool = True  # 是否适用死亡豁免（NPC 血量条目为 False）

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
        self.clear_death_state()

    def clear_death_state(self, *, revive: bool = True) -> None:
        """清除死亡豁免进度（成功/失败计数与稳定标记）。

        ``revive=True``（默认）连死亡标记一起清掉——用于重设角色卡、
        ``.死亡豁免 重置`` 与治疗回正；``revive=False`` 只清计数，
        用于「重新开始死亡豁免」（稳定中再受伤、或死亡已裁决后重新开始）。
        """
        self.ds_success = 0
        self.ds_failure = 0
        self.is_stable = False
        if revive:
            self.is_dead = False

    def is_dying(self) -> bool:
        """是否处于濒死（HP 归 0、昏迷、未稳定、未死亡）。

        只看 ``hp_cur``（而不是 ``is_alive``）：未设上限的「损失记录」模式下
        HP 会记成负数，同样属于濒死，不该因为标记位不同而漏判。NPC 血量
        （``death_saves=False``）不适用死亡豁免，一律返回 False。
        """
        return (
            self.death_saves
            and self.is_init
            and self.hp_cur <= 0
            and not self.is_stable
            and not self.is_dead
        )

    def add_death_success(self, count: int = 1) -> bool:
        """记成功 N 次；到达 3 次即伤势稳定、计数清零，返回是否刚转为稳定。"""
        if self.is_dead:
            return False
        self.ds_success += count
        if self.ds_success >= 3:
            self.is_stable = True
            self.ds_success = 0
            self.ds_failure = 0
            return True
        return False

    def add_death_failure(self, count: int = 1) -> bool:
        """记失败 N 次；到达 3 次即死亡，返回是否刚死亡。"""
        if self.is_dead:
            return False
        self.ds_failure += count
        if self.ds_failure >= 3:
            self.is_stable = False
            self.is_dead = True
            return True
        return False

    def revive_with_hp(self, value: int) -> None:
        """治疗回正：HP 至少 1 点并清除全部死亡豁免状态（死亡的卡不复活）。"""
        if self.is_dead:
            return
        self.hp_cur = max(1, value)
        self.is_alive = True
        self.clear_death_state()

    def get_death_info(self) -> str:
        """死亡豁免摘要，如 ``濒死(成功1 失败2)`` / ``伤势稳定`` / ``已死亡``。

        未进入濒死流程（HP 大于 0、角色卡未初始化、或不适用死亡豁免的 NPC
        血量）时返回空串。
        """
        if not self.death_saves or not self.is_init or self.hp_cur > 0:
            return ""
        if self.is_dead:
            return "已死亡"
        if self.is_stable:
            return "伤势稳定"
        return f"濒死(成功{self.ds_success} 失败{self.ds_failure})"

    def is_record_normal(self) -> bool:
        """当前是否正常记录生命值（拥有 HP 值，而非单纯记录受损）。"""
        return self.hp_cur > 0 or (self.hp_cur == 0 and not self.is_alive)

    def is_record_damage(self) -> bool:
        """当前是否是记录受损生命值的情况。"""
        return not self.is_record_normal()

    def take_damage(self, value: int) -> None:
        """受到伤害：临时 HP 先吸收，溢出扣当前 HP，降至 0 即昏迷。

        只做数值结算；死亡豁免（濒死进入、受击记失败、即死）见
        ``character.services.HPService.*death*``——NPC 血量也用本方法，
        不应被玩家角色的濒死流程影响。
        """
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
        """治疗：不超过最大 HP；受损模式下向 0 恢复；HP 回正即清除死亡豁免状态。

        已死亡（``is_dead``）的卡不复活（提示用 ``.死亡豁免 重置``）——
        否则「给尸体加血」会让人直接站起来。
        """
        if self.is_dead:
            return
        if self.is_record_normal():
            if self.hp_max == 0:
                self.hp_cur += value
            else:
                self.hp_cur = min(self.hp_max, self.hp_cur + value)
        else:
            self.hp_cur = min(0, self.hp_cur + value)
        self.is_alive = True
        self.clear_death_state()

    def long_rest(self, *, dice_full: bool = False) -> str:
        """长休：恢复 HP 至上限、清除临时 HP、恢复生命骰、清死亡豁免状态。

        ``dice_full=True`` 恢复**全部**已消耗生命骰（2024 口径）；默认
        ``False`` 回复总枚数的一半（至少 1 枚，2014 口径）——两版差异由
        调用方按群级规则版本传入，模型自己不读配置。
        生命骰恢复量按卡面 ``$生命骰$`` 的录入值计算，不按职业/等级推导。
        """
        info = ""
        if self.hp_max != 0:
            info = f"生命值回复至上限({self.hp_max})"
            self.hp_cur = self.hp_max
        if self.hp_temp != 0:
            info += f" {self.hp_temp}点临时生命值失效"
            self.hp_temp = 0
        if self.hp_dice_max != 0 and self.hp_dice_type != 0:
            prev_num = self.hp_dice_num
            if dice_full:
                self.hp_dice_num = self.hp_dice_max
            else:
                self.hp_dice_num = int(max(1, min(
                    self.hp_dice_max,
                    self.hp_dice_num + self.hp_dice_max // 2
                )))
            info += f"\n回复{self.hp_dice_num - prev_num}个生命骰, "
            info += f"当前拥有{self.hp_dice_num}/{self.hp_dice_max}个D{self.hp_dice_type}生命骰"
        # 长休使 HP 回满：濒死与死亡豁免进度一并结束、昏迷解除
        self.is_alive = True
        self.clear_death_state()
        return info.strip()

    def get_info(self) -> str:
        """HP 摘要，如 ``HP:5/10 (4)``、``HP:0/10 昏迷 濒死(成功1 失败0)``。"""
        temp_info = f" ({self.hp_temp})" if self.hp_temp != 0 else ""
        if self.is_record_normal():
            max_info = f"/{self.hp_max}" if self.hp_max != 0 else ""
            info = f"HP:{self.hp_cur}{max_info}{temp_info}"
            if not self.is_alive:
                info += " 昏迷"
            death_info = self.get_death_info()
            if death_info:
                info += f" {death_info}"
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


def npc_hp_info() -> HPInfo:
    """NPC 血量条目的默认 HP 信息（关闭死亡豁免流程）。

    怪物只有「活着 / 打到 0 就倒下」，没有死亡豁免计数与稳定状态；
    ``NPCHealth.hp_info`` 的默认值用它，PC 角色卡仍用 ``HPInfo()`` 默认值。
    """
    return HPInfo(death_saves=False)


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
    #: ``$熟练$`` 扩展分组（护甲/武器/工具/语言），仅展示，不参与检定计算
    prof_armor: List[str] = Field(default_factory=list)
    prof_weapons: List[str] = Field(default_factory=list)
    prof_tools: List[str] = Field(default_factory=list)
    prof_languages: List[str] = Field(default_factory=list)

    def get_prof_groups(self) -> List[tuple[str, List[str]]]:
        """返回 ``[(分组名, 条目列表), ...]``（只含有内容的分组，固定顺序）。"""
        mapping = {
            "护甲": self.prof_armor,
            "武器": self.prof_weapons,
            "工具": self.prof_tools,
            "语言": self.prof_languages,
        }
        return [
            (label, mapping[label])
            for label in PROFICIENCY_GROUP_LIST
            if mapping[label]
        ]

    def get_prof_bonus(self) -> int:
        """熟练加值：2 + (等级-1)//4（5e 规则）。"""
        return 2 + (self.level - 1) // 4

    def get_modifier(self, ability_index: int) -> int:
        """属性调整值：(值-10)//2（5e 向下取整）。"""
        return (self.ability[ability_index] - 10) // 2

    def get_level_ability_info(self) -> str:
        """``$等级$`` 与 ``$属性$`` 两行（完整卡面插入新段时先输出这两行）。"""
        return (
            f"{CHAR_INFO_KEY_LEVEL} {self.level}\n"
            f"{CHAR_INFO_KEY_ABILITY} {'/'.join(str(v) for v in self.ability)}"
        )

    def get_prof_info(self) -> str:
        """``$熟练$`` 与 ``$额外加值$`` 两行（无内容时为空串）。"""
        info = ""
        prof_parts = []
        for index, scale in enumerate(self.check_prof):
            if scale <= 0:
                continue
            name = CHECK_ITEM_LIST[index]
            prof_parts.append(name if scale == 1 else f"{scale}*{name}")
        # $熟练$ 的扩展分组与技能/豁免条目共用同一段：条目在前，分组在后
        prof_parts.extend(
            f"{label}:{'·'.join(items)}" for label, items in self.get_prof_groups()
        )
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

    def get_char_info(self) -> str:
        """角色卡属性段落（可直接复制再记录，用于自行保存多卡）。"""
        return "\n".join(
            part for part in (self.get_level_ability_info(), self.get_prof_info()) if part
        )


class WeaponInfo(BaseModel):
    """自定义武器/法术项（玩家自行填写，机器人不做规则判断）。

    录入格式与展示格式一致（可复制回 ``$武器$`` 段）：
    ``名称±命中加值,伤害表达式+类型``，如 ``短剑+6,1d4+4穿刺``；
    名称尾部 ``x`` 为「不可攻击检定」标记（如 ``火球术x,8d6火焰``）；
    第三个逗号字段为卡面备注（2026-10-21 批②），如 ``匕首+5,1d4+2穿刺,灵巧·轻型``。
    解析与校验见 ``character/services.py`` 的 ``parse_weapon_item``。
    """

    name: str                 # 武器/法术名（卡内唯一，命令匹配用）
    attack_bonus: str = ""    # 命中加值表达式片段（如 "+6"；空 = 不加）
    damage_expr: str = ""     # 伤害表达式（骰子与常数的加减组合，如 "1d4+4"）
    damage_type: str = ""     # 伤害类型（规范名，如 "穿刺"；空 = 不提示类型）
    no_attack: bool = False   # x 标记：不可进行攻击检定（纯伤害法术，如 火球术）
    note: str = ""            # 卡面备注（如 "灵巧·轻型"；空 = 不显示）

    def get_info(self) -> str:
        """展示/回写文本，如 ``短剑+6,1d4+4穿刺``、``匕首+5,1d4+2穿刺,灵巧·轻型``。"""
        mark = "x" if self.no_attack else ""
        text = f"{self.name}{mark}{self.attack_bonus},{self.damage_expr}"
        if self.damage_type:
            text += self.damage_type
        if self.note:
            text += f",{self.note}"
        return text


class CharacterFeature(BaseModel):
    """有使用次数的能力（``$能力$`` 段，2026-10-20 批②新增）。

    录入与展示格式一致（可复制回 ``$能力$``）：
    ``名称:当前/上限恢复档``，如 ``引导神力:2/2短休+1,长休``；
    末尾可加 ``|说明``（2026-10-21 批②，卡面只展示、不参与结算）。
    ``recover`` 为规范化后的恢复档串（``短休`` / ``长休`` / ``两者`` / ``手动``，
    可带 ``+N``），解析与校验见 ``character/services.py`` 的
    ``parse_feature_item``；恢复量在休息结算时读取（后续批次接入）。
    """

    name: str
    uses_cur: int = 0
    uses_max: int = 0
    recover: str = "手动"
    text: str = ""  # 卡面说明（如 "短休时回复一个已消耗的法术位"）

    def get_info(self) -> str:
        """展示/回写文本，如 ``引导神力:2/2短休+1,长休``、``奥术回想:1/1短休|短休时…``。"""
        text = f"{self.name}:{self.uses_cur}/{self.uses_max}{self.recover}"
        if self.text:
            text += f"|{self.text}"
        return text

    def get_recover_display(self) -> str:
        """恢复档的中文展示（逗号转全角），如 ``短休+1，长休``。"""
        return self.recover.replace(",", "，")


class SpellEntry(BaseModel):
    """已知/准备法术条目（``$法术$`` 段，2026-10-20 批②新增）。

    ``level`` 0 = 戏法（不消耗法术位、无需准备）；``prepared`` 是「今日已准备」
    标记（卡面写 ``*``），只由 ``.法术 准备/取消`` 切换，长休只做提醒、不自动改。

    卡面展示用的五项元数据与备注（2026-10-21 批②）：
    ``cast_time`` / ``range`` / ``concentration`` / ``ritual`` / ``material`` /
    ``note``，写在条目末尾的 ``|`` 之后（``时间=1动作,距离=150尺,专注=是``），
    只用于渲染卡面图，不参与施法与结算。
    """

    name: str
    level: int = 0
    prepared: bool = False
    cast_time: str = ""       # 施法时间（如 "1动作"）
    range: str = ""           # 施法距离（如 "150尺"、"自身"）
    concentration: bool = False  # 专注
    ritual: bool = False         # 仪式
    material: bool = False       # 材料
    note: str = ""               # 备注（如 "8d6 火焰 / 敏捷"）

    def get_detail_text(self) -> str:
        """详情的回写片段（只输出已填项，固定键序）。"""
        parts: List[str] = []
        if self.cast_time:
            parts.append(f"时间={self.cast_time}")
        if self.range:
            parts.append(f"距离={self.range}")
        if self.concentration:
            parts.append("专注=是")
        if self.ritual:
            parts.append("仪式=是")
        if self.material:
            parts.append("材料=是")
        if self.note:
            parts.append(f"备注={self.note}")
        return ",".join(parts)

    def get_info(self) -> str:
        """展示/回写文本，如 ``火球术:3*|时间=1动作,距离=150尺,材料=是``。"""
        mark = "*" if self.prepared else ""
        text = f"{self.name}:{self.level}{mark}"
        detail = self.get_detail_text()
        if detail:
            text += f"|{detail}"
        return text

    def get_level_label(self) -> str:
        """环阶展示：``戏法`` 或 ``3环``。"""
        return "戏法" if self.level == 0 else f"{self.level}环"


class SpellSlots(BaseModel):
    """各环法术位与契约魔法（``$法术位$`` 段，2026-10-20 批②新增）。

    ``slots_cur`` / ``slots_max`` 下标 0~8 对应 1~9 环；``pact_*`` 是契约魔法
    （魔契师）的单列法术位：``pact_level`` 为其环阶，0 表示未记录。
    """

    slots_cur: List[int] = Field(default_factory=lambda: [0] * SPELL_LEVEL_MAX)
    slots_max: List[int] = Field(default_factory=lambda: [0] * SPELL_LEVEL_MAX)
    pact_level: int = 0
    pact_cur: int = 0
    pact_max: int = 0

    def is_empty(self) -> bool:
        """是否没有任何法术位记录。"""
        return not any(self.slots_max) and self.pact_max == 0

    def get_char_info(self) -> str:
        """角色卡段落，如 ``$法术位$ 1:4/4; 2:3/3; 契约3:2/2``。"""
        parts: List[str] = []
        for level in range(1, SPELL_LEVEL_MAX + 1):
            index = level - 1
            if self.slots_max[index] <= 0:
                continue
            parts.append(
                f"{level}:{self.slots_cur[index]}/{self.slots_max[index]}"
            )
        if self.pact_max > 0:
            parts.append(
                f"契约{self.pact_level}:{self.pact_cur}/{self.pact_max}"
            )
        if not parts:
            return ""
        return f"{CHAR_INFO_KEY_SPELL_SLOTS} {'; '.join(parts)}"


class NPCHealth(BaseModel):
    """NPC/怪物血量条目（群级、按名称索引）。

    名称即主键（同一群内 NPC 名唯一），血量复用 HPInfo（与 PC 同款结构，
    但 ``death_saves=False``：怪物不做死亡豁免，0 HP 即昏迷/倒下）。
    条目在 ``.hp 目标 ...`` 且目标经先攻表解析时按需创建——即 NPC 需先
    ``.ri`` 入先攻表（或已存在血量记录）。

    ``persistent``：血量跨战斗保持（``.npc 持久`` 设置）——``.ri`` 再次以
    新条目入先攻表时不自动回满；默认 False 时每次新入表都会回满（同名条目
    在同一场战斗中重掷不触发，见 commands/initiative.py）。
    """

    group_id: str
    name: str
    hp_info: HPInfo = Field(default_factory=npc_hp_info)
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
    features: List[CharacterFeature] = Field(default_factory=list)  # 有次数的能力
    spells: List[SpellEntry] = Field(default_factory=list)  # 已知/准备法术
    spell_slots: SpellSlots = Field(default_factory=SpellSlots)  # 各环与契约法术位
    spellcasting_ability: str = ""  # 施法属性（六属性名；空 = 未填写）
    #: 立绘相对文件名（如 ``portraits/<群>_<QQ>.png``；空 = 未设置）
    portrait: str = ""
    # 完整卡面扩展（2026-10-21；全部有默认值，旧卡零迁移）
    ability_display: Dict[str, str] = Field(default_factory=dict)  # $属性值$
    combat: Dict[str, str] = Field(default_factory=dict)  # $战斗$
    saves: Dict[str, str] = Field(default_factory=dict)  # $豁免$
    skills: Dict[str, str] = Field(default_factory=dict)  # $技能$
    feats: List[str] = Field(default_factory=list)  # $专长$
    traits: List[str] = Field(default_factory=list)  # $特性$
    items: List[str] = Field(default_factory=list)  # $物品$
    background: Dict[str, str] = Field(default_factory=dict)  # $背景$
    combat_notes: List[str] = Field(default_factory=list)  # $战斗记录$
    story: str = ""  # $故事$（长文本，卡面「背景故事」面板）
    progress: Dict[str, str] = Field(default_factory=dict)  # $进度$（经验/激励）
    coins: Dict[str, int] = Field(default_factory=dict)  # $钱币$（CP/SP/EP/GP/PP）
    spell_dc: str = ""  # 法术豁免 DC（$法术$ 头键）
    spell_attack: str = ""  # 法术攻击加值（$法术$ 头键）
    is_init: bool = False

    def _background_items(self) -> List[str]:
        """``$背景$`` 条目：常用键按固定顺序，未列出的键按录入顺序追加。"""
        items = [
            f"{key}:{self.background[key]}"
            for key in BACKGROUND_KEY_LIST
            if self.background.get(key)
        ]
        items.extend(
            f"{key}:{value}"
            for key, value in self.background.items()
            if key not in BACKGROUND_KEY_LIST and value
        )
        return items

    def _combat_items(self) -> List[str]:
        """``$战斗$`` 条目：固定顺序，仅输出已填项。"""
        return [
            f"{key}:{self.combat[key]}"
            for key in COMBAT_KEY_LIST
            if self.combat.get(key)
        ]

    def _ability_display_items(self) -> List[str]:
        """``$属性值$`` 条目：六属性固定顺序。"""
        return [
            f"{name}:{self.ability_display[name]}"
            for name in ABILITY_LIST
            if self.ability_display.get(name)
        ]

    def _save_items(self) -> List[str]:
        """``$豁免$`` 条目：六属性固定顺序。"""
        return [
            f"{name}:{self.saves[name]}"
            for name in ABILITY_LIST
            if self.saves.get(name)
        ]

    def _skill_items(self) -> List[str]:
        """``$技能$`` 条目：技能表固定顺序。"""
        return [
            f"{name}:{self.skills[name]}"
            for name in SKILL_LIST
            if self.skills.get(name)
        ]

    def get_char_info(self) -> str:
        """完整角色卡文本（$xxx$ 段落格式，可再次 .角色卡记录）。

        段顺序：身份 → 数值 → 能力 → 装备 → 法术（新增段只插在各自的
        逻辑位置，既有段的先后保持不变，旧卡输出不受影响）。
        """
        parts = []
        if self.name:
            parts.append(f"{CHAR_INFO_KEY_NAME} {self.name}")
        if self.race:
            parts.append(f"{CHAR_INFO_KEY_RACE} {self.race}")
        if self.char_class:
            parts.append(f"{CHAR_INFO_KEY_CLASS} {self.char_class}")
        if self.subclass:
            parts.append(f"{CHAR_INFO_KEY_SUBCLASS} {self.subclass}")
        background_items = self._background_items()
        if background_items:
            parts.append(f"{CHAR_INFO_KEY_BACKGROUND} {'; '.join(background_items)}")
        if self.story:
            parts.append(f"{CHAR_INFO_KEY_STORY} {self.story}")
        hp_part = self.hp_info.get_char_info()
        if hp_part:
            parts.append(hp_part)
        combat_items = self._combat_items()
        if combat_items:
            parts.append(f"{CHAR_INFO_KEY_COMBAT} {'; '.join(combat_items)}")
        progress_items: List[str] = []
        if self.progress.get("经验"):
            progress_items.append(f"经验:{self.progress['经验']}")
        if self.progress.get("激励"):
            progress_items.append(f"激励:{self.progress['激励']}")
        if progress_items:
            parts.append(f"{CHAR_INFO_KEY_PROGRESS} {'; '.join(progress_items)}")
        level_ability_part = self.ability_info.get_level_ability_info()
        if level_ability_part:
            parts.append(level_ability_part)
        display_items = self._ability_display_items()
        if display_items:
            parts.append(
                f"{CHAR_INFO_KEY_ABILITY_DISPLAY} {'; '.join(display_items)}"
            )
        save_items = self._save_items()
        if save_items:
            parts.append(f"{CHAR_INFO_KEY_SAVES} {'; '.join(save_items)}")
        skill_items = self._skill_items()
        if skill_items:
            parts.append(f"{CHAR_INFO_KEY_SKILLS} {'; '.join(skill_items)}")
        prof_part = self.ability_info.get_prof_info()
        if prof_part:
            parts.append(prof_part)
        if self.feats:
            parts.append(f"{CHAR_INFO_KEY_FEATS} {'/'.join(self.feats)}")
        if self.traits:
            parts.append(f"{CHAR_INFO_KEY_TRAITS} {'/'.join(self.traits)}")
        if self.features:
            feature_str = "; ".join(feature.get_info() for feature in self.features)
            parts.append(f"{CHAR_INFO_KEY_FEATURE} {feature_str}")
        if self.weapons:
            weapon_str = "/".join(weapon.get_info() for weapon in self.weapons)
            parts.append(f"{CHAR_INFO_KEY_WEAPON} {weapon_str}")
        if self.items:
            parts.append(f"{CHAR_INFO_KEY_ITEMS} {'; '.join(self.items)}")
        if self.coins:
            coin_items = [
                f"{key}:{self.coins[key]}"
                for key in COIN_KEY_LIST
                if key in self.coins
            ]
            if coin_items:
                parts.append(f"{CHAR_INFO_KEY_COINS} {'; '.join(coin_items)}")
        spell_parts: List[str] = []
        if self.spellcasting_ability:
            spell_parts.append(f"施法属性:{self.spellcasting_ability}")
        if self.spell_dc:
            spell_parts.append(f"豁免DC:{self.spell_dc}")
        if self.spell_attack:
            spell_parts.append(f"法术攻击:{self.spell_attack}")
        spell_parts.extend(spell.get_info() for spell in self.spells)
        if spell_parts:
            parts.append(f"{CHAR_INFO_KEY_SPELL} {'; '.join(spell_parts)}")
        slots_part = self.spell_slots.get_char_info()
        if slots_part:
            parts.append(slots_part)
        if self.combat_notes:
            parts.append(
                f"{CHAR_INFO_KEY_COMBAT_NOTES} {'; '.join(self.combat_notes)}"
            )
        return "\n".join(parts)
