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
    ARMOR_CATEGORY_LIST,
    BACKGROUND_KEY_LIST,
    BACKGROUND_KEY_LIST_5E_EXTRA,
    BACKGROUND_KEY_LIST_5R,
    BACKGROUND_VALUE_MAX_LEN,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_BACKGROUND,
    CHAR_INFO_KEY_CLASS,
    CHAR_INFO_KEY_CLASS_TRAITS,
    CHAR_INFO_KEY_COINS,
    CHAR_INFO_KEY_COMBAT,
    CHAR_INFO_KEY_COMBAT_NOTES,
    CHAR_INFO_KEY_EXT,
    CHAR_INFO_KEY_FEATS,
    CHAR_INFO_KEY_HALF_PROF,
    CHAR_INFO_KEY_HP,
    CHAR_INFO_KEY_HP_DICE,
    CHAR_INFO_KEY_ITEMS,
    CHAR_INFO_KEY_LEVEL,
    CHAR_INFO_KEY_MAGIC_ITEMS,
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_PROF,
    CHAR_INFO_KEY_PROGRESS,
    CHAR_INFO_KEY_RACE,
    CHAR_INFO_KEY_RACE_TRAITS,
    CHAR_INFO_KEY_RESOURCE,
    CHAR_INFO_KEY_SPELL,
    CHAR_INFO_KEY_SPELL_SLOTS,
    CHAR_INFO_KEY_STORY,
    CHAR_INFO_KEY_SUBCLASS,
    CHAR_INFO_KEY_WEAPON,
    CHECK_ITEM_LIST,
    CLASS_FEATURE_MAX_COUNT,
    CLASS_FEATURE_NAME_MAX_LEN,
    CLASS_FEATURE_TEXT_MAX_LEN,
    CLASS_LIST,
    CLASS_NAME_MAX_LEN,
    CLASS_SYNONYM_DICT,
    COIN_KEY_LIST,
    COIN_VALUE_MAX,
    COMBAT_NOTE_MAX_COUNT,
    COMBAT_NOTE_MAX_LEN,
    COMBAT_SPEED_MAX_LEN,
    DAMAGE_TYPE_LIST,
    DAMAGE_TYPE_SYNONYM_DICT,
    DEFAULT_SUBCLASS_LEVEL,
    EXT_ITEM_LIST,
    FEAT_MAX_COUNT,
    FEAT_NAME_MAX_LEN,
    FEAT_TEXT_MAX_LEN,
    FEATURE_MAX_COUNT,
    FEATURE_NAME_MAX_LEN,
    FEATURE_RECOVER_MODES,
    FEATURE_TEXT_MAX_LEN,
    HALF_PROF_ROUNDING_LIST,
    HALF_PROF_SCOPE_LIST,
    ITEM_MAX_COUNT,
    ITEM_NAME_MAX_LEN,
    ITEM_QUANTITY_MAX,
    LANGUAGE_EXOTIC_LIST,
    LANGUAGE_STANDARD_LIST,
    MAGIC_ITEM_MAX_COUNT,
    MAGIC_ITEM_NAME_MAX_LEN,
    MAGIC_ITEM_TAG_MAX_LEN,
    MAGIC_ITEM_TEXT_MAX_LEN,
    PROFICIENCY_GROUP_ITEM_MAX,
    PROFICIENCY_GROUP_ITEM_MAX_LEN,
    PROFICIENCY_GROUP_LIST,
    RACE_TRAIT_MAX_COUNT,
    RACE_TRAIT_NAME_MAX_LEN,
    RACE_TRAIT_TEXT_MAX_LEN,
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
    SUBCLASS_LEVEL_5E_DICT,
    SUBCLASS_LEVEL_5R,
    TOOL_OPTION_LIST,
    TRUE_SKILL_LIST,
    WEAPON_CATEGORY_LIST,
    WEAPON_MAX_COUNT,
    WEAPON_NAME_MAX_LEN,
    WEAPON_NOTE_MAX_LEN,
    XP_THRESHOLDS,
    XP_VALUE_MAX,
)

#: 表单分组（顺序即页面分组顺序）
CARD_SPEC_GROUPS: List[Dict[str, str]] = [
    {"id": "identity", "label": "身份", "summary": "姓名、种族、等级、职业、子职、背景与故事"},
    {"id": "core", "label": "属性与检定", "summary": "六属性、熟练、半熟练、额外加值（豁免与技能加值自动计算）"},
    {"id": "combat", "label": "战斗", "summary": "生命值、战斗数值、经验与武器"},
    {"id": "traits", "label": "特性与专长", "summary": "专长、种族/职业特性与限定资源"},
    {"id": "spells", "label": "法术", "summary": "施法属性、法术清单、法术位与契约法术"},
    {"id": "gear", "label": "装备", "summary": "物品、钱币与魔法物品"},
    {"id": "other", "label": "其他", "summary": "战斗记录（建卡时无需填写）"},
]

#: 段清单（顺序必须是 ``CHAR_INFO_KEY_LIST`` 的顺序）
CARD_SPEC_SEGMENTS: List[Dict[str, object]] = [
    {
        "key": CHAR_INFO_KEY_NAME,
        "label": "姓名",
        "group": "identity",
        "required": False,
        "summary": "角色名，检定与先攻列表中使用",
        "example": "伊瑟兰·晨星",
    },
    {
        "key": CHAR_INFO_KEY_RACE,
        "label": "种族",
        "group": "identity",
        "required": False,
        "summary": "",
        "example": "高等精灵",
    },
    {
        "key": CHAR_INFO_KEY_CLASS,
        "label": "职业",
        "group": "identity",
        "required": False,
        "summary": "",
        "example": "法师",
    },
    {
        "key": CHAR_INFO_KEY_SUBCLASS,
        "label": "子职",
        "group": "identity",
        "required": False,
        "summary": "子职名；达到该规则与职业的子职等级后才显示",
        "example": "塑能师",
    },
    {
        "key": CHAR_INFO_KEY_BACKGROUND,
        "label": "背景",
        "group": "identity",
        "required": False,
        "summary": "",
        "example": (
            "背景:智者; 阵营:中立善良; 信仰:密斯特拉; 体型:中型; 年龄:132; "
            "外貌:银发绿眼，深蓝法袍; 个性:喜欢追问原理"
        ),
    },
    {
        "key": CHAR_INFO_KEY_STORY,
        "label": "故事",
        "group": "identity",
        "required": False,
        "summary": "背景故事，可多段，无需手动打空格缩进，最多 1000 字",
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
        "key": CHAR_INFO_KEY_HP,
        "label": "生命值",
        "group": "combat",
        "required": False,
        "summary": "",
        "example": "37/37",
    },
    {
        "key": CHAR_INFO_KEY_HP_DICE,
        "label": "生命骰",
        "group": "combat",
        "required": False,
        "summary": "",
        "example": "5/5 D6",
    },
    {
        "key": CHAR_INFO_KEY_COMBAT,
        "label": "战斗",
        "group": "combat",
        "required": False,
        "summary": "",
        "example": "AC:16; 速度:30",
    },
    {
        "key": CHAR_INFO_KEY_PROGRESS,
        "label": "进度",
        "group": "combat",
        "required": False,
        "summary": "",
        "example": "经验:6500; 激励:有",
    },
    {
        "key": CHAR_INFO_KEY_LEVEL,
        "label": "等级",
        "group": "identity",
        "required": True,
        "summary": "自动计算：熟练加值 = 2 + (等级 - 1) / 4",
        "example": "5",
    },
    {
        "key": CHAR_INFO_KEY_ABILITY,
        "label": "属性",
        "group": "core",
        "required": True,
        "summary": "最终的六个属性值",
        "example": "8/14/16/18/11/8",
    },
    {
        "key": CHAR_INFO_KEY_PROF,
        "label": "熟练",
        "group": "core",
        "required": False,
        "summary": "",
        "example": (
            "奥秘; 历史; 2*调查; 洞悉; 察觉; 智力豁免; 感知豁免; "
            "武器:简易武器; 工具:书法工具; 语言:通用语,精灵语,龙语"
        ),
    },
    {
        "key": CHAR_INFO_KEY_HALF_PROF,
        "label": "半熟练",
        "group": "core",
        "required": False,
        "summary": (
            "半熟练只在没有熟练或专精时生效；不同来源取整不同"
            "（万事通向下、运动健将向上）。"
        ),
        # 不写示例：buildExampleCard 会把示例拼进示例卡，默认示例卡不带半熟练。
        "example": "",
    },
    {
        "key": CHAR_INFO_KEY_EXT,
        "label": "额外加值",
        "group": "core",
        "required": False,
        "summary": "各种检定与豁免的额外加值",
        "example": "豁免:+1",
    },
    {
        "key": CHAR_INFO_KEY_FEATS,
        "label": "专长",
        "group": "traits",
        "required": False,
        "summary": "",
        "example": (
            "魔法学徒（法师）:习得光亮术、心灵之楔与护盾术；护盾术可免法术位施展一次，长休恢复; "
            "属性值提升:智力 +1、感知 +1"
        ),
    },
    {
        "key": CHAR_INFO_KEY_RACE_TRAITS,
        "label": "种族特性",
        "group": "traits",
        "required": False,
        "summary": "",
        "example": (
            "黑暗视觉:60 尺内微光视为明亮，黑暗视为微光; "
            "妖精血统:进行避免或结束魅惑状态的豁免时具有优势; "
            "敏锐感官:获得察觉熟练; "
            "出神:无需睡眠，魔法无法使你入睡；4 小时即可完成长休并保持清醒; "
            "高等精灵血系:习得魔法伎俩；3 级习得侦测魔法、5 级习得迷踪步，"
            "始终准备，各可免法术位施展一次，长休恢复"
        ),
    },
    {
        "key": CHAR_INFO_KEY_CLASS_TRAITS,
        "label": "职业特性",
        "group": "traits",
        "required": False,
        "summary": "",
        "example": (
            "1|仪式学家:法术书中的仪式法术可直接以仪式施展，无需准备; "
            "1|奥术回想:短休时恢复总环阶不超过 3 的法术位（6 环以下），每长休一次; "
            "2|学者:获得调查专精; "
            "3|塑能学者:法术书免费加入燃烧之手、粉碎音波与火球术; "
            "3|强力戏法:伤害戏法攻击失手或目标豁免成功时，仍受一半伤害; "
            "5|记忆法术:短休时可研究法术书，替换一道已准备的一环及以上法术"
        ),
    },
    {
        "key": CHAR_INFO_KEY_WEAPON,
        "label": "武器",
        "group": "combat",
        "required": False,
        "summary": "武器和法术攻击都填在这里",
        "example": (
            "火焰箭+8|2d10火焰|法术攻击, 120尺; "
            "冷冻射线+8|2d8寒冷|法术攻击, 60尺, 速度-10; "
            "匕首+5|1d4+2穿刺|灵巧, 轻型; "
            "长棍+2|1d6-1钝击|奥术法器, 两用(1d8)"
        ),
    },
    {
        "key": CHAR_INFO_KEY_ITEMS,
        "label": "物品",
        "group": "gear",
        "required": False,
        "summary": "普通物品只填名称与数量，不写详细说明",
        "example": (
            "法术书x1; 长棍x1; 匕首x2; 长袍x1; "
            "学者套组x1; 书法工具x1; 书籍（历史）x1; 羊皮纸x8; 治疗药水x1"
        ),
    },
    {
        "key": CHAR_INFO_KEY_COINS,
        "label": "钱币",
        "group": "gear",
        "required": False,
        "summary": "",
        "example": "CP:0; SP:0; EP:0; GP:13; PP:0",
    },
    {
        "key": CHAR_INFO_KEY_RESOURCE,
        "label": "限定资源",
        "group": "traits",
        "required": False,
        "summary": "只记录有使用次数的资源，奥术回想、狂暴等",
        "example": (
            "奥术回想:1/1短休|短休时恢复总环阶不超过 3 的法术位（6 环以下），每长休一次; "
            "魔法学徒:1/1长休|无需法术位施展一次护盾术，长休恢复"
        ),
    },
    {
        "key": CHAR_INFO_KEY_MAGIC_ITEMS,
        "label": "魔法物品",
        "group": "gear",
        "required": False,
        "summary": "特殊物品填在这里，可以写标签和详细说明",
        "example": (
            "战法师魔杖 +1|魔杖，非普通（需施法者同调）|"
            "持握这根魔杖期间，你的法术攻击检定获得 +1 加值。"
            "//此外，你在进行法术攻击检定时无视半身掩护。; "
            "防护斗篷|奇物，非普通（需同调）|着装此斗篷期间，你的 AC 和豁免获得 +1 加值。"
        ),
    },
    {
        "key": CHAR_INFO_KEY_SPELL,
        "label": "法术与法术清单",
        "group": "spells",
        "required": False,
        "summary": "",
        "example": (
            "施法属性:智力; 豁免DC:15; 法术攻击:+8; "
            "火焰箭:0|时间:1动作|距离:120尺|备注:2d10 火焰 / 法术攻击; "
            "冷冻射线:0|时间:1动作|距离:60尺|备注:2d8 寒冷 / 速度-10; "
            "法师之手:0|时间:1动作|距离:30尺|备注:操控物件 / 1分钟; "
            "次级幻象:0|时间:1动作|距离:30尺|材料:是|备注:声音或影像 / 1分钟; "
            "魔法伎俩:0|时间:1动作|距离:10尺|备注:无害小魔法 / 至多1小时; "
            "光亮术:0|时间:1动作|距离:触碰|材料:是|备注:20尺明亮光照 / 1小时; "
            "心灵之楔:0|时间:1动作|距离:60尺|备注:2d6 心灵 / 智力豁免; "
            "护盾术:1*|时间:1反应|距离:自身|备注:+5 AC / 1轮 / 学徒免位1次; "
            "魔法飞弹:1*|时间:1动作|距离:120尺|备注:3d4+3 力场 / 升环+1飞镖; "
            "法师护甲:1*|时间:1动作|距离:触碰|材料:是|备注:AC 13+敏捷 / 8小时; "
            "侦测魔法:1*|时间:1动作或仪式|距离:自身|专注:是|仪式:是|"
            "备注:30尺灵光 / 血系免位1次; "
            "羽落术:1*|时间:1反应|距离:60尺|材料:是|备注:至多5个生物 / 1分钟; "
            "迷踪步:2*|时间:1附赠动作|距离:自身|备注:传送30尺 / 血系免位1次; "
            "蛛网术:2*|时间:1动作|距离:60尺|专注:是|材料:是|备注:20尺立方 / 束缚; "
            "镜影术:2*|时间:1动作|距离:自身|备注:3个分身 / 1分钟; "
            "火球术:3*|时间:1动作|距离:150尺|材料:是|备注:20尺半径 / 8d6 火焰 / 敏捷; "
            "闪电束:3*|时间:1动作|距离:自身|材料:是|备注:100尺线 / 8d6 闪电 / 敏捷; "
            "法术反制:3*|时间:1反应|距离:60尺|备注:体质豁免 / 打断施法; "
            "加速术:3*|时间:1动作|距离:30尺|专注:是|材料:是|"
            "备注:速度翻倍 / +2 AC / 额外动作"
        ),
    },
    {
        "key": CHAR_INFO_KEY_SPELL_SLOTS,
        "label": "法术位与契约法术",
        "group": "spells",
        "required": False,
        "summary": "",
        "example": "1:4/4; 2:3/3; 3:2/2",
    },
    {
        "key": CHAR_INFO_KEY_COMBAT_NOTES,
        "label": "战斗记录",
        "group": "other",
        "required": False,
        "summary": "建卡时无需填写；开团后由骰娘记录战斗中的临时事项",
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

#: 网页建卡器的表单展示顺序（与卡文本回写顺序解耦）。
#:
#: 用户动线要求「先填等级、再填职业与子职」：等级必须排在职业前，
#: 否则子职门槛要来回滚动才能判断。``CARD_SPEC_SEGMENTS`` 的顺序仍必须等于
#: ``CHAR_INFO_KEY_LIST``（卡文本解析顺序），所以单独维护这一份表单顺序。
CARD_SPEC_FORM_ORDER: List[str] = [
    CHAR_INFO_KEY_NAME,
    CHAR_INFO_KEY_RACE,
    CHAR_INFO_KEY_LEVEL,
    CHAR_INFO_KEY_CLASS,
    CHAR_INFO_KEY_SUBCLASS,
    CHAR_INFO_KEY_BACKGROUND,
    CHAR_INFO_KEY_STORY,
    CHAR_INFO_KEY_ABILITY,
    CHAR_INFO_KEY_HALF_PROF,
    CHAR_INFO_KEY_PROF,
    CHAR_INFO_KEY_EXT,
    CHAR_INFO_KEY_HP,
    CHAR_INFO_KEY_HP_DICE,
    CHAR_INFO_KEY_COMBAT,
    CHAR_INFO_KEY_PROGRESS,
    CHAR_INFO_KEY_WEAPON,
    CHAR_INFO_KEY_FEATS,
    CHAR_INFO_KEY_RACE_TRAITS,
    CHAR_INFO_KEY_CLASS_TRAITS,
    CHAR_INFO_KEY_RESOURCE,
    CHAR_INFO_KEY_SPELL,
    CHAR_INFO_KEY_SPELL_SLOTS,
    CHAR_INFO_KEY_ITEMS,
    CHAR_INFO_KEY_COINS,
    CHAR_INFO_KEY_MAGIC_ITEMS,
    CHAR_INFO_KEY_COMBAT_NOTES,
]

#: 表单与校验用到的上限
CARD_SPEC_LIMITS: Dict[str, int] = {
    "level_max": 20,
    "ability_score_min": 1,
    "ability_score_max": 30,
    "signed_bonus_max": 99,
    "class_name_max_len": CLASS_NAME_MAX_LEN,
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
    "race_trait_max_count": RACE_TRAIT_MAX_COUNT,
    "race_trait_name_max_len": RACE_TRAIT_NAME_MAX_LEN,
    "race_trait_text_max_len": RACE_TRAIT_TEXT_MAX_LEN,
    "class_feature_max_count": CLASS_FEATURE_MAX_COUNT,
    "class_feature_name_max_len": CLASS_FEATURE_NAME_MAX_LEN,
    "class_feature_text_max_len": CLASS_FEATURE_TEXT_MAX_LEN,
    "magic_item_max_count": MAGIC_ITEM_MAX_COUNT,
    "magic_item_name_max_len": MAGIC_ITEM_NAME_MAX_LEN,
    "magic_item_tag_max_len": MAGIC_ITEM_TAG_MAX_LEN,
    "magic_item_text_max_len": MAGIC_ITEM_TEXT_MAX_LEN,
    "item_max_count": ITEM_MAX_COUNT,
    "item_name_max_len": ITEM_NAME_MAX_LEN,
    "item_quantity_max": ITEM_QUANTITY_MAX,
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
    "background_keys_5r": list(BACKGROUND_KEY_LIST_5R),
    "background_keys_5e": list(
        BACKGROUND_KEY_LIST_5R + BACKGROUND_KEY_LIST_5E_EXTRA
    ),
    "background_keys": list(BACKGROUND_KEY_LIST),
    "proficiency_groups": list(PROFICIENCY_GROUP_LIST),
    # 熟练分组的结构化选项（网页端复选框 / 多选 / 下拉）
    "armor_categories": list(ARMOR_CATEGORY_LIST),
    "weapon_categories": list(WEAPON_CATEGORY_LIST),
    "tool_options": list(TOOL_OPTION_LIST),
    "languages_standard": list(LANGUAGE_STANDARD_LIST),
    "languages_exotic": list(LANGUAGE_EXOTIC_LIST),
    # 子职等级：5r 全部 3 级；5e 按职业；自定义职业默认 3 级
    "subclass_level_5r": SUBCLASS_LEVEL_5R,
    "subclass_level_5e": dict(SUBCLASS_LEVEL_5E_DICT),
    "default_subclass_level": DEFAULT_SUBCLASS_LEVEL,
    # 1~20 级累计经验门槛（下标 0 = 1 级）
    "xp_thresholds": list(XP_THRESHOLDS),
    # 熟练/额外加值的条目表（顺序即卡文本回写顺序）
    "skills": list(SKILL_LIST),
    "true_skills": list(TRUE_SKILL_LIST),
    "saving_items": list(SAVING_LIST),
    "check_items": list(CHECK_ITEM_LIST),
    "half_prof_scopes": list(HALF_PROF_SCOPE_LIST),
    "half_prof_roundings": list(HALF_PROF_ROUNDING_LIST),
    "ext_items": list(EXT_ITEM_LIST),
    "saving_all_key": SAVING_ALL_KEY,
    # 技能/豁免 → 父属性（网页端预览加值与骰娘同一套算法）
    "skill_parent": dict(SKILL_PARENT_DICT),
    "saving_parent": dict(SAVING_PARENT_DICT),
    # 录入容错：同义词在导入时归一为规范名（与插件解析一致）
    "skill_synonyms": dict(SKILL_SYNONYM_DICT),
    "class_synonyms": dict(CLASS_SYNONYM_DICT),
    "damage_type_synonyms": dict(DAMAGE_TYPE_SYNONYM_DICT),
}

#: 导出给网页建卡器的完整清单
CARD_SPEC: Dict[str, object] = {
    "version": 7,
    "groups": CARD_SPEC_GROUPS,
    "segments": CARD_SPEC_SEGMENTS,
    "output_order": CARD_SPEC_OUTPUT_ORDER,
    "form_order": CARD_SPEC_FORM_ORDER,
    "limits": CARD_SPEC_LIMITS,
    "enums": CARD_SPEC_ENUMS,
}
