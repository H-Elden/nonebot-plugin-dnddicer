"""自定义武器项 / 职业段 / 偷袭骰（服务层解析与命令层录入）。

覆盖：``$武器$`` 单项与多项解析校验、名称限制、职业段（12 职业 + 禁兼职）、
伤害类型容错、偷袭骰自动计算（游荡者等级表）、旧卡兼容与卡面往返；
命令层：``.角色卡记录`` 带新段的录入与查看、保留名（插件命令）拦截。

后续步骤（``.X攻击``/``.X伤害`` 与后缀、``.设置武器``）在本文件继续扩充。
"""

import nonebot
import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

from nonebot_plugin_dnddicer.character.models import DNDCharacter
from nonebot_plugin_dnddicer.character.services import (
    CharacterService,
    gen_template_char,
    get_sneak_attack_dice,
    normalize_class_name,
    normalize_damage_type,
    parse_weapon_item,
    parse_weapon_list,
)

_GROUP = 87654322


@pytest.fixture(autouse=True)
def _clear_store():
    """每个用例前清空角色卡数据（缓存 + JSON）。"""
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file

    _chars._cache = None
    path = get_data_file("characters.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")
    yield


def _event(text: str, user_id: int = 20001):
    return fake_group_message_event_v11(
        message=Message(text), group_id=_GROUP, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


# ── 武器项解析（服务层）──────────────────────────────────────────────────


def test_parse_weapon_item_basic():
    """标准写法：名称+命中加值,伤害表达式+类型。"""
    weapon = parse_weapon_item("短剑+6,1d4+4穿刺")
    assert weapon.name == "短剑"
    assert weapon.attack_bonus == "+6"
    assert weapon.damage_expr == "1d4+4"
    assert weapon.damage_type == "穿刺"
    assert weapon.get_info() == "短剑+6,1d4+4穿刺"


def test_parse_weapon_item_without_bonus():
    """省略命中加值（法术类常见）：火焰箭,2d10火焰。"""
    weapon = parse_weapon_item("火焰箭,2d10火焰")
    assert weapon.name == "火焰箭"
    assert weapon.attack_bonus == ""
    assert weapon.damage_expr == "2d10"
    assert weapon.damage_type == "火焰"


def test_parse_weapon_item_without_type():
    """省略伤害类型：无类型提示。"""
    weapon = parse_weapon_item("短剑+6,1d4+4")
    assert weapon.damage_expr == "1d4+4"
    assert weapon.damage_type == ""


def test_parse_weapon_item_fullwidth_comma():
    """全角逗号与半角等价。"""
    weapon = parse_weapon_item("短剑+6，1d4+4穿刺")
    assert weapon.name == "短剑" and weapon.damage_type == "穿刺"


def test_parse_weapon_item_slash_synonym():
    """伤害类型异译容错：斩击 → 挥砍。"""
    weapon = parse_weapon_item("巨剑+5,2d6+3斩击")
    assert weapon.damage_type == "挥砍"


def test_parse_weapon_item_multi_dice_and_dice_bonus():
    """多骰伤害与骰子加值均合法。"""
    weapon = parse_weapon_item("双头武器+1d4,2d6+1d4+3")
    assert weapon.attack_bonus == "+1d4"
    assert weapon.damage_expr == "2d6+1d4+3"


@pytest.mark.parametrize(
    ("item", "message"),
    [
        ("短剑+6", "武器条目不完整"),
        ("短剑+6,", "武器条目不完整"),
        ("+6,1d4+4", "武器名称不能为空"),
        ("一二三四五六七八九十一二三四五六七八九十甲+1,1d6", "武器名称过长"),
        ("猛虎攻击+5,1d6", "不能包含「攻击」字样"),
        ("命中匕首+1,1d4", "不能包含「命中」字样"),
        ("力量+5,1d6", "不能与检定条目重名"),
        ("短剑+abc,1d4+4", "武器命中加值无效"),
        ("短剑+6,2d6*2", "武器伤害表达式无效"),
        ("短剑+6,(1d4+2)", "武器伤害表达式无效"),
        ("短剑+6,1d4+", "武器伤害表达式无效"),
    ],
)
def test_parse_weapon_item_invalid(item, message):
    with pytest.raises(AssertionError, match=message):
        parse_weapon_item(item)


def test_parse_weapon_item_reserved_command_name():
    """武器名不得与插件固定命令重名（命令层传入保留名）。"""
    with pytest.raises(AssertionError, match="不能与插件命令重名"):
        parse_weapon_item("r+5,1d4", reserved_names=("r", "角色卡"))


def test_parse_weapon_list_multi():
    weapons = parse_weapon_list("短剑+6,1d4+4穿刺/长弓+5,1d8+3穿刺")
    assert [w.name for w in weapons] == ["短剑", "长弓"]


def test_parse_weapon_list_duplicate():
    with pytest.raises(AssertionError, match="武器名称重复"):
        parse_weapon_list("短剑+6,1d4+4/短剑+5,1d6")


def test_parse_weapon_list_limit():
    content = "/".join(f"武器{i}+1,1d6" for i in range(21))
    with pytest.raises(AssertionError, match="武器数量最多 20 件"):
        parse_weapon_list(content)


def test_parse_weapon_item_whitespace_tolerance():
    """兼容性：逗号前后空格 / 全角逗号 / 表达式与加值内部空白均等价。"""
    for item in (
        "长剑+8,  1d8+5挥砍",
        "长剑+8，1d8+5挥砍",
        "长剑+8 , 1d8 + 5 挥砍",
        "长剑+ 8,1d8+5挥砍",
    ):
        weapon = parse_weapon_item(item)
        assert weapon.name == "长剑"
        assert weapon.attack_bonus == "+8"
        assert weapon.damage_expr == "1d8+5"
        assert weapon.damage_type == "挥砍"
        assert weapon.get_info() == "长剑+8,1d8+5挥砍"  # 归一化回写


def test_parse_weapon_item_no_attack_mark():
    """x 标记：不可攻击检定（纯伤害法术）；英文名尾 x 不误判；与加值互斥。"""
    spell = parse_weapon_item("火球术x,8d6火焰")
    assert spell.no_attack is True
    assert spell.name == "火球术"
    assert spell.get_info() == "火球术x,8d6火焰"

    sword = parse_weapon_item("Box+2,1d6")
    assert sword.no_attack is False
    assert sword.name == "Box"

    with pytest.raises(AssertionError, match="不要再写命中加值"):
        parse_weapon_item("火球术x+2,1d6")


# ── 职业与伤害类型归一 ──────────────────────────────────────────────────


def test_normalize_class_name():
    assert normalize_class_name("游荡者") == "游荡者"
    assert normalize_class_name(" 法师 ") == "法师"
    assert normalize_class_name("盗贼") == "游荡者"  # 异译容错


@pytest.mark.parametrize("value", ["圣武士/游荡者", "圣武士兼游荡者", "法师+牧师"])
def test_normalize_class_name_multi_fails(value):
    """复合写法（兼职）明确报错，不做拆分计算。"""
    with pytest.raises(AssertionError, match="暂不支持兼职"):
        normalize_class_name(value)


def test_normalize_class_name_invalid():
    with pytest.raises(AssertionError, match="职业无效"):
        normalize_class_name("龙骑士")


def test_normalize_damage_type():
    assert normalize_damage_type("穿刺") == "穿刺"
    assert normalize_damage_type("斩击") == "挥砍"
    assert normalize_damage_type("未知") == ""


# ── 偷袭骰自动计算 ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("level", "expected"),
    [(1, 1), (2, 1), (3, 2), (4, 2), (5, 3), (11, 6), (19, 10), (20, 10), (25, 10)],
)
def test_sneak_attack_dice_table(level, expected):
    """游荡者偷袭骰 = ceil(等级/2)，封顶 10（规则表 1d6~10d6）。"""
    assert get_sneak_attack_dice(level, "游荡者") == expected


def test_sneak_attack_dice_not_rogue():
    assert get_sneak_attack_dice(5, "战士") == 0
    assert get_sneak_attack_dice(5, "") == 0
    assert get_sneak_attack_dice(0, "游荡者") == 0


# ── 整卡解析与兼容 ──────────────────────────────────────────────────────


def test_parse_character_with_new_fields():
    char = CharacterService.parse(
        "$姓名$ 伊丽莎白\n"
        "$种族$ 半精灵\n"
        "$职业$ 游荡者\n"
        "$子职$ 刺客\n"
        "$等级$ 5\n"
        "$属性$ 15/14/13/12/10/8\n"
        "$武器$ 短剑+6,1d4+4穿刺/长弓+5,1d8+3穿刺",
        "g",
        "u",
    )
    assert char.race == "半精灵"
    assert char.char_class == "游荡者"
    assert char.subclass == "刺客"
    assert [w.name for w in char.weapons] == ["短剑", "长弓"]
    assert char.weapons[0].damage_type == "穿刺"


def test_parse_character_class_multi_fails():
    with pytest.raises(AssertionError, match="暂不支持兼职"):
        CharacterService.parse(
            "$等级$ 3\n$属性$ 15/14/13/12/10/8\n$职业$ 圣武士/游荡者", "g", "u"
        )


def test_character_round_trip_with_weapons():
    """卡面输出可再记录（武器/职业段往返一致）。"""
    content = (
        "$姓名$ 伊丽莎白\n$种族$ 半精灵\n$职业$ 游荡者\n$子职$ 刺客\n"
        "$等级$ 5\n$属性$ 15/14/13/12/10/8\n$武器$ 短剑+6,1d4+4穿刺/长弓+5,1d8+3穿刺"
    )
    char = CharacterService.parse(content, "g", "u")
    again = CharacterService.parse(char.get_char_info(), "g", "u")
    assert again.weapons == char.weapons
    assert again.race == char.race and again.char_class == char.char_class


def test_legacy_character_defaults():
    """旧数据（无新字段）读入 → 默认空，不破坏兼容。"""
    legacy = {
        "group_id": "1",
        "user_id": "2",
        "name": "旧卡",
        "hp_info": {},
        "ability_info": {},
        "is_init": True,
    }
    char = DNDCharacter.model_validate(legacy)
    assert char.race == "" and char.char_class == "" and char.subclass == ""
    assert char.weapons == []


def test_template_char_weapons_recordable():
    """模板卡的武器段可被再次解析（与既有模板闭环测试同源）。"""
    text = gen_template_char().get_char_info()
    char = CharacterService.parse(text, "g2", "u2")
    assert char.char_class == "游荡者"
    assert char.weapons and char.weapons[0].name == "短剑"


# ── 命令层：录入与查看 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_and_view_with_new_fields(app: App):
    """.角色卡记录 带种族/职业/子职/武器 → 记录成功且卡面完整回显。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    content = (
        ".角色卡记录 $姓名$ 伊丽莎白\n"
        "$种族$ 半精灵\n"
        "$职业$ 游荡者\n"
        "$子职$ 刺客\n"
        "$等级$ 5\n"
        "$属性$ 15/14/13/12/10/8\n"
        "$武器$ 短剑+6,1d4+4穿刺/长弓+5,1d8+3穿刺"
    )
    await _expect(app, char_matcher, _event(content), "角色卡已设置")

    expected = (
        "$姓名$ 伊丽莎白\n"
        "$种族$ 半精灵\n"
        "$职业$ 游荡者\n"
        "$子职$ 刺客\n"
        "$等级$ 5\n"
        "$属性$ 15/14/13/12/10/8\n"
        "$武器$ 短剑+6,1d4+4穿刺/长弓+5,1d8+3穿刺"
    )
    await _expect(app, char_matcher, _event(".角色卡"), expected)


@pytest.mark.asyncio
async def test_record_weapon_reserved_name_rejected(app: App):
    """命令层传入保留名：武器名与插件命令同名 → 报错、不落库。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    content = ".角色卡记录 $等级$ 1\n$属性$ 15/14/13/12/10/8\n$武器$ r+5,1d4"
    await _expect(app, char_matcher, _event(content), "武器名称不能与插件命令重名: r")


@pytest.mark.asyncio
async def test_record_weapon_invalid_rejected(app: App):
    """非法武器项（名称含禁词）→ 报错文案面向用户。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    content = ".角色卡记录 $等级$ 1\n$属性$ 15/14/13/12/10/8\n$武器$ 猛虎攻击+5,1d6"
    await _expect(
        app, char_matcher, _event(content), "武器名称不能包含「攻击」字样: 猛虎攻击"
    )


# ── 命令层：攻击检定（.X攻击 / .X命中）──────────────────────────────────

_CARD = (
    ".角色卡记录 $姓名$ 伊丽莎白\n"
    "$职业$ 游荡者\n"  # 5 级游荡者 → 偷袭 3d6
    "$等级$ 5\n"
    "$属性$ 15/14/13/12/10/8\n"
    "$武器$ 短剑+6,1d4+4穿刺/火焰箭,2d10火焰"
)


def _mention_event(*parts, user_id: int = 20010):
    """构造带 @ 段的群消息事件（parts 依次拼接，可为文本或消息段）。"""
    message = Message()
    for part in parts:
        message += part
    return fake_group_message_event_v11(
        message=message, group_id=_GROUP, user_id=user_id
    )


async def _record(app: App, card: str = _CARD, user_id: int = 20001):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(app, char_matcher, _event(card, user_id=user_id), "角色卡已设置")


@pytest.mark.asyncio
async def test_weapon_attack_basic_and_alias(app: App):
    """.短剑攻击 / .短剑命中 → 1D20+武器命中加值（同义）。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)
    expected = (
        "伊丽莎白进行【短剑攻击检定】：\n"
        "武器命中加值:+6\n"
        "1D20+6=[14]+6=20"
    )
    token = set_runtime(SequenceRuntime([14]))
    try:
        await _expect(app, weapon_matcher, _event(".短剑攻击"), expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([14]))
    try:
        await _expect(app, weapon_matcher, _event(".短剑命中"), expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_weapon_attack_advantage_and_mod(app: App):
    """优势 / 劣势 / ±临时加值 / 组合写法。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)

    token = set_runtime(SequenceRuntime([4, 18]))
    try:
        expected = (
            "伊丽莎白进行【短剑攻击检定】：\n"
            "武器命中加值:+6 优势\n"
            "2D20K1+6=MAX{[4], [18]}+6=24"
        )
        await _expect(app, weapon_matcher, _event(".短剑攻击优势"), expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([4, 18]))
    try:
        expected = (
            "伊丽莎白进行【短剑攻击检定】：\n"
            "武器命中加值:+6 劣势\n"
            "2D20KL1+6=MIN{[4], [18]}+6=10"
        )
        await _expect(app, weapon_matcher, _event(".短剑攻击劣势"), expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([14]))
    try:
        expected = (
            "伊丽莎白进行【短剑攻击检定】：\n"
            "武器命中加值:+6\n"
            "1D20+6+2=[14]+6+2=22"
        )
        await _expect(app, weapon_matcher, _event(".短剑攻击+2"), expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([4, 18]))
    try:
        expected = (
            "伊丽莎白进行【短剑攻击检定】：\n"
            "武器命中加值:+6 优势\n"
            "2D20K1+6+2=MAX{[4], [18]}+6+2=26"
        )
        await _expect(app, weapon_matcher, _event(".短剑攻击优势+2"), expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_weapon_attack_multi_and_nat(app: App):
    """N# 批量；天然 20/1 用 DND 术语提示（重击引导 / 必失）。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)

    token = set_runtime(SequenceRuntime([3, 4]))
    try:
        expected = (
            "伊丽莎白进行【2次短剑攻击检定】：\n"
            "武器命中加值:+6\n"
            "1D20+6=[3]+6=9\n1D20+6=[4]+6=10"
        )
        await _expect(app, weapon_matcher, _event(".2#短剑攻击"), expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([20]))
    try:
        expected = (
            "伊丽莎白进行【短剑攻击检定】：\n"
            "武器命中加值:+6\n"
            "1D20+6=[20]+6=26\n"
            "天然20：重击！伤害用 .短剑重击伤害 结算"
        )
        await _expect(app, weapon_matcher, _event(".短剑攻击"), expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([1]))
    try:
        expected = (
            "伊丽莎白进行【短剑攻击检定】：\n"
            "武器命中加值:+6\n"
            "1D20+6=[1]+6=7\n"
            "天然1：必失"
        )
        await _expect(app, weapon_matcher, _event(".短剑攻击"), expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_weapon_attack_no_bonus_weapon(app: App):
    """无命中加值的武器（法术类）→ 无命中加值。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)
    token = set_runtime(SequenceRuntime([15]))
    try:
        expected = (
            "伊丽莎白进行【火焰箭攻击检定】：\n"
            "无命中加值\n"
            "1D20=[15]=15"
        )
        await _expect(app, weapon_matcher, _event(".火焰箭攻击"), expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_weapon_attack_not_found_and_no_char(app: App):
    """未设置该武器 → 引导提示；无卡 → 找不到角色卡。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)
    await _expect(
        app, weapon_matcher, _event(".长枪攻击"),
        "未找到武器「长枪」。可用 .设置武器 查看已有武器或添加新武器。",
    )

    await _expect(
        app, weapon_matcher, _event(".短剑攻击", user_id=20099), "找不到角色卡"
    )


@pytest.mark.asyncio
async def test_weapon_attack_mention_target(app: App):
    """DM 代掷：.短剑攻击 @玩家 → 用目标角色卡武器项；目标无卡 → 真 @ 引导。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app, user_id=20012)  # 被 @ 的玩家有卡（DM 自己无卡）

    token = set_runtime(SequenceRuntime([15]))
    try:
        expected = (
            "伊丽莎白进行【短剑攻击检定】：\n"
            "武器命中加值:+6\n"
            "1D20+6=[15]+6=21"
        )
        await _expect(
            app, weapon_matcher,
            _mention_event(".短剑攻击 ", MessageSegment.at(20012), user_id=20001),
            expected,
        )
    finally:
        reset_runtime(token)

    await _expect(
        app, weapon_matcher,
        _mention_event(".短剑攻击 ", MessageSegment.at(39993), user_id=20001),
        Message(MessageSegment.at("39993"))
        + " 还没有在本群建立角色卡（可用 .角色卡记录 建卡后再试）",
    )


@pytest.mark.asyncio
async def test_weapon_attack_private_denied(app: App):
    """私聊使用武器攻击 → 仅群聊提示（同角色卡族口径）。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    event = fake_private_message_event_v11(message=Message(".短剑攻击"))
    await _expect(app, weapon_matcher, event, "该指令仅在群聊中可用。")


def test_weapon_attack_let_check_commands_take_over():
    """让位：检定点可解析的条目（属性+攻击）不被武器命令接管。"""
    from nonebot_plugin_dnddicer.commands.weapon import parse_weapon_attack_body

    assert parse_weapon_attack_body("力量攻击") is None
    assert parse_weapon_attack_body("敏捷攻击优势") is None
    assert parse_weapon_attack_body("短剑攻击") == (1, "短剑", "")
    assert parse_weapon_attack_body("2#短剑攻击优势+2") == (2, "短剑", "优势+2")
    assert parse_weapon_attack_body("火焰箭命中") == (1, "火焰箭", "")
    # 不含「攻击/命中」→ 攻击解析不接管（伤害命令由伤害解析处理）
    assert parse_weapon_attack_body("短剑伤害") is None


# ── 命令层：伤害（.X伤害）与后缀 ───────────────────────────────────────


@pytest.mark.asyncio
async def test_weapon_damage_basic_and_type(app: App):
    """.短剑伤害 → 伤害骰 + 类型提示；无类型武器省略类型词。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)
    token = set_runtime(SequenceRuntime([4]))
    try:
        expected = (
            "伊丽莎白用【短剑】造成了 8 点穿刺伤害：\n"
            "1D4+4=[4]+4=8"
        )
        await _expect(app, weapon_matcher, _event(".短剑伤害"), expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([7, 3]))
    try:
        expected = (
            "伊丽莎白用【火焰箭】造成了 10 点火焰伤害：\n"
            "2D10=[7+3]=10"
        )
        await _expect(app, weapon_matcher, _event(".火焰箭伤害"), expected)
    finally:
        reset_runtime(token)

    # 无类型武器（木棍 1d6）
    await _record(
        app,
        card=".角色卡记录 $姓名$ 薇拉\n$等级$ 3\n$属性$ 15/14/13/12/10/8\n$武器$ 木棍+4,1d6",
    )
    token = set_runtime(SequenceRuntime([5]))
    try:
        expected = "薇拉用【木棍】造成了 5 点伤害：\n1D6=[5]=5"
        await _expect(app, weapon_matcher, _event(".木棍伤害"), expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_weapon_damage_suffixes(app: App):
    """重击 / 副手 / 偷袭与组合（游荡者 5 级 → 3d6 偷袭骰）。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)

    token = set_runtime(SequenceRuntime([3, 2]))
    try:
        expected = (
            "伊丽莎白用【短剑】造成了 9 点穿刺伤害（重击）：\n"
            "2D4+4=[3+2]+4=9"
        )
        await _expect(app, weapon_matcher, _event(".短剑重击伤害"), expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([4]))
    try:
        expected = (
            "伊丽莎白用【短剑】造成了 4 点穿刺伤害（副手：不加任何加值）：\n"
            "1D4=[4]=4"
        )
        await _expect(app, weapon_matcher, _event(".短剑副手伤害"), expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([2, 1, 3, 4]))
    try:
        expected = (
            "伊丽莎白用【短剑】造成了 14 点穿刺伤害（含偷袭3D6）：\n"
            "1D4+4+3D6=[2]+4+[1+3+4]=14"
        )
        await _expect(app, weapon_matcher, _event(".短剑偷袭伤害"), expected)
    finally:
        reset_runtime(token)

    # 重击 + 偷袭：偷袭骰同样翻倍（3d6 → 6d6）
    token = set_runtime(SequenceRuntime([3, 2, 1, 2, 3, 4, 5, 6]))
    try:
        expected = (
            "伊丽莎白用【短剑】造成了 30 点穿刺伤害（重击，含偷袭6D6）：\n"
            "2D4+4+6D6=[3+2]+4+[1+2+3+4+5+6]=30"
        )
        await _expect(app, weapon_matcher, _event(".短剑重击偷袭伤害"), expected)
    finally:
        reset_runtime(token)

    # 副手 + 重击：先去常数再翻倍（1d4+4 → 1d4 → 2d4）
    token = set_runtime(SequenceRuntime([3, 2]))
    try:
        expected = (
            "伊丽莎白用【短剑】造成了 5 点穿刺伤害（副手：不加任何加值，重击）：\n"
            "2D4=[3+2]=5"
        )
        await _expect(app, weapon_matcher, _event(".短剑副手重击伤害"), expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_weapon_damage_sneak_rejects(app: App):
    """偷袭后缀：未设职业 → 引导设置；非游荡者 → 提示无偷袭特性。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(
        app,
        card=".角色卡记录 $姓名$ 薇拉\n$等级$ 3\n$属性$ 15/14/13/12/10/8\n$武器$ 短剑+4,1d6",
    )
    await _expect(
        app, weapon_matcher, _event(".短剑偷袭伤害"),
        "「短剑」的偷袭后缀需要职业为游荡者：请先在角色卡设置职业（12 职业名之一）",
    )

    await _record(
        app,
        card=(
            ".角色卡记录 $姓名$ 薇拉\n$职业$ 战士\n$等级$ 3\n"
            "$属性$ 15/14/13/12/10/8\n$武器$ 短剑+4,1d6"
        ),
    )
    await _expect(
        app, weapon_matcher, _event(".短剑偷袭伤害"),
        "当前职业「战士」没有偷袭特性，偷袭后缀不适用",
    )


@pytest.mark.asyncio
async def test_weapon_damage_offhand_no_dice(app: App):
    """副手 + 纯常数伤害（吹箭筒 1 点）→ 提示不适用。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(
        app,
        card=".角色卡记录 $姓名$ 薇拉\n$等级$ 3\n$属性$ 15/14/13/12/10/8\n$武器$ 吹箭筒,1",
    )
    await _expect(
        app, weapon_matcher, _event(".吹箭筒副手伤害"),
        "「吹箭筒」的伤害没有骰子，副手后缀不适用（副手攻击不加任何加值）。",
    )


@pytest.mark.asyncio
async def test_weapon_damage_bad_tail(app: App):
    """「伤害」之后的多余内容 → 可读提示。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app)
    await _expect(
        app, weapon_matcher, _event(".短剑伤害优势"),
        "伤害命令不支持的写法: 优势（用法：.武器名[副手/重击/偷袭]伤害[±加值]，可 @玩家）",
    )


@pytest.mark.asyncio
async def test_weapon_damage_mention_target(app: App):
    """DM 代掷伤害：.短剑伤害 @玩家 → 用目标角色卡武器项。"""
    from nonebot_plugin_dnddicer.commands.weapon import weapon_matcher

    await _record(app, user_id=20012)
    token = set_runtime(SequenceRuntime([4]))
    try:
        expected = (
            "伊丽莎白用【短剑】造成了 8 点穿刺伤害：\n"
            "1D4+4=[4]+4=8"
        )
        await _expect(
            app, weapon_matcher,
            _mention_event(".短剑伤害 ", MessageSegment.at(20012), user_id=20001),
            expected,
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_weapon_spell_no_attack_and_upcast(app: App):
    """x 标记法术：攻击被拒、伤害可用；升环两种写法（预设多条 / 临时加值）。"""
    from nonebot_plugin_dnddicer.commands.weapon import (
        set_weapon_matcher,
        weapon_matcher,
    )

    await _record(app)

    await _expect(
        app, set_weapon_matcher,
        _event(".设置武器 火球术x,8d6火焰/四环火球术x,9d6火焰"),
        "已设置武器：火球术/四环火球术（当前共 4 件）\n"
        "1. 短剑+6,1d4+4穿刺\n2. 火焰箭,2d10火焰\n"
        "3. 火球术x,8d6火焰\n4. 四环火球术x,9d6火焰",
    )

    # 攻击检定被拒（x 标记）
    await _expect(
        app, weapon_matcher, _event(".火球术命中"), "【火球术】不可进行攻击检定！"
    )

    # 升环方式 1：预设多条（.四环火球术伤害）
    token = set_runtime(SequenceRuntime([6, 5, 4, 3, 2, 1, 6, 6, 5]))
    try:
        expected = (
            "伊丽莎白用【四环火球术】造成了 38 点火焰伤害：\n"
            "9D6=[6+5+4+3+2+1+6+6+5]=38"
        )
        await _expect(app, weapon_matcher, _event(".四环火球术伤害"), expected)
    finally:
        reset_runtime(token)

    # 升环方式 2：临时加值（.火球术伤害+1d6）
    token = set_runtime(SequenceRuntime([6, 5, 4, 3, 2, 1, 6, 6, 5]))
    try:
        expected = (
            "伊丽莎白用【火球术】造成了 38 点火焰伤害：\n"
            "8D6+1D6=[6+5+4+3+2+1+6+6]+[5]=38"
        )
        await _expect(app, weapon_matcher, _event(".火球术伤害+1d6"), expected)
    finally:
        reset_runtime(token)

    # 临时加值参与重击翻倍（.短剑重击伤害+1d6）
    token = set_runtime(SequenceRuntime([3, 2, 5, 4]))
    try:
        expected = (
            "伊丽莎白用【短剑】造成了 18 点穿刺伤害（重击）：\n"
            "2D4+4+2D6=[3+2]+4+[5+4]=18"
        )
        await _expect(app, weapon_matcher, _event(".短剑重击伤害+1d6"), expected)
    finally:
        reset_runtime(token)


def test_parse_weapon_damage_body():
    """伤害命令体解析：后缀组合与名称回溯边界。"""
    from nonebot_plugin_dnddicer.commands.weapon import parse_weapon_damage_body

    assert parse_weapon_damage_body("短剑伤害") == ("短剑", [], "")
    assert parse_weapon_damage_body("短剑重击伤害") == ("短剑", ["重击"], "")
    # 后缀从右向左剥（顺序对语义无影响，均按包含判断）
    assert parse_weapon_damage_body("短剑重击偷袭伤害") == ("短剑", ["偷袭", "重击"], "")
    assert parse_weapon_damage_body("短剑副手重击伤害") == ("短剑", ["重击", "副手"], "")
    # 名为「重击」的武器不被剥空误判
    assert parse_weapon_damage_body("重击伤害") == ("重击", [], "")
    assert parse_weapon_damage_body("伤害") is None


def test_damage_transform_functions():
    """重击翻倍与副手去常数（纯函数边界）。"""
    from nonebot_plugin_dnddicer.character.services import (
        apply_critical_to_damage,
        strip_damage_constants,
    )

    assert apply_critical_to_damage("1d4+4") == "2d4+4"
    assert apply_critical_to_damage("2d6+1d4+3") == "4d6+2d4+3"
    assert apply_critical_to_damage("d6") == "2d6"
    assert apply_critical_to_damage("1D8") == "2D8"  # 保留大小写

    assert strip_damage_constants("1d4+4") == "1d4"
    assert strip_damage_constants("2d6+1d4+3") == "2d6+1d4"
    assert strip_damage_constants("1") == ""
    assert strip_damage_constants("-1d4+4") == "-1d4"


# ── 命令层：武器管理（.设置武器 / .删除武器）────────────────────────────


@pytest.mark.asyncio
async def test_set_weapon_add_override_and_use(app: App):
    """新建设置 → 立即可用于 .X攻击；同名覆盖。"""
    from nonebot_plugin_dnddicer.commands.weapon import set_weapon_matcher, weapon_matcher

    await _record(app)
    await _expect(
        app, set_weapon_matcher,
        _event(".设置武器 长弓+5,1d8+3穿刺"),
        "已设置武器：长弓（当前共 3 件）\n"
        "1. 短剑+6,1d4+4穿刺\n2. 火焰箭,2d10火焰\n3. 长弓+5,1d8+3穿刺",
    )

    token = set_runtime(SequenceRuntime([10]))
    try:
        await _expect(
            app, weapon_matcher, _event(".长弓攻击"),
            "伊丽莎白进行【长弓攻击检定】：\n武器命中加值:+5\n1D20+5=[10]+5=15",
        )
    finally:
        reset_runtime(token)

    await _expect(
        app, set_weapon_matcher,
        _event(".设置武器 短剑+7,1d6+4穿刺"),
        "已设置武器：短剑（当前共 3 件）\n"
        "1. 短剑+7,1d6+4穿刺\n2. 火焰箭,2d10火焰\n3. 长弓+5,1d8+3穿刺",
    )


@pytest.mark.asyncio
async def test_set_weapon_multi_and_limit(app: App):
    """一次多条（/ 分隔）；超出数量上限报错。"""
    from nonebot_plugin_dnddicer.commands.weapon import set_weapon_matcher

    await _record(app)
    await _expect(
        app, set_weapon_matcher,
        _event(".设置武器 长弓+5,1d8+3穿刺/木棍+2,1d6钝击"),
        "已设置武器：长弓/木棍（当前共 4 件）\n"
        "1. 短剑+6,1d4+4穿刺\n2. 火焰箭,2d10火焰\n3. 长弓+5,1d8+3穿刺\n4. 木棍+2,1d6钝击",
    )

    # 上限 20 件：现有 4 件 + 新 17 件 = 21 件 → 报错
    extra = "/".join(f"甲{i}+1,1d6" for i in range(1, 18))
    await _expect(
        app, set_weapon_matcher,
        _event(f".设置武器 {extra}"),
        "武器数量最多 20 件",
    )


@pytest.mark.asyncio
async def test_set_weapon_list_and_empty(app: App):
    """无参数：空列表提示 / 当前武器列表；非法条目报错（校验复用）。"""
    from nonebot_plugin_dnddicer.commands.weapon import set_weapon_matcher

    await _expect(
        app, set_weapon_matcher, _event(".设置武器", user_id=20098), "找不到角色卡"
    )

    await _record(
        app,
        card=".角色卡记录 $姓名$ 薇拉\n$等级$ 3\n$属性$ 15/14/13/12/10/8",
    )
    await _expect(
        app, set_weapon_matcher, _event(".设置武器"),
        "还没有设置武器。用法：.设置武器 短剑+6,1d4+4穿刺（多项用 / 分隔）",
    )

    await _record(app)  # _CARD：短剑 + 火焰箭
    await _expect(
        app, set_weapon_matcher, _event(".设置武器"),
        "当前武器（2 件）：\n1. 短剑+6,1d4+4穿刺\n2. 火焰箭,2d10火焰\n"
        "用法：.设置武器 短剑+6,1d4+4穿刺（多项用 / 分隔）；删除用 .删除武器 名称",
    )

    await _expect(
        app, set_weapon_matcher, _event(".设置武器 猛虎攻击+5,1d6"),
        "武器名称不能包含「攻击」字样: 猛虎攻击",
    )


@pytest.mark.asyncio
async def test_del_weapon(app: App):
    """删除单个 / 部分未命中 / 全部未命中 / 无参数用法。"""
    from nonebot_plugin_dnddicer.commands.weapon import del_weapon_matcher, weapon_matcher

    await _record(app)
    await _expect(
        app, del_weapon_matcher, _event(".删除武器 火焰箭"), "已删除武器: 火焰箭"
    )
    await _expect(
        app, weapon_matcher, _event(".火焰箭攻击"),
        "未找到武器「火焰箭」。可用 .设置武器 查看已有武器或添加新武器。",
    )
    await _expect(
        app, del_weapon_matcher, _event(".删除武器 短剑/长枪"),
        "已删除武器: 短剑；未找到: 长枪",
    )
    await _expect(
        app, del_weapon_matcher, _event(".删除武器 长枪"),
        "未找到武器: 长枪（可用 .设置武器 查看当前武器）",
    )
    await _expect(
        app, del_weapon_matcher, _event(".删除武器"),
        "用法：.删除武器 名称（多个用 / 分隔）",
    )


@pytest.mark.asyncio
async def test_weapon_manage_private_denied(app: App):
    """私聊使用管理命令 → 仅群聊提示。"""
    from nonebot_plugin_dnddicer.commands.weapon import (
        del_weapon_matcher,
        set_weapon_matcher,
    )

    cases = (
        (set_weapon_matcher, ".设置武器 短剑+1,1d6"),
        (del_weapon_matcher, ".删除武器 短剑"),
    )
    for matcher, cmd in cases:
        event = fake_private_message_event_v11(message=Message(cmd))
        await _expect(app, matcher, event, "该指令仅在群聊中可用。")
