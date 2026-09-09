""".角色卡 / .状态 / 检定点命令 nonebug 测试。

存储隔离：每个用例使用独立 user_id（角色卡主键 = 群+QQ），互不干扰。
"""

import nonebot
import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11

from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_GROUP = 87654321


def _event(text: str, user_id: int = 10001):
    return fake_group_message_event_v11(
        message=Message(text), group_id=_GROUP, user_id=user_id
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


_RECORD = (
    ".角色卡记录 $姓名$ 伊丽莎白\n"
    "$等级$ 5\n"
    "$生命值$ 20/30(5)\n"
    "$生命骰$ 3/4 D8\n"
    "$属性$ 15/14/13/12/10/8\n"
    "$熟练$ 力量/隐匿\n"
    "$额外加值$ 隐匿:优势"
)


@pytest.mark.asyncio
async def test_char_template(app: App):
    """.角色卡模板 → 示例角色卡文本 + 属性顺序/额外加值提示（8.4 #5）。"""
    from nonebot_plugin_dnddicer.character.services import gen_template_char
    from nonebot_plugin_dnddicer.commands.character import _gen_template_feedback, char_matcher

    expected = _gen_template_feedback()
    assert "$" not in expected.split("——提示")[1], "提示说明文字不得含 $ 字符"
    assert expected.endswith(
        "额外加值段键 = 六属性/技能/豁免/攻击条目, 另有作用于全部的全局键: 豁免 与 攻击\n"
        "额外加值取值 = 可选 优势/劣势 前缀 + ±掷骰表达式, 如: 隐匿:优势+2"
    )
    assert gen_template_char().get_char_info() in expected

    event = _event(".角色卡模板")
    await _expect(app, char_matcher, event, expected)


@pytest.mark.asyncio
async def test_char_miss(app: App):
    """无卡时查看 → 找不到角色卡。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    event = _event(".角色卡", user_id=10002)
    await _expect(app, char_matcher, event, "找不到角色卡")


@pytest.mark.asyncio
async def test_char_set_and_view(app: App):
    """记录 → 成功；再查看 → 输出与存储一致的卡文本。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher
    from nonebot_plugin_dnddicer.data.characters import get_character

    await _expect(app, char_matcher, _event(_RECORD, user_id=10003), "角色卡已设置")

    char = await get_character(_GROUP, 10003)
    assert char is not None and char.name == "伊丽莎白"
    expected = char.get_char_info()
    assert "$姓名$ 伊丽莎白" in expected
    assert "$属性$ 15/14/13/12/10/8" in expected

    event = _event(".角色卡", user_id=10003)
    await _expect(app, char_matcher, event, expected)


@pytest.mark.asyncio
async def test_char_state(app: App):
    """.状态 → HP 摘要（记录中含生命值/生命骰）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, state_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=10008), "角色卡已设置")

    event = _event(".状态", user_id=10008)
    await _expect(
        app,
        state_matcher,
        event,
        "HP:20/30 (5)\n生命骰:3/4 D8",
    )


@pytest.mark.asyncio
async def test_char_delete(app: App):
    """清除后 → 找不到角色卡。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=10005), "角色卡已设置")
    await _expect(app, char_matcher, _event(".角色卡清除", user_id=10005), "角色卡已删除")
    await _expect(app, char_matcher, _event(".角色卡", user_id=10005), "找不到角色卡")


@pytest.mark.asyncio
async def test_check_strength_full_feedback(app: App):
    """.力量检定 → 完整检定反馈（属性检定展示名=力量检定；骰 10，力量 15 → 15）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=10006), "角色卡已设置")

    token = set_runtime(SequenceRuntime([10]))
    try:
        event = _event(".力量检定", user_id=10006)
        # 伊丽莎白 5级 力量15：熟练(力量熟练)加值 3 + 力量调整 2，骰 10 → 15
        expected = (
            "伊丽莎白进行【力量检定】：\n"
            "熟练加值:3 力量调整值:2\n"
            "1D20+2+3=[10]+2+3=15"
        )
        await _expect(app, check_matcher, event, expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_check_saving_and_attack_display_name(app: App):
    """.体质豁免/.敏捷攻击 → 展示名用原名（不含「检定」后缀）。"""
    from nonebot_plugin_dnddicer.commands.character import char_matcher, check_matcher

    await _expect(app, char_matcher, _event(_RECORD, user_id=10009), "角色卡已设置")

    # 伊丽莎白 体质13 → 调整+1，未熟练（8.4 #8 后默认全不熟练）
    token = set_runtime(SequenceRuntime([9]))
    try:
        event = _event(".体质豁免", user_id=10009)
        expected = (
            "伊丽莎白进行【体质豁免】：\n"
            "无熟练加值 体质调整值:1\n"
            "1D20+1=[9]+1=10"
        )
        await _expect(app, check_matcher, event, expected)
    finally:
        reset_runtime(token)

    # 伊丽莎白 敏捷14 → 调整+2；攻击默认不熟练（8.4 #8），无熟练加值
    token = set_runtime(SequenceRuntime([3]))
    try:
        event = _event(".敏捷攻击", user_id=10009)
        expected = (
            "伊丽莎白进行【敏捷攻击】：\n"
            "无熟练加值 敏捷调整值:2\n"
            "1D20+2=[3]+2=5"
        )
        await _expect(app, check_matcher, event, expected)
    finally:
        reset_runtime(token)


@pytest.mark.asyncio
async def test_check_miss_without_char(app: App):
    """无卡时检定 → 找不到角色卡。"""
    from nonebot_plugin_dnddicer.commands.character import check_matcher

    event = _event(".力量检定", user_id=10007)
    await _expect(app, check_matcher, event, "找不到角色卡")
