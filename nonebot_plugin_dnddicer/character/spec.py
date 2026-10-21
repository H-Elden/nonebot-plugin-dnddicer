"""角色卡段语法的机器可读清单（网页建卡器与测试共用）。

只依赖 ``constants.py``，不读文件、不解析文本。网页建卡器读取由本模块生成的
``docs/.vitepress/theme/card-builder/card-spec.json``，测试断言两边逐字一致；
各段 ``example`` 必须与示例卡（``gen_template_char``）对应段逐字相同，改段语法
或示例卡时测试会立刻报错。
"""

from __future__ import annotations

from typing import Dict, List

from .constants import (
    ABILITY_LIST,
    BACKGROUND_KEY_LIST,
    BACKGROUND_KEY_MAX_LEN,
    BACKGROUND_MAX_COUNT,
    BACKGROUND_VALUE_MAX_LEN,
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
    CHECK_ITEM_LIST,
    CLASS_LIST,
    CLASS_SYNONYM_DICT,
    COIN_KEY_LIST,
    COIN_VALUE_MAX,
    COMBAT_NOTE_MAX_COUNT,
    COMBAT_NOTE_MAX_LEN,
    COMBAT_SPEED_MAX_LEN,
    DAMAGE_TYPE_LIST,
    DAMAGE_TYPE_SYNONYM_DICT,
    EXT_ITEM_LIST,
    FEAT_MAX_COUNT,
    FEAT_NAME_MAX_LEN,
    FEAT_TEXT_MAX_LEN,
    FEATURE_MAX_COUNT,
    FEATURE_NAME_MAX_LEN,
    FEATURE_RECOVER_MODES,
    FEATURE_TEXT_MAX_LEN,
    ITEM_MAX_COUNT,
    ITEM_NAME_MAX_LEN,
    ITEM_QUANTITY_MAX,
    PROFICIENCY_GROUP_ITEM_MAX,
    PROFICIENCY_GROUP_ITEM_MAX_LEN,
    PROFICIENCY_GROUP_LIST,
    SAVING_ALL_KEY,
    SKILL_LIST,
    SKILL_SYNONYM_DICT,
    SPELL_DC_MAX,
    SPELL_DETAIL_KEYS,
    SPELL_LEVEL_MAX,
    SPELL_MAX_COUNT,
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
    WEAPON_NAME_MAX_LEN,
    WEAPON_NOTE_MAX_LEN,
    XP_VALUE_MAX,
)

#: 表单分组（顺序即页面分组顺序）
CARD_SPEC_GROUPS: List[Dict[str, str]] = [
    {"id": "identity", "label": "身份", "summary": "姓名、种族、职业、背景与故事"},
    {"id": "core", "label": "属性与检定", "summary": "等级、六属性、豁免、技能与熟练"},
    {"id": "combat", "label": "战斗", "summary": "生命值、战斗数值、经验与武器"},
    {"id": "resources", "label": "能力与法术", "summary": "有次数的能力、法术清单与法术位"},
    {"id": "gear", "label": "装备", "summary": "物品与钱币"},
    {"id": "other", "label": "其他", "summary": "专长、特性与战斗记录"},
]

#: 段清单（顺序必须是 ``CHAR_INFO_KEY_LIST`` 的顺序）
CARD_SPEC_SEGMENTS: List[Dict[str, object]] = [
    {
        "key": CHAR_INFO_KEY_NAME,
        "label": "姓名",
        "group": "identity",
        "required": False,
        "summary": "角色名，检定落款与先攻列表用",
        "example": "张三",
    },
    {
        "key": CHAR_INFO_KEY_RACE,
        "label": "种族",
        "group": "identity",
        "required": False,
        "summary": "种族名，仅记录与展示",
        "example": "高等精灵",
    },
    {
        "key": CHAR_INFO_KEY_CLASS,
        "label": "职业",
        "group": "identity",
        "required": False,
        "summary": "12 职业规范名之一；游荡者的偷袭骰按等级计算",
        "example": "法师",
    },
    {
        "key": CHAR_INFO_KEY_SUBCLASS,
        "label": "子职",
        "group": "identity",
        "required": False,
        "summary": "子职名，仅记录与展示",
        "example": "塑能师",
    },
    {
        "key": CHAR_INFO_KEY_BACKGROUND,
        "label": "背景",
        "group": "identity",
        "required": False,
        "summary": "背景、阵营、信仰、体型、年龄、外貌、个性/理想/羁绊/缺点",
        "example": (
            "背景:贤者; 阵营:中立善良; 信仰:密斯特拉; 体型:中型; 年龄:132; "
            "外貌:银发绿眼，深蓝法袍; 个性:喜欢追问原理; 理想:知识应当被分享; "
            "羁绊:导师的笔记; 缺点:说话太直"
        ),
    },
    {
        "key": CHAR_INFO_KEY_STORY,
        "label": "故事",
        "group": "identity",
        "required": False,
        "summary": "背景故事长文本，单行不超过 300 字",
        "example": (
            "张三出身于银月城的学者世家，少年时在塔中抄录古籍，一次偶然的星象记录"
            "让他看见奥术网络背后的裂隙。此后他离开书斋，以旅行者的身份追查那些被"
            "刻意抹去的法术痕迹；他相信知识应当被分享，但也清楚有些门一旦打开就"
            "再难关上。如今他随商队来到边境，既是为了寻找失落的抄本，也是为了证明"
            "自己不只是导师笔记里的一个名字。"
        ),
    },
    {
        "key": CHAR_INFO_KEY_LEVEL,
        "label": "等级",
        "group": "core",
        "required": True,
        "summary": "角色等级；熟练加值 = 2 + (等级 - 1) // 4",
        "example": "5",
    },
    {
        "key": CHAR_INFO_KEY_HP,
        "label": "生命值",
        "group": "combat",
        "required": False,
        "summary": "当前/最大(临时)，如 29/37 (5)；可只写当前值",
        "example": "29/37 (5)",
    },
    {
        "key": CHAR_INFO_KEY_HP_DICE,
        "label": "生命骰",
        "group": "combat",
        "required": False,
        "summary": "当前/总数 D骰面，如 5/5 D6",
        "example": "5/5 D6",
    },
    {
        "key": CHAR_INFO_KEY_COMBAT,
        "label": "战斗",
        "group": "combat",
        "required": False,
        "summary": "AC / 先攻 / 速度 / 被动察觉，只写有值的",
        "example": "AC:15; 先攻:+2; 速度:30; 被动察觉:13",
    },
    {
        "key": CHAR_INFO_KEY_PROGRESS,
        "label": "进度",
        "group": "combat",
        "required": False,
        "summary": "经验:当前/下一级; 激励:有 或 无",
        "example": "经验:6500/14000; 激励:有",
    },
    {
        "key": CHAR_INFO_KEY_ABILITY,
        "label": "属性",
        "group": "core",
        "required": True,
        "summary": "六个原始值，用 / 分隔：力量/敏捷/体质/智力/感知/魅力",
        "example": "8/15/16/18/10/8",
    },
    {
        "key": CHAR_INFO_KEY_ABILITY_DISPLAY,
        "label": "属性值",
        "group": "core",
        "required": False,
        "summary": "六项展示值：属性:值/调整值，六项全写，仅展示",
        "example": (
            "力量:8/-1; 敏捷:15/+2; 体质:16/+3; 智力:18/+4; 感知:10/+0; 魅力:8/-1"
        ),
    },
    {
        "key": CHAR_INFO_KEY_SAVES,
        "label": "豁免",
        "group": "core",
        "required": False,
        "summary": "六项豁免展示值，只写有值的",
        "example": "力量:+1; 敏捷:+4; 体质:+5; 智力:+9; 感知:+5; 魅力:+1",
    },
    {
        "key": CHAR_INFO_KEY_SKILLS,
        "label": "技能",
        "group": "core",
        "required": False,
        "summary": "技能展示值，尾部 * 表示专精，只写有值的",
        "example": (
            "运动:-1; 体操:+2; 巧手:+2; 隐匿:+2; 先攻:+2; 奥秘:+10*; "
            "历史:+7; 调查:+7; 自然:+4; 宗教:+7; 驯兽:+0; 洞悉:+0; 医药:+0; "
            "察觉:+3; 求生:+0; 欺瞒:-1; 威吓:-1; 表演:-1; 游说:-1"
        ),
    },
    {
        "key": CHAR_INFO_KEY_PROF,
        "label": "熟练",
        "group": "core",
        "required": False,
        "summary": "检定条目 / 2*专精 / 护甲:… / 武器:… / 工具:… / 语言:…",
        "example": (
            "2*奥秘/历史/调查/宗教/察觉/智力豁免/感知豁免/"
            "武器:匕首·法杖·轻弩/工具:书法工具/语言:通用语·精灵语"
        ),
    },
    {
        "key": CHAR_INFO_KEY_EXT,
        "label": "额外加值",
        "group": "core",
        "required": False,
        "summary": "条目:优势/劣势±加值，多项用 / 分隔",
        "example": "豁免:+2",
    },
    {
        "key": CHAR_INFO_KEY_FEATS,
        "label": "专长",
        "group": "other",
        "required": False,
        "summary": "专长名或 名称:说明，多项用 / 分隔",
        "example": "战法师:专注豁免具有优势；可借机施法",
    },
    {
        "key": CHAR_INFO_KEY_TRAITS,
        "label": "特性",
        "group": "other",
        "required": False,
        "summary": "种族/职业/背景特性，可写 名称（来源）:说明，多项用 / 分隔",
        "example": (
            "黑暗视觉（种族）:60 尺内微光视为明亮，黑暗视为微光/"
            "妖精血统（种族）:对抗魅惑的豁免具有优势，魔法无法使你入睡/"
            "出神（种族）:长休只需 4 小时，期间保持清醒"
        ),
    },
    {
        "key": CHAR_INFO_KEY_WEAPON,
        "label": "武器",
        "group": "combat",
        "required": False,
        "summary": "名称+命中,伤害+类型[,备注]，多项用 / 分隔；名称尾 x 表示不做攻击检定",
        "example": (
            "火焰箭+7,2d10火焰,法术攻击 · 120尺/"
            "匕首+5,1d4+2穿刺,灵巧 · 轻型/"
            "法杖+5,1d6+2钝击,奥术法器/"
            "轻弩+5,1d8+2穿刺,双手 · 80-320尺"
        ),
    },
    {
        "key": CHAR_INFO_KEY_ITEMS,
        "label": "物品",
        "group": "gear",
        "required": False,
        "summary": "名称x数量[装备]，多项用 ; 分隔",
        "example": (
            "法术书x1[装备]; 治疗药水x2; 背包x1[装备]; 绳索50尺x1; 火把x5; "
            "羊皮纸x10; 墨水笔x1; 施法材料包x1[装备]; 旅行者服装x1[装备]"
        ),
    },
    {
        "key": CHAR_INFO_KEY_COINS,
        "label": "钱币",
        "group": "gear",
        "required": False,
        "summary": "CP/SP/EP/GP/PP 五种币值，只写有值的",
        "example": "CP:0; SP:8; EP:0; GP:18; PP:0",
    },
    {
        "key": CHAR_INFO_KEY_FEATURE,
        "label": "能力",
        "group": "resources",
        "required": False,
        "summary": "名称:当前/上限恢复档[|说明]，多项用 ; 分隔",
        "example": "奥术回想:1/1短休|短休时回复一个已消耗的法术位，环阶不超过 3 环",
    },
    {
        "key": CHAR_INFO_KEY_SPELL,
        "label": "法术",
        "group": "resources",
        "required": False,
        "summary": (
            "施法属性、豁免DC、法术攻击三个头键，其余为 名称:环阶[*][|详情]；"
            "详情键：时间/距离/专注/仪式/材料/备注"
        ),
        "example": (
            "施法属性:智力; 豁免DC:15; 法术攻击:+7; "
            "火焰箭:0*|时间=1动作,距离=120尺,备注=2d10 火焰 / 敏捷; "
            "魔法飞弹:1*|时间=1动作,距离=120尺,备注=3d4+3 力场; "
            "护盾术:1*|时间=1反应,距离=自身,备注=+5 AC / 1轮; "
            "云雾术:1|时间=1动作,距离=120尺,专注=是,材料=是,备注=20尺半径 / 专注; "
            "侦测魔法:1|时间=1动作,距离=30尺,专注=是,仪式=是,备注=专注 / 仪式; "
            "镜影术:2*|时间=1动作,距离=自身,备注=3个镜像 / 1分钟; "
            "火球术:3*|时间=1动作,距离=150尺,材料=是,备注=8d6 火焰 / 敏捷; "
            "闪电束:3|时间=1动作,距离=100尺,材料=是,备注=8d6 闪电 / 敏捷"
        ),
    },
    {
        "key": CHAR_INFO_KEY_SPELL_SLOTS,
        "label": "法术位",
        "group": "resources",
        "required": False,
        "summary": "环阶:当前/上限；契约写 契约3:2/2",
        "example": "1:3/4; 2:2/3; 3:1/2",
    },
    {
        "key": CHAR_INFO_KEY_COMBAT_NOTES,
        "label": "战斗记录",
        "group": "other",
        "required": False,
        "summary": "战斗中的临时记录，自由文本多项用 ; 分隔",
        "example": "法师护甲(8小时); 专注:飞行术",
    },
]

#: 卡文本的回写顺序（与 ``DNDCharacter.get_char_info()`` 的段顺序一致）。
#: 网页建卡器按此顺序拼整卡，保证「导入骰娘输出的卡 → 导出」逐字不变；
#: 它只决定输出顺序，与上面的表单清单顺序（``CHAR_INFO_KEY_LIST``）无关。
CARD_SPEC_OUTPUT_ORDER: List[str] = [
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
    CHAR_INFO_KEY_ABILITY_DISPLAY,
    CHAR_INFO_KEY_SAVES,
    CHAR_INFO_KEY_SKILLS,
    CHAR_INFO_KEY_PROF,
    CHAR_INFO_KEY_EXT,
    CHAR_INFO_KEY_FEATS,
    CHAR_INFO_KEY_TRAITS,
    CHAR_INFO_KEY_FEATURE,
    CHAR_INFO_KEY_WEAPON,
    CHAR_INFO_KEY_ITEMS,
    CHAR_INFO_KEY_COINS,
    CHAR_INFO_KEY_SPELL,
    CHAR_INFO_KEY_SPELL_SLOTS,
    CHAR_INFO_KEY_COMBAT_NOTES,
]

#: 表单与校验用到的上限
CARD_SPEC_LIMITS: Dict[str, int] = {
    "level_max": 20,
    "ability_score_min": 1,
    "ability_score_max": 30,
    "ability_mod_min": -10,
    "ability_mod_max": 10,
    "signed_bonus_max": 99,
    "combat_speed_max_len": COMBAT_SPEED_MAX_LEN,
    "proficiency_group_item_max": PROFICIENCY_GROUP_ITEM_MAX,
    "proficiency_group_item_max_len": PROFICIENCY_GROUP_ITEM_MAX_LEN,
    "spell_level_max": SPELL_LEVEL_MAX,
    "feature_max_count": FEATURE_MAX_COUNT,
    "feature_name_max_len": FEATURE_NAME_MAX_LEN,
    "feature_text_max_len": FEATURE_TEXT_MAX_LEN,
    "spell_max_count": SPELL_MAX_COUNT,
    "spell_name_max_len": SPELL_NAME_MAX_LEN,
    "spell_slot_max": SPELL_SLOT_MAX,
    "spell_dc_max": SPELL_DC_MAX,
    "spell_time_max_len": SPELL_TIME_MAX_LEN,
    "spell_range_max_len": SPELL_RANGE_MAX_LEN,
    "spell_note_max_len": SPELL_NOTE_MAX_LEN,
    "weapon_max_count": WEAPON_MAX_COUNT,
    "weapon_name_max_len": WEAPON_NAME_MAX_LEN,
    "weapon_note_max_len": WEAPON_NOTE_MAX_LEN,
    "feat_max_count": FEAT_MAX_COUNT,
    "feat_name_max_len": FEAT_NAME_MAX_LEN,
    "feat_text_max_len": FEAT_TEXT_MAX_LEN,
    "trait_max_count": TRAIT_MAX_COUNT,
    "trait_name_max_len": TRAIT_ITEM_MAX_LEN,
    "trait_text_max_len": TRAIT_TEXT_MAX_LEN,
    "item_max_count": ITEM_MAX_COUNT,
    "item_name_max_len": ITEM_NAME_MAX_LEN,
    "item_quantity_max": ITEM_QUANTITY_MAX,
    "background_max_count": BACKGROUND_MAX_COUNT,
    "background_key_max_len": BACKGROUND_KEY_MAX_LEN,
    "background_value_max_len": BACKGROUND_VALUE_MAX_LEN,
    "combat_note_max_count": COMBAT_NOTE_MAX_COUNT,
    "combat_note_max_len": COMBAT_NOTE_MAX_LEN,
    "story_max_len": STORY_MAX_LEN,
    "coin_max": COIN_VALUE_MAX,
    "xp_max": XP_VALUE_MAX,
}

#: 下拉选项与固定键
CARD_SPEC_ENUMS: Dict[str, object] = {
    "abilities": list(ABILITY_LIST),
    "classes": list(CLASS_LIST),
    "damage_types": list(DAMAGE_TYPE_LIST),
    "recover_modes": list(FEATURE_RECOVER_MODES),
    "coin_keys": list(COIN_KEY_LIST),
    "spell_detail_keys": list(SPELL_DETAIL_KEYS),
    "background_keys": list(BACKGROUND_KEY_LIST),
    "proficiency_groups": list(PROFICIENCY_GROUP_LIST),
    # 熟练/额外加值的条目表（顺序即卡文本回写顺序）
    "skills": list(SKILL_LIST),
    "check_items": list(CHECK_ITEM_LIST),
    "ext_items": list(EXT_ITEM_LIST),
    "saving_all_key": SAVING_ALL_KEY,
    # 录入容错：同义词在导入时归一为规范名（与插件解析口径一致）
    "skill_synonyms": dict(SKILL_SYNONYM_DICT),
    "class_synonyms": dict(CLASS_SYNONYM_DICT),
    "damage_type_synonyms": dict(DAMAGE_TYPE_SYNONYM_DICT),
}

#: 导出给网页建卡器的完整清单
CARD_SPEC: Dict[str, object] = {
    "version": 2,
    "groups": CARD_SPEC_GROUPS,
    "segments": CARD_SPEC_SEGMENTS,
    "output_order": CARD_SPEC_OUTPUT_ORDER,
    "limits": CARD_SPEC_LIMITS,
    "enums": CARD_SPEC_ENUMS,
}
