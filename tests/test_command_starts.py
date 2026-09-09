"""命令起始符兼容开关测试（config.dnddicer_use_host_command_starts）。

背景：宿主 NoneBot ``COMMAND_START`` 默认含
"/"——若无条件兼容，"/help"、"/bot" 等常见单词命令可能与本插件同时命中宿主
其他插件（冲突）。约定：默认**只匹配 "." / "。"**；配置为 true 时才叠加宿主
起始符（此时 "/help"、"/bot" 亦可触发）。

实现要点：起始符集合经 ``base._compute_command_starts``（lru_cache）惰性计算，
配置经 ``config._config`` 缓存——测试通过 monkeypatch ``config._config`` 模拟
开关，autouse 夹具在每个用例前后清空起始符缓存保证重算。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.adapters.onebot.v11.event import Sender

from fake_event import fake_group_message_event_v11

from nonebot_plugin_dnddicer.commands import text


@pytest.fixture(autouse=True)
def _clean_command_starts_cache():
    """每个用例前后清空起始符 lru_cache，保证按当前配置重算。"""
    from nonebot_plugin_dnddicer.commands import base

    base._compute_command_starts.cache_clear()
    yield
    base._compute_command_starts.cache_clear()


def _set_host_starts_enabled(monkeypatch: pytest.MonkeyPatch, enabled: bool) -> None:
    """直接替换 config 模块缓存为指定开关的配置（等价环境变量生效后形态）。"""
    from nonebot_plugin_dnddicer import config as config_mod

    monkeypatch.setattr(
        config_mod,
        "_config",
        config_mod.Config(dnddicer_use_host_command_starts=enabled),
    )


def _group_event(text_str: str, role: str = "member", to_me: bool = True):
    return fake_group_message_event_v11(
        message=Message(text_str),
        sender=Sender(card="", nickname=role, role=role),
        to_me=to_me,
    )


async def _expect_silence(app: App, matcher, event) -> None:
    """断言不命中（静默）：出现任何发送即 pytest 失败。"""
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.receive_event(bot, event)


async def _expect(app: App, matcher, event, expected: str) -> None:
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_slash_commands_ignored_by_default(app: App):
    """默认（兼容关）：斜杠命令 /help、/bot 不命中本插件（静默放行宿主）。"""
    from nonebot_plugin_dnddicer.commands.bot import bot_matcher
    from nonebot_plugin_dnddicer.commands.help import help_matcher

    await _expect_silence(app, help_matcher, _group_event("/help"))
    await _expect_silence(app, bot_matcher, _group_event("/bot on", role="owner"))


@pytest.mark.asyncio
async def test_dot_and_chinese_dot_matched_by_default(app: App):
    """默认：点号与中文句号命令照常命中（仅起始符开关生效，不影响既有匹配）。"""
    from nonebot_plugin_dnddicer.commands.help import help_matcher

    await _expect(
        app,
        help_matcher,
        _group_event(".help 不存在"),
        "未找到命令「不存在」。发送 .help 查看全部命令。",
    )
    await _expect(
        app,
        help_matcher,
        _group_event("。帮助 不存在"),
        "未找到命令「不存在」。发送 .help 查看全部命令。",
    )


@pytest.mark.asyncio
async def test_host_starts_enabled_matches_slash(app: App, monkeypatch: pytest.MonkeyPatch):
    """兼容开启后：/help、/bot 命中本插件（斜杠起始符由宿主 COMMAND_START 提供）。"""
    from nonebot_plugin_dnddicer.commands import base
    from nonebot_plugin_dnddicer.commands.bot import bot_matcher
    from nonebot_plugin_dnddicer.commands.help import help_matcher

    _set_host_starts_enabled(monkeypatch, True)

    assert "/" in base.get_command_starts()
    await _expect(
        app,
        help_matcher,
        _group_event("/help 不存在"),
        "未找到命令「不存在」。发送 .help 查看全部命令。",
    )
    await _expect(
        app,
        bot_matcher,
        _group_event("/bot xyz", role="owner"),
        text.TXT_BOT_BAD_ARG,
    )
