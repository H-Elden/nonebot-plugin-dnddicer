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

#: 正式技能（18 项，不含「先攻」；先攻是敏捷检定，不是技能）
TRUE_SKILL_LIST = [name for name in SKILL_LIST if name != "先攻"]

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
#: 自定义职业名长度上限（扩展职业可原样记录）
CLASS_NAME_MAX_LEN = 20
#: 偷袭骰的职业判定名（角色卡职业为此职业时按等级自动计算偷袭骰）
SNEAK_ATTACK_CLASS = "游荡者"
#: 子职等级：2024 全部职业 3 级；2014 按职业不同
SUBCLASS_LEVEL_5R = 3
SUBCLASS_LEVEL_5E_DICT = {
    "牧师": 1,
    "术士": 1,
    "魔契师": 1,
    "德鲁伊": 2,
    "法师": 2,
}
#: 自定义职业没有规则表，默认按 3 级获得子职
DEFAULT_SUBCLASS_LEVEL = 3

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

# ── 限定资源（$限定资源$ 段）────────────────────────────────────────
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
#: ``$战斗$`` 可录入并回写的键（先攻 / 被动察觉由骰娘现算，不写入卡文本）
COMBAT_KEY_LIST = ("AC", "速度")
#: 卡面核心数值展示顺序（含由骰娘现算的先攻 / 被动察觉）
COMBAT_DISPLAY_KEY_LIST = ("AC", "先攻", "速度", "被动察觉")
#: 旧版 ``$战斗$`` 的派生键：解析时兼容并忽略，以骰娘现算值为准
COMBAT_LEGACY_KEY_LIST = ("先攻", "被动察觉")
#: ``$战斗$`` 速度文本长度上限（允许「30」「30尺」「飞行60尺」等写法）
COMBAT_SPEED_MAX_LEN = 20
#: ``$熟练$`` 的扩展分组前缀（顺序即卡面展示顺序）
PROFICIENCY_GROUP_LIST = ("护甲", "武器", "工具", "语言")
#: 护甲受训分类（网页端复选框）
ARMOR_CATEGORY_LIST = ("轻甲", "中甲", "重甲", "盾牌")
#: 武器熟练分类（网页端复选框；个别特性给的特定武器可手填）
WEAPON_CATEGORY_LIST = ("简易武器", "军用武器")
#: 工具选项（网页端下拉建议 + 手填）
TOOL_OPTION_LIST = (
    "炼金工具", "酿酒工具", "书法工具", "木匠工具", "制图工具", "鞋匠工具",
    "厨师工具", "玻璃工工具", "珠宝匠工具", "皮匠工具", "石匠工具",
    "画家工具", "陶匠工具", "铁匠工具", "修补匠工具", "织布工具", "木雕工具",
    "盗贼工具", "易容工具", "伪造工具", "草药工具", "毒药工具", "领航工具",
    "载具（陆上）", "载具（水上）",
    "风笛", "鼓", "扬琴", "笛子", "鲁特琴", "里拉琴", "号角", "排箫", "长笛",
    "维奥尔琴",
    "骰子套组", "纸牌套组", "龙棋套组", "三龙棋套组",
)
#: 标准语言与稀有语言（网页端多选 + 手填）
LANGUAGE_STANDARD_LIST = (
    "通用语", "矮人语", "精灵语", "巨人语", "侏儒语", "地精语", "半身人语", "兽人语",
)
LANGUAGE_EXOTIC_LIST = (
    "深渊语", "天界语", "龙语", "深潜语", "炼狱语", "原初语", "木族语", "地底通用语",
)
#: 单个扩展分组最多几项、每项最长字数
PROFICIENCY_GROUP_ITEM_MAX = 20
PROFICIENCY_GROUP_ITEM_MAX_LEN = 20
#: ``$专长$`` 条数与名称长度上限
FEAT_MAX_COUNT = 20
FEAT_NAME_MAX_LEN = 20
#: ``$专长$`` 说明文本长度上限（2026-10-21 批②）
FEAT_TEXT_MAX_LEN = 60
#: ``$种族特性$`` 条数与单条长度上限
RACE_TRAIT_MAX_COUNT = 20
RACE_TRAIT_NAME_MAX_LEN = 30
RACE_TRAIT_TEXT_MAX_LEN = 80
#: ``$职业特性$`` 条数与单条长度上限
CLASS_FEATURE_MAX_COUNT = 30
CLASS_FEATURE_NAME_MAX_LEN = 30
CLASS_FEATURE_TEXT_MAX_LEN = 80
#: ``$魔法物品$`` 件数、字段长度与段落数上限
MAGIC_ITEM_MAX_COUNT = 20
MAGIC_ITEM_NAME_MAX_LEN = 30
MAGIC_ITEM_TAG_MAX_LEN = 60
MAGIC_ITEM_TEXT_MAX_LEN = 500
MAGIC_ITEM_PARAGRAPH_MAX = 5
#: ``$物品$`` 条数、名称长度与数量上限
ITEM_MAX_COUNT = 50
ITEM_NAME_MAX_LEN = 30
ITEM_QUANTITY_MAX = 999
#: ``$背景$`` 值长上限
BACKGROUND_VALUE_MAX_LEN = 100
#: ``$战斗记录$`` 条数与单条长度上限
COMBAT_NOTE_MAX_COUNT = 20
COMBAT_NOTE_MAX_LEN = 60
#: 2024 与 2014 通用的背景键（按此顺序展示）
BACKGROUND_KEY_LIST_5R = (
    "背景", "阵营", "信仰", "体型", "年龄", "外貌", "个性",
)
#: 2014 追加的背景键（理想 / 羁绊 / 缺点）
BACKGROUND_KEY_LIST_5E_EXTRA = ("理想", "羁绊", "缺点")
#: 卡文本接受的背景键（两版并集；网页端再按规则版本过滤）
BACKGROUND_KEY_LIST = BACKGROUND_KEY_LIST_5R + BACKGROUND_KEY_LIST_5E_EXTRA

# ── 卡面展示扩展段批②（2026-10-21）──────────────────────────────────────
#: ``$进度$`` 的可用键（顺序即回写顺序）
PROGRESS_KEY_LIST = ("经验", "激励")
#: 经验值 / 下一级的数值上限（含 0）
XP_VALUE_MAX = 9_999_999
#: 1~20 级累计经验门槛（2014 与 2024 同表；下标 0 = 1 级）
XP_THRESHOLDS = (
    0, 300, 900, 2700, 6500, 14000, 23000, 34000, 48000, 64000,
    85000, 100000, 120000, 140000, 165000, 195000, 225000, 265000,
    305000, 355000,
)
#: ``$钱币$`` 的五种币值（顺序即展示顺序）
COIN_KEY_LIST = ("CP", "SP", "EP", "GP", "PP")
#: 单个币值上限
COIN_VALUE_MAX = 999_999
#: ``$故事$`` 最大字数（可多行多段；换行不计入字数，2026-10-22 起由 300 放宽）
STORY_MAX_LEN = 1000
#: ``$武器$`` 备注最大字数
WEAPON_NOTE_MAX_LEN = 30
#: ``$限定资源$`` 说明文本最大字数
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
#: 半熟练规则段：``全部:向下/技能:向下/力敏体:向上``
CHAR_INFO_KEY_HALF_PROF = "$半熟练$"
#: 半熟练的适用范围
HALF_PROF_SCOPE_LIST = ("全部", "技能", "力敏体")
#: 半熟练的取整方式
HALF_PROF_ROUNDING_LIST = ("向下", "向上")
CHAR_INFO_KEY_EXT = "$额外加值$"
CHAR_INFO_KEY_WEAPON = "$武器$"
CHAR_INFO_KEY_RESOURCE = "$限定资源$"
CHAR_INFO_KEY_SPELL = "$法术$"
CHAR_INFO_KEY_SPELL_SLOTS = "$法术位$"
#: 完整卡面扩展段
CHAR_INFO_KEY_BACKGROUND = "$背景$"
CHAR_INFO_KEY_COMBAT = "$战斗$"
CHAR_INFO_KEY_FEATS = "$专长$"
CHAR_INFO_KEY_RACE_TRAITS = "$种族特性$"
CHAR_INFO_KEY_CLASS_TRAITS = "$职业特性$"
CHAR_INFO_KEY_MAGIC_ITEMS = "$魔法物品$"
CHAR_INFO_KEY_ITEMS = "$物品$"
CHAR_INFO_KEY_COMBAT_NOTES = "$战斗记录$"
#: 卡面展示扩展段
CHAR_INFO_KEY_STORY = "$故事$"
CHAR_INFO_KEY_PROGRESS = "$进度$"
CHAR_INFO_KEY_COINS = "$钱币$"
# ── 角色卡库（卡名与上限，2026-10-23）────────────────────────────────────
#: 卡名最大字符数（玩家可见的库内标识，与 $姓名$ 分开）
CARD_NAME_MAX_LEN = 20
#: 一个 QQ 最多同时持有的角色卡数量
CARD_LIMIT = 10
#: 卡名不能与 .角色卡 子命令重名，避免查看命令歧义
CARD_NAME_RESERVED = (
    "新建", "修改", "改名", "列表", "绑定", "解绑", "清除", "记录",
)
#: 卡名禁含符号（空白另按字符判断）
CARD_NAME_FORBIDDEN_CHARS = ("$", "@")

CHAR_INFO_KEY_LIST = [
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_RACE,
    CHAR_INFO_KEY_CLASS,
    CHAR_INFO_KEY_SUBCLASS,
    CHAR_INFO_KEY_BACKGROUND,
    CHAR_INFO_KEY_STORY,
    CHAR_INFO_KEY_HP,
    CHAR_INFO_KEY_HP_DICE,
    CHAR_INFO_KEY_COMBAT,
    CHAR_INFO_KEY_PROGRESS,
    CHAR_INFO_KEY_LEVEL,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_PROF,
    CHAR_INFO_KEY_HALF_PROF,
    CHAR_INFO_KEY_EXT,
    CHAR_INFO_KEY_FEATS,
    CHAR_INFO_KEY_RACE_TRAITS,
    CHAR_INFO_KEY_CLASS_TRAITS,
    CHAR_INFO_KEY_WEAPON,
    CHAR_INFO_KEY_ITEMS,
    CHAR_INFO_KEY_COINS,
    CHAR_INFO_KEY_RESOURCE,
    CHAR_INFO_KEY_MAGIC_ITEMS,
    CHAR_INFO_KEY_SPELL,
    CHAR_INFO_KEY_SPELL_SLOTS,
    CHAR_INFO_KEY_COMBAT_NOTES,
]
