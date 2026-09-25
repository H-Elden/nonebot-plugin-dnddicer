"""规则查询命令（.查询/.搜索 + 候选选择）的 nonebug 测试（全离线：假数据源）。

覆盖：开关默认关闭的提示、用法与关键词上限、候选列表渲染、别名（.q/.s）、
数字选择与越界、+/- 翻页（含到头到底）、条目头定位与回退提示、长内容分段、
私有会话可用、服务不可用降级、多端点回退、以及「过期记录 / 他人数字 /
无记录数字」一律不响应（不与其他插件抢消息）；门禁单独用例（service_gate）。

注：NoneBot 群聊会话 id 形如 ``group_<群号>_<用户号>``（已含用户维度），
候选记录按「会话 + 用户」隔离即等价于按用户隔离。
"""

from __future__ import annotations

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11
from query_fakes import (
    PAGE_NARRATIVE,
    PAGE_SPELLS_2024,
    FakeTransport,
    make_candidate,
    make_result,
    make_search_response,
)

from nonebot_plugin_dnddicer.commands import query as query_cmd
from nonebot_plugin_dnddicer.commands import text
from nonebot_plugin_dnddicer.config import get_config
from nonebot_plugin_dnddicer.query import (
    DEFAULT_TTL,
    PAGE_SIZE,
    FiveChmSource,
    default_store,
)
from nonebot_plugin_dnddicer.query.source import MODE_NAME

_BASE = "https://5echmsearch.kagangtuya.top"
_LOCAL = "http://127.0.0.1:13000"

_G = 33333          # 专用群号（与其它测试文件隔离）
_USER = 12345678
_OTHER_USER = 99999999


# ── 夹具 ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_query_state():
    """每个用例前后清理候选记录与数据源注入（用例互不影响）。"""
    default_store.reset()
    yield
    default_store.reset()
    query_cmd.set_source(None)


@pytest.fixture
def enabled_query(monkeypatch):
    """打开查询开关（配置默认关闭，避免默认外呼）。"""
    monkeypatch.setattr(get_config(), "dnddicer_query_enabled", True)


def _install(transport: FakeTransport, base_urls=(_BASE,)) -> FakeTransport:
    """注入假数据源（走真实数据源逻辑，只替换网络层）。"""
    query_cmd.set_source(FiveChmSource(list(base_urls), transport=transport))
    return transport


def _session_id(group_id: int = _G, user_id: int = _USER) -> str:
    """群聊会话 id（NoneBot 形态：group_<群号>_<用户号>）。"""
    return f"group_{group_id}_{user_id}"


def _routes(title_results, full_results=None):
    """（标题查询、全文查询）两条响应路由；全文未给时与标题相同。"""
    return [
        ("titleOnly=true", make_search_response(title_results)),
        (
            "titleOnly=false",
            make_search_response(title_results if full_results is None else full_results),
        ),
    ]


def _group_event(text_str: str, *, user_id: int = _USER, group_id: int = _G):
    return fake_group_message_event_v11(
        message=Message(text_str), user_id=user_id, group_id=group_id
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


def _expected_list(keyword: str, items, *, page: int = 1, pages: int = 1, count=None) -> str:
    """按文案常量拼出候选列表期望文本（items 为 (标题, 分类) 序列）。"""
    lines = [
        text.TXT_QUERY_LIST_HEAD.format(
            keyword=keyword,
            count=count if count is not None else len(items),
            limited="",
            page=page,
            pages=pages,
        )
    ]
    base_no = (page - 1) * PAGE_SIZE
    for offset, (title, category) in enumerate(items):
        lines.append(
            text.TXT_QUERY_LIST_ITEM.format(
                no=base_no + offset + 1,
                title=title,
                category=text.TXT_QUERY_LIST_CATEGORY.format(category=category),
            )
        )
    lines.append(text.TXT_QUERY_LIST_TAIL.format(seconds=int(DEFAULT_TTL)))
    return "\n".join(lines)


def _expected_entry(title: str, category: str, body: str, *, fallback: bool = False) -> str:
    """按文案常量拼出词条回复期望文本。"""
    lines = [text.TXT_QUERY_ENTRY_HEAD.format(category=category, title=title)]
    if fallback:
        lines.append(text.TXT_QUERY_ENTRY_FALLBACK)
    lines.extend(body.strip().splitlines())
    return "\n".join(lines)


# ── 开关、用法与参数 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disabled_by_default(app: App):
    """默认关闭：只回一条提示，不外呼（假传输若被调用会直接报错）。"""
    _install(FakeTransport([]))
    event = _group_event(".查询 火球术")
    await _expect(app, query_cmd.query_matcher, event, text.TXT_QUERY_DISABLED)


@pytest.mark.asyncio
async def test_usage_when_keyword_missing(app: App, enabled_query):
    """.查询 / .搜索 无参数：各自给出用法提示。"""
    _install(FakeTransport([]))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询"),
        text.TXT_QUERY_USAGE.format(usage=text.TXT_QUERY_USAGE_NAME),
    )
    await _expect(
        app,
        query_cmd.search_matcher,
        _group_event(".搜索"),
        text.TXT_QUERY_USAGE.format(usage=text.TXT_QUERY_USAGE_FULL),
    )


@pytest.mark.asyncio
async def test_too_many_keywords(app: App, enabled_query):
    """关键词超过上限：提示且不外呼。"""
    _install(FakeTransport([]))
    event = _group_event(".查询 甲 乙 丙 丁 戊 己")
    await _expect(
        app,
        query_cmd.query_matcher,
        event,
        text.TXT_QUERY_TOO_MANY_KEYWORDS.format(max=query_cmd.MAX_KEYWORDS),
    )


# ── 候选列表 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_candidates_list_literal(app: App, enabled_query):
    """.查询 命中标题精确：候选列表文本（逐字断言）。"""
    _install(FakeTransport(_routes([make_result(1, "火球术", PAGE_SPELLS_2024)])))
    event = _group_event(".查询 火球术")
    await _expect(
        app,
        query_cmd.query_matcher,
        event,
        "「火球术」共 1 条候选（第 1/1 页）：\n"
        "1. 火球术（玩家手册2024）\n"
        "回复数字查看详情，+ / - 翻页（60 秒内有效）",
    )


@pytest.mark.asyncio
async def test_alias_q(app: App, enabled_query):
    """别名 .q：等同 .查询。"""
    _install(FakeTransport(_routes([make_result(1, "火球术", PAGE_SPELLS_2024)])))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".q 火球术"),
        _expected_list("火球术", [("火球术", "玩家手册2024")]),
    )


@pytest.mark.asyncio
async def test_alias_s_full_search(app: App, enabled_query):
    """别名 .s：等同 .搜索（全文模式）。"""
    _install(FakeTransport(_routes([], [make_result(2, "借机攻击", PAGE_NARRATIVE)])))
    await _expect(
        app,
        query_cmd.search_matcher,
        _group_event(".s 借机攻击"),
        _expected_list("借机攻击", [("借机攻击", "玩家手册2024")]),
    )


@pytest.mark.asyncio
async def test_private_chat_available(app: App, enabled_query):
    """私聊可用（查询不依赖群上下文）。"""
    _install(FakeTransport(_routes([make_result(1, "火球术", PAGE_SPELLS_2024)])))
    event = fake_private_message_event_v11(message=Message(".查询 火球术"))
    await _expect(
        app,
        query_cmd.query_matcher,
        event,
        _expected_list("火球术", [("火球术", "玩家手册2024")]),
    )


@pytest.mark.asyncio
async def test_no_result(app: App, enabled_query):
    """无结果：给出换词/全文检索建议。"""
    _install(FakeTransport(_routes([])))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 不存在的词"),
        text.TXT_QUERY_NO_RESULT.format(keyword="不存在的词"),
    )


@pytest.mark.asyncio
async def test_unavailable_after_all_endpoints(app: App, enabled_query):
    """全部端点失败：降级提示（含尝试过的地址数）。"""
    transport = FakeTransport(
        [
            (_LOCAL, ConnectionRefusedError("拒绝连接")),
            (_BASE, TimeoutError("超时")),
        ]
    )
    _install(transport, base_urls=(_LOCAL, _BASE))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 火球术"),
        text.TXT_QUERY_UNAVAILABLE.format(count=2),
    )


@pytest.mark.asyncio
async def test_fallback_endpoint_serves_query(app: App, enabled_query):
    """自建端点不可用 → 自动回退在线端点，查询照常可用。"""
    transport = FakeTransport(
        [
            (_LOCAL, ConnectionRefusedError("拒绝连接")),
            ("titleOnly=true", make_search_response([make_result(1, "火球术", PAGE_SPELLS_2024)])),
        ]
    )
    _install(transport, base_urls=(_LOCAL, _BASE))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 火球术"),
        _expected_list("火球术", [("火球术", "玩家手册2024")]),
    )


# ── 选择、翻页与不干扰 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_select_number_sends_entry(app: App, enabled_query):
    """回复数字：发送词条正文（条目头定位成功）。"""
    _install(FakeTransport(_routes([make_result(1, "二环", PAGE_SPELLS_2024)])))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 镜影术"),
        _expected_list("镜影术", [("二环", "玩家手册2024")]),
    )
    entry_body = (
        "二环 幻术\n"
        "施法时间：1 动作\n"
        "距离：自身\n"
        "成分：V、S\n"
        "持续时间：1 分钟\n"
        "三个镜像出现在你周围，用于迷惑攻击者。"
    )
    await _expect(
        app,
        query_cmd.selection_matcher,
        _group_event("1"),
        _expected_entry("二环", "玩家手册2024", entry_body),
    )


@pytest.mark.asyncio
async def test_select_entry_fallback_note(app: App, enabled_query):
    """未定位到条目（叙述页）：给出页面片段 + 回退提示。"""
    _install(FakeTransport(_routes([], [make_result(5, "优势与劣势", PAGE_NARRATIVE)])))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 优势与劣势"),
        _expected_list("优势与劣势", [("优势与劣势", "玩家手册2024")]),
    )
    await _expect(
        app,
        query_cmd.selection_matcher,
        _group_event("1"),
        _expected_entry("优势与劣势", "玩家手册2024", PAGE_NARRATIVE, fallback=True),
    )


@pytest.mark.asyncio
async def test_select_out_of_range(app: App, enabled_query):
    """编号越界：提示合法范围。"""
    _install(FakeTransport(_routes([make_result(1, "火球术", PAGE_SPELLS_2024)])))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 火球术"),
        _expected_list("火球术", [("火球术", "玩家手册2024")]),
    )
    await _expect(
        app,
        query_cmd.selection_matcher,
        _group_event("9"),
        text.TXT_QUERY_BAD_INDEX.format(no=9, max=1),
    )


@pytest.mark.asyncio
async def test_paging_forward_and_back(app: App, enabled_query):
    """翻页：+ 到下一页、- 回上一页；到头/到底保持不动。"""
    candidates = [make_candidate(i, f"法术{i}") for i in range(1, 11)]
    default_store.put(
        _session_id(), str(_USER), keyword="法术", mode=MODE_NAME, candidates=candidates
    )

    page_two_items = [("法术9", "玩家手册2024"), ("法术10", "玩家手册2024")]
    page_one_items = [(f"法术{i}", "玩家手册2024") for i in range(1, PAGE_SIZE + 1)]

    await _expect(
        app,
        query_cmd.selection_matcher,
        _group_event("+"),
        _expected_list("法术", page_two_items, page=2, pages=2, count=10),
    )
    await _expect(
        app,
        query_cmd.selection_matcher,
        _group_event("-"),
        _expected_list("法术", page_one_items, page=1, pages=2, count=10),
    )
    # 首页再往前翻：仍是第 1 页
    await _expect(
        app,
        query_cmd.selection_matcher,
        _group_event("-"),
        _expected_list("法术", page_one_items, page=1, pages=2, count=10),
    )


@pytest.mark.asyncio
async def test_expired_record_is_silent(app: App, enabled_query):
    """记录过期后：数字消息不再被接管（不打扰正常聊天）。"""
    record = default_store.put(
        _session_id(),
        str(_USER),
        keyword="火球术",
        mode=MODE_NAME,
        candidates=[make_candidate(1, "火球术")],
    )
    record.touched_at -= DEFAULT_TTL * 2

    await _expect_silence(app, query_cmd.selection_matcher, _group_event("1"))


@pytest.mark.asyncio
async def test_other_user_number_is_silent(app: App, enabled_query):
    """候选记录只响应发起者本人：他人发数字不接管。"""
    default_store.put(
        _session_id(),
        str(_USER),
        keyword="火球术",
        mode=MODE_NAME,
        candidates=[make_candidate(1, "火球术")],
    )
    await _expect_silence(
        app, query_cmd.selection_matcher, _group_event("1", user_id=_OTHER_USER)
    )


@pytest.mark.asyncio
async def test_plain_number_without_record_is_silent(app: App):
    """没有候选记录时：普通数字消息完全不受影响。"""
    await _expect_silence(app, query_cmd.selection_matcher, _group_event("3"))


@pytest.mark.asyncio
async def test_long_entry_split_into_messages(app: App, enabled_query):
    """超长词条：按 20 行分段发送（本例两段）。"""
    body_lines = [f"第{i}行" for i in range(1, 26)]
    long_body = "长词条｜Long Entry\n" + "\n".join(body_lines)
    _install(FakeTransport(_routes([make_result(1, "长词条", long_body)])))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 长词条"),
        _expected_list("长词条", [("长词条", "玩家手册2024")]),
    )

    lines = [text.TXT_QUERY_ENTRY_HEAD.format(category="玩家手册2024", title="长词条")]
    lines.extend(body_lines)
    first = "\n".join(lines[:20])
    second = "\n".join(lines[20:])

    async with app.test_matcher(query_cmd.selection_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        event = _group_event("1")
        ctx.should_call_send(event, first)
        ctx.should_call_send(event, second)
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_overlong_entry_truncated_with_note(app: App, enabled_query):
    """超长词条超过分段上限（3 段）：最后一段追加截断提示。"""
    body_lines = [f"第{i}行" for i in range(1, 71)]
    long_body = "长词条｜Long Entry\n" + "\n".join(body_lines)
    _install(FakeTransport(_routes([make_result(1, "长词条", long_body)])))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 长词条"),
        _expected_list("长词条", [("长词条", "玩家手册2024")]),
    )

    # 定位层给到 60 行上限（正文以省略号结尾），发送层此时正好 3 段；
    # 加上标题行与省略号行共 62 行 → 第 4 段被裁掉并追加截断提示。
    lines = [text.TXT_QUERY_ENTRY_HEAD.format(category="玩家手册2024", title="长词条")]
    lines.extend(body_lines[:60])
    lines.append("…")

    async with app.test_matcher(query_cmd.selection_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        event = _group_event("1")
        for start in (0, 20, 40):
            chunk = lines[start : start + 20]
            if start == 40:
                chunk = chunk + [text.TXT_QUERY_TRUNCATED]
            ctx.should_call_send(event, "\n".join(chunk))
        ctx.receive_event(bot, event)


# ── 门禁（真实服务开关，不旁路）──────────────────────────────────────────


@pytest.mark.service_gate
@pytest.mark.asyncio
async def test_gate_silences_query_in_disabled_group(app: App):
    """关闭服务的群：查询命令静默（与其它命令一致）。"""
    from nonebot_plugin_dnddicer.data import service_state

    group_id = 44444
    await service_state.set_service_enabled(group_id, False)
    await _expect_silence(
        app, query_cmd.query_matcher, _group_event(".查询 火球术", group_id=group_id)
    )
