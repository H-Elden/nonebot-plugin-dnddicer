"""页面抓取层（query/fetch.py）的单元测试（全离线：假传输 + 假时钟）。

覆盖：URL 拼接（topics 相对路径与站点根路径）、页面缓存（命中零外呼）、
后缀变体回退（404 → 互换 .htm/.html）、多端点顺序回退与冷却、最小请求间隔。
"""

from __future__ import annotations

import urllib.error

import pytest

from nonebot_plugin_dnddicer.query.fetch import HtmlFetcher, build_page_url, path_variants
from nonebot_plugin_dnddicer.query.models import QueryUnavailableError


def test_build_page_url() -> None:
    """URL 拼接：topics 相对路径（逐段转义）与站点根路径（前导斜杠）。"""
    import urllib.parse

    url = build_page_url("https://example.com", "玩家手册2024/法术详述/1环.htm")
    assert url.startswith("https://example.com/topics/")
    assert urllib.parse.unquote(url[len("https://example.com/topics/") :]) == (
        "玩家手册2024/法术详述/1环.htm"
    )
    assert build_page_url("https://example.com", "/webhelpcontents.htm") == (
        "https://example.com/webhelpcontents.htm"
    )


def test_path_variants() -> None:
    """后缀变体：原路径在前，互换后缀在后。"""
    assert path_variants("a/b.html") == ["a/b.html", "a/b.htm"]
    assert path_variants("a/b.htm") == ["a/b.htm", "a/b.html"]
    assert path_variants("toc") == ["toc"]


class _FakeTransport:
    """假传输：按 URL 返回预置内容或抛异常；记录调用顺序。"""

    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.calls: list = []

    async def __call__(self, url, timeout, headers):
        self.calls.append(url)
        for key, value in self.routes.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"未配置的请求：{url}")


@pytest.mark.asyncio
async def test_fetch_and_cache() -> None:
    """抓取成功并写缓存：同一路径第二次零外呼。"""
    transport = _FakeTransport({"1%E7%8E%AF.htm": "<html>页面</html>"})
    fetcher = HtmlFetcher(
        ["https://example.com"], transport=transport, min_interval=0.0
    )
    first = await fetcher.get_page("玩家手册2024/法术详述/1环.htm")
    second = await fetcher.get_page("玩家手册2024/法术详述/1环.htm")
    assert first == second == "<html>页面</html>"
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_suffix_variant_on_404() -> None:
    """404 触发后缀变体：.html 链接回退到 .htm 抓取成功。"""
    transport = _FakeTransport(
        {
            "3%E7%8E%AF.html": urllib.error.HTTPError(
                "u", 404, "Not Found", None, None  # type: ignore[arg-type]
            ),
            "3%E7%8E%AF.htm": "<html>三环页</html>",
        }
    )
    fetcher = HtmlFetcher(
        ["https://example.com"], transport=transport, min_interval=0.0
    )
    html = await fetcher.get_page("玩家手册/魔法/法术详述/3环.html")
    assert html == "<html>三环页</html>"
    assert len(transport.calls) == 2
    # 缓存键用原路径（避免二次变体探测）
    assert await fetcher.get_page("玩家手册/魔法/法术详述/3环.html") == "<html>三环页</html>"
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_endpoint_fallback_and_cooldown() -> None:
    """端点回退：首个端点失败进冷却，第二个端点接管。"""
    transport = _FakeTransport(
        {
            "bad.example": urllib.error.URLError("拒绝连接"),
            "good.example": "<html>内容</html>",
        }
    )
    fetcher = HtmlFetcher(
        ["https://bad.example", "https://good.example"],
        transport=transport,
        min_interval=0.0,
    )
    assert await fetcher.get_page("a.htm") == "<html>内容</html>"

    # 冷却期内跳过坏端点：新路径只请求好端点
    calls_before = len(transport.calls)
    assert await fetcher.get_page("b.htm") == "<html>内容</html>"
    new_calls = transport.calls[calls_before:]
    assert all("good.example" in url for url in new_calls)


@pytest.mark.asyncio
async def test_min_interval_throttles_requests() -> None:
    """最小请求间隔：两次实际外呼之间按配置等待（缓存命中不等待）。"""
    waits: list = []

    async def _fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    now = [0.0]
    transport = _FakeTransport({"a.htm": "<html>a</html>", "b.htm": "<html>b</html>"})
    fetcher = HtmlFetcher(
        ["https://example.com"],
        transport=transport,
        min_interval=0.5,
        clock=lambda: now[0],
        sleep=_fake_sleep,
    )
    await fetcher.get_page("a.htm")
    await fetcher.get_page("a.htm")  # 缓存命中：不再等待
    assert waits == []

    await fetcher.get_page("b.htm")
    assert waits and waits[0] > 0


@pytest.mark.asyncio
async def test_all_endpoints_fail_raises() -> None:
    """全部端点失败：抛 QueryUnavailableError（附尝试数）。"""
    transport = _FakeTransport(
        {"example.com": urllib.error.URLError("拒绝连接")}
    )
    fetcher = HtmlFetcher(
        ["https://example.com"], transport=transport, min_interval=0.0
    )
    with pytest.raises(QueryUnavailableError):
        await fetcher.get_page("a.htm")
