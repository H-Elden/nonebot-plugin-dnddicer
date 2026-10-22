"""网页建卡器角色卡预览的 CSS 复制件必须与插件源逐字一致。"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SOURCE = _ROOT / "nonebot_plugin_dnddicer" / "render" / "templates" / "char_card.css"
_TARGET = (
    _ROOT
    / "docs"
    / ".vitepress"
    / "theme"
    / "card-builder"
    / "char-card.css"
)


def test_preview_css_copy_matches_plugin_source() -> None:
    """`docs:sync-card-css` 的产物必须与插件源文件逐字相同，避免预览样式漂移。"""
    assert _TARGET.read_text(encoding="utf-8") == _SOURCE.read_text(encoding="utf-8")
