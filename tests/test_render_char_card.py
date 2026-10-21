"""角色卡图真实渲染冒烟（需要可选的 [render] 依赖）。

CI 不安装 htmlkit 时整组跳过；本机装了 [render] 才会真正渲染 PNG。
"""

from __future__ import annotations

import importlib.util

import pytest

from nonebot_plugin_dnddicer import render
from nonebot_plugin_dnddicer.character.card_view import build_card_view
from nonebot_plugin_dnddicer.character.services import gen_template_char
from nonebot_plugin_dnddicer.config import get_config
from nonebot_plugin_dnddicer.render import engine

_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


@pytest.fixture(autouse=True)
def _enable_card_image(monkeypatch):
    if importlib.util.find_spec("nonebot_plugin_htmlkit") is None:
        pytest.skip("需要 [render] 可选依赖（nonebot-plugin-htmlkit）")
    monkeypatch.setattr(get_config(), "dnddicer_card_image_enabled", True)
    render.reset_renderer()
    yield
    render.reset_renderer()


def _png_size(png: bytes) -> tuple[int, int]:
    """从 PNG 的 IHDR 读宽高（不依赖 Pillow）。"""
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


@pytest.mark.asyncio
async def test_render_char_card_without_portrait() -> None:
    png = await render.render_char_card(build_card_view(gen_template_char()))
    width, height = _png_size(png)
    assert width == engine.CHAR_CARD_WIDTH == 940
    assert height > 500


@pytest.mark.asyncio
async def test_render_char_card_with_portrait() -> None:
    view = build_card_view(gen_template_char(), _PNG_1PX, "image/png")
    png = await render.render_char_card(view)
    width, height = _png_size(png)
    assert width == engine.CHAR_CARD_WIDTH == 940
    assert height > 500
