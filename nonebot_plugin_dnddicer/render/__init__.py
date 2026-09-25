"""渲染模块：规则查询词条 → 图片卡片。

设计目标：
- 对外暴露 ``render_available()`` 与 ``render_rule_card()``（async）；
- ``nonebot-plugin-htmlkit`` 为可选依赖：配置关闭或依赖未装时
  ``render_available()`` 返回 False，命令层据此回退文字输出；
- 测试可注入假渲染器（``set_renderer`` / ``reset_renderer``），CI 无需装 htmlkit。

模块划分：
- ``engine.py``：条件 require、模板环境与渲染调用适配；
- ``layout.py``：纯函数——正文分块与避头尾折行（无第三方依赖，易测）；
- ``templates/``：HTML/CSS 模板（仿 5e 不全书站点样式，随包分发）。
"""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from . import engine

#: 渲染器签名：(标题, 分类, 正文, 来源路径, 是否已定位) → PNG 字节（异步）
Renderer = Callable[[str, str, str, str, bool], Awaitable[bytes]]

_renderer: Optional[Renderer] = None
_resolved = False  # 是否已尝试过解析（含「解析结果为不可用」）


def render_available() -> bool:
    """图片渲染是否可用（配置开启 + 依赖已装 + require 成功）。"""
    return _resolve() is not None


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


def set_renderer(renderer: Optional[Renderer]) -> None:
    """替换渲染器（测试注入用；传 None 等价于重置为按配置解析）。"""
    global _renderer, _resolved
    _renderer = renderer
    _resolved = renderer is not None


def reset_renderer() -> None:
    """重置渲染器状态（测试清理用）。

    连同引擎的可用性判定缓存一并清空——判定结果与当时的配置绑定，测试中
    改过配置（monkeypatch）后必须重判，否则会沿用加载期的旧结论。
    """
    global _renderer, _resolved
    _renderer = None
    _resolved = False
    engine.reset_availability()


def _resolve() -> Optional[Renderer]:
    """解析渲染器（首次调用时按配置与依赖构建，失败结果同样缓存）。"""
    global _renderer, _resolved
    if not _resolved:
        _renderer = engine.build_renderer()
        _resolved = True
    return _renderer
