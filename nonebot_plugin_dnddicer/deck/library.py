"""牌堆库：扫描骰主自定义目录、搜索与重载。

本插件不内置任何牌堆，所有牌堆都来自数据目录下的 ``decks/*.json``。
同名文件内的重复牌组按解析顺序后者覆盖前者，并写入加载错误摘要。
"""

from __future__ import annotations

import asyncio
import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .models import Deck, DeckFileError, normalize_name
from .parser import parse_deck_file


@dataclass
class DeckResolution:
    """名称解析结果：唯一命中给 deck，多候选给 candidates。"""

    deck: Optional[Deck] = None
    candidates: list[Deck] = field(default_factory=list)


class DeckLibrary:
    """牌堆库（懒加载 + 手动重载）。"""

    def __init__(self, custom_dir: Optional[Path] = None) -> None:
        self._custom_dir = custom_dir
        self._decks: dict[str, Deck] = {}
        self._errors: list[DeckFileError] = []
        self._loaded = False
        self._lock = asyncio.Lock()

    @property
    def custom_dir(self) -> Path:
        """自定义牌堆目录（懒解析，避免导入期依赖 localstore 插件上下文）。"""
        if self._custom_dir is None:
            from ..data import get_data_dir

            self._custom_dir = get_data_dir() / "decks"
        return self._custom_dir

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def errors(self) -> list[DeckFileError]:
        return list(self._errors)

    async def ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._lock:
            if not self._loaded:
                await self._reload_locked()

    async def reload(self) -> None:
        async with self._lock:
            await self._reload_locked()

    async def _reload_locked(self) -> None:
        self._decks = {}
        self._errors = []
        await asyncio.to_thread(self.custom_dir.mkdir, parents=True, exist_ok=True)

        for path in sorted(self.custom_dir.glob("*.json")):
            decks, errors = await asyncio.to_thread(parse_deck_file, path)
            self._errors.extend(errors)
            for deck in decks:
                key = normalize_name(deck.name)
                if key in self._decks:
                    self._errors.append(
                        DeckFileError(
                            file=path,
                            message=f"牌组「{deck.name}」与已加载牌组同名，后者覆盖前者",
                        )
                    )
                self._decks[key] = deck
        self._loaded = True

    # ── 查询 ────────────────────────────────────────────────────────────
    def all_decks(self) -> list[Deck]:
        """全部牌组（含隐藏，供嵌套引用/内部使用）。"""
        return list(self._decks.values())

    def visible(self) -> list[Deck]:
        """可见牌组，按名称排序。"""
        decks = [deck for deck in self._decks.values() if not deck.hidden]
        return sorted(decks, key=lambda deck: deck.name.casefold())

    def exact(self, name: str) -> Optional[Deck]:
        """按名称精确查找可见牌组。"""
        deck = self._decks.get(normalize_name(name))
        if deck is None or deck.hidden:
            return None
        return deck

    def exact_any(self, name: str) -> Optional[Deck]:
        """按名称精确查找任意牌组（含隐藏，供嵌套引用）。"""
        return self._decks.get(normalize_name(name))

    def resolve(self, name: str) -> DeckResolution:
        """精确优先，未命中再按子串匹配。"""
        exact = self.exact(name)
        if exact is not None:
            return DeckResolution(deck=exact)

        keyword = normalize_name(name)
        if not keyword:
            return DeckResolution()
        matches = [
            deck
            for deck in self.visible()
            if keyword in normalize_name(deck.name)
        ]
        if len(matches) == 1:
            return DeckResolution(deck=matches[0])
        return DeckResolution(candidates=matches)

    def search(self, keyword: str, limit: int = 10) -> list[Deck]:
        """按名称搜索可见牌组；完全匹配排在最前。"""
        key = normalize_name(keyword)
        if not key:
            return []
        matches = [
            deck
            for deck in self.visible()
            if key in normalize_name(deck.name)
        ]
        matches.sort(
            key=lambda deck: (
                normalize_name(deck.name) != key,
                deck.name.casefold(),
            )
        )
        return matches[:limit]

    def suggestions(self, name: str, limit: int = 3) -> list[str]:
        """相近名称建议（只给提示，不自动选择）。"""
        names = [deck.name for deck in self.visible()]
        return difflib.get_close_matches(name, names, n=limit, cutoff=0.4)

    def image_roots(self) -> list[Path]:
        """图片根目录（只有骰主自定义目录）。"""
        return [self.custom_dir / "images"]


__all__ = ["DeckLibrary", "DeckResolution"]
