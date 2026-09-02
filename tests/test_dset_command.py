""".dset 群默认骰面命令测试 + 群默认骰面与 .r 的联动。

存储隔离：本文件统一使用群号 11111（roll 命令测试使用 87654321，互不干扰；
87654321 无群配置时回退全局默认 D20）。
"""

import nonebot
import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.adapters.onebot.v11.event import Sender

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

_GROUP = 11111


def _group_event(text: str, role: str = "member", group_id: int = _GROUP):
    return fake_group_message_event_v11(
        message=Message(text),
        group_id=group_id,
        sender=Sender(card="", nickname="manager" if role != "member" else "player", role=role),
    )


async def _expect(app: App, matcher, event, expected: str):
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_dset_set_by_admin(app: App):
    """管理员设置 .dset 100 → 成功文案（D100）。"""
    from nonebot_plugin_dnddicer.commands.group_config import dset_matcher

    event = _group_event(".dset 100", role="admin")
    await _expect(app, dset_matcher, event, "本群默认掷骰表达式已改为D100。")


@pytest.mark.asyncio
async def test_dset_denied_for_member(app: App):
    """普通成员修改被拒。"""
    from nonebot_plugin_dnddicer.commands.group_config import dset_matcher

    event = _group_event(".dset 100", role="member")
    await _expect(app, dset_matcher, event, "仅群主或管理员可以设置群默认骰面。")


@pytest.mark.asyncio
async def test_dset_query_any_member(app: App):
    """无参数查询（任何成员）：显示当前默认（继承前面用例写入的 D100）。"""
    from nonebot_plugin_dnddicer.commands.group_config import dset_matcher

    event = _group_event(".dset")
    await _expect(
        app,
        dset_matcher,
        event,
        "当前默认掷骰表达式为D100。使用 .dset [表达式] 进行修改。",
    )


@pytest.mark.asyncio
async def test_dset_invalid_input(app: App):
    """非法输入（面数 < 2）被拒并回显原因。"""
    from nonebot_plugin_dnddicer.commands.group_config import dset_matcher

    event = _group_event(".dset 1", role="admin")
    await _expect(app, dset_matcher, event, "默认掷骰表达式无效：默认骰面数至少为2")


@pytest.mark.asyncio
async def test_dset_private_denied(app: App):
    """私聊使用 .dset → 提示仅群聊可用。"""
    from nonebot_plugin_dnddicer.commands.group_config import dset_matcher

    event = fake_private_message_event_v11(message=Message(".dset 100"))
    await _expect(app, dset_matcher, event, "该指令仅在群聊中可用。")


@pytest.mark.asyncio
async def test_roll_uses_group_default_dice(app: App):
    """.r 裸 d 优先使用本群 .dset 设置的默认骰面（联动验证）。"""
    from nonebot_plugin_dnddicer.commands.roll import roll_matcher
    from nonebot_plugin_dnddicer.data.group_config import set_group_config_field

    # 直接经数据层给本文件测试群写入默认 D6
    await set_group_config_field(_GROUP, "default_dice", "D6")

    token = set_runtime(SequenceRuntime([4]))
    try:
        event = _group_event(".r d")  # 群 11111 → 1D6 而非全局 D20
        await _expect(app, roll_matcher, event, "player 的掷骰结果为 1D6=[4]=4")
    finally:
        reset_runtime(token)
