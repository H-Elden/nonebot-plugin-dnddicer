"""牌堆数据模型：文件元数据、牌组、条目与加载错误。

牌堆文件保持 Dice! JSON 的「牌组名 → 字符串数组」结构，本模块只做只读承载；
权重、隐藏、图片等语法在 ``parser`` / ``draw`` / ``media`` 中处理。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

def normalize_name(name: str) -> str:
    """牌堆名归一：NFKC、去首尾空白、大小写不敏感。"""
    return unicodedata.normalize("NFKC", name or "").strip().casefold()


@dataclass(frozen=True)
class DeckMeta:
    """牌堆文件的元数据（值通常来自 JSON 的字符串数组）。"""

    title: str = ""
    author: str = ""
    version: str = ""
    license: str = ""
    source: str = ""
    brief: str = ""
    date: str = ""
    update_date: str = ""
    export: tuple[str, ...] = ()
    keys: tuple[str, ...] = ()


@dataclass
class DeckItem:
    """牌组中的一条内容（保留原始文本，图片/表达式在抽取时解析）。"""

    raw: str
    weight: int = 1
    line: int = 0


@dataclass
class Deck:
    """一个可抽取的牌组。"""

    name: str
    items: list[DeckItem]
    file: Path
    meta: DeckMeta
    hidden: bool = False

    @property
    def count(self) -> int:
        """条目数。"""
        return len(self.items)

    @property
    def has_images(self) -> bool:
        """是否至少有一条包含 ``[img:...]`` 标记（仅作列表/详情展示用）。"""
        return any("[img:" in item.raw for item in self.items)

    @property
    def image_count(self) -> int:
        """条目中出现的图片标记总数（粗略统计，实际以抽取时的展开为准）。"""
        total = 0
        for item in self.items:
            total += item.raw.count("[img:")
        return total


@dataclass
class DeckFileError:
    """单个牌堆文件的加载错误（只进日志与骰主重载摘要）。"""

    file: Path
    message: str


@dataclass
class RenderedEntry:
    """一条渲染后的抽取结果：文本段与图片段按出现顺序排列。"""

    parts: list[object] = field(default_factory=list)

    @property
    def has_image(self) -> bool:
        return any(isinstance(part, DeckImagePart) for part in self.parts)

    @property
    def text(self) -> str:
        return "".join(
            part.text for part in self.parts if isinstance(part, DeckTextPart)
        )


@dataclass(frozen=True)
class DeckTextPart:
    """渲染结果中的文本段。"""

    text: str


@dataclass(frozen=True)
class DeckImagePart:
    """渲染结果中的图片段（相对路径，由命令层读取并校验）。"""

    rel_path: str
    filename: str


@dataclass
class DrawResult:
    """一次顶层抽取的结果。"""

    entries: list[RenderedEntry]
    requested: int
    exhausted: bool = False

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def has_image(self) -> bool:
        return any(entry.has_image for entry in self.entries)
