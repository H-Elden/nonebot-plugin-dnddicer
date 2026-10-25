""".角色卡 / .状态 / 检定点命令 nonebug 测试（2026-10-23 卡库化）。

覆盖：群内新建自动绑定、绑定卡修改、私聊按卡名选中、无默认卡、改名 /
列表 / 绑定 / 解绑 / 清除、旧 .角色卡记录 退役，以及检定点与 @ 目标。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.commands import text
from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_GROUP = 87654321
_OTHER_GROUP = 87654322

_RECORD = (
    "$姓名$ 伊丽莎白\n"
    "$等级$ 5\n"
    "$生命值$ 20/30(5)\n"
    "$生命骰$ 3/4 D8\n"
    "$属性$ 15/14/13/12/10/8\n"
    "$熟练$ 力量/隐匿\n"
    "$额外加值$ 隐匿:优势"
)
_NEW_OK = text.TXT_CHAR_NEW_GROUP.format(name="测试卡")
_MOD_OK = text.TXT_CHAR_MODIFY_OK.format(name="测试卡")


@pytest.fixture(autouse=True)
def _clear_store():
    """每个用例前清空角色卡/先攻表数据（缓存 + JSON）。"""
    from nonebot_plugin_dnddicer.data import characters as _chars
    from nonebot_plugin_dnddicer.data import get_data_file
    from nonebot_plugin_dnddicer.data import hp_records as _hp_records
    from nonebot_plugin_dnddicer.data import initiative as _init
    from nonebot_plugin_dnddicer.data import npc_health as _npc

    _chars._cache = None
    _hp_records._cache = None
    _init._cache = None
    _npc._cache = None
    for name in ("cards.json", "hp_records.json", "initiative.json", "npc_health.json"):
        path = get_data_file(name)
        if path.exists():
            path.write_text("{}", encoding="utf-8")
    yield


def _event(
    text_value: str, user_id: int = 10001, group_id: int = _GROUP
):
    return fake_group_message_event_v11(
        message=Message(text_value), group_id=group_id, user_id=user_id
    )


def _private(text_value: str, user_id: int = 10001):
    return fake_private_message_event_v11(
        message=Message(text_value), user_id=user_id
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _create(
    app: App,
    user_id: int,
    *,
    group_id: int = _GROUP,
    card_name: str = "测试卡",
    content: str = _RECORD,
    expected: str = _NEW_OK,
):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(
        app,
        char_matcher,
        _event(f".角色卡新建 {card_name}\n{content}", user_id, group_id),
        expected,
    )


async def _create_private(
    app: App,
    user_id: int,
    *,
    card_name: str,
    content: str,
):
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(
        app,
        char_matcher,
        _private(f".角色卡新建 {card_name}\n{content}", user_id),
        text.TXT_CHAR_NEW_PRIVATE.format(name=card_name),
    )


# =========================================================================
# 查看 / 状态 / 删除
# =========================================================================


@pytest.mark.asyncio
async def test_char_miss(app: App):
    """群内未绑定 → 提示绑定并引导网页建卡器。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(
        app, char_matcher, _event(".角色卡", 10002),
        text.TXT_CHAR_VIEW_MISS_GROUP.format(url=text.TXT_CARD_BUILDER_URL),
    )


@pytest.mark.asyncio
async def test_char_miss_private(app: App):
    """私聊无卡 → 引导网页建卡器。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(
        app, char_matcher, _private(".角色卡", 10050),
        text.TXT_CHAR_VIEW_MISS_PRIVATE.format(url=text.TXT_CARD_BUILDER_URL),
    )


@pytest.mark.asyncio
async def test_char_set_and_view(app: App):
    """群内新建自动绑定；.角色卡 输出可复制卡文本。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _create(app, 10003)
    char = await get_character(_GROUP, 10003)
    assert char is not None and char.name == "伊丽莎白"
    expected = char.get_char_info()
    assert "$姓名$ 伊丽莎白" in expected
    await _expect(app, char_matcher, _event(".角色卡", 10003), expected)


@pytest.mark.asyncio
async def test_char_state(app: App):
    """.状态 → HP 摘要；私聊多卡需带卡名。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, state_matcher

    await _create(app, 10008)
    await _expect(
        app, state_matcher, _event(".状态", 10008),
        "HP:20/30 (5)\n生命骰:3/4 D8",
    )
    await _create_private(app, 10008, card_name="私卡", content=_RECORD)
    await _expect(
        app, state_matcher, _private(".状态", 10008),
        text.TXT_CHAR_NEED_NAME.format(count=2),
    )
    await _expect(
        app, state_matcher, _private(".状态 私卡", 10008),
        "私卡: HP:20/30 (5)\n生命骰:3/4 D8",
    )


@pytest.mark.asyncio
async def test_char_delete_requires_unbind_and_confirm(app: App):
    """删除已绑定卡拒绝；解绑后仍需确认。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _create(app, 10005)
    await _expect(
        app, char_matcher, _event(".角色卡清除 测试卡 确认", 10005),
        text.TXT_CHAR_DELETE_BOUND.format(
            name="测试卡", groups=str(_GROUP)
        ),
    )
    await _expect(
        app, char_matcher, _event(".角色卡解绑", 10005),
        text.TXT_CHAR_UNBIND_OK,
    )
    await _expect(
        app, char_matcher, _event(".角色卡清除 测试卡", 10005),
        text.TXT_CHAR_DELETE_CONFIRM.format(name="测试卡"),
    )
    await _expect(
        app, char_matcher, _event(".角色卡清除 测试卡 确认", 10005),
        text.TXT_CHAR_DELETE_OK.format(name="测试卡"),
    )
    await _expect(
        app, char_matcher, _event(".角色卡", 10005),
        text.TXT_CHAR_VIEW_MISS_GROUP.format(url=text.TXT_CARD_BUILDER_URL),
    )


# =========================================================================
# 新建 / 修改 / 改名 / 列表
# =========================================================================


@pytest.mark.asyncio
async def test_char_new_requires_full_card(app: App):
    """新建必须含姓名、等级与属性；失败不落库。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(
        app, char_matcher,
        _event(".角色卡新建 测试卡 $姓名$ 甲", 10020),
        "必须设定等级与属性",
    )
    await _expect(
        app, char_matcher,
        _event(".角色卡新建 测试卡 $等级$ 1\n$属性$ 10/10/10/10/10/10", 10020),
        "必须设定姓名",
    )
    await _expect(
        app, char_matcher, _event(".角色卡", 10020),
        text.TXT_CHAR_VIEW_MISS_GROUP.format(url=text.TXT_CARD_BUILDER_URL),
    )


@pytest.mark.asyncio
async def test_char_card_name_rules(app: App):
    """卡名长度/字符/保留词/重名校验。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    long_name = "卡" * 21
    await _expect(
        app, char_matcher,
        _event(f".角色卡新建 {long_name}\n{_RECORD}", 10021),
        "卡名最多 20 个字符",
    )
    await _expect(
        app, char_matcher,
        _event(f".角色卡新建 卡$名\n{_RECORD}", 10021),
        "卡名不能包含 $ 或 @",
    )
    await _expect(
        app, char_matcher,
        _event(f".角色卡新建 列表\n{_RECORD}", 10021),
        "卡名「列表」是保留词，请换一个",
    )
    await _create(app, 10021)
    await _expect(
        app, char_matcher,
        _event(f".角色卡新建 测试卡\n{_RECORD}", 10021),
        "卡名「测试卡」已存在，请换一个",
    )


@pytest.mark.asyncio
async def test_char_modify_segments_and_clear(app: App):
    """修改只覆盖提到的段；空段清空；含等级/属性的多段不整卡覆盖。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    content = _RECORD + "\n$物品$ 治疗药水x2"
    await _create(app, 10030, content=content)
    await _expect(
        app, char_matcher,
        _event(".角色卡修改 测试卡 $姓名$ 新名字\n$物品$ 解毒药x1", 10030),
        _MOD_OK,
    )
    char = await get_character(_GROUP, 10030)
    assert char is not None
    assert char.name == "新名字"
    assert char.items == ["解毒药x1"]
    assert char.ability_info.level == 5

    await _expect(
        app, char_matcher,
        _event(".角色卡修改 测试卡 $物品$", 10030),
        _MOD_OK,
    )
    char = await get_character(_GROUP, 10030)
    assert char is not None and char.items == []

    await _expect(
        app, char_matcher,
        _event(
            ".角色卡修改 测试卡 $等级$ 6\n$属性$ 16/14/13/12/10/8",
            10030,
        ),
        _MOD_OK,
    )
    char = await get_character(_GROUP, 10030)
    assert char is not None and char.ability_info.level == 6
    assert char.name == "新名字"


@pytest.mark.asyncio
async def test_char_modify_atomic_and_required_clear(app: App):
    """未知段/空必填段整条拒绝，卡不变。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _create(app, 10031)
    await _expect(
        app, char_matcher,
        _event(".角色卡修改 测试卡 $不存在$ 1", 10031),
        "未知段: $不存在$（可用段见网页建卡器）",
    )
    await _expect(
        app, char_matcher,
        _event(".角色卡修改 测试卡 $等级$", 10031),
        "等级不能清空",
    )
    char = await get_character(_GROUP, 10031)
    assert char is not None and char.name == "伊丽莎白"
    assert char.ability_info.level == 5


@pytest.mark.asyncio
async def test_char_rename(app: App):
    """群内改名只改绑定卡；新名重复拒绝。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _create(app, 10032)
    await _expect(
        app, char_matcher, _event(".角色卡改名 测试卡 新卡名", 10032),
        text.TXT_CHAR_RENAME_OK.format(old="测试卡", new="新卡名"),
    )
    await _expect(
        app, char_matcher, _event(".角色卡列表", 10032),
        text.TXT_CHAR_LIST_TITLE
        + "\n新卡名（伊丽莎白，5级）"
        + text.TXT_CHAR_LIST_BOUND.format(groups=str(_GROUP))
        + text.TXT_CHAR_LIST_CURRENT,
    )
    await _create_private(
        app, 10032, card_name="重复卡",
        content="$姓名$ 丙\n$等级$ 1\n$属性$ 10/10/10/10/10/10",
    )
    await _expect(
        app, char_matcher, _event(".角色卡改名 新卡名 重复卡", 10032),
        "卡名「重复卡」已存在，请换一个",
    )


@pytest.mark.asyncio
async def test_char_list_group_and_private(app: App):
    """列表：群内标本群绑定；私聊列出全部卡与绑定群。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _create(app, 10033)
    await _create_private(
        app, 10033, card_name="私卡甲",
        content="$姓名$ 甲\n$等级$ 1\n$属性$ 10/10/10/10/10/10",
    )
    await _expect(
        app, char_matcher, _event(".角色卡列表", 10033),
        text.TXT_CHAR_LIST_TITLE
        + "\n测试卡（伊丽莎白，5级）"
        + text.TXT_CHAR_LIST_BOUND.format(groups=str(_GROUP))
        + text.TXT_CHAR_LIST_CURRENT
        + "\n私卡甲（甲，1级）",
    )
    await _expect(
        app, char_matcher, _private(".角色卡列表", 10033),
        text.TXT_CHAR_LIST_TITLE
        + "\n测试卡（伊丽莎白，5级）"
        + text.TXT_CHAR_LIST_BOUND.format(groups=str(_GROUP))
        + "\n私卡甲（甲，1级）",
    )


# =========================================================================
# 私聊多卡 / 绑定 / 解绑
# =========================================================================


@pytest.mark.asyncio
async def test_char_private_multi_selection(app: App):
    """私聊多张卡：不带卡名报错；带卡名查看/修改。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _create_private(
        app, 10040, card_name="卡A",
        content="$姓名$ 甲\n$等级$ 1\n$属性$ 10/10/10/10/10/10",
    )
    await _create_private(
        app, 10040, card_name="卡B",
        content="$姓名$ 乙\n$等级$ 2\n$属性$ 10/10/10/10/10/10",
    )
    await _expect(
        app, char_matcher, _private(".角色卡", 10040),
        text.TXT_CHAR_NEED_NAME.format(count=2),
    )
    await _expect(
        app, char_matcher, _private(".角色卡修改 $等级$ 3", 10040),
        text.TXT_CHAR_NEED_NAME.format(count=2),
    )
    await _expect(
        app, char_matcher, _private(".角色卡 卡A", 10040),
        "$姓名$ 甲\n$等级$ 1\n$属性$ 10/10/10/10/10/10",
    )
    await _expect(
        app, char_matcher, _private(".角色卡修改 卡A $等级$ 3", 10040),
        text.TXT_CHAR_MODIFY_OK.format(name="卡A"),
    )
    await _expect(
        app, char_matcher, _private(".角色卡 卡A", 10040),
        "$姓名$ 甲\n$等级$ 3\n$属性$ 10/10/10/10/10/10",
    )
    await _expect(
        app, char_matcher, _private(".角色卡 @123", 10040),
        text.TXT_CHAR_PRIVATE_TARGET_UNSUPPORTED,
    )


@pytest.mark.asyncio
async def test_char_private_single_omits_name(app: App):
    """私聊只有一张卡时可省略卡名。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _create_private(app, 10041, card_name="唯一卡", content=_RECORD)
    await _expect(
        app, char_matcher, _private(".角色卡", 10041),
        "$姓名$ 伊丽莎白\n$生命值$ 20/30 (5)\n$生命骰$ 3/4 D8\n"
        "$等级$ 5\n$属性$ 15/14/13/12/10/8\n"
        "$熟练$ 力量/隐匿\n$额外加值$ 隐匿:优势",
    )
    await _expect(
        app, char_matcher, _private(".角色卡修改 $物品$ 治疗药水x2", 10041),
        text.TXT_CHAR_MODIFY_OK.format(name="唯一卡"),
    )


@pytest.mark.asyncio
async def test_char_private_bind_and_unbind(app: App):
    """私聊按群号绑定/解绑；骰娘不在群时拒绝。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _create_private(app, 10042, card_name="私卡", content=_RECORD)
    bind_event = _private(f".角色卡绑定 私卡 {_GROUP}", 10042)
    async with app.test_matcher(char_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_api(
            "get_group_list", data={}, result=[{"group_id": _GROUP}]
        )
        ctx.should_call_send(
            bind_event,
            text.TXT_CHAR_BIND_OK.format(name="私卡", group=_GROUP)
            + text.TXT_CHAR_BIND_PRIVATE_HINT,
        )
        ctx.receive_event(bot, bind_event)

    await _expect(
        app, char_matcher, _event(".角色卡", 10042),
        "$姓名$ 伊丽莎白\n$生命值$ 20/30 (5)\n$生命骰$ 3/4 D8\n"
        "$等级$ 5\n$属性$ 15/14/13/12/10/8\n"
        "$熟练$ 力量/隐匿\n$额外加值$ 隐匿:优势",
    )

    await _expect(
        app, char_matcher, _private(f".角色卡解绑 {_GROUP}", 10042),
        text.TXT_CHAR_UNBIND_PRIVATE_OK.format(group=_GROUP),
    )
    await _expect(
        app, char_matcher, _event(".角色卡", 10042),
        text.TXT_CHAR_VIEW_MISS_BOUND,
    )

    await _create_private(
        app, 10043, card_name="私卡2",
        content="$姓名$ 丙\n$等级$ 1\n$属性$ 10/10/10/10/10/10",
    )
    bad_event = _private(f".角色卡绑定 私卡2 {_OTHER_GROUP}", 10043)
    async with app.test_matcher(char_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_api("get_group_list", data={}, result=[{"group_id": _GROUP}])
        ctx.should_call_send(
            bad_event,
            text.TXT_CHAR_BIND_GROUP_MISSING.format(group=_OTHER_GROUP),
        )
        ctx.receive_event(bot, bad_event)


@pytest.mark.asyncio
async def test_char_private_bind_multi_group_warns(app: App):
    """私聊把同一张卡绑到第二个群：照常绑定并提醒数据冲突。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _create_private(app, 10047, card_name="多群卡", content=_RECORD)
    group_list = [{"group_id": _GROUP}, {"group_id": _OTHER_GROUP}]

    first_event = _private(f".角色卡绑定 多群卡 {_GROUP}", 10047)
    async with app.test_matcher(char_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_api("get_group_list", data={}, result=group_list)
        ctx.should_call_send(
            first_event,
            text.TXT_CHAR_BIND_OK.format(name="多群卡", group=_GROUP)
            + text.TXT_CHAR_BIND_PRIVATE_HINT,
        )
        ctx.receive_event(bot, first_event)

    second_event = _private(f".角色卡绑定 多群卡 {_OTHER_GROUP}", 10047)
    async with app.test_matcher(char_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_api("get_group_list", data={}, result=group_list)
        ctx.should_call_send(
            second_event,
            text.TXT_CHAR_BIND_OK.format(name="多群卡", group=_OTHER_GROUP)
            + text.TXT_CHAR_BIND_PRIVATE_HINT
            + "\n"
            + text.TXT_CHAR_BIND_MULTI_GROUP_WARNING,
        )
        ctx.receive_event(bot, second_event)

    # 绑回已经绑过的群不算新增群，不重复提醒
    again_event = _private(f".角色卡绑定 多群卡 {_GROUP}", 10047)
    async with app.test_matcher(char_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_api("get_group_list", data={}, result=group_list)
        ctx.should_call_send(
            again_event,
            text.TXT_CHAR_BIND_OK.format(name="多群卡", group=_GROUP)
            + text.TXT_CHAR_BIND_PRIVATE_HINT,
        )
        ctx.receive_event(bot, again_event)


@pytest.mark.asyncio
async def test_char_group_bind_multi_group_warns(app: App):
    """群内把已绑在其他群的卡绑到本群：照常绑定并提醒数据冲突。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _create(app, 10048)
    await _expect(
        app,
        char_matcher,
        _event(".角色卡绑定 测试卡", 10048, _OTHER_GROUP),
        text.TXT_CHAR_BIND_OK.format(name="测试卡", group=_OTHER_GROUP)
        + "\n"
        + text.TXT_CHAR_BIND_MULTI_GROUP_WARNING,
    )
    # 绑回已经绑过的群不算新增群，不重复提醒
    await _expect(
        app,
        char_matcher,
        _event(".角色卡绑定 测试卡", 10048, _GROUP),
        text.TXT_CHAR_BIND_OK.format(name="测试卡", group=_GROUP),
    )


@pytest.mark.asyncio
async def test_char_group_modify_only_bound(app: App):
    """群内只能修改本群绑定卡；私聊卡不参与。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _create(app, 10044)
    await _create_private(
        app, 10044, card_name="私卡",
        content="$姓名$ 甲\n$等级$ 1\n$属性$ 10/10/10/10/10/10",
    )
    await _expect(
        app, char_matcher,
        _event(".角色卡修改 私卡 $等级$ 2", 10044),
        text.TXT_CHAR_MODIFY_GROUP_MISMATCH.format(name="测试卡"),
    )
    await _expect(
        app, char_matcher,
        _event(".角色卡修改 $等级$ 6", 10044),
        _MOD_OK,
    )


@pytest.mark.asyncio
async def test_char_group_new_and_bind_replace(app: App):
    """群内新建会替换本群绑定；群内也可绑定私聊建好的卡。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _create(app, 10050)
    await _create_private(
        app, 10050, card_name="卡B",
        content="$姓名$ 乙\n$等级$ 2\n$属性$ 10/10/10/10/10/10",
    )
    await _expect(
        app, char_matcher,
        _event(
            ".角色卡新建 卡C\n$姓名$ 丙\n$等级$ 3\n$属性$ 10/10/10/10/10/10",
            10050,
        ),
        text.TXT_CHAR_NEW_GROUP_REPLACED.format(name="卡C", old="测试卡"),
    )
    loaded = await get_character(_GROUP, 10050)
    assert loaded is not None and loaded.name == "丙"

    await _expect(
        app, char_matcher, _event(".角色卡绑定 卡B", 10050),
        text.TXT_CHAR_BIND_REPLACED.format(
            name="卡B", group=_GROUP, old="卡C"
        ),
    )
    loaded = await get_character(_GROUP, 10050)
    assert loaded is not None and loaded.name == "乙"


@pytest.mark.asyncio
async def test_char_record_retired_default_error(app: App):
    """.角色卡记录 不再特殊处理：按普通未匹配走默认错误，卡不变。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _create(app, 10045)
    await _expect(
        app, char_matcher,
        _event(".角色卡记录 $等级$ 1", 10045),
        text.TXT_CHAR_TARGET_MISS.format(name="记录 $等级$ 1"),
    )
    char = await get_character(_GROUP, 10045)
    assert char is not None and char.ability_info.level == 5

    await _create_private(app, 10046, card_name="单卡", content=_RECORD)
    await _expect(
        app, char_matcher,
        _private(".角色卡记录 $等级$ 1", 10046),
        text.TXT_CHAR_NAME_MISS.format(name="记录 $等级$ 1"),
    )


# =========================================================================
# 检定类点命令
# =========================================================================


@pytest.mark.asyncio
async def test_check_strength_full_feedback(app: App):
    """.力量检定 → 完整检定反馈（力量 15 + 力量熟练 3，骰 10 → 15）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _create(app, 10006)
    token = set_runtime(SequenceRuntime([10]))
    try:
        expected = (
            "伊丽莎白进行【力量检定】：\n"
            "熟练加值:3 力量调整值:2\n"
            "1D20+2+3=[10]+2+3=15"
        )
        await _expect(app, check_matcher, _event(".力量检定", 10006), expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_check_saving_display_name(app: App):
    """.体质豁免 → 展示名用原名。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _create(app, 10009)
    token = set_runtime(SequenceRuntime([9]))
    try:
        expected = (
            "伊丽莎白进行【体质豁免】：\n"
            "无熟练加值 体质调整值:1\n"
            "1D20+1=[9]+1=10"
        )
        await _expect(app, check_matcher, _event(".体质豁免", 10009), expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_check_miss_without_char(app: App):
    """无卡时检定 → 统一未绑定提示。"""
    from nonebot_plugin_dnddicer.commands.character import check_matcher

    await _expect(app, check_matcher, _event(".力量检定", 10007), text.TXT_CHAR_MISS)


@pytest.mark.asyncio
async def test_check_critical_success_and_failure(app: App):
    """.力量检定 掷 20/1 → 大成功/大失败播报。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _create(app, 10010)
    token = set_runtime(SequenceRuntime([20]))
    try:
        expected = (
            "伊丽莎白进行【力量检定】：\n"
            "熟练加值:3 力量调整值:2\n"
            "1D20+2+3=[20]+2+3=25\n"
            "好耶！大成功!"
        )
        await _expect(app, check_matcher, _event(".力量检定", 10010), expected)
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([1]))
    try:
        expected = (
            "伊丽莎白进行【力量检定】：\n"
            "熟练加值:3 力量调整值:2\n"
            "1D20+2+3=[1]+2+3=6\n"
            "哇哦！大失败!"
        )
        await _expect(app, check_matcher, _event(".力量检定", 10010), expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_check_multi_critical_summary(app: App):
    """.2#力量检定 连掷 → 汇总另起一行。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _create(app, 10011)
    token = set_runtime(SequenceRuntime([20, 1]))
    try:
        expected = (
            "伊丽莎白进行【2次力量检定】：\n"
            "熟练加值:3 力量调整值:2\n"
            "1D20+2+3=[20]+2+3=25\n"
            "1D20+2+3=[1]+2+3=6\n"
            "1次 大成功 1次 大失败"
        )
        await _expect(app, check_matcher, _event(".2#力量检定", 10011), expected)
    finally:
        reset_runtime(token)


# =========================================================================
# @ 目标
# =========================================================================


def _mention_event(*parts, user_id: int = 31000, group_id: int = _GROUP):
    message = Message()
    for part in parts:
        message += part
    return fake_group_message_event_v11(
        message=message, group_id=group_id, user_id=user_id
    )


@pytest.mark.asyncio
async def test_char_view_other_by_mention_and_name(app: App):
    """.角色卡 @玩家 与 .角色卡 角色名 → 查看他人本群绑定卡。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _create(app, 31010)
    target = await get_character(_GROUP, 31010)
    assert target is not None
    expected = "伊丽莎白 的角色卡：\n" + target.get_char_info()
    await _expect(
        app, char_matcher,
        _mention_event(".角色卡 ", MessageSegment.at(31010)),
        expected,
    )
    await _expect(
        app, char_matcher, _event(".角色卡 伊丽莎白", 31000), expected
    )


@pytest.mark.asyncio
async def test_char_view_other_misses(app: App):
    """@ 无卡 / NPC 条目 / 查无此卡。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _expect(
        app, initiative_matcher, _event(".ri20 独目守卫"),
        "独目守卫的先攻值是 20",
    )
    await _expect(
        app, char_matcher, _event(".角色卡 独目守卫"),
        "「独目守卫」是NPC条目，没有角色卡",
    )
    await _expect(
        app, char_matcher, _event(".角色卡 查无此人"),
        "找不到查无此人的角色卡",
    )
    await _expect(
        app, char_matcher,
        _mention_event(".角色卡 ", MessageSegment.at(39990)),
        Message(MessageSegment.at("39990")) + " 未在本群绑定角色卡",
    )


@pytest.mark.asyncio
async def test_char_and_state_ignore_cardless_hp_record(app: App):
    """只有无卡 HP 记录的玩家：.角色卡 / .状态 仍按未绑定角色卡处理。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, state_matcher
    from nonebot_plugin_dnddicer.commands.hp import hp_matcher

    uid = 39991
    await _expect(
        app, hp_matcher, _event(".hp 10/10", uid),
        "test: HP=10/10\n当前HP:10/10",
    )
    expected = (
        Message(MessageSegment.at(str(uid))) + " 未在本群绑定角色卡"
    )
    await _expect(
        app, char_matcher,
        _mention_event(".角色卡 ", MessageSegment.at(uid)),
        expected,
    )
    await _expect(
        app, state_matcher,
        _mention_event(".状态 ", MessageSegment.at(uid)),
        expected,
    )


@pytest.mark.asyncio
async def test_char_record_and_clear_write_self_only(app: App):
    """新建/清除恒为本人；他人的卡不受影响。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _create(app, 31011)
    await _create(
        app, 31000, card_name="自己的卡",
        content="$姓名$ 自己的卡\n$等级$ 1\n$属性$ 10/10/10/10/10/10",
        expected=text.TXT_CHAR_NEW_GROUP.format(name="自己的卡"),
    )
    sender = await get_character(_GROUP, 31000)
    target = await get_character(_GROUP, 31011)
    assert sender is not None and sender.name == "自己的卡"
    assert target is not None and target.name == "伊丽莎白"

    await _expect(
        app, char_matcher, _event(".角色卡解绑", 31000), text.TXT_CHAR_UNBIND_OK
    )
    await _expect(
        app, char_matcher, _event(".角色卡清除 自己的卡 确认", 31000),
        text.TXT_CHAR_DELETE_OK.format(name="自己的卡"),
    )
    assert await get_character(_GROUP, 31000) is None
    assert await get_character(_GROUP, 31011) is not None


@pytest.mark.asyncio
async def test_state_mention_target(app: App):
    """.状态 @玩家 → 他人本群绑定卡；无卡 → @ 引导。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, state_matcher

    await _create(app, 31012)
    await _expect(
        app, state_matcher,
        _mention_event(".状态 ", MessageSegment.at(31012)),
        "伊丽莎白: HP:20/30 (5)\n生命骰:3/4 D8",
    )
    await _expect(
        app, state_matcher,
        _mention_event(".状态 ", MessageSegment.at(39992)),
        Message(MessageSegment.at("39992")) + " 未在本群绑定角色卡",
    )


@pytest.mark.asyncio
async def test_check_mention_target(app: App):
    """.力量豁免 @玩家 / .敏捷豁免优势 @玩家 → 用目标卡代掷。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _create(app, 31013)
    token = set_runtime(SequenceRuntime([9]))
    try:
        await _expect(
            app, check_matcher,
            _mention_event(".力量豁免 ", MessageSegment.at(31013)),
            "伊丽莎白进行【力量豁免】：\n无熟练加值 力量调整值:2\n"
            "1D20+2=[9]+2=11",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([9, 7]))
    try:
        await _expect(
            app, check_matcher,
            _mention_event(".敏捷豁免优势 ", MessageSegment.at(31013)),
            "伊丽莎白进行【敏捷豁免】：\n无熟练加值 敏捷调整值:2\n"
            "2D20K1+2=MAX{[9], [7]}+2=11",
        )
    finally:
        reset_runtime(token)

    token = set_runtime(SequenceRuntime([3, 4]))
    try:
        await _expect(
            app, check_matcher,
            _mention_event(".2#敏捷豁免 ", MessageSegment.at(31013)),
            "伊丽莎白进行【2次敏捷豁免】：\n无熟练加值 敏捷调整值:2\n"
            "1D20+2=[3]+2=5\n1D20+2=[4]+2=6",
        )
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_check_mention_no_char(app: App):
    """检定点 @ 目标无卡 → 真 @ 段引导。"""
    from nonebot_plugin_dnddicer.commands.character import check_matcher

    await _expect(
        app, check_matcher,
        _mention_event(".力量豁免 ", MessageSegment.at(39993)),
        Message(MessageSegment.at("39993")) + " 未在本群绑定角色卡",
    )


@pytest.mark.asyncio
async def test_check_initiative_mention_binds_owner(app: App):
    """.先攻检定 @玩家 → 以该玩家为 owner 入先攻表。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher
    from nonebot_plugin_dnddicer.data.initiative import get_init_list

    g = 100050
    await _create(app, 31015, group_id=g)
    token = set_runtime(SequenceRuntime([5]))
    try:
        event = _mention_event(
            ".先攻检定 ", MessageSegment.at(31015), user_id=31000, group_id=g
        )
        await _expect(
            app, check_matcher, event,
            "伊丽莎白进行【先攻检定】：\n无熟练加值 敏捷调整值:2\n"
            "伊丽莎白的先攻值是 1D20+2=[5]+2=7",
        )
    finally:
        reset_runtime(token)

    init_data = await get_init_list(g)
    assert init_data is not None
    assert [(e.name, e.owner, e.init) for e in init_data.entities] == [
        ("伊丽莎白", "31015", 7)
    ]
    await _expect(
        app, initiative_matcher, _event(".init", 31000, g),
        "先攻列表如下: \n当前是第1轮,伊丽莎白的回合\n1.伊丽莎白 先攻:7 HP:20/30 (5)",
    )


@pytest.mark.asyncio
async def test_check_private_denied(app: App):
    """检定点仍在私聊提示仅群聊可用。"""
    from nonebot_plugin_dnddicer.commands.character import check_matcher

    await _expect(
        app, check_matcher, _private(".力量检定"), text.TXT_GROUP_ONLY
    )
