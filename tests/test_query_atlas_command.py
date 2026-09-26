"""速查子命令（.查询法术 等）的 nonebug 测试（全离线：假抓取器 + 合成页面）。

覆盖：唯一命中直出正文（抓页 → 解码 → 文字输出）、多候选列表（含出处与
元数据、目录名映射为书名）、回数字选择（选择流程分流到站点正文路径）、
范围过滤（命中收窄与选择期范围变更）、索引未就绪、功能开关与用法提示。
"""

from __future__ import annotations

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11

from nonebot_plugin_dnddicer.commands import atlas as atlas_cmd
from nonebot_plugin_dnddicer.commands import query as query_cmd
from nonebot_plugin_dnddicer.commands import query_atlas, text
from nonebot_plugin_dnddicer.config import get_config
from nonebot_plugin_dnddicer.data import query_settings
from nonebot_plugin_dnddicer.query import atlas as atlas_mod
from nonebot_plugin_dnddicer.query import books

_G = 55555
_USER = 12345678

_LEGACY_PATH = "玩家手册/魔法/法术详述/1环.htm"

_SPELL_TABLE = """<TABLE>
<TR spell="样例法术Sample Spell">
<TD><a href="../玩家手册2024/法术详述/1环.htm#Sample_Spell">样例法术Sample Spell</a></TD>
<TD>一环</TD><TD>惑控</TD><TD>法</TD><TD>动作</TD>
<TD>V</TD><TD>S</TD><TD>M</TD><TD>×</TD><TD>×</TD><TD>PHB24</TD>
</TR>
<TR spell="旧版样例法术Legacy Sample">
<TD><a href="../玩家手册/魔法/法术详述/1环.htm#Legacy_Sample">旧版样例法术Legacy Sample</a></TD>
<TD>一环</TD><TD>惑控</TD><TD>法</TD><TD>动作</TD>
<TD>V</TD><TD>S</TD><TD>M</TD><TD>×</TD><TD>×</TD><TD>PHB14</TD>
</TR>
</TABLE>"""

_SPELL_PAGE = """<html><body>
<H2>法术详述</H2>
<H4 id="Sample_Spell">样例法术｜Sample Spell</H4>
<P><STRONG>施法时间：</STRONG>动作<BR>样例说明文字。</P>
<H4 id="Other_Spell">另一个法术｜Other Spell</H4>
<P>其它内容。</P>
</body></html>"""

_LEGACY_PAGE = """<html><body>
<H2>法术详述</H2>
<H4 id="Legacy_Sample">旧版样例法术｜Legacy Sample</H4>
<P><STRONG>施法时间：</STRONG>动作<BR>旧版说明文字。</P>
<H4 id="Other_Legacy">别的法术｜Other Legacy</H4>
<P>其它内容。</P>
</body></html>"""


def _group_event(message: str, *, user_id: int = _USER):
    return fake_group_message_event_v11(
        message=Message(message), user_id=user_id, group_id=_G
    )


async def _expect(app: App, matcher, event, expected: str) -> None:
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


class _FakeFetcher:
    """假抓取器：按路径返回预置 HTML（未配置即报错）。"""

    def __init__(self, pages: dict) -> None:
        self.pages = pages

    async def get_page(self, path: str) -> str:
        if path not in self.pages:
            raise AssertionError(f"未配置页面：{path}")
        return self.pages[path]


def _reset_query_settings() -> None:
    """清空按处设置（缓存 + JSON）——回到默认（全部书目、文字显示）。"""
    from nonebot_plugin_dnddicer.data import get_data_file
    from nonebot_plugin_dnddicer.data import query_settings as _qs

    _qs._cache = None
    path = get_data_file("query_settings.json")
    if path.exists():
        path.write_text("{}", encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_state():
    """每个用例前后复位索引注入、候选记录与按处设置。"""
    from nonebot_plugin_dnddicer.query import default_store

    _reset_query_settings()
    default_store.reset()
    yield
    default_store.reset()
    atlas_cmd.set_store(None)
    _reset_query_settings()


@pytest.fixture
def enabled_query(monkeypatch):
    """打开查询开关（默认关）。"""
    monkeypatch.setattr(get_config(), "dnddicer_query_enabled", True)


@pytest.fixture
def store(tmp_path):
    """注入索引存储：速查表（两条法术）+ 两个详情页（假抓取器，全离线）。"""
    fetcher = _FakeFetcher(
        {
            atlas_mod._QUICKREF_PAGES["spell"][0]: _SPELL_TABLE,
            atlas_mod._QUICKREF_PAGES["spell"][1]: "<TABLE></TABLE>",
            "玩家手册2024/法术详述/1环.htm": _SPELL_PAGE,
            _LEGACY_PATH: _LEGACY_PAGE,
        }
    )
    instance = atlas_mod.AtlasStore(fetcher, cache_file=tmp_path / "query_atlas.json")
    atlas_cmd.set_store(instance)
    return instance


def _entry_text(category: str, title: str, body: list) -> str:
    """按文案拼出速查正文的期望文本。"""
    lines = [text.TXT_QUERY_ENTRY_HEAD.format(category=category, title=title)]
    lines.extend(body)
    return "\n".join(lines)


_TWO_CANDIDATES = (
    "「样例法术」共 2 条法术候选：\n"
    "1. 样例法术（玩家手册2024 · 一环 · 惑控）\n"
    "2. 旧版样例法术（玩家手册2014 · 一环 · 惑控）\n"
    "回复数字查看详情（60 秒内有效）"
)


# ── 唯一命中直出 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unique_hit_sends_entry(app: App, enabled_query, store):
    """.查询法术（唯一命中）：抓页解码后直接展示正文。"""
    await _expect(
        app,
        query_atlas.spell_matcher,
        _group_event(".查询法术 旧版"),
        _entry_text(
            "玩家手册2014 · 一环 · 惑控",
            "旧版样例法术｜Legacy Sample",
            ["施法时间：动作", "旧版说明文字。"],
        ),
    )


@pytest.mark.asyncio
async def test_scope_narrows_to_unique(app: App, enabled_query, store):
    """范围过滤：范围限定旧版资源后，同关键词只剩一条（直接展示正文）。"""
    legacy_category = books.find_entry("PHB14").category  # type: ignore[union-attr]
    await query_settings.set_scope(query_settings.group_key(_G), [legacy_category])
    await _expect(
        app,
        query_atlas.spell_matcher,
        _group_event(".查询法术 样例法术"),
        _entry_text(
            "玩家手册2014 · 一环 · 惑控",
            "旧版样例法术｜Legacy Sample",
            ["施法时间：动作", "旧版说明文字。"],
        ),
    )


# ── 多候选：列表 / 选择 / 范围变更 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_candidates_list_literal(app: App, enabled_query, store):
    """多候选列表：标题带出处与元数据（目录名映射为书名，短名优先）。"""
    await _expect(
        app, query_atlas.spell_matcher, _group_event(".查询法术 样例法术"), _TWO_CANDIDATES
    )


@pytest.mark.asyncio
async def test_select_number_sends_entry(app: App, enabled_query, store):
    """回复数字：选择流程分流到速查正文（抓页解码）。"""
    await _expect(
        app, query_atlas.spell_matcher, _group_event(".查询法术 样例法术"), _TWO_CANDIDATES
    )
    await _expect(
        app,
        query_cmd.selection_matcher,
        _group_event("1"),
        _entry_text(
            "玩家手册2024 · 一环 · 惑控",
            "样例法术｜Sample Spell",
            ["施法时间：动作", "样例说明文字。"],
        ),
    )


@pytest.mark.asyncio
async def test_select_out_of_scope_after_change(app: App, enabled_query, store):
    """选择期间范围被改：范围外条目不展示，给出说明。"""
    await _expect(
        app, query_atlas.spell_matcher, _group_event(".查询法术 样例法术"), _TWO_CANDIDATES
    )
    legacy_category = books.find_entry("PHB14").category  # type: ignore[union-attr]
    await query_settings.set_scope(query_settings.group_key(_G), [legacy_category])
    await _expect(
        app,
        query_cmd.selection_matcher,
        _group_event("1"),
        text.TXT_ATLAS_OUT_OF_SCOPE.format(category="玩家手册2024"),
    )


# ── 无结果 / 未就绪 / 开关 / 用法 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_no_result(app: App, enabled_query, store):
    """无结果：按类型给出提示。"""
    await _expect(
        app,
        query_atlas.spell_matcher,
        _group_event(".查询法术 不存在"),
        text.TXT_ATLAS_NO_RESULT.format(keyword="不存在", kind="法术"),
    )


@pytest.mark.asyncio
async def test_no_result_scoped(app: App, enabled_query, store):
    """范围生效且无结果：说明当前范围。"""
    await query_settings.set_scope(query_settings.group_key(_G), ["玩家手册2024"])
    await _expect(
        app,
        query_atlas.spell_matcher,
        _group_event(".查询法术 旧版"),
        text.TXT_ATLAS_NO_RESULT_SCOPED.format(
            keyword="旧版", kind="法术", scope="玩家手册2024"
        ),
    )


@pytest.mark.asyncio
async def test_not_ready_when_build_fails(app: App, enabled_query, tmp_path):
    """索引未就绪（懒构建失败）：给出提示。"""
    atlas_cmd.set_store(
        atlas_mod.AtlasStore(
            _FakeFetcher({}), cache_file=tmp_path / "query_atlas.json"
        )
    )
    await _expect(
        app,
        query_atlas.spell_matcher,
        _group_event(".查询法术 火球"),
        text.TXT_ATLAS_NOT_READY,
    )


@pytest.mark.asyncio
async def test_disabled_by_default(app: App, store):
    """功能未开启：只回提示、不查索引。"""
    await _expect(
        app,
        query_atlas.spell_matcher,
        _group_event(".查询法术 火球"),
        text.TXT_QUERY_DISABLED,
    )


@pytest.mark.asyncio
async def test_usage_when_keyword_missing(app: App, enabled_query, store):
    """无参数：给出用法（含示例）。"""
    await _expect(
        app,
        query_atlas.spell_matcher,
        _group_event(".查询法术"),
        text.TXT_QUERY_USAGE.format(
            usage=text.TXT_ATLAS_USAGE.format(kind="法术", example=".查询法术 火球术")
        ),
    )
