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

# ── 有使用次数的能力（$能力$ 段，2026-10-20 批②）────────────────────────
#: 能力条数上限与名称长度上限
FEATURE_MAX_COUNT = 20
FEATURE_NAME_MAX_LEN = 20
#: 能力名禁含字样（与武器口径一致，避免与命令切分/检定点歧义）
FEATURE_NAME_FORBIDDEN_WORDS = ("攻击", "命中", "伤害", "检定", "豁免")
#: 能力名禁含符号（条目内 ``:`` 分字段、``;`` 分条、``/`` 分当前上限、``|`` 分说明）
FEATURE_NAME_FORBIDDEN_CHARS = (
    "/", ",", "，", ":", "：", ";", "；", "$", "+", "-", "|", "｜",
)
#: 恢复档（顺序即展示顺序）：短休 / 长休 / 两者 / 手动；
#: 可后缀 ``+N``（恢复 N 次）或 ``满``（回满，可省略）
FEATURE_RECOVER_MODES = ("短休", "长休", "两者", "手动")

# ── 休息与施法（2026-10-20 批③）────────────────────────────────────────
#: 休息类型（能力恢复与法术位恢复共用）
REST_SHORT = "短休"
REST_LONG = "长休"

#: 2024 施法职业（`.施法` 未准备提醒的覆盖范围）
SPELLCASTING_CLASSES_2024 = (
    "吟游诗人", "牧师", "德鲁伊", "术士", "魔契师", "法师", "圣武士", "游侠",
)
#: 2014 准备型施法职业（只有这些职业在 5e 口径下提醒未准备）
PREPARED_CASTERS_2014 = ("牧师", "德鲁伊", "圣武士", "法师")

# ── 法术清单与法术位（$法术$ / $法术位$ 段，2026-10-20 批②）─────────────
#: 法术条数上限与名称长度上限
SPELL_MAX_COUNT = 50
SPELL_NAME_MAX_LEN = 20
#: 法术名禁含符号（``:`` 分字段、``;`` 分条、``*`` 是准备标记、``|`` 分详情）
SPELL_NAME_FORBIDDEN_CHARS = (
    "/", ",", "，", ":", "：", ";", "；", "$", "*", "＊", "|", "｜",
)
#: 法术环阶上限（0 = 戏法）
SPELL_LEVEL_MAX = 9
#: 单级法术位上限（防止误写超大数字）
SPELL_SLOT_MAX = 99
#: ``$法术$`` 段首条可写的施法属性前缀
SPELLCASTING_ABILITY_KEY = "施法属性"

# ── 完整卡面扩展段（2026-10-21）────────────────────────────────────────
#: ``$战斗$`` 的固定键（顺序即卡面展示顺序）
COMBAT_KEY_LIST = ("AC", "先攻", "速度", "被动察觉")
#: ``$战斗$`` 速度文本长度上限（允许「30」「30尺」「飞行60尺」等写法）
COMBAT_SPEED_MAX_LEN = 20
#: ``$熟练$`` 的扩展分组前缀（顺序即卡面展示顺序）
PROFICIENCY_GROUP_LIST = ("护甲", "武器", "工具", "语言")
#: 单个扩展分组最多几项、每项最长字数
PROFICIENCY_GROUP_ITEM_MAX = 20
PROFICIENCY_GROUP_ITEM_MAX_LEN = 20
#: ``$专长$`` 条数与名称长度上限
FEAT_MAX_COUNT = 20
FEAT_NAME_MAX_LEN = 20
#: ``$专长$`` 说明文本长度上限（2026-10-21 批②）
FEAT_TEXT_MAX_LEN = 60
#: ``$特性$`` 条数与单条长度上限
TRAIT_MAX_COUNT = 30
TRAIT_ITEM_MAX_LEN = 40
#: ``$特性$`` 说明文本长度上限（2026-10-21 批②）
TRAIT_TEXT_MAX_LEN = 80
#: ``$物品$`` 条数、名称长度与数量上限
ITEM_MAX_COUNT = 50
ITEM_NAME_MAX_LEN = 30
ITEM_QUANTITY_MAX = 999
#: ``$背景$`` 条数、键长与值长上限
BACKGROUND_MAX_COUNT = 12
BACKGROUND_KEY_MAX_LEN = 10
BACKGROUND_VALUE_MAX_LEN = 100
#: ``$战斗记录$`` 条数与单条长度上限
COMBAT_NOTE_MAX_COUNT = 20
COMBAT_NOTE_MAX_LEN = 60
#: ``$背景$`` 的常用键（按此顺序展示；未列出的键追加在末尾）
BACKGROUND_KEY_LIST = (
    "背景", "阵营", "信仰", "体型", "年龄", "外貌",
    "个性", "理想", "羁绊", "缺点",
)

# ── 卡面展示扩展段批②（2026-10-21）──────────────────────────────────────
#: ``$进度$`` 的可用键（顺序即回写顺序）
PROGRESS_KEY_LIST = ("经验", "激励")
#: 经验值 / 下一级的数值上限（含 0）
XP_VALUE_MAX = 9_999_999
#: ``$钱币$`` 的五种币值（顺序即展示顺序）
COIN_KEY_LIST = ("CP", "SP", "EP", "GP", "PP")
#: 单个币值上限
COIN_VALUE_MAX = 999_999
#: ``$故事$`` 最大字数（可多行多段；换行不计入字数，2026-10-22 起由 300 放宽）
STORY_MAX_LEN = 1000
#: ``$武器$`` 备注最大字数
WEAPON_NOTE_MAX_LEN = 30
#: ``$能力$`` 说明文本最大字数
FEATURE_TEXT_MAX_LEN = 80
#: ``$法术$`` 的保留头键（施法属性之外的两项）
SPELL_DC_KEY = "豁免DC"
SPELL_ATTACK_KEY = "法术攻击"
#: ``$法术$`` 条目详情的键（顺序即回写顺序）
SPELL_DETAIL_KEYS = ("时间", "距离", "专注", "仪式", "材料", "备注")
#: 法术详情各字段长度上限
SPELL_TIME_MAX_LEN = 12
SPELL_RANGE_MAX_LEN = 12
SPELL_NOTE_MAX_LEN = 40
#: 法术豁免 DC 上限
SPELL_DC_MAX = 99

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
CHAR_INFO_KEY_FEATURE = "$能力$"
CHAR_INFO_KEY_SPELL = "$法术$"
CHAR_INFO_KEY_SPELL_SLOTS = "$法术位$"
#: 完整卡面扩展段（2026-10-21）
CHAR_INFO_KEY_BACKGROUND = "$背景$"
CHAR_INFO_KEY_COMBAT = "$战斗$"
#: 以下三段 2026-10-22 起由骰娘按属性/熟练自动计算：不再出现在卡文本里，
#: 也不再接受录入；旧卡里若仍有这三段，解析时静默忽略（见 LEGACY_CHAR_INFO_KEY_LIST）。
CHAR_INFO_KEY_ABILITY_DISPLAY = "$属性值$"
CHAR_INFO_KEY_SAVES = "$豁免$"
CHAR_INFO_KEY_SKILLS = "$技能$"
CHAR_INFO_KEY_FEATS = "$专长$"
CHAR_INFO_KEY_TRAITS = "$特性$"
CHAR_INFO_KEY_ITEMS = "$物品$"
CHAR_INFO_KEY_COMBAT_NOTES = "$战斗记录$"
#: 卡面展示扩展段批②（2026-10-21）
CHAR_INFO_KEY_STORY = "$故事$"
CHAR_INFO_KEY_PROGRESS = "$进度$"
CHAR_INFO_KEY_COINS = "$钱币$"
CHAR_INFO_KEY_LIST = [
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_RACE,
    CHAR_INFO_KEY_CLASS,
    CHAR_INFO_KEY_SUBCLASS,
    CHAR_INFO_KEY_BACKGROUND,
    CHAR_INFO_KEY_STORY,
    CHAR_INFO_KEY_LEVEL,
    CHAR_INFO_KEY_HP,
    CHAR_INFO_KEY_HP_DICE,
    CHAR_INFO_KEY_COMBAT,
    CHAR_INFO_KEY_PROGRESS,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_PROF,
    CHAR_INFO_KEY_EXT,
    CHAR_INFO_KEY_FEATS,
    CHAR_INFO_KEY_TRAITS,
    CHAR_INFO_KEY_WEAPON,
    CHAR_INFO_KEY_ITEMS,
    CHAR_INFO_KEY_COINS,
    CHAR_INFO_KEY_FEATURE,
    CHAR_INFO_KEY_SPELL,
    CHAR_INFO_KEY_SPELL_SLOTS,
    CHAR_INFO_KEY_COMBAT_NOTES,
]

#: 仅用于兼容旧卡的段：由骰娘自动计算，不输出、不接受单独录入。
#: 解析器认识这些键是为了在整卡重录时静默忽略，而不是把它们当成未知段。
LEGACY_CHAR_INFO_KEY_LIST = (
    CHAR_INFO_KEY_ABILITY_DISPLAY,
    CHAR_INFO_KEY_SAVES,
    CHAR_INFO_KEY_SKILLS,
)
