"""查询数据源：5echm 搜索服务（在线与自建实例共用同一实现）。

设计要点（依据 T2 数据源评估与自部署方案）：

- **多端点顺序回退**：``base_urls`` 按顺序尝试，首个成功者生效；失败端点进入
  冷却（``endpoint_cooldown`` 秒内跳过）——自建实例重启/更新索引的几秒窗口
  不会让每次查询都先撞一次本机；
- **两段式检索**：先标题查询（``titleOnly=true``，标题/条目名命中），需要时再
  补全文查询；合并后按「标题精确 > 标题包含 > 条目头命中 > 全文命中」排序、
  按 ``index`` 去重（服务端结果存在同页重复项）；
- **关键词结果缓存**：按「关键词 + 查询模式」缓存（默认 10 分钟），显著减少外呼；
- **礼貌外呼**：全局并发上限、超时、如实标注插件身份的 UA；
- **HTTP 实现**：标准库 ``urllib`` 走 ``asyncio.to_thread``（不阻塞事件循环），
  不新增运行时依赖；请求低频且命中缓存，线程池开销可忽略。

本模块不做内容分发：只把服务端响应用于当次会话的内存结果与短时缓存，不落盘。
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
import urllib.request
from dataclasses import replace
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from nonebot import logger

from ..version import __version__
from .locating import BODY_MAX_CHARS, BODY_MAX_LINES, locate_entry
from .models import Candidate, QueryUnavailableError

#: 查询模式：name = 名称优先（.查询）；full = 全文（.搜索）
MODE_NAME = "name"
MODE_FULL = "full"

#: 请求头：如实标注插件身份（对方为个人站点，便于识别来源与联系）
_HEADERS = {
    "User-Agent": (
        f"nonebot-plugin-dnddicer/{__version__} "
        "(+https://github.com/H-Elden/nonebot-plugin-dnddicer)"
    ),
    "Accept": "application/json",
    "Referer": "https://5echm.kagangtuya.top/",
}

#: 候选排序权重（数值越大越优先）
SCORE_TITLE_EXACT = 100
SCORE_TITLE_CONTAINS = 60
SCORE_ENTRY_HEAD = 50
SCORE_ENTRY_HEAD_SHORT = 40
SCORE_CONTENT = 10

#: 「正文充实」的判定：定位出的正文非空行数 ≥ 2 行、或字符数 ≥ 100。
#: 实测：索引/速查表页只有条目头一行（十来个字符），真词条页成段（数行以上），
#: 满足其一即视为真词条页、排序时高一档。
_SUBSTANTIVE_MIN_LINES = 2
_SUBSTANTIVE_MIN_CHARS = 100

#: 索引/速查表类页面标题特征：这些页面是「查表用的清单」（实测例如
#: 《速查》万法大全速查表、《速查》术士法术列表），命中条目头也只是一行索引，
#: 排序时再降一档，让真词条页排在前面（不降出名称模式的最低档）。
_INDEX_PAGE_TITLE_HINTS = ("速查", "列表", "一览", "索引", "总表")
_INDEX_PAGE_PENALTY = 10

#: 名称模式保留的最低分：纯全文命中不进入 .查询 的候选，除非一个都没有
_NAME_MODE_MIN_SCORE = SCORE_ENTRY_HEAD_SHORT

#: 单次查询最多返回的候选数
MAX_CANDIDATES = 20

#: 服务端单次请求的返回条数。全文查询取 50：实测（2026-09-25）「火球术」
#: 的真词条页（《玩家手册2024》三环）只排到第 50 位，20 条会漏掉；
#: 50 条的响应约 400KB，单次请求成本与服务端一次全量扫描相同。
_TITLE_PAGE_SIZE = 8
_FULL_PAGE_SIZE = 50

#: 关键词缓存条数上限（按「关键词 + 查询模式」计数，单条最坏约 400KB，
#: 上限 32 条对应最坏约 13MB 内存）
_CACHE_MAX_ENTRIES = 32

#: 外呼并发上限（礼貌原则：不对个人站点并发轰炸）
_MAX_CONCURRENCY = 2

#: 传输函数签名：``(url, timeout, headers) -> 解析后的 JSON``（async）
Transport = Callable[[str, float, Dict[str, str]], Awaitable[dict]]


def _http_get_json(url: str, timeout: float, headers: Dict[str, str]) -> dict:
    """同步 HTTP GET 并解析 JSON（在 ``asyncio.to_thread`` 中执行）。

    非 2xx / 网络错误由 ``urllib`` 抛异常、JSON 解析失败抛 ``ValueError``——
    两者对调用方都表示「该端点不可用」，由 ``_get_json`` 统一处理。
    """
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def _validate_search_payload(data: dict) -> None:
    """校验 ``/api/search`` 响应结构（不合法即视为该端点不可用）。"""
    if not isinstance(data.get("results"), list):
        raise ValueError("响应缺少 results 字段")


class FiveChmSource:
    """5echm 搜索服务数据源（在线与自建实例同一实现，多端点回退）。"""

    name = "5echm"

    def __init__(
        self,
        base_urls: List[str],
        *,
        timeout: float = 8.0,
        cache_ttl: float = 600.0,
        endpoint_cooldown: float = 60.0,
        transport: Optional[Transport] = None,
        clock: Callable[[], float] = time.monotonic,
        cache_max: int = _CACHE_MAX_ENTRIES,
    ) -> None:
        urls = [str(url).strip().rstrip("/") for url in base_urls if str(url).strip()]
        if not urls:
            raise ValueError("base_urls 不能为空")
        self._base_urls: Tuple[str, ...] = tuple(dict.fromkeys(urls))
        self._timeout = float(timeout)
        self._cache_ttl = float(cache_ttl)
        self._endpoint_cooldown = float(endpoint_cooldown)
        self._transport = transport
        self._clock = clock
        self._cache_max = max(1, int(cache_max))
        #: 缓存：``(关键词小写, 是否仅标题) -> (过期时刻, 候选列表)``
        self._cache: Dict[Tuple[str, bool], Tuple[float, List[Candidate]]] = {}
        #: 端点冷却：``base_url -> 冷却截止时刻``
        self._cooldown: Dict[str, float] = {}
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    # ── 对外接口 ────────────────────────────────────────────────────────

    @property
    def base_urls(self) -> Tuple[str, ...]:
        """配置的端点列表（原序、已去重）。"""
        return self._base_urls

    def clear_cache(self) -> None:
        """清空关键词缓存与端点冷却（测试与排障用）。"""
        self._cache.clear()
        self._cooldown.clear()

    async def search(self, keyword: str, *, mode: str = MODE_NAME) -> List[Candidate]:
        """检索关键词，返回排序去重后的候选列表（最多 ``MAX_CANDIDATES`` 条）。

        Args:
            keyword: 关键词（支持空格多关键词与 ``|`` 或，语义由服务端定义）。
            mode: ``MODE_NAME``（名称优先，标题精确命中时不再发全文查询）或
                ``MODE_FULL``（全文）。

        Raises:
            QueryUnavailableError: 全部端点尝试失败。
        """
        keyword = keyword.strip()
        title_hits = await self._search_endpoint(keyword, title_only=True)
        has_exact = any(self._is_title_exact(c, keyword) for c in title_hits)
        need_full = mode == MODE_FULL or not has_exact
        pool = list(title_hits)
        if need_full:
            pool.extend(await self._search_endpoint(keyword, title_only=False))

        scored: Dict[int, Candidate] = {}
        for candidate in pool:
            scored_candidate = replace(candidate, score=self._score(candidate, keyword))
            existing = scored.get(candidate.index)
            if existing is None or scored_candidate.score > existing.score:
                scored[candidate.index] = scored_candidate

        candidates = list(scored.values())
        if mode == MODE_NAME:
            preferred = [c for c in candidates if c.score >= _NAME_MODE_MIN_SCORE]
            if preferred:
                candidates = preferred

        candidates.sort(key=lambda c: (-c.score, -c.rank, c.index))
        return candidates[:MAX_CANDIDATES]

    # ── 检索与排序 ──────────────────────────────────────────────────────

    async def _search_endpoint(self, keyword: str, *, title_only: bool) -> List[Candidate]:
        """调用 ``/api/search`` 并把响应解析为候选列表（带缓存）。"""
        cache_key = (keyword.casefold(), title_only)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        params = {
            "keyword": keyword,
            "page": 1,
            "pageSize": _TITLE_PAGE_SIZE if title_only else _FULL_PAGE_SIZE,
            "titleOnly": "true" if title_only else "false",
        }
        data, base_url = await self._get_json(
            "/api/search", params, validate=_validate_search_payload
        )
        candidates = self._parse_results(data, base_url)
        self._cache_put(cache_key, candidates)
        return candidates

    @staticmethod
    def _parse_results(data: dict, base_url: str) -> List[Candidate]:
        """把服务端响应解析为候选列表（字段缺失按空值处理）。"""
        results = data.get("results")
        if not isinstance(results, list):
            raise ValueError("响应缺少 results 字段")
        candidates: List[Candidate] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index"))
            except (TypeError, ValueError):
                continue
            candidates.append(
                Candidate(
                    index=index,
                    title=str(item.get("title") or "").strip(),
                    category=str(item.get("category") or "").strip(),
                    path=str(item.get("path") or "").strip(),
                    rank=int(item.get("rank") or 0),
                    content=str(item.get("content") or ""),
                    base_url=base_url,
                )
            )
        return candidates

    @staticmethod
    def _is_title_exact(candidate: Candidate, keyword: str) -> bool:
        return candidate.title.casefold() == keyword.casefold()

    def _score(self, candidate: Candidate, keyword: str) -> int:
        """插件侧排序分：标题精确 > 标题包含 > 条目头（正文充实 > 短条目）> 全文。

        条目头一档区分「真词条页」与「索引/速查表页」：前者正文成段（可达
        数十行），后者往往只有一行条目——实测服务端排序会把索引页排得更靠前，
        靠这一档把真正的词条页提到候选列表前面。
        """
        keyword_fold = keyword.casefold()
        if candidate.title.casefold() == keyword_fold:
            return SCORE_TITLE_EXACT
        if keyword_fold in candidate.title.casefold():
            return SCORE_TITLE_CONTAINS
        text, located = locate_entry(
            candidate.content,
            keyword,
            max_lines=BODY_MAX_LINES,
            max_chars=BODY_MAX_CHARS,
        )
        if located:
            lines = [line for line in text.splitlines() if line.strip()]
            if (
                len(lines) >= _SUBSTANTIVE_MIN_LINES
                or len(text) >= _SUBSTANTIVE_MIN_CHARS
            ):
                score = SCORE_ENTRY_HEAD
            else:
                score = SCORE_ENTRY_HEAD_SHORT
            if any(hint in candidate.title for hint in _INDEX_PAGE_TITLE_HINTS):
                score -= _INDEX_PAGE_PENALTY
            return score
        return SCORE_CONTENT

    # ── 端点多地址与回退 ────────────────────────────────────────────────

    def _ordered_endpoints(self) -> List[str]:
        """按配置顺序返回可用端点（跳过冷却中的；全部冷却时全部重试）。"""
        now = self._clock()
        ready = [url for url in self._base_urls if self._cooldown.get(url, 0.0) <= now]
        return ready or list(self._base_urls)

    async def _get_json(
        self,
        path: str,
        params: dict,
        *,
        validate: Optional[Callable[[dict], None]] = None,
    ) -> Tuple[dict, str]:
        """按顺序尝试各端点，返回 (响应 JSON, 命中的端点)。

        Args:
            validate: 响应结构校验（抛异常即视为该端点不可用，继续回退下一个）。

        Raises:
            QueryUnavailableError: 全部端点失败（网络错误、超时、响应非法）。
        """
        attempts: List[str] = []
        last_error: Optional[Exception] = None
        for base_url in self._ordered_endpoints():
            attempts.append(base_url)
            try:
                data = await self._call(base_url, path, params)
                if not isinstance(data, dict):
                    raise ValueError("响应不是 JSON 对象")
                if validate is not None:
                    validate(data)
                self._cooldown.pop(base_url, None)
                return data, base_url
            except Exception as exc:  # noqa: BLE001 - 任何失败都视为该端点不可用
                last_error = exc
                self._cooldown[base_url] = self._clock() + self._endpoint_cooldown
                logger.warning(
                    "DNDDicer 规则查询端点失败 base_url={} path={}: {}",
                    base_url,
                    path,
                    exc,
                )
        raise QueryUnavailableError(attempts, last_error)

    async def _call(self, base_url: str, path: str, params: dict) -> dict:
        """调用单个端点的 JSON 接口（可注入 transport 供测试使用）。"""
        url = f"{base_url}{path}?{urllib.parse.urlencode(params)}"
        async with self._semaphore:
            if self._transport is not None:
                return await self._transport(url, self._timeout, dict(_HEADERS))
            return await asyncio.to_thread(_http_get_json, url, self._timeout, dict(_HEADERS))

    # ── 缓存 ────────────────────────────────────────────────────────────

    def _cache_get(self, key: Tuple[str, bool]) -> Optional[List[Candidate]]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        expire_at, candidates = entry
        if expire_at <= self._clock():
            self._cache.pop(key, None)
            return None
        # 命中后重新插入以刷新顺序（简易 LRU）
        self._cache.pop(key, None)
        self._cache[key] = entry
        return candidates

    def _cache_put(self, key: Tuple[str, bool], candidates: List[Candidate]) -> None:
        self._cache[key] = (self._clock() + self._cache_ttl, candidates)
        while len(self._cache) > self._cache_max:
            oldest = next(iter(self._cache))
            self._cache.pop(oldest, None)
