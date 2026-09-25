"""渲染引擎适配：条件 require htmlkit、模板渲染与调用。

设计：
- **条件 require**：仅在「NoneBot 已初始化 **且** 配置开启 **且** 依赖已装」时
  ``require("nonebot_plugin_htmlkit")``——默认装机零加载、零内存增量；判定结果
  进程内缓存（``ensure_available()``），插件加载期即先行判定一次（fontconfig 的
  初始化挂在驱动的 startup 钩子上，延后到首次查询就来不及了）；
- 渲染在 htmlkit 的独立线程内执行（不阻塞事件循环）；``html_to_pic`` 需在事件
  循环内 await，故对外渲染器为 **async**；
- **禁网**：``img_fetch_fn`` / ``css_fetch_fn`` 均传 ``none_fetcher``（模板内联
  CSS、无外部资源），渲染过程不发任何网络请求；
- ``allow_refit=False``：保持固定宽度（卡片场景不按内容缩宽）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from nonebot import logger

if TYPE_CHECKING:
    from . import Renderer

#: 卡片渲染宽度（px）——与实测的推荐默认一致
CARD_WIDTH = 700

#: 模板目录与模板名
_TEMPLATE_DIR = Path(__file__).parent / "templates"
_TEMPLATE_NAME = "rule_card.html"
_BOOKS_TEMPLATE_NAME = "books_card.html"

#: 可用性判定结果（None = 尚未判定；未初始化时会话下不缓存，留待下次重试）
_ready: Optional[bool] = None

_env: Any = None
_css_cache: Dict[str, str] = {}


def htmlkit_installed() -> bool:
    """检测 nonebot-plugin-htmlkit 是否已安装（不触发导入）。"""
    try:
        return importlib.util.find_spec("nonebot_plugin_htmlkit") is not None
    except (ImportError, ValueError):
        return False


def _nonebot_initialized() -> bool:
    """NoneBot 是否已初始化（本模块可能被单测在收集阶段直接导入）。"""
    try:
        from nonebot import get_driver

        get_driver()
        return True
    except ValueError:
        return False


def ensure_available() -> bool:
    """判定渲染是否可用（首次调用时执行条件 require）。

    - 配置关闭 → 不 require（默认装机零负担）；
    - 依赖未装 → 不 require，记一条警示日志（命令层回退文字）；
    - 二者齐备 → require 并缓存为可用。
    """
    global _ready
    if _ready is not None:
        return _ready
    if not _nonebot_initialized():
        # 未初始化：不缓存，等 NoneBot 就绪后再判
        return False

    from ..config import get_config

    if not get_config().dnddicer_query_image_enabled:
        _ready = False
        return False
    if not htmlkit_installed():
        logger.warning(
            "规则查询图片模式已开启，但未安装渲染依赖，将回退文字输出；"
            "如需出图请安装：pip install nonebot-plugin-dnddicer[render]"
        )
        _ready = False
        return False
    try:
        from nonebot import require

        require("nonebot_plugin_htmlkit")
    except Exception:
        logger.exception("DNDDicer 加载渲染依赖 nonebot-plugin-htmlkit 失败，将回退文字输出")
        _ready = False
        return False
    logger.info("DNDDicer 规则查询图片模式已启用（nonebot-plugin-htmlkit）")
    _ready = True
    return True


def reset_availability() -> None:
    """清空可用性判定缓存（测试清理用；下次调用时按当前配置重判）。"""
    global _ready
    _ready = None


def _get_env():
    """构建（并缓存）Jinja2 模板环境。仅在可用时调用。"""
    global _env
    if _env is None:
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        _env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            enable_async=True,
            # 正文来自在线内容，一律转义（模板内亦显式 |e，双重保险）
            autoescape=select_autoescape(["html", "htm"]),
        )
    return _env


def _css_text(name: str) -> str:
    """读取（并缓存）模板样式表文本（内联进 HTML，避免外部请求）。"""
    if name not in _css_cache:
        _css_cache[name] = (_TEMPLATE_DIR / name).read_text(encoding="utf-8")
    return _css_cache[name]


async def _render(
    title: str,
    category: str,
    body: str,
    source_path: str,
    located: bool,
) -> bytes:
    """渲染词条卡片为 PNG 字节（内部实现）。"""
    from nonebot_plugin_htmlkit import html_to_pic, none_fetcher

    from .layout import prepare_blocks

    template = _get_env().get_template(_TEMPLATE_NAME)
    html = await template.render_async(
        title=title,
        category=category,
        blocks=prepare_blocks(body),
        # 未精确定位时在正文顶部加一行说明（与文字模式同口径）
        fallback_note="" if located else "（未精确定位到词条，以下为页面片段）",
        source_path=source_path,
        css=_css_text("rule_card.css"),
    )
    return await html_to_pic(
        html,
        max_width=CARD_WIDTH,
        allow_refit=False,
        img_fetch_fn=none_fetcher,
        css_fetch_fn=none_fetcher,
    )


async def _render_books(
    sections: List[dict],
    title: str,
    hint: str,
    footer: str,
) -> bytes:
    """渲染书目卡片为 PNG 字节（内部实现）。"""
    from nonebot_plugin_htmlkit import html_to_pic, none_fetcher

    template = _get_env().get_template(_BOOKS_TEMPLATE_NAME)
    html = await template.render_async(
        title=title,
        hint=hint,
        footer=footer,
        sections=sections,
        css=_css_text("books_card.css"),
    )
    return await html_to_pic(
        html,
        max_width=CARD_WIDTH,
        allow_refit=False,
        img_fetch_fn=none_fetcher,
        css_fetch_fn=none_fetcher,
    )


def build_renderer() -> Optional["Renderer"]:
    """构建词条卡片渲染器；不可用时返回 None。"""
    return _render if ensure_available() else None


def build_books_renderer():
    """构建书目卡片渲染器；不可用时返回 None。"""
    return _render_books if ensure_available() else None


# 插件加载期先行判定一次（使条件 require 尽早生效）；
# 单测在 NoneBot 未初始化时直接导入本模块不会报错，判定留待 NoneBot 就绪后重试。
ensure_available()
