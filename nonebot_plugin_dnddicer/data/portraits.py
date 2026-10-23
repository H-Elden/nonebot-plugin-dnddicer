"""角色立绘：原图直存、魔数校验、读取与清理（2026-10-21）。

口径（2026-10-21 立绘批次）：插件端**零图像后处理**，不压缩、不缩放、不重编码、
不转正 EXIF、不裁切；只校验图片格式（按魔数，不看扩展名）与 4 MB 体积上限。
剪裁与取景由后续网页建卡器的裁切工具负责。

存储：``<插件数据目录>/portraits/<card_id>.<扩展名>``（2026-10-23 卡库化后）。
旧格式 ``<群号>_<QQ号>.<扩展名>`` 若存在仍可读取，不做文件迁移。

图片获取只在 ``.立绘`` 上传时发生：本地路径优先，其次 http(s) URL，
最后走 OneBot ``get_image``；渲染阶段只读本地文件并转 data URI，不联网。
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional, Tuple

from nonebot import logger

from . import get_data_dir

#: 立绘体积上限（4 MB，2026-10-21 立绘批次口径）
MAX_PORTRAIT_BYTES = 4 * 1024 * 1024

#: 支持的图片类型：扩展名 -> MIME
_IMAGE_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
}

#: 相对文件名的安全形态（只允许 portraits/ 下的字母数字与固定扩展名）
_NAME_RE = re.compile(r"^portraits/[A-Za-z0-9_-]+\.(png|jpg|webp)$")

#: 下载超时（秒）与分块大小
_FETCH_TIMEOUT = 10.0
_CHUNK_SIZE = 64 * 1024
_USER_AGENT = "DNDDicer-Portrait/0.1 (OneBot image fetch)"


class PortraitError(Exception):
    """立绘相关错误的基类（命令层映射为用户文案）。"""


class PortraitTooLarge(PortraitError):
    """图片超过体积上限。"""


class PortraitBadFormat(PortraitError):
    """不是受支持的图片格式。"""


class PortraitFetchFailed(PortraitError):
    """图片读取/下载失败。"""


def detect_image_type(data: bytes) -> Optional[Tuple[str, str]]:
    """按魔数识别图片，返回 ``(扩展名, MIME)``；不支持时返回 None。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", _IMAGE_TYPES["png"]
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", _IMAGE_TYPES["jpg"]
    if (
        len(data) >= 12
        and data[:4] == b"RIFF"
        and data[8:12] == b"WEBP"
    ):
        return "webp", _IMAGE_TYPES["webp"]
    return None


def _portrait_path(name: str) -> Path:
    """把相对文件名解析为数据目录下的安全路径。"""
    if not _NAME_RE.fullmatch(name):
        raise PortraitFetchFailed("立绘文件名不合法")
    return get_data_dir() / name


def _target_name(card_id: str, ext: str) -> str:
    """生成当前卡的立绘文件名（只保留字母数字、下划线与短横线）。"""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", str(card_id))[:80]
    return f"portraits/{safe}.{ext}"


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _remove_same_stem(path: Path) -> None:
    """删除同主键的其他扩展名文件（换图时旧格式不残留）。"""
    for ext in _IMAGE_TYPES:
        candidate = path.with_suffix(f".{ext}")
        if candidate != path and candidate.exists():
            candidate.unlink(missing_ok=True)


async def save_portrait(
    card_id: str, data: bytes, old_name: str = ""
) -> str:
    """校验并原样保存立绘，返回相对文件名；失败抛 ``PortraitError``。"""
    if len(data) > MAX_PORTRAIT_BYTES:
        raise PortraitTooLarge
    detected = detect_image_type(data)
    if detected is None:
        raise PortraitBadFormat
    ext, _mime = detected
    name = _target_name(card_id, ext)
    path = _portrait_path(name)
    # 先写新图再清旧文件：写盘失败时旧图仍在
    try:
        await asyncio.to_thread(_write_bytes, path, data)
        await asyncio.to_thread(_remove_same_stem, path)
    except OSError as exc:
        raise PortraitFetchFailed from exc
    if old_name and old_name != name:
        await delete_portrait(old_name)
    return name


async def load_portrait(name: str) -> Optional[Tuple[bytes, str]]:
    """读取立绘字节与 MIME；文件不存在/损坏返回 None（不阻断卡面渲染）。"""
    if not name:
        return None
    try:
        path = _portrait_path(name)
    except PortraitFetchFailed:
        return None
    if not await asyncio.to_thread(path.is_file):
        return None
    try:
        data = await asyncio.to_thread(path.read_bytes)
    except OSError:
        logger.warning("DNDDicer 立绘读取失败: {}", name)
        return None
    detected = detect_image_type(data)
    if detected is None:
        logger.warning("DNDDicer 立绘格式异常，按无图处理: {}", name)
        return None
    return data, detected[1]


async def delete_portrait(name: str) -> None:
    """删除立绘文件；不存在或文件名异常时静默返回。"""
    if not name:
        return
    try:
        path = _portrait_path(name)
    except PortraitFetchFailed:
        return
    try:
        await asyncio.to_thread(path.unlink, missing_ok=True)
    except OSError:
        logger.warning("DNDDicer 立绘删除失败: {}", name)


# ── 上传时的图片获取 ────────────────────────────────────────────────


def _read_limited(path: Path) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise PortraitFetchFailed from exc
    if size > MAX_PORTRAIT_BYTES:
        raise PortraitTooLarge
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PortraitFetchFailed from exc
    if len(data) > MAX_PORTRAIT_BYTES:
        raise PortraitTooLarge
    return data


def _is_public_host(host: str) -> bool:
    """判断主机是否只解析到公网地址（拒绝回环/私网/链路本地/保留地址）。"""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """跟随重定向前再次校验目标主机，防止跳转到内网地址。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        parsed = urllib.parse.urlparse(newurl)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or not _is_public_host(parsed.hostname)
        ):
            raise PortraitFetchFailed
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download_limited(url: str) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise PortraitFetchFailed
    if not _is_public_host(parsed.hostname):
        raise PortraitFetchFailed
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    opener = urllib.request.build_opener(_SafeRedirectHandler())
    try:
        with opener.open(request, timeout=_FETCH_TIMEOUT) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_PORTRAIT_BYTES:
                raise PortraitTooLarge
            chunks = []
            total = 0
            while True:
                chunk = response.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_PORTRAIT_BYTES:
                    raise PortraitTooLarge
                chunks.append(chunk)
            return b"".join(chunks)
    except PortraitError:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一转为可读错误
        raise PortraitFetchFailed from exc


async def _read_local_or_base64(file_value: str) -> Optional[bytes]:
    """处理本地路径、file:// 与 base64:// 三种 file 形态；不匹配返回 None。"""
    if file_value.startswith("base64://"):
        try:
            data = base64.b64decode(file_value[len("base64://"):])
        except Exception as exc:  # noqa: BLE001
            raise PortraitFetchFailed from exc
        if len(data) > MAX_PORTRAIT_BYTES:
            raise PortraitTooLarge
        return data
    if file_value.startswith("file://"):
        parsed = urllib.parse.urlparse(file_value)
        file_value = urllib.request.url2pathname(parsed.path)
    path = Path(file_value)
    if await asyncio.to_thread(path.is_file):
        return await asyncio.to_thread(_read_limited, path)
    return None


async def fetch_image_bytes(bot: Any, segment_data: dict) -> bytes:
    """从 OneBot 图片段获取原始字节。

    顺序：本地路径/base64 → http(s) URL → ``get_image``（返回本地路径或 URL）。
    体积上限在每一层都检查；失败抛 ``PortraitError``。
    """
    if not isinstance(segment_data, dict):
        raise PortraitFetchFailed
    file_value = str(segment_data.get("file") or "")
    url_value = str(segment_data.get("url") or "")

    if file_value.startswith(("http://", "https://")):
        return await asyncio.to_thread(_download_limited, file_value)
    if file_value:
        local = await _read_local_or_base64(file_value)
        if local is not None:
            return local
    if url_value:
        return await asyncio.to_thread(_download_limited, url_value)
    if not file_value:
        raise PortraitFetchFailed

    try:
        result = await bot.call_api("get_image", file=file_value)
    except Exception as exc:  # noqa: BLE001
        raise PortraitFetchFailed from exc
    data = result if isinstance(result, dict) else {}
    returned_file = str(data.get("file") or "")
    returned_url = str(data.get("url") or "")
    if returned_file:
        local = await _read_local_or_base64(returned_file)
        if local is not None:
            return local
    if returned_url:
        return await asyncio.to_thread(_download_limited, returned_url)
    raise PortraitFetchFailed
