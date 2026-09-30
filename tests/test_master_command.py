""".master 反馈命令测试（2026-09-30 批次 C）。

覆盖：群聊 / 私聊转发（骰娘私聊配置的骰主 QQ）、来源行格式、收件人取配置、
未配置骰主 QQ、投递失败、空消息用法、超长截断、频率限制（同一人 60 秒一条）、
群聊服务门禁（真实门禁，不旁路）。

收件人一律取配置项 ``dnddicer_master_qq``（单个 QQ），与本仓库宿主配置
``SUPERUSERS`` 无关。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.adapters.onebot.v11.event import Sender

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.commands import master as master_cmd
from nonebot_plugin_dnddicer.commands import text as cmd_text

#: 测试用骰主 QQ（配置项里配它，转发应发给它）
_MASTER_QQ = 90001
#: 测试用群号 / 玩家 QQ
_GROUP = 33333
_PLAYER = 10001


@pytest.fixture(autouse=True)
def _clean_rate_limit():
    """每个用例前后清空频率限制记录（限流状态是模块级、跨用例）。"""
    master_cmd.reset_rate_limit()
    yield
    master_cmd.reset_rate_limit()


def _patch_master_qq(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """把 .master 读到的配置替换为带指定骰主 QQ 的真实 ``Config`` 实例。"""
    from nonebot_plugin_dnddicer import config as config_module

    monkeypatch.setattr(
        master_cmd, "get_config", lambda: config_module.Config(dnddicer_master_qq=value)
    )


def _group_event(message: str, *, user_id: int = _PLAYER, nickname: str = "小鹿",
                 group_id: int = _GROUP):
    return fake_group_message_event_v11(
        message=Message(message),
        group_id=group_id,
        user_id=user_id,
        sender=Sender(card="", nickname=nickname, role="member"),
    )


def _private_event(message: str, *, user_id: int = _PLAYER):
    return fake_private_message_event_v11(message=Message(message), user_id=user_id)


async def _expect(
    app: App,
    event,
    *,
    reply: str,
    forwarded: str | None = None,
    api_exception: Exception | None = None,
) -> None:
    """投递事件并断言回复；``forwarded`` 非空时同时断言一次私聊外呼。"""
    async with app.test_matcher(master_cmd.master_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        if forwarded is not None:
            ctx.should_call_api(
                "send_private_msg",
                data={"user_id": _MASTER_QQ, "message": forwarded},
                exception=api_exception,
            )
        ctx.should_call_send(event, reply)
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_master_group_forward(app: App, monkeypatch: pytest.MonkeyPatch):
    """群聊 .master：骰娘私聊转发给配置的骰主 QQ，发送者收到成功提示。"""
    _patch_master_qq(monkeypatch, str(_MASTER_QQ))
    forwarded = cmd_text.TXT_MASTER_FORWARD.format(
        source=cmd_text.TXT_MASTER_SOURCE_GROUP.format(
            group=_GROUP, name="小鹿", qq=_PLAYER
        ),
        body="先攻列表顺序好像不对",
    )
    await _expect(
        app,
        _group_event(".master 先攻列表顺序好像不对"),
        reply=cmd_text.TXT_MASTER_SENT,
        forwarded=forwarded,
    )


@pytest.mark.asyncio
async def test_master_private_forward(app: App, monkeypatch: pytest.MonkeyPatch):
    """私聊 .master：同样转发，来源行写「私聊（QQ …）」。"""
    _patch_master_qq(monkeypatch, str(_MASTER_QQ))
    forwarded = cmd_text.TXT_MASTER_FORWARD.format(
        source=cmd_text.TXT_MASTER_SOURCE_PRIVATE.format(qq=_PLAYER),
        body="火球术的伤害算错了",
    )
    await _expect(
        app,
        _private_event(".master 火球术的伤害算错了"),
        reply=cmd_text.TXT_MASTER_SENT,
        forwarded=forwarded,
    )


@pytest.mark.asyncio
async def test_master_group_card_priority(app: App, monkeypatch: pytest.MonkeyPatch):
    """群聊来源行取群名片（有则优先于昵称）。"""
    _patch_master_qq(monkeypatch, str(_MASTER_QQ))
    event = fake_group_message_event_v11(
        message=Message(".master 反馈一下"),
        group_id=_GROUP,
        user_id=_PLAYER,
        sender=Sender(card="铁匠铺", nickname="阿花", role="member"),
    )
    forwarded = cmd_text.TXT_MASTER_FORWARD.format(
        source=cmd_text.TXT_MASTER_SOURCE_GROUP.format(
            group=_GROUP, name="铁匠铺", qq=_PLAYER
        ),
        body="反馈一下",
    )
    await _expect(app, event, reply=cmd_text.TXT_MASTER_SENT, forwarded=forwarded)


@pytest.mark.asyncio
async def test_master_not_configured(app: App, monkeypatch: pytest.MonkeyPatch):
    """未配置骰主 QQ：只回提示，不外呼。"""
    _patch_master_qq(monkeypatch, "")
    await _expect(
        app, _group_event(".master 有人在吗"), reply=cmd_text.TXT_MASTER_NOT_CONFIGURED
    )


@pytest.mark.asyncio
async def test_master_send_failed(app: App, monkeypatch: pytest.MonkeyPatch):
    """投递失败（骰主未加好友等）：回可读提示，不抛异常。"""
    _patch_master_qq(monkeypatch, str(_MASTER_QQ))
    await _expect(
        app,
        _group_event(".master 反馈"),
        reply=cmd_text.TXT_MASTER_SEND_FAILED,
        forwarded=cmd_text.TXT_MASTER_FORWARD.format(
            source=cmd_text.TXT_MASTER_SOURCE_GROUP.format(
                group=_GROUP, name="小鹿", qq=_PLAYER
            ),
            body="反馈",
        ),
        api_exception=Exception("send_private_msg failed"),
    )


@pytest.mark.asyncio
async def test_master_empty_message(app: App, monkeypatch: pytest.MonkeyPatch):
    """空消息：只回用法，不外呼（不读配置也不外呼）。"""
    _patch_master_qq(monkeypatch, str(_MASTER_QQ))
    await _expect(app, _group_event(".master"), reply=cmd_text.TXT_MASTER_USAGE)
    await _expect(app, _group_event(".master   "), reply=cmd_text.TXT_MASTER_USAGE)


@pytest.mark.asyncio
async def test_master_truncates_long_message(app: App, monkeypatch: pytest.MonkeyPatch):
    """超长消息：正文截断到 200 字并在末尾标注「（已截断）」。"""
    _patch_master_qq(monkeypatch, str(_MASTER_QQ))
    await _expect(
        app,
        _group_event(f".master {'长' * 260}"),
        reply=cmd_text.TXT_MASTER_SENT,
        forwarded=cmd_text.TXT_MASTER_FORWARD.format(
            source=cmd_text.TXT_MASTER_SOURCE_GROUP.format(
                group=_GROUP, name="小鹿", qq=_PLAYER
            ),
            body="长" * master_cmd.MAX_MESSAGE_CHARS + cmd_text.TXT_MASTER_TRUNCATED,
        ),
    )


@pytest.mark.asyncio
async def test_master_rate_limited(app: App, monkeypatch: pytest.MonkeyPatch):
    """频率限制：同一人 60 秒内第二条被拒，并提示剩余秒数。"""
    _patch_master_qq(monkeypatch, str(_MASTER_QQ))
    now = [1000.0]
    master_cmd.set_clock(lambda: now[0])
    try:
        await _expect(
            app,
            _group_event(".master 第一条"),
            reply=cmd_text.TXT_MASTER_SENT,
            forwarded=cmd_text.TXT_MASTER_FORWARD.format(
                source=cmd_text.TXT_MASTER_SOURCE_GROUP.format(
                    group=_GROUP, name="小鹿", qq=_PLAYER
                ),
                body="第一条",
            ),
        )
        # 20 秒后：仍需等待 40 秒
        now[0] += 20.0
        await _expect(
            app,
            _group_event(".master 第二条"),
            reply=cmd_text.TXT_MASTER_RATE_LIMITED.format(seconds=40),
        )
        # 又过 45 秒（距上条 65 秒）：放行
        now[0] += 45.0
        await _expect(
            app,
            _group_event(".master 第三条"),
            reply=cmd_text.TXT_MASTER_SENT,
            forwarded=cmd_text.TXT_MASTER_FORWARD.format(
                source=cmd_text.TXT_MASTER_SOURCE_GROUP.format(
                    group=_GROUP, name="小鹿", qq=_PLAYER
                ),
                body="第三条",
            ),
        )
    finally:
        master_cmd.set_clock(None)


@pytest.mark.asyncio
async def test_master_rate_limit_is_per_user(app: App, monkeypatch: pytest.MonkeyPatch):
    """频率限制按人计：另一人不受影响。"""
    _patch_master_qq(monkeypatch, str(_MASTER_QQ))
    master_cmd.set_clock(lambda: 1000.0)
    try:
        await _expect(
            app,
            _group_event(".master 甲", user_id=20001, nickname="甲"),
            reply=cmd_text.TXT_MASTER_SENT,
            forwarded=cmd_text.TXT_MASTER_FORWARD.format(
                source=cmd_text.TXT_MASTER_SOURCE_GROUP.format(
                    group=_GROUP, name="甲", qq=20001
                ),
                body="甲",
            ),
        )
        await _expect(
            app,
            _group_event(".master 乙", user_id=20002, nickname="乙"),
            reply=cmd_text.TXT_MASTER_SENT,
            forwarded=cmd_text.TXT_MASTER_FORWARD.format(
                source=cmd_text.TXT_MASTER_SOURCE_GROUP.format(
                    group=_GROUP, name="乙", qq=20002
                ),
                body="乙",
            ),
        )
    finally:
        master_cmd.set_clock(None)


@pytest.mark.asyncio
async def test_master_failed_send_does_not_count(app: App, monkeypatch: pytest.MonkeyPatch):
    """投递失败不计入频率限制（骰主没加好友时不至于把玩家锁 60 秒）。"""
    _patch_master_qq(monkeypatch, str(_MASTER_QQ))
    master_cmd.set_clock(lambda: 1000.0)
    try:
        await _expect(
            app,
            _group_event(".master 第一次"),
            reply=cmd_text.TXT_MASTER_SEND_FAILED,
            forwarded=cmd_text.TXT_MASTER_FORWARD.format(
                source=cmd_text.TXT_MASTER_SOURCE_GROUP.format(
                    group=_GROUP, name="小鹿", qq=_PLAYER
                ),
                body="第一次",
            ),
            api_exception=Exception("send_private_msg failed"),
        )
        await _expect(
            app,
            _group_event(".master 紧接着再试"),
            reply=cmd_text.TXT_MASTER_SENT,
            forwarded=cmd_text.TXT_MASTER_FORWARD.format(
                source=cmd_text.TXT_MASTER_SOURCE_GROUP.format(
                    group=_GROUP, name="小鹿", qq=_PLAYER
                ),
                body="紧接着再试",
            ),
        )
    finally:
        master_cmd.set_clock(None)


def test_master_helper_functions(monkeypatch: pytest.MonkeyPatch):
    """纯函数：截断、来源行、骰主 QQ 解析。"""
    assert master_cmd.truncate_message("短") == "短"
    long_body = "长" * (master_cmd.MAX_MESSAGE_CHARS + 1)
    truncated = master_cmd.truncate_message(long_body)
    assert truncated == "长" * master_cmd.MAX_MESSAGE_CHARS + cmd_text.TXT_MASTER_TRUNCATED

    assert master_cmd.format_source(_private_event(".master x")) == (
        cmd_text.TXT_MASTER_SOURCE_PRIVATE.format(qq=_PLAYER)
    )
    assert master_cmd.format_source(_group_event(".master x")) == (
        cmd_text.TXT_MASTER_SOURCE_GROUP.format(group=_GROUP, name="小鹿", qq=_PLAYER)
    )

    # 取不到群名片/昵称：来源行省略姓名部分
    nameless = fake_group_message_event_v11(
        message=Message(".master x"),
        group_id=_GROUP,
        user_id=_PLAYER,
        sender=Sender(card="", nickname="", role="member"),
    )
    assert master_cmd.format_source(nameless) == (
        cmd_text.TXT_MASTER_SOURCE_GROUP_NO_NAME.format(group=_GROUP, qq=_PLAYER)
    )

    # 骰主 QQ 解析：留空或非纯数字一律视为未配置
    for value in ("", "   ", "abc", "12345x"):
        _patch_master_qq(monkeypatch, value)
        assert master_cmd.master_qq() == ""
    _patch_master_qq(monkeypatch, str(_MASTER_QQ))
    assert master_cmd.master_qq() == str(_MASTER_QQ)


# ── 帮助体系里的位置 ────────────────────────────────────────────────────


def test_master_registered_as_command():
    """.master 是正式注册命令（`.help master` 走命令详情，不再是只进帮助条目）。"""
    from nonebot_plugin_dnddicer.commands import base, help_layout

    assert "master" in base.get_registered_commands()
    assert base.get_command_doc("master") == "guide/faq"
    assert all(entry.name != "master" for entry in help_layout.HELP_ONLY_ENTRIES)


def test_master_not_listed_in_manage_group():
    """`.help 管理` 组清单不列 .master（发现入口是 .help 联系与 .help master）。"""
    from nonebot_plugin_dnddicer.commands import help_layout

    group = help_layout.find_group("管理")
    assert group is not None
    assert not any(".master" in line for line in group[1])


# ── 群聊服务门禁（真实门禁，不旁路）──────────────────────────────────────


@pytest.mark.service_gate
@pytest.mark.asyncio
async def test_master_silent_in_disabled_group(app: App, monkeypatch: pytest.MonkeyPatch):
    """关闭服务的群：.master 静默（与其他命令一致）。"""
    from nonebot_plugin_dnddicer.data import service_state

    _patch_master_qq(monkeypatch, str(_MASTER_QQ))
    group_id = 55555
    await service_state.set_service_enabled(group_id, False)
    event = _group_event(".master 有人在吗", group_id=group_id)
    async with app.test_matcher(master_cmd.master_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.receive_event(bot, event)
