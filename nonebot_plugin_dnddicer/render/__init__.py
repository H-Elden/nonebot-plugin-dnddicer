"""渲染模块：规则查询输出 → 图片卡片。

两类卡片（共用同一套主题与渲染基建）：
- **词条卡片**（``render_rule_card``）：``.查询`` 的词条正文（仿 5e 不全书正文样式）；
- **书目卡片**（``render_books_card``）：``.规则书`` 的可查询书目表（分组 + 缩写对照）。

设计目标：
- 对外暴露 ``render_available()`` / ``books_available()`` 与两个渲染函数（均 async）；
- ``nonebot-plugin-htmlkit`` 为可选依赖：配置关闭或依赖未装时两者均返回 False，
  命令层据此回退文字输出；
- 测试可注入假渲染器（``set_renderer`` / ``set_books_renderer``），CI 无需装 htmlkit；
  两类卡片**各查各的可用性**（2026-09-26 修订：书目表此前借用词条渲染器的判定，
  只注入书目假渲染器的测试会在未装 htmlkit 的环境误判不可用）。

模块划分：
- ``engine.py``：条件 require、模板环境与渲染调用适配；
- ``layout.py``：纯函数——正文分块与避头尾折行（无第三方依赖，易测）；
- ``templates/``：HTML/CSS 模板（仿 5e 不全书站点样式，随包分发）。
"""

from __future__ import annotations

from typing import Awaitable, Callable, List, Optional

from . import engine

#: 词条卡片渲染器签名：(标题, 分类, 正文, 来源路径, 是否已定位) → PNG 字节（异步）
Renderer = Callable[[str, str, str, str, bool], Awaitable[bytes]]

#: 富文本词条卡片渲染器签名：(标题, 分类, 正文 HTML 片段, 来源路径, 是否已定位)
RichRenderer = Callable[[str, str, str, str, bool], Awaitable[bytes]]

#: 书目卡片渲染器签名：(分组列表, 标题, 说明行, 底注) → PNG 字节（异步）
BooksRenderer = Callable[[List[dict], str, str, str], Awaitable[bytes]]

_renderer: Optional[Renderer] = None
_resolved = False  # 是否已尝试过解析（含「解析结果为不可用」）
_rich_renderer: Optional[RichRenderer] = None
_rich_resolved = False
_books_renderer: Optional[BooksRenderer] = None
_books_resolved = False


def render_available() -> bool:
    """词条卡片图片渲染是否可用（配置开启 + 依赖已装 + require 成功）。"""
    return _resolve() is not None


def rich_available() -> bool:
    """富文本词条卡片是否可用（与普通词条卡片同一引擎判定，可独立注入）。"""
    return _resolve_rich() is not None


def books_available() -> bool:
    """书目卡片图片渲染是否可用（与词条卡片同一引擎判定，可独立注入）。"""
    return _resolve_books() is not None


async def render_rule_card(
    title: str,
    category: str,
    body: str,
    source_path: str,
    located: bool,
) -> bytes:
    """渲染词条卡片为 PNG 字节。调用前应先检查 ``render_available()``。"""
    renderer = _resolve()
    if renderer is None:
        raise RuntimeError("渲染器不可用")
    return await renderer(title, category, body, source_path, located)


async def render_rich_card(
    title: str,
    category: str,
    body_html: str,
    source_path: str,
    located: bool,
) -> bytes:
    """渲染**富文本**词条卡片（站点 HTML 清洗后的片段）。

    调用前应先检查 ``rich_available()``；片段需经 ``query/decode.py`` 清洗
    （模板以 ``| safe`` 直出）。
    """
    renderer = _resolve_rich()
    if renderer is None:
        raise RuntimeError("渲染器不可用")
    return await renderer(title, category, body_html, source_path, located)


async def render_books_card(
    sections: List[dict],
    *,
    title: str,
    hint: str,
    footer: str,
) -> bytes:
    """渲染书目卡片为 PNG 字节。调用前应先检查 ``books_available()``。"""
    renderer = _resolve_books()
    if renderer is None:
        raise RuntimeError("渲染器不可用")
    return await renderer(sections, title, hint, footer)


def set_renderer(renderer: Optional[Renderer]) -> None:
    """替换词条卡片渲染器（测试注入用；传 None 等价于重置为按配置解析）。"""
    global _renderer, _resolved
    _renderer = renderer
    _resolved = renderer is not None


def set_rich_renderer(renderer: Optional[RichRenderer]) -> None:
    """替换**富文本**词条卡片渲染器（测试注入用；传 None 恢复按配置解析）。"""
    global _rich_renderer, _rich_resolved
    _rich_renderer = renderer
    _rich_resolved = renderer is not None


def set_books_renderer(renderer: Optional[BooksRenderer]) -> None:
    """替换书目卡片渲染器（测试注入用；传 None 等价于重置为按配置解析）。"""
    global _books_renderer, _books_resolved
    _books_renderer = renderer
    _books_resolved = renderer is not None


def reset_renderer() -> None:
    """重置渲染器状态（测试清理用）。

    连同引擎的可用性判定缓存一并清空——判定结果与当时的配置绑定，测试中
    改过配置（monkeypatch）后必须重判，否则会沿用加载期的旧结论。
    """
    global _renderer, _resolved, _rich_renderer, _rich_resolved
    global _books_renderer, _books_resolved
    _renderer = None
    _resolved = False
    _rich_renderer = None
    _rich_resolved = False
    _books_renderer = None
    _books_resolved = False
    engine.reset_availability()


def _resolve() -> Optional[Renderer]:
    """解析词条卡片渲染器（首次调用时按配置与依赖构建，失败结果同样缓存）。"""
    global _renderer, _resolved
    if not _resolved:
        _renderer = engine.build_renderer()
        _resolved = True
    return _renderer


def _resolve_rich() -> Optional[RichRenderer]:
    """解析富文本词条卡片渲染器（首次调用时按配置与依赖构建）。"""
    global _rich_renderer, _rich_resolved
    if not _rich_resolved:
        _rich_renderer = engine.build_rich_renderer()
        _rich_resolved = True
    return _rich_renderer


def _resolve_books() -> Optional[BooksRenderer]:
    """解析书目卡片渲染器（首次调用时按配置与依赖构建，失败结果同样缓存）。"""
    global _books_renderer, _books_resolved
    if not _books_resolved:
        _books_renderer = engine.build_books_renderer()
        _books_resolved = True
    return _books_renderer
