"""牌堆图片路径安全、魔数与体积校验。"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from nonebot_plugin_dnddicer.deck.media import (
    MAX_IMAGE_BYTES,
    DeckImageError,
    image_paths,
    load_image,
)

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2nXQAAAAASUVORK5CYII="
)


def _image_root(tmp_path: Path) -> Path:
    root = tmp_path / "images"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_image_paths():
    assert image_paths("文字[img:images/a.png]尾巴[img:images/b.jpg]") == [
        "images/a.png",
        "images/b.jpg",
    ]
    assert image_paths("没有图片") == []


def test_load_valid_image(tmp_path: Path):
    root = _image_root(tmp_path)
    (root / "a.png").write_bytes(PNG_1PX)
    data = load_image("images/a.png", [root])
    assert data.filename == "a.png"
    assert data.mime == "image/png"
    assert data.data == PNG_1PX


def test_custom_root_wins(tmp_path: Path):
    first = _image_root(tmp_path / "first")
    second = _image_root(tmp_path / "second")
    (first / "a.png").write_bytes(PNG_1PX)
    (second / "a.png").write_bytes(PNG_1PX + b"x")
    data = load_image("images/a.png", [first, second])
    assert data.data == PNG_1PX


@pytest.mark.parametrize(
    "path",
    [
        "images/../secret.png",
        "/images/a.png",
        "images\\a.png",
        "http://example.com/a.png",
        "base64://abc",
        "other/a.png",
        "[CQ:image,file=a.png]",
    ],
)
def test_reject_unsafe_paths(tmp_path: Path, path: str):
    root = _image_root(tmp_path)
    with pytest.raises(DeckImageError):
        load_image(path, [root])


def test_missing_and_bad_format(tmp_path: Path):
    root = _image_root(tmp_path)
    with pytest.raises(DeckImageError) as missing:
        load_image("images/missing.png", [root])
    assert missing.value.missing is True

    (root / "bad.png").write_bytes(b"not an image")
    with pytest.raises(DeckImageError):
        load_image("images/bad.png", [root])


def test_oversized_image(tmp_path: Path):
    root = _image_root(tmp_path)
    (root / "big.png").write_bytes(b"\x00" * (MAX_IMAGE_BYTES + 1))
    with pytest.raises(DeckImageError):
        load_image("images/big.png", [root])


def test_symlink_rejected(tmp_path: Path):
    root = _image_root(tmp_path)
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG_1PX)
    link = root / "link.png"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("当前环境不支持创建符号链接")
    with pytest.raises(DeckImageError):
        load_image("images/link.png", [root])
