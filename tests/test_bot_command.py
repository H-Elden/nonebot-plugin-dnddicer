""".bot 命令与群聊服务开关（白名单门禁）测试。

本文件整体标记 ``service_gate``：走**真实**门禁（conftest 对普通测试自动旁路，
见 tests/conftest.py）。服务状态写入仓库 data/ 下 service_state.json（跨会话
持久），因此每个用例开头先把所用群号 normalize 到目标状态，保证确定性。

专用群号：22222（开关流转）、22223（信息/权限类），与其它测试文件隔离。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.adapters.onebot.v11.event import Sender

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.commands import text
from nonebot_plugin_dnddicer.data import service_state
from nonebot_plugin_dnddicer.engine.roll.karma_runtime import reset_runtime, set_runtime
from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime
from nonebot_plugin_dnddicer.version import __version__

pytestmark = pytest.mark.service_gate

_G_FLOW = 22222
_G_STATE = 22223


def _group_event(
    text_str: str,
    role: str = "member",
    nickname: str = "member",
    group_id: int = _G_STATE,
    to_me: bool = True,
):
    """群消息事件。.bot 在群聊中需 @ 机器人（to_me=True）才响应；适配器剥除
    at 段后命令文本为纯文本，故测试消息不含 at 段、默认 to_me=True，
    未 @ 场景显式传 to_me=False。"""
    return fake_group_message_event_v11(
        message=Message(text_str),
        group_id=group_id,
        sender=Sender(card="", nickname=nickname, role=role),
        to_me=to_me,
    )


async def _set(group_id: int, enabled: bool) -> None:
    """直接经数据层把群号 normalize 到目标服务状态（确定性）。"""
    await service_state.set_service_enabled(group_id, enabled)


async def _expect(app: App, matcher, event, expected: str) -> None:
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _expect_silence(app: App, matcher, event) -> None:
    """断言门禁拦截 = 静默：不注册任何发送期望，出现发送即 pytest 失败。"""
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.receive_event(bot, event)


def _info_lines(state_line: str) -> str:
    return "\n".join(
        [
            text.TXT_BOT_HEAD.format(version=__version__),
            text.TXT_BOT_INTRO,
            state_line,
            text.TXT_BOT_USAGE,
            text.TXT_DOCS_LINK,
        ]
    )


# ── .bot 信息（无参数）───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bot_info_private(app: App):
    """私聊 .bot：显示插件信息（私聊不受群聊服务开关限制）。"""
    from nonebot_plugin_dnddicer.commands.bot import bot_matcher

    event = fake_private_message_event_v11(message=Message(".bot"))
    await _expect(
        app,
        bot_matcher,
        event,
        _info_lines(text.TXT_BOT_STATE_PRIVATE),
    )


@pytest.mark.asyncio
async def test_bot_info_group_off(app: App):
    """关闭的群里 .bot：信息 + 「本群服务未开启」状态行（任何成员可查）。"""
    from nonebot_plugin_dnddicer.commands.bot import bot_matcher

    await _set(_G_STATE, False)
    event = _group_event(".bot")
    await _expect(
        app,
        bot_matcher,
        event,
        _info_lines(text.TXT_BOT_STATE_OFF),
    )


@pytest.mark.asyncio
async def test_bot_info_group_on(app: App):
    """开启的群里 .bot：信息 + 「本群服务已开启」状态行。"""
    from nonebot_plugin_dnddicer.commands.bot import bot_matcher

    await _set(_G_STATE, True)
    event = _group_event(".bot")
    await _expect(
        app,
        bot_matcher,
        event,
        _info_lines(text.TXT_BOT_STATE_ON),
    )


# ── .bot on / .bot off 权限与可用范围 ────────────────────────────────────


@pytest.mark.asyncio
async def test_bot_on_denied_for_member(app: App):
    """关闭的群里普通成员 .bot on → 权限拒绝，状态不变。"""
    from nonebot_plugin_dnddicer.commands.bot import bot_matcher

    await _set(_G_STATE, False)
    event = _group_event(".bot on", role="member")
    await _expect(app, bot_matcher, event, text.TXT_BOT_NO_PERMISSION)
    assert not await service_state.is_service_enabled(_G_STATE)


@pytest.mark.asyncio
async def test_bot_private_on_rejected(app: App):
    """私聊 .bot on → 提示仅群聊可用。"""
    from nonebot_plugin_dnddicer.commands.bot import bot_matcher

    event = fake_private_message_event_v11(message=Message(".bot on"))
    await _expect(app, bot_matcher, event, text.TXT_GROUP_ONLY)


@pytest.mark.asyncio
async def test_bot_group_requires_to_me(app: App):
    """群聊中未 @ 机器人（to_me=False）：.bot 系列一律不响应（静默）。"""
    from nonebot_plugin_dnddicer.commands.bot import bot_matcher

    await _set(_G_STATE, False)
    # 普通成员未 @ 发 .bot（信息查询）
    await _expect_silence(app, bot_matcher, _group_event(".bot", to_me=False))
    # 管理员未 @ 发 .bot on（即使权限足够也不响应）
    await _expect_silence(
        app,
        bot_matcher,
        _group_event(".bot on", role="owner", nickname="owner", to_me=False),
    )


@pytest.mark.asyncio
async def test_bot_invalid_arg(app: App):
    """无效参数 → 用法提示（不受服务开关与权限限制，同 .bot 信息）。"""
    from nonebot_plugin_dnddicer.commands.bot import bot_matcher

    await _set(_G_STATE, False)
    event = _group_event(".bot 安装")
    await _expect(app, bot_matcher, event, text.TXT_BOT_BAD_ARG)


# ── 开关流转与门禁联动（专用群 22222） ───────────────────────────────────


@pytest.mark.asyncio
async def test_bot_on_off_flow_and_gate(app: App):
    """管理员 .bot on → 服务开启、掷骰可用；.bot off → 服务关闭、掷骰静默。"""
    from nonebot_plugin_dnddicer.commands.bot import bot_matcher
    from nonebot_plugin_dnddicer.commands.roll import roll_matcher

    await _set(_G_FLOW, False)

    # 关闭态：.r 静默（门禁拦截）
    await _expect_silence(app, roll_matcher, _group_event(".r d", group_id=_G_FLOW))

    # 管理员 .bot on → 成功；状态落盘
    on_event = _group_event(
        ".bot on", role="owner", nickname="owner", group_id=_G_FLOW
    )
    await _expect(app, bot_matcher, on_event, text.TXT_BOT_ON)
    assert await service_state.is_service_enabled(_G_FLOW)

    # 开启后：掷骰可用
    token = set_runtime(SequenceRuntime([4]))
    try:
        roll_event = _group_event(
            ".r d", role="owner", nickname="owner", group_id=_G_FLOW
        )
        await _expect(app, roll_matcher, roll_event, "owner 的掷骰结果为 1D20=[4]=4")
    finally:
        reset_runtime(token)

    # 管理员 .bot off → 成功；再掷骰静默
    off_event = _group_event(
        ".bot off", role="owner", nickname="owner", group_id=_G_FLOW
    )
    await _expect(app, bot_matcher, off_event, text.TXT_BOT_OFF)
    assert not await service_state.is_service_enabled(_G_FLOW)
    await _expect_silence(app, roll_matcher, _group_event(".r d", group_id=_G_FLOW))


# ── 门禁覆盖范围：关闭的群内各类 matcher 一律静默（.bot 除外）──────────────


@pytest.mark.asyncio
async def test_gate_silences_registered_command(app: App):
    """关闭的群：固定命令（.帮助）静默。"""
    from nonebot_plugin_dnddicer.commands.help import help_matcher

    await _set(_G_STATE, False)
    await _expect_silence(app, help_matcher, _group_event(".帮助"))


@pytest.mark.asyncio
async def test_gate_silences_check_point_command(app: App):
    """关闭的群：检定点命令（.力量检定）静默。"""
    from nonebot_plugin_dnddicer.commands.character import check_matcher

    await _set(_G_STATE, False)
    await _expect_silence(app, check_matcher, _group_event(".力量检定"))


@pytest.mark.asyncio
async def test_gate_silences_initiative_command(app: App):
    """关闭的群：先攻列表命令（.init）静默。"""
    from nonebot_plugin_dnddicer.commands.initiative import initiative_matcher

    await _set(_G_STATE, False)
    await _expect_silence(app, initiative_matcher, _group_event(".init"))
