"""速查索引的编排与骰主命令（``.查询索引``，2026-09-26）。

职责：

- **索引单例**：按配置构建抓取器（``query/fetch.py``）与索引存储
  （``query/atlas.py``），供规则查询子命令（``.查询法术`` 等）复用；
- **启动构建**：插件启动时后台全量构建一次（异步、不阻塞启动；失败保留旧
  缓存）。仅在规则查询功能开启（``dnddicer_query_enabled``）且开关未关
  （``dnddicer_query_atlas_build_on_startup``）时执行；
- **懒构建兜底**：缓存缺失时按需构建单类（``ensure_kind``，子命令使用）；
- **骰主命令** ``.查询索引``（别名 ``.qatlas``）：查看状态 / 手动刷新。仅
  骰主私聊可用（群聊静默不响应、不暴露），且不进 ``.帮助``（隐藏注册）。

提示：索引只存条目名与元数据（不含规则正文），存插件本地缓存目录、不随
插件分发；详见 ``query/atlas.py`` 的模块说明。
"""

from __future__ import annotations

import asyncio
import time
from typing import List, Optional, Sequence, Set

from nonebot import get_driver, logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent

from ..config import get_config
from ..query import atlas as atlas_mod
from ..query.fetch import HtmlFetcher
from . import base, text

#: 索引存储单例（None = 尚未按配置构建；测试可注入替换）
_store: Optional[atlas_mod.AtlasStore] = None

#: 后台构建任务引用（防止被垃圾回收；完成后自动移除）
_background_tasks: Set[asyncio.Task] = set()


def get_store() -> atlas_mod.AtlasStore:
    """返回索引存储单例（首次调用时按配置构建抓取器）。

    抓取用 ``dnddicer_query_site_urls``（站点地址；实测在线检索服务域名只
    覆盖部分静态页），检索仍走 ``dnddicer_query_base_urls``（见 query/source.py）。
    """
    global _store
    if _store is None:
        config = get_config()
        fetcher = HtmlFetcher(
            config.dnddicer_query_site_urls,
            timeout=config.dnddicer_query_timeout,
            cache_ttl=config.dnddicer_query_page_cache_ttl,
            endpoint_cooldown=config.dnddicer_query_endpoint_cooldown,
            min_interval=config.dnddicer_query_page_interval,
        )
        _store = atlas_mod.AtlasStore(fetcher)
    return _store


def set_store(store: Optional[atlas_mod.AtlasStore]) -> None:
    """替换索引存储（测试注入用；传 None 恢复按配置构建）。"""
    global _store
    _store = store


def _track(task: asyncio.Task) -> None:
    """持有后台任务引用并在完成后移除。"""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def ensure_loaded() -> bool:
    """确保索引从缓存加载进内存（已有内存索引时直接返回 True）。"""
    store = get_store()
    if store.ready:
        return True
    try:
        return await asyncio.to_thread(store.load)
    except Exception:  # noqa: BLE001 - 读缓存失败不阻塞后续（按未加载处理）
        logger.exception("DNDDicer 速查索引读取缓存失败")
        return False


async def ensure_kind(kind: str) -> bool:
    """确保某类索引可用（内存/缓存有则用；否则懒构建该类）。

    供规则查询子命令（.查询法术 等）在查询前调用；返回该类是否可用。
    """
    store = get_store()
    if not (store.ready and store.counts().get(kind)):
        await ensure_loaded()
    if store.counts().get(kind):
        return True
    try:
        built = await store.build([kind])
        await asyncio.to_thread(store.merge_and_save, built)
    except Exception as exc:  # noqa: BLE001 - 懒构建失败按不可用处理（上层降级）
        logger.warning("DNDDicer 速查索引懒构建失败 kind={}: {}", kind, exc)
        return False
    return store.counts().get(kind, 0) > 0


async def refresh_index(kinds: Optional[Sequence[str]] = None) -> dict:
    """构建并合并索引（供命令层与测试调用），返回各类别处理结果。"""
    store = get_store()
    built = await store.build(kinds)
    return await asyncio.to_thread(store.merge_and_save, built)


async def wait_background_tasks() -> None:
    """等待后台任务（启动构建 / 手动刷新）执行完毕。

    手动刷新是「先回报、后台执行」：脚本化场景（示例时间线、回归脚本）需要
    等任务跑完再继续，否则回报消息与后续步骤的转录顺序不稳定。
    """
    if _background_tasks:
        await asyncio.gather(*tuple(_background_tasks), return_exceptions=True)


# =========================================================================
# 启动构建（后台、不阻塞启动）
# =========================================================================


async def _background_build() -> None:
    """启动时的后台全量构建：先加载旧缓存，再构建并合并（失败保留旧索引）。"""
    await ensure_loaded()
    try:
        built = await get_store().build()
        outcomes = await asyncio.to_thread(get_store().merge_and_save, built)
    except Exception as exc:  # noqa: BLE001 - 启动构建失败不影响插件其它功能
        logger.warning("DNDDicer 速查索引启动构建失败（保留旧索引）：{}", exc)
        return
    logger.info("DNDDicer 速查索引启动构建完成：{}", outcomes)


async def _on_startup() -> None:
    """启动钩子：按配置决定是否发起后台全量构建。"""
    config = get_config()
    if not config.dnddicer_query_enabled:
        return
    if not config.dnddicer_query_atlas_build_on_startup:
        logger.info("DNDDicer 速查索引：启动构建已关闭（可按需手动刷新）")
        return
    _track(asyncio.create_task(_background_build()))


def register_startup_build() -> None:
    """注册启动构建钩子（模块导入时调用一次）。"""
    get_driver().on_startup(_on_startup)


# =========================================================================
# 骰主命令 .查询索引（仅骰主私聊；.帮助 不显示）
# =========================================================================

index_matcher = base.on_dnd_command(
    "查询索引",
    text.TXT_INDEX_HELP,
    aliases=("qatlas",),
    hidden=True,
    private_superuser=True,
)

#: 中文类型名 → 类别键
_KIND_BY_LABEL = {label: kind for kind, label in atlas_mod.KIND_LABELS.items()}

#: 刷新动作词（中英文）
_REFRESH_WORDS = ("刷新", "refresh")


def _kinds_help() -> str:
    """类型清单文案（顿号相连）。"""
    return "、".join(atlas_mod.KIND_LABELS[kind] for kind in atlas_mod.BUILD_KINDS)


def _status_text(store: atlas_mod.AtlasStore) -> str:
    """索引状态文案（条目数 + 构建时间；未建立时给出构建指引）。"""
    if not store.ready:
        return text.TXT_INDEX_STATUS_EMPTY
    built_at = store.built_at
    stamp = (
        time.strftime("%Y-%m-%d %H:%M", time.localtime(built_at))
        if built_at
        else "未知"
    )
    counts = store.counts()
    lines = [text.TXT_INDEX_STATUS_HEAD.format(built_at=stamp)]
    for kind in atlas_mod.BUILD_KINDS:
        lines.append(
            text.TXT_INDEX_STATUS_ROW.format(
                label=atlas_mod.KIND_LABELS[kind], count=counts.get(kind, 0)
            )
        )
    return "\n".join(lines)


def _parse_kinds(names: Sequence[str]) -> tuple:
    """解析「刷新 <类型…>」的参数：返回 (类别列表, 未知类型名)。"""
    kinds: List[str] = []
    for name in names:
        kind = _KIND_BY_LABEL.get(name)
        if kind is None and name in atlas_mod.BUILD_KINDS:
            kind = name
        if kind is None:
            return [], name
        if kind not in kinds:
            kinds.append(kind)
    return kinds, None


async def _safe_send(bot: Bot, event: MessageEvent, message: str) -> None:
    """回报消息（发送失败只记日志，不影响后台任务）。"""
    try:
        await bot.send(event, message)
    except Exception:  # noqa: BLE001 - 回报失败不影响索引状态
        logger.warning("DNDDicer 骰主命令回报发送失败")


async def _run_refresh(
    bot: Bot, event: MessageEvent, kinds: Optional[List[str]]
) -> None:
    """后台执行索引重建并在完成后回报（成功/失败各一条）。"""
    store = get_store()
    try:
        outcomes = await refresh_index(kinds)
    except Exception as exc:  # noqa: BLE001 - 站点不可达/解析异常统一回报
        logger.warning("DNDDicer 速查索引手动刷新失败：{}", exc)
        await _safe_send(bot, event, text.TXT_INDEX_REFRESH_FAILED)
        return
    counts = store.counts()
    details = []
    for kind, outcome in outcomes.items():
        label = atlas_mod.KIND_LABELS.get(kind, kind)
        count = counts.get(kind, 0)
        suffix = text.TXT_INDEX_REFRESH_KEPT if outcome == "kept" else ""
        details.append(f"· {label}：{count} 条{suffix}")
    await _safe_send(
        bot, event, text.TXT_INDEX_REFRESH_DONE.format(details="\n".join(details))
    )


@index_matcher.handle()
async def handle_index(bot: Bot, event: MessageEvent) -> None:
    """``.查询索引``：查看索引状态 / 手动刷新（仅骰主私聊）。"""
    await base.guard_superuser(index_matcher, event)

    rest = (base.get_command_rest(event) or "").strip()
    if not rest:
        await ensure_loaded()
        await index_matcher.finish(_status_text(get_store()))

    parts = rest.split()
    if parts[0] not in _REFRESH_WORDS:
        await index_matcher.finish(text.TXT_INDEX_USAGE)

    kinds, unknown = _parse_kinds(parts[1:])
    if unknown is not None:
        await index_matcher.finish(
            text.TXT_INDEX_UNKNOWN_KIND.format(name=unknown, kinds=_kinds_help())
        )

    target = kinds or list(atlas_mod.BUILD_KINDS)
    await index_matcher.send(
        text.TXT_INDEX_REFRESHING.format(
            kinds="、".join(atlas_mod.KIND_LABELS[kind] for kind in target)
        )
    )
    # 刷新前先读入旧索引：自检（条目数异常保护）需要旧值作对比基准
    await ensure_loaded()
    _track(asyncio.create_task(_run_refresh(bot, event, kinds or None)))
    await index_matcher.finish()


register_startup_build()
