"""DND5e 角色卡/检定词汇表与索引常量。

词汇与索引结构——六属性 / 18 技能（DND5e 官方技能表，其中「先攻」归入敏捷
技能组）/ 六豁免，全部汇入统一的「检定条目表」，并附技能→属性、同义词映射；
新增条目只改此处（声明式建模，T3 友好）。

2026-09-24 起属性攻击条目（力量攻击 等）退役：攻击检定统一走角色卡
``$武器$`` 项（见 ``character/services.py`` 的武器解析与 ``commands/weapon.py``），
检定点命令只保留属性/技能/豁免。
"""

# ── 六属性 ──────────────────────────────────────────────────────────────
ABILITY_LIST = ["力量", "敏捷", "体质", "智力", "感知", "魅力"]
ABILITY_NUM = len(ABILITY_LIST)

# ── 技能（DND5e 18 技能；「先攻」归入敏捷组）────────────────────────────
SKILL_LIST = [
    # 力量
    "运动",
    # 敏捷
    "体操", "巧手", "隐匿", "先攻",
    # 智力
    "奥秘", "历史", "调查", "自然", "宗教",
    # 感知
    "驯兽", "洞悉", "医药", "察觉", "求生",
    # 魅力
    "欺瞒", "威吓", "表演", "游说",
]
SKILL_NUM = len(SKILL_LIST)

#: 技能 → 关联属性
SKILL_PARENT_DICT = {
    "运动": "力量",
    "体操": "敏捷", "巧手": "敏捷", "隐匿": "敏捷", "先攻": "敏捷",
    "奥秘": "智力", "历史": "智力", "调查": "智力", "自然": "智力", "宗教": "智力",
    "驯兽": "感知", "洞悉": "感知", "医药": "感知", "察觉": "感知", "求生": "感知",
    "欺瞒": "魅力", "威吓": "魅力", "表演": "魅力", "游说": "魅力",
}

#: 技能/属性常见中文别名（避免玩家用词差异）
SKILL_SYNONYM_DICT = {
    "特技": "体操", "妙手": "巧手", 
    "潜行": "隐匿", "隐蔽": "隐匿",
    "隐秘": "隐匿", "躲藏": "隐匿",
    "驯养": "驯兽", "驯服": "驯兽",
    "医疗": "医药", "医术": "医药",
    "观察": "察觉", "生存": "求生",
    "欺骗": "欺瞒", "欺诈": "欺瞒", 
    "哄骗": "欺瞒", "唬骗": "欺瞒",
    "威胁": "威吓", "说服": "游说",
}

# ── 豁免（按属性派生）───────────────────────────────────────────────────
SAVING_LIST = ["力量豁免", "敏捷豁免", "体质豁免", "智力豁免", "感知豁免", "魅力豁免"]
SAVING_PARENT_DICT = {
    "力量豁免": "力量", "敏捷豁免": "敏捷", "体质豁免": "体质",
    "智力豁免": "智力", "感知豁免": "感知", "魅力豁免": "魅力",
}

# ── 统一检定条目表（属性 + 技能 + 豁免）─────────────────────────────────
CHECK_ITEM_LIST = ABILITY_LIST + SKILL_LIST + SAVING_LIST
CHECK_ITEM_INDEX_DICT = {name: i for i, name in enumerate(CHECK_ITEM_LIST)}

#: 全局附加加值键：作用于所有豁免
SAVING_ALL_KEY = "豁免"
EXT_ITEM_LIST = CHECK_ITEM_LIST + [SAVING_ALL_KEY]
EXT_ITEM_INDEX_DICT = {name: i for i, name in enumerate(EXT_ITEM_LIST)}

# ── 职业与伤害类型（自定义武器/偷袭计算用，2026-09-24 新增）─────────────
#: DND5e 12 职业（2024 译名，偷袭计算只认游荡者）
CLASS_LIST = [
    "野蛮人", "吟游诗人", "牧师", "德鲁伊", "战士", "武僧",
    "圣武士", "游侠", "游荡者", "术士", "魔契师", "法师",
]
#: 职业最小异译容错
CLASS_SYNONYM_DICT = {
    "盗贼": "游荡者",
}
#: 偷袭骰的职业判定名（角色卡职业为此职业时按等级自动计算偷袭骰）
SNEAK_ATTACK_CLASS = "游荡者"

#: 伤害类型 13 种（2024/2014 译名一致）
DAMAGE_TYPE_LIST = [
    "强酸", "钝击", "寒冷", "火焰", "力场", "闪电", "暗蚀",
    "穿刺", "毒素", "心灵", "光耀", "挥砍", "雷鸣",
]
#: 伤害类型异译容错（仅「斩击」→「挥砍」）
DAMAGE_TYPE_SYNONYM_DICT = {
    "斩击": "挥砍",
}

#: 自定义武器项限制（武器 ≤20 件、名称 ≤20 字）
WEAPON_MAX_COUNT = 20
WEAPON_NAME_MAX_LEN = 20
#: 武器名禁含字样（与命令切分、检定点命令歧义）
WEAPON_NAME_FORBIDDEN_WORDS = ("攻击", "命中", "伤害", "检定", "豁免")
#: 武器名禁含符号（与段分隔符、表达式片段冲突）
WEAPON_NAME_FORBIDDEN_CHARS = ("/", ",", "，", "$", "+", "-")
#: 伤害命令支持的后缀（写在「伤害」之前、可任意组合）
WEAPON_DAMAGE_SUFFIX_LIST = ("副手", "重击", "偷袭")

# ── 角色卡关键字（$xxx$ 模板段落）────────────────────────────────────────
CHAR_INFO_KEY_NAME = "$姓名$"
CHAR_INFO_KEY_RACE = "$种族$"
CHAR_INFO_KEY_CLASS = "$职业$"
CHAR_INFO_KEY_SUBCLASS = "$子职$"
CHAR_INFO_KEY_LEVEL = "$等级$"
CHAR_INFO_KEY_HP = "$生命值$"
CHAR_INFO_KEY_HP_DICE = "$生命骰$"
CHAR_INFO_KEY_ABILITY = "$属性$"
CHAR_INFO_KEY_PROF = "$熟练$"
CHAR_INFO_KEY_EXT = "$额外加值$"
CHAR_INFO_KEY_WEAPON = "$武器$"
CHAR_INFO_KEY_LIST = [
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_RACE,
    CHAR_INFO_KEY_CLASS,
    CHAR_INFO_KEY_SUBCLASS,
    CHAR_INFO_KEY_LEVEL,
    CHAR_INFO_KEY_HP,
    CHAR_INFO_KEY_HP_DICE,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_PROF,
    CHAR_INFO_KEY_EXT,
    CHAR_INFO_KEY_WEAPON,
]
