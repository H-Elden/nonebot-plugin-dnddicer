"""牌堆图片：路径安全、魔数/体积校验与读取。

安全边界（2026-11-02 计划）：

- 只允许 ``[img:images/...]`` 的本地相对路径；
- 禁止绝对路径、``..``、反斜杠、``~``、URL、CQ 码；不跟随符号链接；
- 解析后必须仍在 ``images/`` 根目录内；
- PNG / JPG / WebP，单张 ≤ 4 MB；按魔数识别，不信任扩展名。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Iterable, Optional

from ..data.portraits import detect_image_type

#: 单张与单次抽取的图片限制
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGES_PER_ENTRY = 5
MAX_IMAGES_PER_DRAW = 10

#: 图片标记（与 draw 层共用；路径中不允许右方括号）
IMAGE_TOKEN_RE = re.compile(r"\[img:([^\]]+)\]")

#: 路径中不允许的控制字符
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class DeckImageError(Exception):
    """图片缺失、路径非法、格式不符或超体积。"""

    def __init__(self, filename: str, message: str, *, missing: bool = False):
        super().__init__(message)
        self.filename = filename
        self.missing = missing


@dataclass(frozen=True)
class ImageData:
    """通过校验的图片字节与展示名。"""

    data: bytes
    filename: str
    mime: str


def image_paths(raw: str) -> list[str]:
    """提取条目文本中的全部图片相对路径（按出现顺序）。"""
    return [match.group(1).strip() for match in IMAGE_TOKEN_RE.finditer(raw)]


def _validate_rel_path(rel_path: str) -> PurePosixPath:
    """校验并返回安全的相对路径；非法时抛 ``DeckImageError``。"""
    name = rel_path.strip()
    if not name:
        raise DeckImageError("", "图片路径为空")
    if "\\" in name or "\x00" in name or _CONTROL_RE.search(name):
        raise DeckImageError(name, "图片路径包含非法字符")
    if name.startswith("/") or name.startswith("~") or re.match(r"^[A-Za-z]:", name):
        raise DeckImageError(name, "图片路径必须是相对路径")
    if "://" in name or name.lower().startswith(("http:", "https:", "base64:")):
        raise DeckImageError(name, "图片路径不支持 URL / base64")
    if "[CQ:" in name.upper():
        raise DeckImageError(name, "图片路径不支持 CQ 码")

    path = PurePosixPath(name)
    parts = path.parts
    if not parts or parts[0] != "images":
        raise DeckImageError(name, "图片必须放在 images/ 目录下")
    if any(part in {"", ".", ".."} for part in parts):
        raise DeckImageError(name, "图片路径不能包含 . 或 ..")
    return path


def _resolve_path(rel_path: str, roots: Iterable[Path]) -> Optional[Path]:
    """在给定根目录中查找图片；自定义根优先（由调用方排序）。"""
    path = _validate_rel_path(rel_path)
    relative_parts = path.parts[1:]  # 去掉开头的 images/
    for root in roots:
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        candidate = root_resolved.joinpath(*relative_parts)
        # 逐级检查符号链接，避免图片目录被链接到根目录之外
        current = root_resolved
        has_symlink = False
        for part in relative_parts:
            current = current / part
            if current.is_symlink():
                has_symlink = True
                break
        if has_symlink:
            continue
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if not resolved.is_relative_to(root_resolved):
            continue
        if not resolved.is_file():
            continue
        return resolved
    return None


@lru_cache(maxsize=8)
def _read_bytes(path_str: str, mtime_ns: int, size: int) -> bytes:
    """按路径 + mtime + size 缓存图片字节（避免连续抽取重复读盘）。"""
    _ = (mtime_ns, size)  # 仅用于缓存键
    return Path(path_str).read_bytes()


def load_image(rel_path: str, roots: Iterable[Path]) -> ImageData:
    """读取并校验一张图片。

    Raises:
        DeckImageError: 路径非法、文件缺失、格式不支持或超过体积。
    """
    filename = PurePosixPath(rel_path.strip()).name or rel_path.strip()
    resolved = _resolve_path(rel_path, roots)
    if resolved is None:
        raise DeckImageError(filename, f"图片不存在：{filename}", missing=True)

    try:
        stat = resolved.stat()
        if stat.st_size > MAX_IMAGE_BYTES:
            raise DeckImageError(
                filename,
                f"图片超过 {MAX_IMAGE_BYTES // 1024 // 1024} MB：{filename}",
            )
        data = _read_bytes(str(resolved), stat.st_mtime_ns, stat.st_size)
    except DeckImageError:
        raise
    except OSError as exc:
        raise DeckImageError(filename, f"图片读取失败：{filename}（{exc}）") from exc

    detected = detect_image_type(data)
    if detected is None:
        raise DeckImageError(filename, f"图片格式不支持：{filename}")
    _, mime = detected
    return ImageData(data=data, filename=filename, mime=mime)


__all__ = [
    "DeckImageError",
    "ImageData",
    "IMAGE_TOKEN_RE",
    "MAX_IMAGES_PER_DRAW",
    "MAX_IMAGES_PER_ENTRY",
    "MAX_IMAGE_BYTES",
    "MAX_TOTAL_IMAGE_BYTES",
    "image_paths",
    "load_image",
]
