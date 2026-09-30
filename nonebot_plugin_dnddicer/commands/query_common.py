"""规则查询命令层的共享辅助（2026-09-26，通用检索与速查子命令共用）。

- **按处键与处所代词**：``.查询图片`` / ``.查询范围`` / 速查子命令共用同一套
  「群聊按群、私聊按人」的定位（``chat_key`` / ``where``）；
- **图片形态判定**：``image_enabled`` 统一「显式设置优先、否则跟随骰主配置的
  默认形态」这一口径，通用检索与速查子命令共用（避免两处各判一次走偏）；
- **候选列表框架**：头部 + 条目行 + 收尾（回复数字 / 翻页提示）；只有一页时
  不显示页码与翻页提示（2026-09-26 用户拍板，两条查询路径共用同一实现）；
- **书名映射**：站内目录名 → 书架中文书名（如「玩家手册」→「玩家手册2014」），
  候选项展示不再出现无法分辨版本的目录名。
"""

from __future__ import annotations

from typing import Sequence

from nonebot.adapters.onebot.v11 import MessageEvent

from ..config import get_config
from ..data import query_settings
from ..query import books
from ..query.interaction import DEFAULT_TTL
from . import text

#: 候选来源标记：速查索引子命令（``.查询法术`` 等），区别于服务端检索
#: 的 ``name`` / ``full``；候选记录据此分流「正文取站点页面」的路径
MODE_ATLAS = "atlas"

#: 图片模式回退提示是否已发出（依赖缺失时**全插件只提示一次**，避免刷屏；
#: 通用检索与速查子命令共用同一发出口）
_image_fallback_notified = False


def notify_image_fallback() -> bool:
    """领取「图片回退提示」的发出口：首次返回 True，其后返回 False。"""
    global _image_fallback_notified
    if _image_fallback_notified:
        return False
    _image_fallback_notified = True
    return True


def reset_image_fallback() -> None:
    """重置图片回退提示标记（测试清理用）。"""
    global _image_fallback_notified
    _image_fallback_notified = False


def chat_key(event: MessageEvent) -> str:
    """本处设置键：群聊按群（对该群全员生效）、私聊按用户（仅影响本人）。"""
    group_id = getattr(event, "group_id", None)
    if group_id is not None:
        return query_settings.group_key(group_id)
    return query_settings.private_key(event.user_id)


def where(event: MessageEvent) -> str:
    """文案中的处所代词：群聊「本群」、私聊「你」。"""
    return "本群" if getattr(event, "group_id", None) is not None else "你"


async def image_enabled(event: MessageEvent) -> bool:
    """本处当前是否以图片显示词条正文（**实际生效**的形态）。

    两级取值（2026-09-30 起）：
    1. 本处做过 ``.查询图片 on`` / ``off`` → 按显式设置（写死，不随默认变化）；
    2. 没做过 → 跟随骰主配置 ``dnddicer_query_image_default``（群聊与私聊同一口径）。

    注：骰主总开关（``dnddicer_query_image_enabled``）与渲染依赖在本函数之外把关
    ——本函数只回答「本处要不要图」，能不能出图由调用方另判。
    """
    override = await query_settings.get_image_setting(chat_key(event))
    if override is not None:
        return override
    return bool(get_config().dnddicer_query_image_default)


def list_frame(*, head: str, items: Sequence[str], pages: int) -> str:
    """拼装候选列表：头部 + 条目行 + 收尾（翻页提示按页数取舍）。

    Args:
        head: 头部行（调用方按各自文案渲染：关键词 / 条数 / 页码后缀）。
        items: 候选条目行（已带编号）。
        pages: 总页数（>1 时收尾带 ``+ / -`` 翻页提示）。
    """
    tail = (
        text.TXT_QUERY_LIST_TAIL if pages > 1 else text.TXT_QUERY_LIST_TAIL_ONE_PAGE
    )
    return "\n".join([head, *items, tail.format(seconds=int(DEFAULT_TTL))])


def category_label(category: str) -> str:
    """站内目录名 → 书架中文书名（查不到时原样返回）。

    例：目录「玩家手册」→「玩家手册2014」；「玩家手册2024」原样。
    """
    entry = books.entry_by_category(category)
    return entry.title if entry is not None else category


def display_meta(category: str, meta: str) -> str:
    """候选项/标题的展示用出处串：「书名 · 元数据」（元数据为空时只给书名）。"""
    label = category_label(category)
    if meta:
        return f"{label} · {meta}"
    return label
