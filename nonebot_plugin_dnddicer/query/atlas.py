"""速查索引（Atlas）：规则查询子命令（``.查询法术`` 等）的检索层（2026-09-26）。

**内容边界与合规**：索引只存**条目名与元数据**（名称、英文名、环阶 / CR /
稀有度 / 出处、目标页面路径与锚点），**不含规则正文**；正文仍在用户查询时
实时抓取（见 ``query/fetch.py`` 与 ``query/decode.py``）并按当次会话展示。
索引存插件本地缓存目录（localstore），不随插件分发。

**索引来源（自动跟随站点目录，不硬编码页面清单）**：

- 法术 / 怪物 / 物品：站点「本书速查」下的三对速查表（官方 + 合作），每行
  带条目标题、元数据列与「详情页 + 锚点」链接；
- 职业 / 起源：``toc.htm``（站点自动生成的全站目录）里按路径段筛选页面，
  条目名取目录节点名（职业页 / 子职页 / 种族页 / 背景页都是独立页面）；
- 专长：专长页内以紫红加粗块（``<FONT color=#800000>``）标记条目，扫描得到
  条目名（站点专长不是独立页面，无法只靠目录）；
- 术语：术语速查页的「术语 → 状态页锚点」链接索引；
- 单位：单位转换页的小节标题（长度 / 重量 / 温度 / 体积 / 货币）。

**刷新策略（2026-09-26 用户拍板）**：启动时后台全量构建一次，缓存不自动
过期（站点几个月才更新一版）；需要更新时由骰主手动刷新（``.查询索引``）。
"""

from __future__ import annotations

import re
import time
import urllib.parse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from nonebot import logger

from . import books
from .fetch import HtmlFetcher
from .models import QueryUnavailableError

# ── 类别常量 ───────────────────────────────────────────────────────────

KIND_SPELL = "spell"
KIND_MONSTER = "monster"
KIND_ITEM = "item"
KIND_FEAT = "feat"
KIND_CLASS = "class"
KIND_ORIGIN = "origin"
KIND_TERM = "term"
KIND_UNIT = "unit"

#: 类别 → 中文展示名（子命令、状态输出共用）
KIND_LABELS: Dict[str, str] = {
    KIND_SPELL: "法术",
    KIND_MONSTER: "怪物",
    KIND_ITEM: "物品",
    KIND_FEAT: "专长",
    KIND_CLASS: "职业",
    KIND_ORIGIN: "起源",
    KIND_TERM: "术语",
    KIND_UNIT: "单位",
}

#: 构建顺序（速查表类在前，页面扫描类在后）
BUILD_KINDS: Tuple[str, ...] = (
    KIND_SPELL,
    KIND_MONSTER,
    KIND_ITEM,
    KIND_FEAT,
    KIND_CLASS,
    KIND_ORIGIN,
    KIND_TERM,
    KIND_UNIT,
)

#: 速查表 / 入口页路径（2026-09-26 实测；站点若改路径属「站点改版」类维护）
_QUICKREF_PAGES: Dict[str, Tuple[str, ...]] = {
    KIND_SPELL: ("速查/法术速查/5E万法大全.html", "速查/法术速查/合作方万法大全.html"),
    KIND_MONSTER: ("速查/5E万兽大全.html", "速查/合作万兽大全.html"),
    KIND_ITEM: ("速查/5E万器大全.htm", "速查/合作万器大全.htm"),
}
_TERM_PAGE = "玩家手册2024/术语汇编/术语速查.htm"
_UNIT_PAGE = "速查/单位转换.htm"
#: 站点根路径（不在 topics 下，前导斜杠约定见 fetch.build_page_url）。
#: 目录页 = 站点首页 iframe 引用的 ``webhelpcontents.htm``（WinCHM 生成的
#: 全站目录，含全部页面节点与标题；2026-09-26 实测 `/toc.htm` 已 404）。
_TOC_PAGE = "/webhelpcontents.htm"

#: toc 路径筛选（职业 / 起源页面）
_CLASS_HINT = "角色职业/"
_ORIGIN_HINT = "角色起源/"
_FEAT_HINT = "专长/"

#: 单次查询返回上限
LOOKUP_LIMIT = 20


# ── 数据模型 ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AtlasEntry:
    """一条索引项（不含规则正文）。"""

    kind: str
    name: str
    category: str  # 站内一级目录名（查询范围的过滤键）
    page_path: str  # 站内相对路径（含后缀，供 fetch.build_page_url 拼接）
    anchor: str = ""  # 详情页锚点（可空，空则按标题形态定位）
    name_en: str = ""  # 英文名（可空）
    meta: str = ""  # 展示用元数据（如「三环 · 塑能」「CR2 · 大型巨人」）

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "AtlasEntry":
        return AtlasEntry(
            kind=str(data.get("kind", "")),
            name=str(data.get("name", "")),
            category=str(data.get("category", "")),
            page_path=str(data.get("page_path", "")),
            anchor=str(data.get("anchor", "")),
            name_en=str(data.get("name_en", "")),
            meta=str(data.get("meta", "")),
        )


# ── 纯解析函数（离线可测）─────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_ROW_TMPL = r'<TR[^>]*?\b{hint}="([^"]*)"[^>]*>(.*?)</TR>'
_CELL_RE = re.compile(r"<TD[^>]*>(.*?)</TD>", re.S | re.I)
_HREF_RE = re.compile(r'href="([^"]+)"', re.I)


def _clean(text: str) -> str:
    """去标签、折叠空白（含全角空格）。"""
    text = _TAG_RE.sub("", text)
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


def split_name_zh_en(combo: str) -> Tuple[str, str]:
    """把「中文名English Name」拆为 (中文名, 英文名)。

    速查表的标题属性与专长页的红标题都是连写形态（如
    ``塔莎泡泡坩埚Tasha's Bubbling Cauldron``）；纯中文名（无英文）时
    英文名为空串。星号（复选标记）一律去掉。
    """
    combo = _clean(combo).replace("*", "").strip()
    match = re.search(r"[A-Za-z]", combo)
    if match is None:
        return combo, ""
    name = combo[: match.start()].strip(" ·：:")
    name_en = combo[match.start() :].strip()
    return name or combo, name_en


def parse_href(href: str) -> Tuple[str, str]:
    """把页面内的相对链接拆为 (站内相对路径, 锚点)。

    链接形如 ``../城主指南2024/7.宝藏/…/神器.htm#Orb_of_Dragonkind``（速查表
    在 ``topics/速查/…`` 下，``../`` 回退到 ``topics/``）；返回的路径是
    ``topics/`` **之后**的相对路径（与 ``AtlasEntry.page_path`` 同一体系）。
    """
    target = urllib.parse.unquote(href).strip()
    anchor = ""
    if "#" in target:
        target, anchor = target.split("#", 1)
    while target.startswith("../"):
        target = target[3:]
    target = target[2:] if target.startswith("./") else target
    return target.strip("/"), anchor


def _category_of(page_path: str) -> str:
    """条目所属站内一级目录（页面路径第一段）。"""
    return page_path.split("/", 1)[0] if page_path else ""


def _page_stem(page_path: str) -> str:
    """页面文件名（去目录与后缀）——专长条目的分类展示（如「通用专长」）。"""
    return page_path.rsplit("/", 1)[-1].rsplit(".", 1)[0] if page_path else ""


def _category_rank(category: str) -> int:
    """书目排序权重：按书架顺序（核心 2024 在前、旧版在后、整目录最后）。

    让同名条目（如「火球术」的 2024 与 2014 版）默认把新版排在前；不在书目
    表中的目录（如「速查」）排在最后。
    """
    entry = books.entry_by_category(category)
    if entry is None:
        return 999
    return _CATEGORY_ORDER.get(category, 999)


#: 目录名 → 书架顺序（模块加载时构建一次）
_CATEGORY_ORDER: Dict[str, int] = {
    entry.category: index for index, entry in enumerate(books.SCOPE_ENTRIES)
}


def _quickref_meta(kind: str, cells: Sequence[str]) -> str:
    """速查表行的展示元数据（按类别取列）。"""
    try:
        if kind == KIND_SPELL:
            return " · ".join(part for part in (cells[1], cells[2]) if part)
        if kind == KIND_MONSTER:
            parts = [part for part in (cells[1], cells[2]) if part]
            if len(cells) > 4 and cells[4]:
                parts.append(f"CR{cells[4]}")
            return " · ".join(parts)
        if kind == KIND_ITEM:
            return " · ".join(part for part in (cells[1], cells[2]) if part)
    except IndexError:
        return ""
    return ""


def parse_quickref(html: str, *, kind: str) -> List[AtlasEntry]:
    """解析速查表页（万法 / 万兽 / 万器，行属性含条目名与链接）。"""
    row_re = re.compile(_ROW_TMPL.format(hint=kind), re.S | re.I)
    entries: List[AtlasEntry] = []
    for match in row_re.finditer(html):
        name, name_en = split_name_zh_en(match.group(1))
        if not name:
            continue
        row = match.group(2)
        href_match = _HREF_RE.search(row)
        if href_match is None:
            continue
        page_path, anchor = parse_href(href_match.group(1))
        if not page_path:
            continue
        cells = [_clean(cell) for cell in _CELL_RE.findall(row)]
        entries.append(
            AtlasEntry(
                kind=kind,
                name=name,
                name_en=name_en,
                category=_category_of(page_path),
                page_path=page_path,
                anchor=anchor,
                meta=_quickref_meta(kind, cells),
            )
        )
    return entries


_TERM_LINK_RE = re.compile(r'<A[^>]*href="([^"]+)"[^>]*>(.*?)</A>', re.I | re.S)


def parse_terms(html: str, *, page_path: str) -> List[AtlasEntry]:
    """解析术语速查页：``<A href="./状态.htm#Prone">倒地</A>`` → 术语条目。"""
    base_dir = page_path.rsplit("/", 1)[0] + "/"
    entries: List[AtlasEntry] = []
    seen: set = set()
    for href, inner in _TERM_LINK_RE.findall(html):
        name = _clean(inner)
        if not name or name in seen:
            continue
        target = urllib.parse.urljoin(base_dir, urllib.parse.unquote(href).strip())
        path, anchor = parse_href(target)
        if not path:
            continue
        seen.add(name)
        entries.append(
            AtlasEntry(
                kind=KIND_TERM,
                name=name,
                category=_category_of(path),
                page_path=path,
                anchor=anchor,
            )
        )
    return entries


_FEAT_HEAD_RE = re.compile(
    r"<FONT\s+color=#800000[^>]*>(.{0,200}?)</FONT>", re.S | re.I
)

#: 专长页里的章节性标题（非条目，扫描时排除）
_FEAT_NOISE = ("描述", "列表", "组成部分", "先决", "分类", "复选", "译注", "目录")


def parse_feat_page(html: str, *, page_path: str) -> List[AtlasEntry]:
    """扫描专长页的紫红加粗标题块，得到该页的专长条目。

    站点专长不是独立页面（一页含多个专长），条目以
    ``<FONT color=#800000>中文名<BR>English</FONT>`` 形态标记；章节标题
    （如「专长描述 Feat Descriptions」）按关键词与长度过滤。``meta`` 取页面
    文件名作为**分类**（站点专长按类分页：通用专长 / 起源专长 / 战斗风格专长…）。
    """
    entries: List[AtlasEntry] = []
    seen: set = set()
    meta = _page_stem(page_path)
    for match in _FEAT_HEAD_RE.finditer(html):
        text = _clean(re.sub(r"<BR\s*/?>", " ", match.group(1), flags=re.I))
        if not text or len(text) > 40:
            continue
        name, name_en = split_name_zh_en(text)
        if not name or name in seen:
            continue
        if any(word in name for word in _FEAT_NOISE):
            continue
        seen.add(name)
        entries.append(
            AtlasEntry(
                kind=KIND_FEAT,
                name=name,
                name_en=name_en,
                category=_category_of(page_path),
                page_path=page_path,
                meta=meta,
            )
        )
    return entries


_TOC_LINK_RE = re.compile(
    r'href="topics/([^"]+\.html?)"[^>]*>(?:<[^>]+>)*<span[^>]*>([^<]*)</span>',
    re.I,
)


def parse_toc_pages(html: str) -> List[Tuple[str, str]]:
    """解析 toc.htm：返回 (站内相对路径, 目录节点名) 列表。"""
    pages: List[Tuple[str, str]] = []
    for path, title in _TOC_LINK_RE.findall(html):
        path = urllib.parse.unquote(path)
        title = _clean(title)
        if not title or title.startswith("—"):
            continue
        pages.append((path, title))
    return pages


def entries_from_toc(pages: Iterable[Tuple[str, str]]) -> List[AtlasEntry]:
    """从目录页集合筛出职业 / 起源条目（条目名取目录节点名）。"""
    entries: List[AtlasEntry] = []
    seen: set = set()
    for path, title in pages:
        kind = ""
        meta = ""
        if _CLASS_HINT in path:
            kind = KIND_CLASS
            segments = path.split("/")
            # 角色职业/<职业>/<职业>.htm = 职业；同目录下其它页 = 子职
            parent = segments[-2] if len(segments) >= 2 else ""
            meta = "职业" if segments[-1].rsplit(".", 1)[0] == parent else "子职"
        elif _ORIGIN_HINT in path:
            kind = KIND_ORIGIN
            segments = path.split("/")
            meta = segments[segments.index("角色起源") + 1] if "角色起源" in segments else ""
            if meta not in ("背景", "种族"):
                continue  # 章节导览页等
        if not kind:
            continue
        key = (kind, title)
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            AtlasEntry(
                kind=kind,
                name=title,
                category=_category_of(path),
                page_path=path,
                meta=meta,
            )
        )
    return entries


def feat_page_paths(pages: Iterable[Tuple[str, str]]) -> List[str]:
    """从目录页集合筛出专长页路径（供逐页扫描条目）。"""
    paths: List[str] = []
    for path, _title in pages:
        if _FEAT_HINT in path and path.endswith((".htm", ".html")):
            if path not in paths:
                paths.append(path)
    return paths


_UNIT_SECTION_RE = re.compile(
    r"<FONT\s+color=#800000[^>]*>(.{1,20}?)</FONT>", re.S | re.I
)


def parse_unit_sections(html: str, *, page_path: str) -> List[AtlasEntry]:
    """解析单位转换页的小节标题（长度 / 重量 / 温度 / 体积 / 货币）。"""
    entries: List[AtlasEntry] = []
    seen: set = set()
    for match in _UNIT_SECTION_RE.finditer(html):
        name = _clean(match.group(1))
        if not name or name in seen or len(name) > 8:
            continue
        seen.add(name)
        entries.append(
            AtlasEntry(
                kind=KIND_UNIT,
                name=name,
                category=_category_of(page_path),
                page_path=page_path,
                meta="单位转换",
            )
        )
    return entries


# ── 索引存储（构建 / 缓存 / 查询）──────────────────────────────────────


class AtlasStore:
    """速查索引的构建、本地缓存与查询。

    - ``build``：抓取来源页并解析出各类条目（可指定类别子集）；
    - ``save`` / ``load``：JSON 缓存（``schema_version`` 版本化，见 data/schema）；
    - 自检：新构建条目数低于旧缓存的 ``min_keep_ratio`` 时**不覆盖**旧缓存
      （站点异常/改版导致解析变空时不至于静默失效），仅记日志；
    - ``lookup``：关键词匹配（精确 > 前缀 > 子串）+ 范围过滤。
    """

    def __init__(
        self,
        fetcher: HtmlFetcher,
        *,
        cache_file: Optional[Path] = None,
        min_keep_ratio: float = 0.5,
        clock: Callable[[], float] = time.time,
    ) -> None:
        # data 层（localstore）按需延迟导入：本模块在 query 包内，引擎单测等
        # 离线场景可能在 NoneBot 初始化前导入本包，顶层 import data 会触发
        # localstore require 失败。
        from ..data import get_data_file

        self._fetcher = fetcher
        self._cache_file = cache_file if cache_file is not None else get_data_file(
            "query_atlas.json"
        )
        self._min_keep_ratio = min_keep_ratio
        #: 构建时间用**墙上时钟**（要落盘并在骰主命令里展示，不能用单调时钟）
        self._clock = clock
        self._entries: Dict[str, List[AtlasEntry]] = {}
        self._built_at: Optional[float] = None

    # ── 查询 ────────────────────────────────────────────────────────────

    @property
    def fetcher(self) -> HtmlFetcher:
        """页面抓取器（正文层按候选页取正文时复用同一实例与缓存）。"""
        return self._fetcher

    @property
    def ready(self) -> bool:
        """是否已有可用索引（构建完成或从缓存加载）。"""
        return bool(self._entries)

    @property
    def built_at(self) -> Optional[float]:
        """索引构建时间（本地时钟；None 表示尚未构建/加载）。"""
        return self._built_at

    def counts(self) -> Dict[str, int]:
        """各类别条目数（供骰主命令状态输出）。"""
        return {kind: len(self._entries.get(kind, ())) for kind in BUILD_KINDS}

    def lookup(
        self,
        kind: str,
        keyword: str,
        *,
        categories: Optional[Sequence[str]] = None,
        limit: int = LOOKUP_LIMIT,
    ) -> List[AtlasEntry]:
        """按关键词查索引：精确 > 前缀 > 子串；可选按站内目录过滤（查询范围）。"""
        keyword = keyword.strip()
        if not keyword:
            return []
        wanted = keyword.casefold()
        scored: List[Tuple[int, AtlasEntry]] = []
        for entry in self._entries.get(kind, ()):
            if categories and entry.category not in categories:
                continue
            name = entry.name.casefold()
            name_en = entry.name_en.casefold()
            score = 0
            if wanted == name or (name_en and wanted == name_en):
                score = 3
            elif name.startswith(wanted) or (name_en and name_en.startswith(wanted)):
                score = 2
            elif wanted in name or (name_en and wanted in name_en):
                score = 1
            if score:
                scored.append((score, entry))
        # 同分排序：名称短者优先（更接近查询词），再按书架顺序（新版在前）、
        # 页面路径稳定排序
        scored.sort(
            key=lambda item: (
                -item[0],
                len(item[1].name),
                _category_rank(item[1].category),
                item[1].page_path,
            )
        )
        return [entry for _score, entry in scored[:limit]]

    # ── 构建 ────────────────────────────────────────────────────────────

    async def build(
        self, kinds: Optional[Sequence[str]] = None
    ) -> Dict[str, List[AtlasEntry]]:
        """抓取来源页并解析指定类别的条目（不落盘；合并与落盘见 merge_and_save）。

        网络失败（QueryUnavailableError）会向上抛出，由调用方决定降级
        （启动构建失败保留旧缓存；手动刷新失败回报错误）。
        """
        targets = tuple(kinds) if kinds else BUILD_KINDS
        entries: Dict[str, List[AtlasEntry]] = {}
        toc_pages: Optional[List[Tuple[str, str]]] = None

        def need_toc() -> bool:
            return any(
                kind in (KIND_FEAT, KIND_CLASS, KIND_ORIGIN) for kind in targets
            )

        if need_toc():
            toc_html = await self._fetcher.get_page(_TOC_PAGE)
            toc_pages = parse_toc_pages(toc_html)
            logger.info("DNDDicer 速查索引：目录页 {} 条链接", len(toc_pages))

        for kind in targets:
            if kind in _QUICKREF_PAGES:
                collected: List[AtlasEntry] = []
                for page in _QUICKREF_PAGES[kind]:
                    html = await self._fetcher.get_page(page)
                    collected.extend(parse_quickref(html, kind=kind))
                entries[kind] = collected
            elif kind == KIND_TERM:
                html = await self._fetcher.get_page(_TERM_PAGE)
                entries[kind] = parse_terms(html, page_path=_TERM_PAGE)
            elif kind == KIND_UNIT:
                html = await self._fetcher.get_page(_UNIT_PAGE)
                entries[kind] = parse_unit_sections(html, page_path=_UNIT_PAGE)
            elif kind == KIND_FEAT:
                collected = []
                for path in feat_page_paths(toc_pages or ()):
                    html = await self._fetcher.get_page(path)
                    collected.extend(parse_feat_page(html, page_path=path))
                entries[kind] = collected
            elif kind in (KIND_CLASS, KIND_ORIGIN):
                entries[kind] = [
                    entry
                    for entry in entries_from_toc(toc_pages or ())
                    if entry.kind == kind
                ]
            logger.info(
                "DNDDicer 速查索引：{} 解析 {} 条",
                KIND_LABELS.get(kind, kind),
                len(entries.get(kind, ())),
            )
        return entries

    async def rebuild(
        self, kinds: Optional[Sequence[str]] = None
    ) -> Dict[str, str]:
        """构建并合并落盘（便捷入口；返回各类别处理结果）。"""
        built = await self.build(kinds)
        return self.merge_and_save(built)

    # ── 缓存 ────────────────────────────────────────────────────────────

    def merge_and_save(self, build_result: Dict[str, List[AtlasEntry]]) -> Dict[str, str]:
        """把一次构建结果合并进索引并按自检规则落盘。

        Returns:
            各类别的处理结果：``updated``（已更新）/ ``kept``（条目数异常，
            保留旧数据）/ ``new``（首次建立）。
        """
        outcomes: Dict[str, str] = {}
        previous = self.counts()
        for kind, items in build_result.items():
            old_count = previous.get(kind, 0)
            if (
                old_count
                and len(items) < old_count * self._min_keep_ratio
            ):
                outcomes[kind] = "kept"
                logger.warning(
                    "DNDDicer 速查索引：{} 新构建 {} 条低于旧值 {} 条的一半，"
                    "保留旧索引（疑似站点异常或改版，请检查）",
                    KIND_LABELS.get(kind, kind),
                    len(items),
                    old_count,
                )
                continue
            self._entries[kind] = list(items)
            outcomes[kind] = "updated" if old_count else "new"
        self._built_at = self._clock()
        self.save()
        return outcomes

    def save(self) -> None:
        """把当前索引写入缓存文件（版本化 JSON）。"""
        from ..data.schema import dump_versioned_dict

        payload = {
            "built_at": self._built_at if self._built_at is not None else self._clock(),
            "entries": {
                kind: [entry.to_dict() for entry in items]
                for kind, items in self._entries.items()
            },
        }
        try:
            dump_versioned_dict(self._cache_file, payload)
        except OSError:
            logger.exception("DNDicer 速查索引写入缓存失败：{}", self._cache_file)

    def load(self) -> bool:
        """从缓存文件加载索引；无缓存或数据损坏返回 False。"""
        from ..data.schema import load_versioned_dict

        data = load_versioned_dict(self._cache_file)
        raw_entries = data.get("entries")
        if not isinstance(raw_entries, dict):
            return False
        loaded: Dict[str, List[AtlasEntry]] = {}
        for kind, items in raw_entries.items():
            if not isinstance(items, list):
                continue
            loaded[str(kind)] = [
                AtlasEntry.from_dict(item) for item in items if isinstance(item, dict)
            ]
        if not loaded:
            return False
        self._entries = loaded
        built_at = data.get("built_at")
        self._built_at = float(built_at) if isinstance(built_at, (int, float)) else None
        return True
