"""规则查询命令（.查询/.搜索 + 候选选择）的 nonebug 测试（全离线：假数据源）。

覆盖：开关默认关闭的提示、用法与关键词上限、候选列表渲染、别名（.q/.s）、
数字选择与越界、+/- 翻页（含到头到底）、条目头定位与回退提示、长内容分段、
私有会话可用、服务不可用降级、多端点回退、以及「过期记录 / 他人数字 /
无记录数字」一律不响应（不与其他插件抢消息）；门禁单独用例（service_gate）；
图片模式（开关开/关、发图、渲染失败回退、依赖缺失回退与首提示一次）。

注：NoneBot 群聊会话 id 形如 ``group_<群号>_<用户号>``（已含用户维度），
候选记录按「会话 + 用户」隔离即等价于按用户隔离。
"""

from __future__ import annotations

import urllib.parse
from typing import Optional

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11
from query_fakes import (
    PAGE_NARRATIVE,
    PAGE_SPELLS_2024,
    PAGE_TERM_2014,
    FakeTransport,
    make_candidate,
    make_result,
    make_search_response,
)

from nonebot_plugin_dnddicer import render
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

#: 1×1 透明 PNG（假渲染器产物；仅用于断言「发的是图片」）
_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)

#: 镜影术条目正文（PAGE_SPELLS_2024 里「镜影术｜Mirror Image」的条目体）
_MIRROR_BODY = (
    "二环 幻术\n"
    "施法时间：1 动作\n"
    "距离：自身\n"
    "成分：V、S\n"
    "持续时间：1 分钟\n"
    "三个镜像出现在你周围，用于迷惑攻击者。"
)

#: 火球术条目正文（PAGE_SPELLS_2024 里「火球术｜Fireball」的条目体）
_FIREBALL_BODY = (
    "三环 塑能\n"
    "施法时间：1 动作\n"
    "距离：150 尺\n"
    "成分：V、S、M\n"
    "持续时间：立即\n"
    "一道亮光从你的指尖射出，在指定点炸成烈焰。"
)


def _fake_renderer(png: bytes = _PNG_1PX, calls: Optional[list] = None):
    """构造假渲染器（记录调用参数，返回固定 PNG 字节）。"""

    async def _render(title, category, body, source_path, located):
        if calls is not None:
            calls.append(
                {
                    "title": title,
                    "category": category,
                    "body": body,
                    "source_path": source_path,
                    "located": located,
                }
            )
        return png

    return _render



# ── 夹具 ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_query_state():
    """每个用例前后清空候选记录、按处设置、数据源注入与渲染器（互不影响）。"""
    _reset_query_settings()
    default_store.reset()
    yield
    default_store.reset()
    query_cmd.set_source(None)
    render.reset_renderer()
    _reset_query_settings()


def _reset_query_settings() -> None:
    """清空按处设置（缓存 + JSON）——回到「默认文字」。"""
    from nonebot_plugin_dnddicer.data import get_data_file
    from nonebot_plugin_dnddicer.data import query_settings as _qs

    _qs._cache = None
    path = get_data_file("query_settings.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")


async def _enable_image_here(event) -> None:
    """把该事件所在处预设为图片显示（等价于先发一次 .查询图片 on）。"""
    from nonebot_plugin_dnddicer.data import query_settings as _qs

    group_id = getattr(event, "group_id", None)
    key = (
        _qs.group_key(group_id)
        if group_id is not None
        else _qs.private_key(event.user_id)
    )
    await _qs.set_image_enabled(key, True)


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
    """按文案常量拼出候选列表期望文本（items 为 (标题, 分类) 序列）。

    只有一页时不含页码后缀与翻页提示（2026-09-26 起）。
    """
    page_suffix = (
        text.TXT_QUERY_LIST_PAGE_SUFFIX.format(page=page, pages=pages)
        if pages > 1
        else ""
    )
    lines = [
        text.TXT_QUERY_LIST_HEAD.format(
            keyword=keyword,
            count=count if count is not None else len(items),
            limited="",
            page=page_suffix,
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
    tail = (
        text.TXT_QUERY_LIST_TAIL if pages > 1 else text.TXT_QUERY_LIST_TAIL_ONE_PAGE
    )
    lines.append(tail.format(seconds=int(DEFAULT_TTL)))
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


@pytest.mark.asyncio
async def test_multi_keyword_passed_through(app: App, enabled_query):
    """多关键词原样透传：`|`=或、空格=且（语义由服务端定义，插件不改写关键词）。

    实测（2026-09-25，服务端 parseSearchKeywords）：空格分隔为多个关键词组
    （「且」，每组都要命中）、组内 `|` 为「或」、引号可把几个词连成一个短语。
    插件侧只做「最多 5 组」的截流，其余原样交给服务端——本用例锁定这一点。
    """
    transport = _install(
        FakeTransport(
            _routes(
                [
                    make_result(1, "三环", PAGE_SPELLS_2024),
                    make_result(2, "二环", PAGE_SPELLS_2024),
                ]
            )
        )
    )
    for keyword in ("火焰|闪电", "火焰 伤害", "火焰 伤害 闪电"):
        await _expect(
            app,
            query_cmd.query_matcher,
            _group_event(f".查询 {keyword}"),
            _expected_list(
                keyword, [("三环", "玩家手册2024"), ("二环", "玩家手册2024")]
            ),
        )
        expected_param = urllib.parse.urlencode({"keyword": keyword})
        assert any(expected_param in url for url in transport.calls), (
            f"关键词未原样透传：{expected_param}"
        )


# ── 候选列表 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_candidates_list_literal(app: App, enabled_query):
    """.查询 命中多条但只有一页：候选列表不显示页码与翻页提示（逐字断言）。"""
    _install(
        FakeTransport(
            _routes(
                [
                    make_result(1, "火球术", PAGE_SPELLS_2024),
                    make_result(2, "灼热射线", PAGE_SPELLS_2024),
                ]
            )
        )
    )
    event = _group_event(".查询 火球")
    await _expect(
        app,
        query_cmd.query_matcher,
        event,
        "「火球」共 2 条候选：\n"
        "1. 火球术（玩家手册2024）\n"
        "2. 灼热射线（玩家手册2024）\n"
        "回复数字查看详情（60 秒内有效）",
    )


@pytest.mark.asyncio
async def test_single_candidate_goes_straight_to_entry(app: App, enabled_query):
    """唯一候选：跳过候选列表直接展示词条正文，且不生成短时记录。"""
    _install(FakeTransport(_routes([make_result(1, "火球术", PAGE_SPELLS_2024)])))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 火球术"),
        _expected_entry("火球术", "玩家手册2024", _FIREBALL_BODY),
    )
    # 未写候选记录：随后回复数字不被接管（走普通聊天，不出现「没有编号」提示）
    assert default_store.size == 0
    await _expect_silence(app, query_cmd.selection_matcher, _group_event("1"))


@pytest.mark.asyncio
async def test_alias_q(app: App, enabled_query):
    """别名 .q：等同 .查询（唯一候选直接出词条）。"""
    _install(FakeTransport(_routes([make_result(1, "火球术", PAGE_SPELLS_2024)])))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".q 火球术"),
        _expected_entry("火球术", "玩家手册2024", _FIREBALL_BODY),
    )


@pytest.mark.asyncio
async def test_alias_s_full_search(app: App, enabled_query):
    """别名 .s：等同 .搜索（全文模式；唯一候选直接出词条）。"""
    _install(
        FakeTransport(_routes([], [make_result(2, "借机攻击", PAGE_TERM_2014)]))
    )
    await _expect(
        app,
        query_cmd.search_matcher,
        _group_event(".s 借机攻击"),
        _expected_entry(
            "借机攻击",
            "玩家手册2024",
            "当敌人离开你的触及范围时，你可以用反应发动一次近战攻击。",
        ),
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
        _expected_entry("火球术", "玩家手册2024", _FIREBALL_BODY),
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
        _expected_entry("火球术", "玩家手册2024", _FIREBALL_BODY),
    )


# ── 选择、翻页与不干扰 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_select_number_sends_entry(app: App, enabled_query):
    """多条候选回复数字：发送词条正文（条目头定位成功）。"""
    _install(
        FakeTransport(
            _routes(
                [
                    make_result(1, "二环", PAGE_SPELLS_2024),
                    make_result(2, "三环", PAGE_SPELLS_2024),
                ]
            )
        )
    )
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 镜影术"),
        _expected_list(
            "镜影术", [("二环", "玩家手册2024"), ("三环", "玩家手册2024")]
        ),
    )
    await _expect(
        app,
        query_cmd.selection_matcher,
        _group_event("1"),
        _expected_entry("二环", "玩家手册2024", _MIRROR_BODY),
    )


@pytest.mark.asyncio
async def test_select_entry_fallback_note(app: App, enabled_query):
    """未定位到条目（叙述页）：给出页面片段 + 回退提示。"""
    _install(
        FakeTransport(
            _routes(
                [],
                [
                    make_result(5, "优势与劣势", PAGE_NARRATIVE),
                    make_result(6, "优势与劣势速查", PAGE_NARRATIVE),
                ],
            )
        )
    )
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 优势与劣势"),
        _expected_list(
            "优势与劣势",
            [("优势与劣势", "玩家手册2024"), ("优势与劣势速查", "玩家手册2024")],
        ),
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
    _install(
        FakeTransport(
            _routes(
                [
                    make_result(1, "火球术", PAGE_SPELLS_2024),
                    make_result(2, "灼热射线", PAGE_SPELLS_2024),
                ]
            )
        )
    )
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 火球"),
        _expected_list(
            "火球", [("火球术", "玩家手册2024"), ("灼热射线", "玩家手册2024")]
        ),
    )
    await _expect(
        app,
        query_cmd.selection_matcher,
        _group_event("9"),
        text.TXT_QUERY_BAD_INDEX.format(no=9, max=2),
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
    """超长词条：唯一候选直接展示，按 20 行分段发送（本例两段）。"""
    body_lines = [f"第{i}行" for i in range(1, 26)]
    long_body = "长词条｜Long Entry\n" + "\n".join(body_lines)
    _install(FakeTransport(_routes([make_result(1, "长词条", long_body)])))

    lines = [text.TXT_QUERY_ENTRY_HEAD.format(category="玩家手册2024", title="长词条")]
    lines.extend(body_lines)
    first = "\n".join(lines[:20])
    second = "\n".join(lines[20:])

    async with app.test_matcher(query_cmd.query_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        event = _group_event(".查询 长词条")
        ctx.should_call_send(event, first)
        ctx.should_call_send(event, second)
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_overlong_entry_truncated_with_note(app: App, enabled_query):
    """超长词条超过分段上限（3 段）：最后一段追加截断提示。"""
    body_lines = [f"第{i}行" for i in range(1, 71)]
    long_body = "长词条｜Long Entry\n" + "\n".join(body_lines)
    _install(FakeTransport(_routes([make_result(1, "长词条", long_body)])))

    # 定位层给到 60 行上限（正文以省略号结尾），发送层此时正好 3 段；
    # 加上标题行与省略号行共 62 行 → 第 4 段被裁掉并追加截断提示。
    lines = [text.TXT_QUERY_ENTRY_HEAD.format(category="玩家手册2024", title="长词条")]
    lines.extend(body_lines[:60])
    lines.append("…")

    async with app.test_matcher(query_cmd.query_matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        event = _group_event(".查询 长词条")
        for start in (0, 20, 40):
            chunk = lines[start : start + 20]
            if start == 40:
                chunk = chunk + [text.TXT_QUERY_TRUNCATED]
            ctx.should_call_send(event, "\n".join(chunk))
        ctx.receive_event(bot, event)


# ── 图片模式（dnddicer_query_image_enabled，默认关）──────────────────────


@pytest.fixture
def image_mode(monkeypatch):
    """打开图片模式开关（渲染器由用例自行注入或缺失）。"""
    monkeypatch.setattr(get_config(), "dnddicer_query_image_enabled", True)
    query_cmd.reset_image_fallback_notice()
    yield
    render.reset_renderer()
    query_cmd.reset_image_fallback_notice()


async def _expect_image(app: App, matcher, event, png: bytes) -> None:
    """断言发出的是图片消息（内容为给定 PNG 字节）。

    注：nonebug 捕获的是命令层直接交给 ``bot.send`` 的 ``MessageSegment``
    （不经过适配器包装），故期望值也用 ``MessageSegment``。
    """
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, MessageSegment.image(png))
        ctx.receive_event(bot, event)


def _setup_entry(transport_routes=None):
    """安装假数据源（默认：镜影术条目）。"""
    routes = transport_routes or _routes([make_result(1, "二环", PAGE_SPELLS_2024)])
    return _install(FakeTransport(routes))


@pytest.mark.asyncio
async def test_image_mode_off_still_sends_text(app: App, enabled_query):
    """开关默认关闭：即便注入了渲染器，词条仍按文字发送（逐字不变）。"""
    calls: list = []
    render.set_renderer(_fake_renderer(calls=calls))
    _setup_entry()
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 镜影术"),
        _expected_entry("二环", "玩家手册2024", _MIRROR_BODY),
    )
    assert calls == []


@pytest.mark.asyncio
async def test_image_mode_sends_rendered_card(app: App, enabled_query, image_mode):
    """开关开 + 本处开启 + 渲染器可用：词条以图片发送，标题取条目头名称。"""
    calls: list = []
    render.set_renderer(_fake_renderer(calls=calls))
    await _enable_image_here(_group_event("1"))
    _setup_entry(
        _routes(
            [
                make_result(1, "二环", PAGE_SPELLS_2024),
                make_result(2, "三环", PAGE_SPELLS_2024),
            ]
        )
    )
    # 候选列表仍为文字（候选列表不出图）
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 镜影术"),
        _expected_list(
            "镜影术", [("二环", "玩家手册2024"), ("三环", "玩家手册2024")]
        ),
    )
    await _expect_image(app, query_cmd.selection_matcher, _group_event("1"), _PNG_1PX)

    assert len(calls) == 1
    call = calls[0]
    # 标题取条目头名称（比页面标题「二环」精确）
    assert call["title"] == "镜影术"
    assert call["category"] == "玩家手册2024"
    assert call["located"] is True
    assert "三个镜像出现在你周围" in call["body"]
    assert call["source_path"].endswith(".htm")


@pytest.mark.asyncio
async def test_image_mode_falls_back_when_title_missing(app: App, enabled_query, image_mode):
    """条目头未命中（叙述页片段）：卡片标题退用关键词。"""
    calls: list = []
    render.set_renderer(_fake_renderer(calls=calls))
    await _enable_image_here(_group_event("1"))
    _install(
        FakeTransport(
            _routes(
                [],
                [
                    make_result(5, "优势与劣势", PAGE_NARRATIVE),
                    make_result(6, "优势与劣势速查", PAGE_NARRATIVE),
                ],
            )
        )
    )
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 优势与劣势"),
        _expected_list(
            "优势与劣势",
            [("优势与劣势", "玩家手册2024"), ("优势与劣势速查", "玩家手册2024")],
        ),
    )
    await _expect_image(app, query_cmd.selection_matcher, _group_event("1"), _PNG_1PX)
    assert calls[0]["title"] == "优势与劣势"
    assert calls[0]["located"] is False


@pytest.mark.asyncio
async def test_image_render_error_falls_back_to_text(app: App, enabled_query, image_mode):
    """渲染抛异常：落回文字输出（与默认文字逐字一致，不加提示）。"""

    async def _boom(title, category, body, source_path, located):
        raise RuntimeError("渲染失败")

    render.set_renderer(_boom)
    await _enable_image_here(_group_event("1"))
    _setup_entry()
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 镜影术"),
        _expected_entry("二环", "玩家手册2024", _MIRROR_BODY),
    )


@pytest.mark.asyncio
async def test_image_dependency_missing_hint_once(app: App, enabled_query, image_mode, monkeypatch):
    """本处已开图片但依赖缺失：回退文字 + 首次附一行提示（第二次不再附）。"""
    monkeypatch.setattr(render, "render_available", lambda: False)
    await _enable_image_here(_group_event("1"))
    _setup_entry()
    # 首次：文字 + 提示行
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 镜影术"),
        _expected_entry("二环", "玩家手册2024", _MIRROR_BODY)
        + "\n"
        + text.TXT_QUERY_IMAGE_FALLBACK,
    )
    # 第二次：文字（不再附提示）
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 镜影术"),
        _expected_entry("二环", "玩家手册2024", _MIRROR_BODY),
    )


@pytest.mark.asyncio
async def test_image_mode_off_no_hint_when_dependency_missing(app: App, enabled_query, monkeypatch):
    """骰主总开关关闭时不检查依赖、也不附提示（默认装机零打扰）。"""
    monkeypatch.setattr(render, "render_available", lambda: False)
    await _enable_image_here(_group_event("1"))  # 存量设置也不生效
    _setup_entry()
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 镜影术"),
        _expected_entry("二环", "玩家手册2024", _MIRROR_BODY),
    )


@pytest.mark.asyncio
async def test_image_mode_skips_empty_body(app: App, enabled_query, image_mode):
    """正文为空（页面无可显示内容）：不出空白图，走文字侧的「无正文」提示。"""
    calls: list = []
    render.set_renderer(_fake_renderer(calls=calls))
    await _enable_image_here(_group_event("1"))
    _install(FakeTransport(_routes([make_result(1, "空页", "\n\n")])))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 空页"),
        _expected_entry(
            "空页", "玩家手册2024", text.TXT_QUERY_ENTRY_EMPTY, fallback=True
        ),
    )
    assert calls == []


# ── 按处开关命令 .查询图片（无权限限制，群/私聊各自生效）────────────────


@pytest.mark.asyncio
async def test_image_setting_view_default_text(app: App, enabled_query, image_mode):
    """无参数：默认（未设置）回报当前为文字，并给开启引导。"""
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片"),
        text.TXT_QUERY_IMAGE_STATE_OFF.format(where="本群"),
    )


@pytest.mark.asyncio
async def test_image_setting_on_then_query_sends_image(app: App, enabled_query, image_mode):
    """开启：成功提示 + 落盘生效——随后查询词条即出图（唯一候选直接出图）。"""
    render.set_renderer(_fake_renderer())
    _setup_entry()
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片 on"),
        text.TXT_QUERY_IMAGE_ON.format(where="本群"),
    )
    await _expect_image(app, query_cmd.query_matcher, _group_event(".查询 镜影术"), _PNG_1PX)


@pytest.mark.asyncio
async def test_image_setting_off_back_to_text(app: App, enabled_query, image_mode):
    """关闭：成功提示 + 词条回到文字（逐字与默认一致）。"""
    render.set_renderer(_fake_renderer())
    await _enable_image_here(_group_event("1"))
    _setup_entry()
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片 off"),
        text.TXT_QUERY_IMAGE_OFF.format(where="本群"),
    )
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 镜影术"),
        _expected_entry("二环", "玩家手册2024", _MIRROR_BODY),
    )


@pytest.mark.asyncio
async def test_image_setting_rejected_when_master_off(app: App, enabled_query):
    """骰主未开启图片模式：开启被拒（报错），设置不写入、仍以文字显示。"""
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片 on"),
        text.TXT_QUERY_IMAGE_DISABLED,
    )
    # 未写入：查看当前仍是文字
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片"),
        text.TXT_QUERY_IMAGE_STATE_OFF.format(where="本群"),
    )
    # 随后查询走文字（渲染器若被调用说明设置泄漏）
    calls: list = []
    render.set_renderer(_fake_renderer(calls=calls))
    _setup_entry()
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 镜影术"),
        _expected_entry("二环", "玩家手册2024", _MIRROR_BODY),
    )
    assert calls == []


@pytest.mark.asyncio
async def test_image_setting_rejected_when_dependency_missing(
    app: App, enabled_query, image_mode, monkeypatch
):
    """总开关已开但渲染依赖未就绪：开启同样被拒，仍以文字显示。"""
    monkeypatch.setattr(render, "render_available", lambda: False)
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片 on"),
        text.TXT_QUERY_IMAGE_NOT_READY,
    )
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片"),
        text.TXT_QUERY_IMAGE_STATE_OFF.format(where="本群"),
    )


@pytest.mark.asyncio
async def test_image_setting_pending_when_master_turned_off(
    app: App, enabled_query, monkeypatch
):
    """存量设置：曾开启、骰主后来关掉总开关 → 查看显示「已设为图片但当前不可用」。"""
    await _enable_image_here(_group_event("1"))
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片"),
        text.TXT_QUERY_IMAGE_STATE_PENDING.format(where="本群"),
    )


@pytest.mark.asyncio
async def test_image_setting_scoped_per_group(app: App, enabled_query, image_mode):
    """按群隔离：A 群开启不影响 B 群（B 仍为文字）。"""
    render.set_renderer(_fake_renderer())
    _setup_entry()
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片 on", group_id=_G),
        text.TXT_QUERY_IMAGE_ON.format(where="本群"),
    )
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片", group_id=_G + 1),
        text.TXT_QUERY_IMAGE_STATE_OFF.format(where="本群"),
    )


@pytest.mark.asyncio
async def test_image_setting_private_scoped_per_user(app: App, enabled_query, image_mode):
    """私聊隔离：按用户各自生效，措辞用「你」；群与私聊也互不影响。"""
    render.set_renderer(_fake_renderer())
    _setup_entry()
    private_event = fake_private_message_event_v11(message=Message(".查询图片 on"))
    await _expect(
        app,
        query_cmd.image_matcher,
        private_event,
        text.TXT_QUERY_IMAGE_ON.format(where="你"),
    )
    # 同一用户私聊已开启 → 私聊查询（唯一候选）直接出图
    await _expect_image(
        app,
        query_cmd.query_matcher,
        fake_private_message_event_v11(message=Message(".查询 镜影术")),
        _PNG_1PX,
    )
    # 群聊不受该私聊设置影响
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片"),
        text.TXT_QUERY_IMAGE_STATE_OFF.format(where="本群"),
    )


@pytest.mark.asyncio
async def test_image_setting_alias_and_bad_arg(app: App, enabled_query, image_mode):
    """别名 .qimg 等价；无效参数给用法提示。"""
    render.set_renderer(_fake_renderer())
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".qimg on"),
        text.TXT_QUERY_IMAGE_ON.format(where="本群"),
    )
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片 图片"),
        text.TXT_QUERY_IMAGE_BAD_ARG.format(
            arg="图片", usage=text.TXT_QUERY_IMAGE_USAGE
        ),
    )


@pytest.mark.asyncio
async def test_image_setting_does_not_shadow_query(app: App, enabled_query, image_mode):
    """命令名不互吃：.查询图片 不被 .查询 抢走，.查询 图片 仍是关键词检索。"""
    _install(FakeTransport(_routes([make_result(1, "图片", PAGE_NARRATIVE)])))
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 图片"),
        _expected_entry("图片", "玩家手册2024", PAGE_NARRATIVE, fallback=True),
    )


# ── 查询范围 .查询范围 与书目表 .规则书（2026-09-25 新增）────────────────


def _fake_books_renderer(png: bytes = _PNG_1PX, calls: Optional[list] = None):
    """构造假书目表渲染器（记录调用参数，返回固定 PNG 字节）。"""

    async def _render(sections, title, hint, footer):
        if calls is not None:
            calls.append(
                {"sections": sections, "title": title, "hint": hint, "footer": footer}
            )
        return png

    return _render


def _expected_books_lines() -> list:
    """按文案常量拼出书目表文字形态的全部行。"""
    from nonebot_plugin_dnddicer.query import books

    lines = [text.TXT_QUERY_BOOKS_HEAD]
    total = 0
    for title, entries in books.sections_for_display():
        lines.append(text.TXT_QUERY_BOOKS_SECTION.format(title=title))
        for entry in entries:
            total += 1
            lines.append(
                text.TXT_QUERY_BOOKS_ROW.format(key=entry.key, name=entry.title)
            )
            if entry.note:
                lines.append(text.TXT_QUERY_BOOKS_NOTE.format(note=entry.note))
    lines.append(text.TXT_QUERY_BOOKS_TAIL.format(count=total))
    return lines


async def _expect_books_text(app: App, matcher, event) -> None:
    """断言书目表以文字形态（按 20 行分段）发送。"""
    lines = _expected_books_lines()
    chunks = [lines[i : i + 20] for i in range(0, len(lines), 20)]
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        for chunk in chunks:
            ctx.should_call_send(event, "\n".join(chunk))
        ctx.receive_event(bot, event)


@pytest.mark.asyncio
async def test_scope_view_default_all(app: App, enabled_query):
    """无参数：默认（未设置）回报全部书目可查。"""
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围"),
        text.TXT_QUERY_SCOPE_CURRENT_ALL.format(where="本群"),
    )


@pytest.mark.asyncio
async def test_scope_set_and_view(app: App, enabled_query):
    """设置：只接受缩写（大小写不敏感），回复列出条目；查看回显、逐字一致。"""
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 PHB24,MM25"),
        text.TXT_QUERY_SCOPE_SET.format(
            where="本群", items="PHB24 玩家手册2024、MM25 怪物图鉴2025"
        ),
    )
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围"),
        text.TXT_QUERY_SCOPE_CURRENT.format(
            where="本群", items="PHB24 玩家手册2024、MM25 怪物图鉴2025"
        ),
    )
    # 大小写不敏感 + 顿号分隔 + 去重
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 phb24、PHB24、xge"),
        text.TXT_QUERY_SCOPE_SET.format(
            where="本群", items="PHB24 玩家手册2024、XGE 珊娜萨的万事指南"
        ),
    )


@pytest.mark.asyncio
async def test_scope_reset_all(app: App, enabled_query):
    """「全部」恢复：清掉设置，查看回到「全部书目」。"""
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 3PP"),
        text.TXT_QUERY_SCOPE_SET.format(where="本群", items="3PP 第三方（合作内容）"),
    )
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 全部"),
        text.TXT_QUERY_SCOPE_RESET.format(where="本群"),
    )
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围"),
        text.TXT_QUERY_SCOPE_CURRENT_ALL.format(where="本群"),
    )


@pytest.mark.asyncio
async def test_scope_unknown_and_umbrella_hint(app: App, enabled_query):
    """未知缩写与整目录提示（合作内容作品 → 请用 3PP）。"""
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 不存在"),
        text.TXT_QUERY_SCOPE_UNKNOWN.format(details="不存在（无此项）"),
    )
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 Dk"),
        text.TXT_QUERY_SCOPE_UNKNOWN.format(details="Dk（请用 3PP）"),
    )
    # 中文书名同样不接受（设置只认缩写）
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 玩家手册2024"),
        text.TXT_QUERY_SCOPE_UNKNOWN.format(details="玩家手册2024（无此项）"),
    )


@pytest.mark.asyncio
async def test_scope_requires_query_enabled(app: App):
    """查询功能未开启：设置被拒（与 .查询 同口径）；「全部」仍可清理。"""
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 PHB24"),
        text.TXT_QUERY_DISABLED,
    )
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 全部"),
        text.TXT_QUERY_SCOPE_RESET.format(where="本群"),
    )


@pytest.mark.asyncio
async def test_scope_scoped_per_chat_and_alias(app: App, enabled_query):
    """按处隔离（A 群设置不影响 B 群）；别名 .qscope 等价。"""
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".qscope PHB24", group_id=_G),
        text.TXT_QUERY_SCOPE_SET.format(where="本群", items="PHB24 玩家手册2024"),
    )
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围", group_id=_G + 1),
        text.TXT_QUERY_SCOPE_CURRENT_ALL.format(where="本群"),
    )
    # 私聊按用户隔离，措辞用「你」
    await _expect(
        app,
        query_cmd.scope_matcher,
        fake_private_message_event_v11(message=Message(".查询范围 XGE")),
        text.TXT_QUERY_SCOPE_SET.format(where="你", items="XGE 珊娜萨的万事指南"),
    )
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围", group_id=_G),
        text.TXT_QUERY_SCOPE_CURRENT.format(
            where="本群", items="PHB24 玩家手册2024"
        ),
    )


@pytest.mark.asyncio
async def test_scoped_search_queries_only_scope(app: App, enabled_query):
    """范围生效时检索：逐目录请求（URL 带 category），候选只来自范围内。"""
    import urllib.parse

    def route(url: str) -> dict:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        category = query["category"][0]
        index = {"玩家手册2024": 21, "珊娜萨的万事指南": 22}[category]
        return make_search_response(
            [make_result(index, "火球术", PAGE_SPELLS_2024, category=category)]
        )

    transport = FakeTransport([("category=", route)])
    _install(transport)
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 PHB24,XGE"),
        text.TXT_QUERY_SCOPE_SET.format(
            where="本群", items="PHB24 玩家手册2024、XGE 珊娜萨的万事指南"
        ),
    )
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 火球术"),
        _expected_list(
            "火球术",
            [("火球术", "玩家手册2024"), ("火球术", "珊娜萨的万事指南")],
            count=2,
        ),
    )
    assert len(transport.calls) == 2
    assert all("category=" in url for url in transport.calls)


@pytest.mark.asyncio
async def test_scoped_no_result_explains_scope(app: App, enabled_query):
    """范围生效且无结果：`.查询` 说明当前范围、放开办法，并建议改用 `.搜索`。"""
    _install(FakeTransport([("category=", make_search_response([]))]))
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 PHB24"),
        text.TXT_QUERY_SCOPE_SET.format(where="本群", items="PHB24 玩家手册2024"),
    )
    await _expect(
        app,
        query_cmd.query_matcher,
        _group_event(".查询 火球术"),
        text.TXT_QUERY_NO_RESULT_SCOPED.format(
            keyword="火球术",
            where="本群",
            scope="玩家手册2024",
            hint=text.TXT_QUERY_NO_RESULT_SCOPED_HINT,
        ),
    )


@pytest.mark.asyncio
async def test_scoped_no_result_full_search_no_hint(app: App, enabled_query):
    """范围生效且无结果：`.搜索` 本身即全文检索，只说明范围，不提示建议改用 `.搜索`。"""
    _install(FakeTransport([("category=", make_search_response([]))]))
    await _expect(
        app,
        query_cmd.scope_matcher,
        _group_event(".查询范围 PHB24"),
        text.TXT_QUERY_SCOPE_SET.format(where="本群", items="PHB24 玩家手册2024"),
    )
    expected = text.TXT_QUERY_NO_RESULT_SCOPED.format(
        keyword="火球术", where="本群", scope="玩家手册2024", hint=""
    )
    assert text.TXT_QUERY_NO_RESULT_SCOPED_HINT not in expected
    await _expect(
        app, query_cmd.search_matcher, _group_event(".搜索 火球术"), expected
    )


@pytest.mark.asyncio
async def test_books_command_sends_image(app: App, image_mode):
    """书目表默认出图（骰主已开图片模式 + 渲染可用），内容为分组数据。"""
    calls: list = []
    render.set_books_renderer(_fake_books_renderer(calls=calls))
    await _expect_image(app, query_cmd.books_matcher, _group_event(".规则书"), _PNG_1PX)

    assert len(calls) == 1
    call = calls[0]
    sections = call["sections"]
    assert sections[0]["title"].startswith("新版核心资源")
    assert sections[-1]["title"].startswith("整目录")
    rows = [(row["key"], row["name"]) for section in sections for row in section["rows"]]
    assert ("PHB24", "玩家手册2024") in rows
    assert ("3PP", "第三方（合作内容）") in rows
    assert any(row["note"] for section in sections for row in section["rows"])


@pytest.mark.asyncio
async def test_books_command_text_fallback(app: App, enabled_query):
    """渲染不可用（默认关）：书目表回退文字（分组 + 缩写对照逐行）。"""
    await _expect_books_text(app, query_cmd.books_matcher, _group_event(".规则书"))


@pytest.mark.asyncio
async def test_books_command_unaffected_by_image_switch(app: App, image_mode):
    """书目表不受 .查询图片 影响：本处关掉图片后，.规则书 仍出图。"""
    render.set_books_renderer(_fake_books_renderer())
    await _expect(
        app,
        query_cmd.image_matcher,
        _group_event(".查询图片 off"),
        text.TXT_QUERY_IMAGE_OFF.format(where="本群"),
    )
    await _expect_image(app, query_cmd.books_matcher, _group_event(".规则书"), _PNG_1PX)


@pytest.mark.asyncio
async def test_books_command_alias(app: App, enabled_query):
    """别名 .qbooks 等价。"""
    await _expect_books_text(app, query_cmd.books_matcher, _group_event(".qbooks"))


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
