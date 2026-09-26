"""站点 HTML 抓取：规则查询重构（2026-09-26）的正文来源。

用途与边界：

- 规则查询的「正文层」按候选页路径抓取原始 HTML（保留加粗、颜色、表格等
  样式信息，供 ``query/decode.py`` 按锚点切条目并清洗渲染）——检索接口
  ``/api/search`` 的 ``content`` 是纯文本，样式在索引阶段已被剥离；
- 与 ``source.py``（JSON 检索）共用同一套外呼纪律：多端点顺序回退 + 端点
  冷却 + 全局并发上限 + 超时 + 如实标注插件身份的 UA；另加**最小请求间隔**
  （默认 0.5 秒，配置项 ``dnddicer_query_page_interval``）——索引构建会连续
  抓取数十页，比逐次查询更密集，单独限流避免对个人站点突发轰炸；
- **只读**：不提交任何数据、不携带凭据。

缓存：页面级（路径 → HTML，TTL 默认 24 小时、LRU 上限）；站点内容更新低频，
同一页在 TTL 内重复查询零外呼（缓存命中不触发限流）。
"""

from __future__ import annotations

import asyncio
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from nonebot import logger

from ..version import __version__
from .models import QueryUnavailableError

#: 请求头：如实标注插件身份（与 source.py 同口径；Accept 面向 HTML 页面）
_HEADERS: Dict[str, str] = {
    "User-Agent": (
        f"nonebot-plugin-dnddicer/{__version__} "
        "(+https://github.com/H-Elden/nonebot-plugin-dnddicer)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://5echm.kagangtuya.top/",
}

#: 页面缓存条数上限（常见页 2~30KB；速查表最大约 400KB）
_PAGE_CACHE_MAX = 64

#: 抓取并发上限（礼貌原则：不对个人站点并发轰炸；与 source.py 同口径）
_MAX_CONCURRENCY = 2

#: 传输函数签名：``(url, timeout, headers) -> HTML 文本``（async；测试注入用）
PageTransport = Callable[[str, float, Dict[str, str]], Awaitable[str]]


def _http_get_html(url: str, timeout: float, headers: Dict[str, str]) -> str:
    """同步 HTTP GET 并解码 HTML（在 ``asyncio.to_thread`` 中执行）。

    非 2xx / 网络错误由 ``urllib`` 抛异常——对调用方都表示「该端点不可用」，
    由 ``get_page`` 统一处理（冷却 + 回退下一个端点）。
    """
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def build_page_url(base_url: str, path: str) -> str:
    """拼出页面 URL。

    - 普通页面：``{base}/topics/{path}``（``path`` 为站内相对路径、含后缀，
      如 ``玩家手册2024/法术详述/1环.htm``）；
    - **站点根路径**：``path`` 以 ``/`` 开头时拼 ``{base}/{path}``（如目录页
      ``/webhelpcontents.htm`` 不在 topics 下）。

    路径里的 ``/`` 保留、中文等字符逐段转义（与站点自身链接形态一致）。
    """
    base = base_url.rstrip("/")
    if path.startswith("/"):
        return f"{base}/{urllib.parse.quote(path.lstrip('/'), safe='/')}"
    return f"{base}/topics/{urllib.parse.quote(path, safe='/')}"


def path_variants(path: str) -> List[str]:
    """页面路径的后缀变体（站点 ``.htm`` / ``.html`` 混用）。

    2026-09-26 实测：速查表里旧版页面链接写作 ``…/3环.html`` 而站点实际为
    ``.htm``（404）；抓取时先试原路径，404 再试互换后缀。
    """
    if path.endswith(".html"):
        return [path, path[:-5] + ".htm"]
    if path.endswith(".htm"):
        return [path, path[:-4] + ".html"]
    return [path]


class HtmlFetcher:
    """站点页面抓取器（多端点顺序回退 + 端点冷却 + 最小间隔 + 页面缓存）。"""

    def __init__(
        self,
        base_urls: List[str],
        *,
        timeout: float = 8.0,
        cache_ttl: float = 86400.0,
        endpoint_cooldown: float = 60.0,
        min_interval: float = 0.5,
        transport: Optional[PageTransport] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        cache_max: int = _PAGE_CACHE_MAX,
    ) -> None:
        urls = [str(url).strip().rstrip("/") for url in base_urls if str(url).strip()]
        if not urls:
            raise ValueError("base_urls 不能为空")
        self._base_urls: Tuple[str, ...] = tuple(dict.fromkeys(urls))
        self._timeout = float(timeout)
        self._cache_ttl = float(cache_ttl)
        self._endpoint_cooldown = float(endpoint_cooldown)
        self._min_interval = max(0.0, float(min_interval))
        self._transport = transport
        self._clock = clock
        self._sleep = sleep
        self._cache_max = max(1, int(cache_max))
        #: 页面缓存：路径 → (过期时刻, HTML)，命中后重插（简易 LRU）
        self._cache: Dict[str, Tuple[float, str]] = {}
        #: 端点冷却：base_url → 冷却截止时刻
        self._cooldown: Dict[str, float] = {}
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
        #: 最小请求间隔（串行化实际外呼；缓存命中不经过这里）。
        #: ``None`` 表示尚未发起过请求（首个请求不等待）
        self._interval_lock = asyncio.Lock()
        self._last_request_at: Optional[float] = None

    # ── 对外接口 ────────────────────────────────────────────────────────

    @property
    def base_urls(self) -> Tuple[str, ...]:
        """配置的端点列表（原序、已去重）。"""
        return self._base_urls

    def clear_cache(self) -> None:
        """清空页面缓存与端点冷却（测试与排障用）。"""
        self._cache.clear()
        self._cooldown.clear()

    async def get_page(self, path: str) -> str:
        """按站内相对路径抓取页面 HTML（缓存命中直接返回）。

        Raises:
            QueryUnavailableError: 全部端点尝试失败（网络错误、超时、非 2xx）。
        """
        cached = self._cache_get(path)
        if cached is not None:
            return cached

        attempts: List[str] = []
        last_error: Optional[Exception] = None
        for base_url in self._ordered_endpoints():
            attempts.append(base_url)
            try:
                html = await self._fetch_variants(base_url, path)
            except Exception as exc:  # noqa: BLE001 - 任何失败都视为该端点不可用
                last_error = exc
                self._cooldown[base_url] = self._clock() + self._endpoint_cooldown
                logger.warning(
                    "DNDDicer 页面抓取端点失败 base_url={} path={}: {}",
                    base_url,
                    path,
                    exc,
                )
                continue
            self._cooldown.pop(base_url, None)
            self._cache_put(path, html)
            return html
        raise QueryUnavailableError(attempts, last_error)

    # ── 抓取与回退 ──────────────────────────────────────────────────────

    async def _fetch_variants(self, base_url: str, path: str) -> str:
        """按后缀变体抓取：仅 404 触发变体重试，其它错误直接抛出。"""
        last_error: Optional[Exception] = None
        for variant in path_variants(path):
            try:
                return await self._fetch_from(base_url, variant)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code != 404:
                    raise
                logger.info(
                    "DNDDicer 页面 404，尝试后缀变体 base_url={} path={}",
                    base_url,
                    variant,
                )
        if last_error is not None:
            raise last_error
        raise QueryUnavailableError([base_url], None)

    async def _fetch_from(self, base_url: str, path: str) -> str:
        """从单个端点抓取（受并发上限与最小间隔约束）。"""
        url = build_page_url(base_url, path)
        async with self._semaphore:
            await self._throttle()
            if self._transport is not None:
                return await self._transport(url, self._timeout, dict(_HEADERS))
            return await asyncio.to_thread(
                _http_get_html, url, self._timeout, dict(_HEADERS)
            )

    async def _throttle(self) -> None:
        """最小请求间隔（串行）：两次实际外呼之间至少间隔 ``min_interval`` 秒。"""
        if self._min_interval <= 0:
            return
        async with self._interval_lock:
            now = self._clock()
            if self._last_request_at is not None:
                wait = self._min_interval - (now - self._last_request_at)
                if wait > 0:
                    await self._sleep(wait)
            self._last_request_at = self._clock()

    def _ordered_endpoints(self) -> List[str]:
        """按配置顺序返回可用端点（跳过冷却中的；全部冷却时全部重试）。"""
        now = self._clock()
        ready = [url for url in self._base_urls if self._cooldown.get(url, 0.0) <= now]
        return ready or list(self._base_urls)

    # ── 缓存 ────────────────────────────────────────────────────────────

    def _cache_get(self, path: str) -> Optional[str]:
        entry = self._cache.get(path)
        if entry is None:
            return None
        expire_at, html = entry
        if expire_at <= self._clock():
            self._cache.pop(path, None)
            return None
        # 命中后重新插入以刷新顺序（简易 LRU）
        self._cache.pop(path, None)
        self._cache[path] = entry
        return html

    def _cache_put(self, path: str, html: str) -> None:
        self._cache[path] = (self._clock() + self._cache_ttl, html)
        while len(self._cache) > self._cache_max:
            oldest = next(iter(self._cache))
            self._cache.pop(oldest, None)
