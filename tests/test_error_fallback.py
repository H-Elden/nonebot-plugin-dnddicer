"""命令层全局异常兜底钩子单元测试（commands/base.py _unknown_error_fallback）。

直接用桩对象驱动钩子函数（nonebug 会把 matcher 运行异常本身判为失败，
不适合端到端触发路径），覆盖：异常为 None / 非本插件 matcher 放行、
本插件 matcher 异常 → 原会话统一回复、兜底回复自身失败不二次抛异常。
"""

from types import SimpleNamespace

import pytest

from nonebot_plugin_dnddicer.commands.text import TXT_UNKNOWN_ERROR


class _StubBot:
    """记录 send 调用的桩 bot；failure 模式时 send 抛异常。"""

    def __init__(self, fail_send: bool = False):
        self.fail_send = fail_send
        self.sent: list[tuple[object, str]] = []

    async def send(self, event, message, **kwargs) -> None:
        if self.fail_send:
            raise RuntimeError("发送失败")
        self.sent.append((event, str(message)))


def _stub_event():
    return SimpleNamespace(get_session_id=lambda: "group_1:user_2")


def _stub_matcher(module_name: str = "nonebot_plugin_dnddicer.commands.hp"):
    return SimpleNamespace(module_name=module_name)


def _fallback():
    from nonebot_plugin_dnddicer.commands.base import _unknown_error_fallback

    return _unknown_error_fallback


@pytest.mark.asyncio
async def test_ignored_without_exception():
    """无异常（正常完成/finish）→ 兜底不介入。"""
    bot = _StubBot()
    await _fallback()(_stub_matcher(), None, bot, _stub_event())
    assert bot.sent == []


@pytest.mark.asyncio
async def test_ignored_for_foreign_matcher():
    """非本插件 matcher 的异常 → 不回复（宿主其他插件不受影响）。"""
    bot = _StubBot()
    await _fallback()(
        _stub_matcher("some_other_plugin.commands.x"),
        RuntimeError("boom"),
        bot,
        _stub_event(),
    )
    assert bot.sent == []


@pytest.mark.asyncio
async def test_replies_unknown_error_for_plugin_matcher():
    """本插件 matcher 未知异常 → 统一文案回复原会话。"""
    bot = _StubBot()
    event = _stub_event()
    await _fallback()(
        _stub_matcher(), RuntimeError("boom"), bot, event
    )
    assert bot.sent == [(event, TXT_UNKNOWN_ERROR)]


@pytest.mark.asyncio
async def test_fallback_send_failure_swallowed():
    """兜底回复发送失败（如 bot 掉线）→ 仅记日志，不二次抛异常。"""
    bot = _StubBot(fail_send=True)
    await _fallback()(
        _stub_matcher(), RuntimeError("boom"), bot, _stub_event()
    )
