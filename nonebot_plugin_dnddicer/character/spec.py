"""角色卡段语法的机器可读清单（网页建卡器与测试共用）。

只依赖 ``constants.py``，不读文件、不解析文本。网页建卡器读取由本模块生成的
``docs/.vitepress/theme/card-builder/card-spec.json``，测试断言两边逐字一致；
各段 ``example`` 必须与示例卡（``gen_template_char``）对应段逐字相同，可选段
未填时为空串，改段语法或示例卡时测试会立刻报错。
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
    SAVING_LIST,
    SAVING_PARENT_DICT,
    SKILL_LIST,
    SKILL_PARENT_DICT,
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
    {"id": "core", "label": "属性与检定", "summary": "等级、六属性、熟练、额外加值（豁免与技能加值自动计算）"},
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
        "example": "伊瑟兰·晨星",
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
            "背景:智者; 阵营:中立善良; 信仰:密斯特拉; 体型:中型; 年龄:132; "
            "外貌:银发绿眼，深蓝法袍; 个性:喜欢追问原理; 理想:知识应当被分享; "
            "羁绊:导师的笔记; 缺点:说话太直"
        ),
    },
    {
        "key": CHAR_INFO_KEY_STORY,
        "label": "故事",
        "group": "identity",
        "required": False,
        "summary": "背景故事，可多行/多段，最多 1000 字（换行不计）",
        "example": (
            "伊瑟兰出身于银月城的学者世家，少年时在塔中抄录古籍，一次偶然的星象记录"
            "让伊瑟兰看见奥术网络背后的裂隙。\n"
            "此后伊瑟兰离开书斋，以旅行者的身份追查那些被刻意抹去的法术痕迹；相信"
            "知识应当被分享，但也清楚有些门一旦打开就再难关上。\n"
            "如今伊瑟兰随商队来到边境，既是为了寻找失落的抄本，也是为了证明自己不只是"
            "导师笔记里的一个名字。"
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
        "example": "37/37",
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
        "example": "8/14/16/18/11/8",
    },
    {
        "key": CHAR_INFO_KEY_PROF,
        "label": "熟练",
        "group": "core",
        "required": False,
        "summary": "技能/豁免条目，2*为专精；可加 护甲:… / 武器:… / 工具:… / 语言:…",
        "example": (
            "奥秘/历史/2*调查/洞悉/察觉/智力豁免/感知豁免/"
            "武器:匕首·长棍/工具:书法工具/语言:通用语·精灵语·龙语"
        ),
    },
    {
        "key": CHAR_INFO_KEY_EXT,
        "label": "额外加值",
        "group": "core",
        "required": False,
        "summary": "条目:优势/劣势±加值，多项用 / 分隔",
        "example": "",
    },
    {
        "key": CHAR_INFO_KEY_FEATS,
        "label": "专长",
        "group": "other",
        "required": False,
        "summary": "专长名或 名称:说明，多项用 / 分隔",
        "example": (
            "魔法学徒（法师）:习得光亮术、心灵之楔与护盾术；护盾术可免法术位施展一次，长休恢复/"
            "属性值提升:智力 +1、感知 +1"
        ),
    },
    {
        "key": CHAR_INFO_KEY_TRAITS,
        "label": "特性",
        "group": "other",
        "required": False,
        "summary": "种族/职业/背景特性，可写 名称（来源）:说明，多项用 / 分隔",
        "example": (
            "黑暗视觉（种族）:60 尺内微光视为明亮，黑暗视为微光/"
            "妖精血统（种族）:进行避免或结束魅惑状态的豁免时具有优势/"
            "敏锐感官（种族）:获得察觉熟练/"
            "出神（种族）:无需睡眠，魔法无法使你入睡；4 小时即可完成长休并保持清醒/"
            "高等精灵血系（种族）:习得魔法伎俩；3 级习得侦测魔法、5 级习得迷踪步，"
            "始终准备，各可免法术位施展一次，长休恢复/"
            "仪式学家（法师）:法术书中的仪式法术可直接以仪式施展，无需准备/"
            "学者（法师）:获得调查专精/"
            "塑能学者（法师）:法术书免费加入燃烧之手、粉碎音波与火球术/"
            "强力戏法（塑能师）:伤害戏法攻击失手或目标豁免成功时，仍受一半伤害/"
            "记忆法术（法师）:短休时可研究法术书，替换一道已准备的一环及以上法术"
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
            "冷冻射线+7,2d8寒冷,法术攻击 · 60尺 · 速度-10/"
            "匕首+5,1d4+2穿刺,灵巧 · 轻型/"
            "长棍+2,1d6-1钝击,奥术法器 · 两用(1d8)"
        ),
    },
    {
        "key": CHAR_INFO_KEY_ITEMS,
        "label": "物品",
        "group": "gear",
        "required": False,
        "summary": "名称x数量[装备]，多项用 ; 分隔",
        "example": (
            "法术书x1[装备]; 长棍x1[装备]; 匕首x2[装备]; 长袍x1[装备]; "
            "学者套组x1; 书法工具x1; 书籍（历史）x1; 羊皮纸x8; 治疗药水x1"
        ),
    },
    {
        "key": CHAR_INFO_KEY_COINS,
        "label": "钱币",
        "group": "gear",
        "required": False,
        "summary": "CP/SP/EP/GP/PP 五种币值，只写有值的",
        "example": "CP:0; SP:0; EP:0; GP:13; PP:0",
    },
    {
        "key": CHAR_INFO_KEY_FEATURE,
        "label": "能力",
        "group": "resources",
        "required": False,
        "summary": "名称:当前/上限恢复档[|说明]，多项用 ; 分隔",
        "example": (
            "奥术回想:1/1短休|短休时恢复总环阶不超过 3 的法术位（6 环以下），长休前一次; "
            "魔法学徒:1/1长休|无需法术位施展一次护盾术，长休恢复"
        ),
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
            "火焰箭:0|时间=1动作,距离=120尺,备注=2d10 火焰 / 法术攻击; "
            "冷冻射线:0|时间=1动作,距离=60尺,备注=2d8 寒冷 / 速度-10; "
            "法师之手:0|时间=1动作,距离=30尺,备注=操控物件 / 1分钟; "
            "次级幻象:0|时间=1动作,距离=30尺,材料=是,备注=声音或影像 / 1分钟; "
            "魔法伎俩:0|时间=1动作,距离=10尺,备注=无害小魔法 / 至多1小时; "
            "光亮术:0|时间=1动作,距离=触碰,材料=是,备注=20尺明亮光照 / 1小时; "
            "心灵之楔:0|时间=1动作,距离=60尺,备注=2d6 心灵 / 智力豁免; "
            "护盾术:1*|时间=1反应,距离=自身,备注=+5 AC / 1轮 / 学徒免位1次; "
            "魔法飞弹:1*|时间=1动作,距离=120尺,备注=3d4+3 力场 / 升环+1飞镖; "
            "法师护甲:1*|时间=1动作,距离=触碰,材料=是,备注=AC 13+敏捷 / 8小时; "
            "侦测魔法:1*|时间=1动作或仪式,距离=自身,专注=是,仪式=是,"
            "备注=30尺灵光 / 血系免位1次; "
            "羽落术:1*|时间=1反应,距离=60尺,材料=是,备注=至多5个生物 / 1分钟; "
            "迷踪步:2*|时间=1附赠动作,距离=自身,备注=传送30尺 / 血系免位1次; "
            "蛛网术:2*|时间=1动作,距离=60尺,专注=是,材料=是,备注=20尺立方 / 束缚; "
            "镜影术:2*|时间=1动作,距离=自身,备注=3个分身 / 1分钟; "
            "火球术:3*|时间=1动作,距离=150尺,材料=是,备注=20尺半径 / 8d6 火焰 / 敏捷; "
            "闪电束:3*|时间=1动作,距离=自身,材料=是,备注=100尺线 / 8d6 闪电 / 敏捷; "
            "法术反制:3*|时间=1反应,距离=60尺,备注=体质豁免 / 打断施法; "
            "加速术:3*|时间=1动作,距离=30尺,专注=是,材料=是,"
            "备注=速度翻倍 / +2 AC / 额外动作"
        ),
    },
    {
        "key": CHAR_INFO_KEY_SPELL_SLOTS,
        "label": "法术位",
        "group": "resources",
        "required": False,
        "summary": "环阶:当前/上限；契约写 契约3:2/2",
        "example": "1:4/4; 2:3/3; 3:2/2",
    },
    {
        "key": CHAR_INFO_KEY_COMBAT_NOTES,
        "label": "战斗记录",
        "group": "other",
        "required": False,
        "summary": "战斗中的临时记录，自由文本多项用 ; 分隔",
        "example": "法师护甲(8小时)",
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
    "saving_items": list(SAVING_LIST),
    "check_items": list(CHECK_ITEM_LIST),
    "ext_items": list(EXT_ITEM_LIST),
    "saving_all_key": SAVING_ALL_KEY,
    # 技能/豁免 → 父属性（网页端预览加值与骰娘同一套算法）
    "skill_parent": dict(SKILL_PARENT_DICT),
    "saving_parent": dict(SAVING_PARENT_DICT),
    # 录入容错：同义词在导入时归一为规范名（与插件解析口径一致）
    "skill_synonyms": dict(SKILL_SYNONYM_DICT),
    "class_synonyms": dict(CLASS_SYNONYM_DICT),
    "damage_type_synonyms": dict(DAMAGE_TYPE_SYNONYM_DICT),
}

#: 旧卡里已退役的派生段：网页端识别后忽略，并提示「由骰娘自动计算」。
CARD_SPEC_LEGACY_SEGMENTS: List[Dict[str, str]] = [
    {
        "key": CHAR_INFO_KEY_ABILITY_DISPLAY,
        "label": "属性值",
        "message": "属性值已由骰娘按属性自动计算，导入时忽略",
    },
    {
        "key": CHAR_INFO_KEY_SAVES,
        "label": "豁免",
        "message": "豁免加值已由骰娘按属性与熟练自动计算，导入时忽略",
    },
    {
        "key": CHAR_INFO_KEY_SKILLS,
        "label": "技能",
        "message": "技能加值已由骰娘按属性与熟练自动计算，导入时忽略",
    },
]

#: 导出给网页建卡器的完整清单
CARD_SPEC: Dict[str, object] = {
    "version": 4,
    "groups": CARD_SPEC_GROUPS,
    "segments": CARD_SPEC_SEGMENTS,
    "output_order": CARD_SPEC_OUTPUT_ORDER,
    "limits": CARD_SPEC_LIMITS,
    "enums": CARD_SPEC_ENUMS,
    "legacy_segments": CARD_SPEC_LEGACY_SEGMENTS,
}
