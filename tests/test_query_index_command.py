"""骰主索引命令 ``.查询索引`` 的 nonebug 测试（2026-09-26）。

覆盖：群聊一律静默（骰主也不例外）、私聊非骰主给提示、骰主私聊查看状态 /
刷新 / 参数校验、后台刷新完成与失败回报、以及 ``.帮助`` 不显示该命令
（列表由既有逐字断言覆盖，另测 ``.help 查询索引`` 详情不可见）。
"""

from __future__ import annotations

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.commands import atlas as atlas_cmd
from nonebot_plugin_dnddicer.commands import base, text
from nonebot_plugin_dnddicer.commands.help import help_matcher
from nonebot_plugin_dnddicer.query import atlas as atlas_mod

_MASTER = 11111111
_OTHER = 99999999
_G = 33333


def _private_event(message: str, *, user_id: int = _MASTER):
    return fake_private_message_event_v11(message=Message(message), user_id=user_id)


def _group_event(message: str, *, user_id: int = _MASTER):
    return fake_group_message_event_v11(
        message=Message(message), user_id=user_id, group_id=_G
    )


async def _expect(app: App, matcher, event, expected: str) -> None:
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _expect_silence(app: App, matcher, event) -> None:
    """不注册发送期望：出现任何发送即失败（用于「不响应」断言）。"""
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.receive_event(bot, event)


@pytest.fixture
def master(monkeypatch):
    """把 _MASTER 设为骰主（SUPERUSERS）。"""
    monkeypatch.setattr(base, "superusers", lambda: {str(_MASTER)})


class _FakeFetcher:
    """假抓取器：按路径返回预置 HTML。"""

    def __init__(self, pages: dict) -> None:
        self.pages = pages

    async def get_page(self, path: str) -> str:
        if path not in self.pages:
            raise AssertionError(f"未配置页面：{path}")
        return self.pages[path]


@pytest.fixture
def store(tmp_path):
    """注入索引存储（用假抓取器；用例结束后恢复按配置构建）。"""
    fetcher = _FakeFetcher(
        {
            atlas_mod._QUICKREF_PAGES[atlas_mod.KIND_SPELL][0]: (
                '<TR spell="样例法术Sample Spell">'
                '<TD><a href="../玩家手册2024/法术详述/1环.htm#Sample">样例法术</a></TD>'
                "<TD>一环</TD><TD>惑控</TD><TD>法</TD><TD>动作</TD>"
                "<TD>V</TD><TD>S</TD><TD>M</TD><TD>×</TD><TD>×</TD><TD>PHB24</TD></TR>"
            ),
            atlas_mod._QUICKREF_PAGES[atlas_mod.KIND_SPELL][1]: "<TABLE></TABLE>",
        }
    )
    instance = atlas_mod.AtlasStore(
        fetcher, cache_file=tmp_path / "query_atlas.json"
    )
    atlas_cmd.set_store(instance)
    yield instance
    atlas_cmd.set_store(None)


# ── 权限：群聊一律静默、私聊非骰主给提示 ───────────────────────────────


@pytest.mark.asyncio
async def test_group_chat_is_silent_even_for_master(app: App, master, store):
    """群聊里不响应（骰主本人也一样，避免暴露命令存在）。"""
    await _expect_silence(app, atlas_cmd.index_matcher, _group_event(".查询索引"))
    await _expect_silence(
        app, atlas_cmd.index_matcher, _group_event(".查询索引", user_id=_OTHER)
    )


@pytest.mark.asyncio
async def test_private_non_master_gets_notice(app: App, master, store):
    """私聊非骰主：提示该命令仅骰主可用。"""
    await _expect(
        app,
        atlas_cmd.index_matcher,
        _private_event(".查询索引", user_id=_OTHER),
        text.TXT_SUPERUSER_ONLY,
    )


# ── 骰主私聊：状态 / 刷新 / 参数校验 ───────────────────────────────────


@pytest.mark.asyncio
async def test_status_empty(app: App, master, store):
    """未建立索引：给出构建指引。"""
    await _expect(
        app, atlas_cmd.index_matcher, _private_event(".查询索引"), text.TXT_INDEX_STATUS_EMPTY
    )


@pytest.mark.asyncio
async def test_status_text_contains_counts(app: App, master, store):
    """状态文案：含各类标签与构建时间行（直接调用文案函数断言）。"""
    await atlas_cmd.refresh_index([atlas_mod.KIND_SPELL])
    status = atlas_cmd._status_text(atlas_cmd.get_store())
    assert status.startswith("速查索引状态（构建于 ")
    assert "· 法术：1 条" in status
    assert "· 怪物：0 条" in status


@pytest.mark.asyncio
async def test_refresh_reports_progress(app: App, master, store, monkeypatch):
    """刷新：先回报「正在重建」，后台任务被调度（此处替换为 no-op 以便断言）。"""
    calls = []

    async def _noop(bot, event, kinds):
        calls.append(kinds)

    monkeypatch.setattr(atlas_cmd, "_run_refresh", _noop)
    await _expect(
        app,
        atlas_cmd.index_matcher,
        _private_event(".查询索引 刷新 法术"),
        text.TXT_INDEX_REFRESHING.format(kinds="法术"),
    )
    assert calls == [[atlas_mod.KIND_SPELL]]


@pytest.mark.asyncio
async def test_refresh_all_uses_all_kinds(app: App, master, store, monkeypatch):
    """刷新（无类型）：目标为全部类别。"""
    calls = []

    async def _noop(bot, event, kinds):
        calls.append(kinds)

    monkeypatch.setattr(atlas_cmd, "_run_refresh", _noop)
    await _expect(
        app,
        atlas_cmd.index_matcher,
        _private_event(".查询索引 刷新"),
        text.TXT_INDEX_REFRESHING.format(
            kinds="、".join(atlas_mod.KIND_LABELS[k] for k in atlas_mod.BUILD_KINDS)
        ),
    )
    assert calls == [None]


@pytest.mark.asyncio
async def test_refresh_unknown_kind(app: App, master, store):
    """未知类型：给出可用类型清单。"""
    await _expect(
        app,
        atlas_cmd.index_matcher,
        _private_event(".查询索引 刷新 不存在"),
        text.TXT_INDEX_UNKNOWN_KIND.format(
            name="不存在",
            kinds="、".join(atlas_mod.KIND_LABELS[k] for k in atlas_mod.BUILD_KINDS),
        ),
    )


@pytest.mark.asyncio
async def test_usage_when_bad_argument(app: App, master, store):
    """非「刷新」的参数：给出用法。"""
    await _expect(
        app,
        atlas_cmd.index_matcher,
        _private_event(".查询索引 看看"),
        text.TXT_INDEX_USAGE,
    )


# ── 后台刷新：完成 / 失败回报 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_refresh_success_reports_counts(app: App, master, store, monkeypatch):
    """后台刷新成功：回报各类条目数。"""
    sent = []

    async def _fake_send(bot, event, message):
        sent.append(message)

    monkeypatch.setattr(atlas_cmd, "_safe_send", _fake_send)
    await atlas_cmd._run_refresh(None, _private_event(".查询索引 刷新"), [atlas_mod.KIND_SPELL])
    assert sent and sent[0].startswith("索引重建完成")
    assert "· 法术：1 条" in sent[0]


@pytest.mark.asyncio
async def test_run_refresh_failure_reports(app: App, master, tmp_path, monkeypatch):
    """后台刷新失败（站点不可达）：回报失败并保留原索引。"""
    store = atlas_mod.AtlasStore(
        _FakeFetcher({}), cache_file=tmp_path / "query_atlas.json"
    )
    atlas_cmd.set_store(store)
    sent = []

    async def _fake_send(bot, event, message):
        sent.append(message)

    monkeypatch.setattr(atlas_cmd, "_safe_send", _fake_send)
    try:
        await atlas_cmd._run_refresh(None, _private_event(".查询索引 刷新"), None)
    finally:
        atlas_cmd.set_store(None)
    assert sent == [text.TXT_INDEX_REFRESH_FAILED]


# ── .帮助 不显示骰主命令 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_help_detail_hides_superuser_command(app: App):
    """.help 查询索引：骰主命令不进详情（按未找到处理）。"""
    await _expect(
        app,
        help_matcher,
        _group_event(".help 查询索引"),
        "未找到命令「查询索引」。发送 .help 查看全部命令。",
    )
