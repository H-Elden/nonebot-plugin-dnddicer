"""DND5e 角色卡/检定词汇表与索引常量。

词汇与索引结构——六属性 / 18 技能（DND5e 官方技能表，其中「先攻」归入敏捷
技能组）/ 六豁免 / 六攻击，全部汇入统一的「检定条目表」，并附技能→属性、
同义词映射；新增条目只改此处（声明式建模，T3 友好）。
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

# ── 豁免与攻击（按属性派生）──────────────────────────────────────────────
SAVING_LIST = ["力量豁免", "敏捷豁免", "体质豁免", "智力豁免", "感知豁免", "魅力豁免"]
SAVING_PARENT_DICT = {
    "力量豁免": "力量", "敏捷豁免": "敏捷", "体质豁免": "体质",
    "智力豁免": "智力", "感知豁免": "感知", "魅力豁免": "魅力",
}

ATTACK_LIST = ["力量攻击", "敏捷攻击", "体质攻击", "智力攻击", "感知攻击", "魅力攻击"]
ATTACK_PARENT_DICT = {
    "力量攻击": "力量", "敏捷攻击": "敏捷", "体质攻击": "体质",
    "智力攻击": "智力", "感知攻击": "感知", "魅力攻击": "魅力",
}

# ── 统一检定条目表（属性 + 技能 + 豁免 + 攻击）───────────────────────────
CHECK_ITEM_LIST = ABILITY_LIST + SKILL_LIST + SAVING_LIST + ATTACK_LIST
CHECK_ITEM_INDEX_DICT = {name: i for i, name in enumerate(CHECK_ITEM_LIST)}

#: 全局附加加值键：作用于所有豁免 / 所有攻击
SAVING_ALL_KEY = "豁免"
ATTACK_ALL_KEY = "攻击"
EXT_ITEM_LIST = CHECK_ITEM_LIST + [SAVING_ALL_KEY, ATTACK_ALL_KEY]
EXT_ITEM_INDEX_DICT = {name: i for i, name in enumerate(EXT_ITEM_LIST)}

# ── 角色卡关键字（$xxx$ 模板段落）────────────────────────────────────────
CHAR_INFO_KEY_NAME = "$姓名$"
CHAR_INFO_KEY_LEVEL = "$等级$"
CHAR_INFO_KEY_HP = "$生命值$"
CHAR_INFO_KEY_HP_DICE = "$生命骰$"
CHAR_INFO_KEY_ABILITY = "$属性$"
CHAR_INFO_KEY_PROF = "$熟练$"
CHAR_INFO_KEY_EXT = "$额外加值$"
CHAR_INFO_KEY_LIST = [
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_LEVEL,
    CHAR_INFO_KEY_HP,
    CHAR_INFO_KEY_HP_DICE,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_PROF,
    CHAR_INFO_KEY_EXT,
]
