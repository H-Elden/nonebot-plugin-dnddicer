"""规则查询数据源 / 条目定位 / 交互状态单测（全离线：假传输，不触碰真实网络）。

覆盖：
- 条目定位三级回退（条目头 → 命中段落 → 页面片段）与截断；
- 数据源：标题精确命中免发全文查询、名称模式筛选与回退、排序去重、缓存、
  多端点顺序回退、失败端点冷却与到期重试、全端点失败抛错、非法响应判定；
- 候选交互状态：选择标记解析、TTL 过期、分页与页码收敛、容量淘汰。
"""

from __future__ import annotations

import pytest

from query_fakes import (
    PAGE_INDEX_LINE,
    PAGE_NARRATIVE,
    PAGE_SPELLS_2024,
    PAGE_TERM_2014,
    PAGE_WRAPPED_FALSE_HEAD,
    FakeTransport,
    make_candidate,
    make_result,
    make_search_response,
)

from nonebot_plugin_dnddicer.query.interaction import (
    PAGE_SIZE,
    SelectionStore,
    parse_selection_token,
)
from nonebot_plugin_dnddicer.query.locating import (
    locate_entry,
    split_entry_head,
)
from nonebot_plugin_dnddicer.query.models import QueryUnavailableError
from nonebot_plugin_dnddicer.query.source import (
    MAX_CANDIDATES,
    MODE_FULL,
    MODE_NAME,
    SCORE_CONTENT,
    SCORE_ENTRY_HEAD,
    SCORE_ENTRY_HEAD_SHORT,
    SCORE_TITLE_CONTAINS,
    SCORE_TITLE_EXACT,
    FiveChmSource,
)

_LOCAL = "http://127.0.0.1:13000"
_ONLINE = "https://5echmsearch.kagangtuya.top"


def _source(transport: FakeTransport, base_urls=(_ONLINE,), **kwargs) -> FiveChmSource:
    return FiveChmSource(list(base_urls), transport=transport, **kwargs)


# =========================================================================
# 条目定位
# =========================================================================


def test_locate_entry_pipe_head():
    """2024 版条目头（名称｜English）：切到下一个条目头为止。"""
    text, located = locate_entry(PAGE_SPELLS_2024, "镜影术")
    assert located is True
    assert "三个镜像出现在你周围" in text
    assert "灼热射线" not in text


def test_locate_entry_ascii_head_2014():
    """2014 版条目头（名称 English）：同样能切出词条正文。"""
    text, located = locate_entry(PAGE_TERM_2014, "借机攻击")
    assert located is True
    assert "反应发动一次近战攻击" in text
    assert "徒手打击" not in text


def test_locate_entry_paragraph_fallback():
    """无条目头时取命中段落（上下以空行为界），located 为 False。"""
    text, located = locate_entry(PAGE_NARRATIVE, "劣势")
    assert located is False
    assert "取较低者" in text


def test_locate_entry_skips_page_title_line():
    """关键词等于页面标题且正文无命中时：回退为页面片段（不走标题行段落）。"""
    text, located = locate_entry(PAGE_NARRATIVE, "优势与劣势")
    assert located is False
    assert text.startswith("优势与劣势")
    assert "取较高者" in text


def test_locate_entry_page_fallback_when_keyword_absent():
    """页面完全没有该关键词：仍返回页面开头片段（命令层会加提示）。"""
    text, located = locate_entry(PAGE_NARRATIVE, "法术位")
    assert located is False
    assert text.startswith("优势与劣势")


def test_locate_entry_truncates_long_entry():
    """超长词条按行数/字符数截断并加省略号。"""
    page = "长词条｜Long Entry\n" + "\n".join(f"第{i}行内容" for i in range(40))
    text, located = locate_entry(page, "长词条", max_lines=10, max_chars=80)
    assert located is True
    assert text.endswith("…")
    assert len(text) <= 81


def test_split_entry_head_variants():
    """条目头三种形态：竖线式 / 空格式 / 无分隔式；列表行不算条目头。"""
    assert split_entry_head("镜影术｜Mirror Image") == ("镜影术", "Mirror Image")
    assert split_entry_head("借机攻击 Opportunity Attacks") == ("借机攻击", "Opportunity Attacks")
    assert split_entry_head("借机攻击Opportunity Attack") == ("借机攻击", "Opportunity Attack")
    # 实测踩坑：这类「多个词条并列」的列表行不是条目头
    assert split_entry_head("火球术fireball，流星爆meteor swarm") is None
    # 正文句（无英文尾）不是条目头
    assert split_entry_head("借机攻击时，我可以用它擒抱或推撞敌人吗？") is None
    assert split_entry_head("") is None


def test_is_entry_head_on_pages():
    """页面级：条目头存在性与关键词匹配（2024 竖线式 / 叙述页无条目头）。"""
    assert split_entry_head("镜影术｜Mirror Image") is not None
    assert split_entry_head("优势与劣势") is None


def test_locate_entry_ignores_index_list_line():
    """列表行不再被当作条目头：关键词只在列表行出现时走回退链。"""
    text, located = locate_entry("火球术fireball，流星爆meteor swarm\n其他内容", "火球术")
    assert located is False
    assert text.startswith("火球术fireball")


def test_head_at_requires_block_start():
    """块首约束：前一行未收束（硬换行片段）不算条目头；空行/句末标点则算。"""
    from nonebot_plugin_dnddicer.query.locating import head_at

    assert head_at(["当发动", "借机攻击Opportunity Attack"], 1) is None
    assert head_at(["上一段结束。", "借机攻击Opportunity Attack"], 1) == (
        "借机攻击",
        "Opportunity Attack",
    )
    assert head_at(["借机攻击 Opportunity Attacks"], 0) == (
        "借机攻击",
        "Opportunity Attacks",
    )


def test_locate_entry_rejects_mid_sentence_false_head():
    """真实语料里的硬换行假条目头：回退为页面片段而非切出错位正文。"""
    text, located = locate_entry(PAGE_WRAPPED_FALSE_HEAD, "借机攻击")
    assert located is False
    assert text.startswith("借机攻击是当你")


def test_find_entry_head_variants():
    """条目头查询（图片卡片标题用）：三种形态命中，未命中返回 None。"""
    from nonebot_plugin_dnddicer.query.locating import find_entry_head

    # 2024 竖线式
    assert find_entry_head(PAGE_SPELLS_2024, "镜影术") == ("镜影术", "Mirror Image")
    # 2014 空格式
    assert find_entry_head(PAGE_TERM_2014, "借机攻击") == ("借机攻击", "Opportunity Attacks")
    # 前缀命中（关键词是条目名的前缀）
    assert find_entry_head(PAGE_SPELLS_2024, "镜影") == ("镜影术", "Mirror Image")
    # 未命中：叙述页无条目头
    assert find_entry_head(PAGE_NARRATIVE, "优势与劣势") is None
    # 未命中：关键词在该页完全不存在
    assert find_entry_head(PAGE_SPELLS_2024, "法术位") is None


# =========================================================================
# 数据源：检索、排序、缓存
# =========================================================================


@pytest.mark.asyncio
async def test_search_title_exact_skips_full_query():
    """标题精确命中：不再发全文查询（省一次外呼）。"""
    transport = FakeTransport(
        [("titleOnly=true", make_search_response([make_result(1, "火球术", PAGE_SPELLS_2024)]))]
    )
    candidates = await _source(transport).search("火球术", mode=MODE_NAME)

    assert len(candidates) == 1
    assert candidates[0].score == SCORE_TITLE_EXACT
    assert transport.calls_for("titleOnly=false") == []


@pytest.mark.asyncio
async def test_search_name_mode_prefers_named_hits():
    """名称模式：剔除纯全文命中，只留标题/条目头命中。"""
    title_response = make_search_response([make_result(7, "终末战争", "无关页面，正文里提到 火球术 一词")])
    full_response = make_search_response(
        [
            make_result(3, "二环", PAGE_SPELLS_2024),
            make_result(7, "终末战争", "无关页面，正文里提到 火球术 一词"),
        ]
    )
    transport = FakeTransport(
        [("titleOnly=true", title_response), ("titleOnly=false", full_response)]
    )
    candidates = await _source(transport).search("火球术", mode=MODE_NAME)

    assert [c.index for c in candidates] == [3]
    assert candidates[0].score == SCORE_ENTRY_HEAD


@pytest.mark.asyncio
async def test_search_name_mode_falls_back_to_content_hits():
    """名称模式在没有任何名称命中时，回退为全文候选（避免查不到）。"""
    response = make_search_response([make_result(7, "终末战争", "无关页面，正文里提到 火球术 一词")])
    transport = FakeTransport([("titleOnly=true", response), ("titleOnly=false", response)])
    candidates = await _source(transport).search("火球术", mode=MODE_NAME)

    assert [c.index for c in candidates] == [7]
    assert candidates[0].score == SCORE_CONTENT


@pytest.mark.asyncio
async def test_search_full_mode_sorts_by_score_and_dedupes():
    """全文模式：按分数降序，同 index 只保留最高分的一条。"""
    title_response = make_search_response([make_result(1, "火球术（术士）", "正文")])
    full_response = make_search_response(
        [
            make_result(1, "火球术（术士）", "正文"),
            make_result(2, "三环", PAGE_SPELLS_2024),
            make_result(3, "终末战争", "无关页面，正文里提到 火球术 一词"),
        ]
    )
    transport = FakeTransport(
        [("titleOnly=true", title_response), ("titleOnly=false", full_response)]
    )
    candidates = await _source(transport).search("火球术", mode=MODE_FULL)

    assert [c.index for c in candidates] == [1, 2, 3]
    assert [c.score for c in candidates] == [
        SCORE_TITLE_CONTAINS,
        SCORE_ENTRY_HEAD,
        SCORE_CONTENT,
    ]


@pytest.mark.asyncio
async def test_search_prefers_substantive_entry_over_index_page():
    """同为条目头命中：正文充实的真词条页排在只有一行条目的页面之前。"""
    full_response = make_search_response(
        [
            make_result(1, "附录页", PAGE_INDEX_LINE, rank=99),
            make_result(2, "三环", PAGE_SPELLS_2024, rank=1),
        ]
    )
    transport = FakeTransport(
        [("titleOnly=true", make_search_response([])), ("titleOnly=false", full_response)]
    )
    candidates = await _source(transport).search("火球术", mode=MODE_FULL)

    assert [c.index for c in candidates] == [2, 1]
    assert candidates[0].score == SCORE_ENTRY_HEAD
    assert candidates[1].score == SCORE_ENTRY_HEAD_SHORT


@pytest.mark.asyncio
async def test_search_index_page_title_is_demoted():
    """标题含「速查/列表」的索引页降一档：真词条页排在它前面。"""
    full_response = make_search_response(
        [
            make_result(1, "万法大全速查表", PAGE_SPELLS_2024, rank=99),
            make_result(2, "三环", PAGE_SPELLS_2024, rank=1),
        ]
    )
    transport = FakeTransport(
        [("titleOnly=true", make_search_response([])), ("titleOnly=false", full_response)]
    )
    candidates = await _source(transport).search("火球术", mode=MODE_FULL)

    assert [c.index for c in candidates] == [2, 1]
    assert candidates[1].score < candidates[0].score


@pytest.mark.asyncio
async def test_search_caches_by_keyword():
    """同关键词重复查询走缓存，不重复外呼。"""
    response = make_search_response([make_result(1, "火球术", PAGE_SPELLS_2024)])
    transport = FakeTransport([("titleOnly=true", response)])
    source = _source(transport)

    await source.search("火球术", mode=MODE_NAME)
    calls_after_first = len(transport.calls)
    await source.search("火球术", mode=MODE_NAME)

    assert calls_after_first > 0
    assert len(transport.calls) == calls_after_first


@pytest.mark.asyncio
async def test_search_candidates_capped():
    """候选数量上限（MAX_CANDIDATES）。"""
    results = [make_result(i, f"法术{i}", PAGE_SPELLS_2024) for i in range(30)]
    transport = FakeTransport(
        [("titleOnly=true", make_search_response([])), ("titleOnly=false", make_search_response(results))]
    )
    candidates = await _source(transport).search("火球术", mode=MODE_FULL)

    assert len(candidates) == MAX_CANDIDATES


# =========================================================================
# 数据源：多端点回退与冷却
# =========================================================================


@pytest.mark.asyncio
async def test_fallback_to_second_endpoint():
    """首个端点连接失败 → 自动回退第二个端点。"""
    response = make_search_response([make_result(1, "火球术", PAGE_SPELLS_2024)])
    transport = FakeTransport(
        [(_LOCAL, ConnectionRefusedError("拒绝连接")), (_ONLINE, response)]
    )
    source = _source(transport, base_urls=[_LOCAL, _ONLINE])
    candidates = await source.search("火球术", mode=MODE_NAME)

    assert candidates and candidates[0].base_url == _ONLINE
    assert transport.calls_for(_LOCAL) and transport.calls_for(_ONLINE)


@pytest.mark.asyncio
async def test_failed_endpoint_enters_cooldown():
    """失败端点在冷却期内被跳过（不再反复撞）。"""
    response = make_search_response([make_result(1, "火球术", PAGE_SPELLS_2024)])
    transport = FakeTransport(
        [(_LOCAL, ConnectionRefusedError("拒绝连接")), (_ONLINE, response)]
    )
    source = _source(transport, base_urls=[_LOCAL, _ONLINE])

    await source.search("火球术", mode=MODE_NAME)
    local_calls = len(transport.calls_for(_LOCAL))
    await source.search("魔法飞弹", mode=MODE_NAME)

    assert local_calls == 1
    assert len(transport.calls_for(_LOCAL)) == local_calls


@pytest.mark.asyncio
async def test_cooldown_expires_after_interval():
    """冷却到期后重新尝试该端点（注入时钟控制）。"""
    now = [0.0]
    response = make_search_response([make_result(1, "火球术", PAGE_SPELLS_2024)])
    transport = FakeTransport(
        [(_LOCAL, ConnectionRefusedError("拒绝连接")), (_ONLINE, response)]
    )
    source = FiveChmSource(
        [_LOCAL, _ONLINE],
        transport=transport,
        endpoint_cooldown=60.0,
        clock=lambda: now[0],
    )

    await source.search("火球术", mode=MODE_NAME)
    assert len(transport.calls_for(_LOCAL)) == 1

    now[0] = 61.0
    await source.search("魔法飞弹", mode=MODE_NAME)
    assert len(transport.calls_for(_LOCAL)) == 2


@pytest.mark.asyncio
async def test_all_endpoints_fail_raises():
    """全部端点失败：抛 QueryUnavailableError（携带尝试过的端点）。"""
    transport = FakeTransport(
        [(_LOCAL, ConnectionRefusedError("拒绝连接")), (_ONLINE, TimeoutError("超时"))]
    )
    source = _source(transport, base_urls=[_LOCAL, _ONLINE])

    with pytest.raises(QueryUnavailableError) as excinfo:
        await source.search("火球术")

    assert excinfo.value.attempts == [_LOCAL, _ONLINE]


@pytest.mark.asyncio
async def test_invalid_payload_treated_as_endpoint_failure():
    """响应缺少 results 字段：视为该端点不可用。"""
    transport = FakeTransport([("/api/search", {"oops": True})])
    with pytest.raises(QueryUnavailableError):
        await _source(transport).search("火球术")


@pytest.mark.asyncio
async def test_empty_base_urls_rejected():
    """端点列表为空属于配置错误（构建即失败）。"""
    with pytest.raises(ValueError):
        FiveChmSource([])


# =========================================================================
# 候选交互状态
# =========================================================================


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3", "3"),
        (" 12 ", "12"),
        ("+", "+"),
        ("-", "-"),
        ("9999", None),
        ("0x1", None),
        ("３", None),  # 全角数字不采纳
        (".r 3d6", None),
        ("abc", None),
        ("", None),
    ],
)
def test_parse_selection_token(text, expected):
    """选择标记解析：仅 ASCII 数字（≤3 位）与 +/-。"""
    assert parse_selection_token(text) == expected


def test_store_put_get_and_expire():
    """记录按会话+用户隔离，超时即失效。"""
    now = [0.0]
    store = SelectionStore(ttl=60.0, clock=lambda: now[0])
    record = store.put("group_1", "100", keyword="火球术", mode=MODE_NAME, candidates=[])

    assert store.get("group_1", "100") is record
    assert store.get("group_1", "200") is None
    assert store.get("private_1", "100") is None

    now[0] = 61.0
    assert store.get("group_1", "100") is None


def test_store_touch_extends_ttl():
    """查看详情/翻页后续期，窗口顺延。"""
    now = [0.0]
    store = SelectionStore(ttl=60.0, clock=lambda: now[0])
    record = store.put("group_1", "100", keyword="火球术", mode=MODE_NAME, candidates=[])

    now[0] = 50.0
    store.touch(record)
    now[0] = 100.0

    assert store.get("group_1", "100") is record


def test_record_paging():
    """分页：每页 PAGE_SIZE 条，页码越界收敛到合法范围。"""
    candidates = [make_candidate(i, f"法术{i}") for i in range(1, PAGE_SIZE * 2 + 4)]
    store = SelectionStore()
    record = store.put("group_1", "100", keyword="火球术", mode=MODE_FULL, candidates=candidates)

    assert record.page_count == 3
    assert len(record.page_slice()) == PAGE_SIZE
    assert record.page_slice()[0].index == 1

    record.page = 2
    assert record.page_slice()[0].index == PAGE_SIZE + 1

    record.page = 99
    assert len(record.page_slice()) == 3
    assert record.page == 3

    record.page = 1
    record.move_page(-1)
    assert record.page == 1  # 首页再往前不越界

    record.page = 3
    record.move_page(1)
    assert record.page == 3  # 末页再往后不越界


def test_store_evicts_oldest_over_capacity():
    """记录数超过上限时淘汰最旧。"""
    store = SelectionStore(max_records=2)
    store.put("group_1", "1", keyword="a", mode=MODE_NAME, candidates=[])
    store.put("group_1", "2", keyword="b", mode=MODE_NAME, candidates=[])
    store.put("group_1", "3", keyword="c", mode=MODE_NAME, candidates=[])

    assert store.size == 2
    assert store.get("group_1", "1") is None
    assert store.get("group_1", "3") is not None
