"""规则查询命令：``.查询`` / ``.q``（名称优先）与 ``.搜索`` / ``.s`` / ``.检索``（全文）。

流程：解析关键词 → 数据源检索（多端点顺序回退，见 query/source.py）→ 候选列表
→ 回复数字查看词条正文（条目级定位，见 query/locating.py）、``+`` / ``-`` 翻页。

约定：
- 候选记录只响应**发起者本人**、默认 60 秒有效（query/interaction.py）；
  其余消息一律不拦截，避免与其他插件抢数字回复；
- 内容只用于当次回复与短时内存缓存，不落盘；输出统一标注来源（《5e不全书》）；
- 长内容按 20 行分段发送，最多 3 段（超出截断并提示），避免刷屏；
- 图片模式分两级开关（2026-09-25）：骰主总开关（``dnddicer_query_image_enabled``，
  默认关）决定**能不能用**图片，各处（群按群、私聊按用户）再用 ``.查询图片``
  决定**本处用不用**——默认文字、需主动开启；开启请求在骰主未配置（总开关关或
  渲染依赖未装）时被拒（报错且不写入，仍以文字显示）；渲染异常或依赖失效则回退
  文字，查询不丢；
- 群聊受 .bot 群聊服务开关（白名单）管辖，与其它命令一致；私聊可用；
- 功能默认关闭（``dnddicer_query_enabled``）：未开启时不外呼、仅回一条提示。
"""

from __future__ import annotations

from typing import List, Optional

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.matcher import Matcher
from nonebot.plugin import on_message
from nonebot.rule import Rule

from .. import render
from ..config import get_config
from ..data import query_settings
from ..query import (
    DEFAULT_TTL,
    MAX_CANDIDATES,
    MODE_FULL,
    MODE_NAME,
    PAGE_SIZE,
    Candidate,
    FiveChmSource,
    QueryUnavailableError,
    SelectionRecord,
    default_store,
    find_entry_head,
    locate_entry,
    parse_selection_token,
)
from . import base, text

#: 单次查询允许的最大关键词组数（与服务端语义一致：空格分隔为 AND）
MAX_KEYWORDS = 5

#: 正文分段发送的行数与段数上限。
#: 词条正文的定位上限（`query/locating.py` 的 BODY_MAX_LINES/CHARS = 3 段 × 20 行）
#: 与这里对应：定位层负责「最多给多少」，本层负责「怎么分」；定位层截断时正文
#: 自带省略号，本层超段时追加截断提示（双保险）。
_CHUNK_LINES = 20
_MAX_CHUNKS = 3

#: 图片模式回退提示是否已发出（依赖缺失时进程内只提示一次，避免刷屏）
_image_fallback_notified = False


def reset_image_fallback_notice() -> None:
    """重置「图片模式回退提示已发出」标记（测试清理用）。"""
    global _image_fallback_notified
    _image_fallback_notified = False


_HELP_QUERY = (
    "规则查询：.查询 <关键词>（.q）\n"
    "- 按名称检索规则内容（标题与词条名优先）\n"
    "- 多关键词用空格分隔（需同时满足），| 表示或（如 火焰|闪电）\n"
    "- 返回候选后：回复数字查看详情，+ / - 翻页（60 秒内有效）\n"
    "示例：.查询 火球术"
)

_HELP_SEARCH = (
    "全文检索：.搜索 <关键词>（.s / .检索）\n"
    "- 在全部正文中检索，适合记不清名称时\n"
    "- 用法与 .查询 相同\n"
    "示例：.搜索 借机攻击"
)

_HELP_IMAGE = (
    "查询图片显示：.查询图片（.qimg）\n"
    "- 无参数：查看本处当前的显示形态\n"
    "- on / off：把本处切换为图片 / 文字显示\n"
    "- 群聊设置对该群全员生效，私聊仅影响本人；无需管理权限，设置持久保存\n"
    "- 需骰主先开启图片模式（并装好渲染依赖），否则开启会被拒绝\n"
    "示例：.查询图片 on"
)

query_matcher = base.on_dnd_command("查询", _HELP_QUERY, aliases=("q",))
search_matcher = base.on_dnd_command("搜索", _HELP_SEARCH, aliases=("s", "检索"))
image_matcher = base.on_dnd_command("查询图片", _HELP_IMAGE, aliases=("qimg",))


# =========================================================================
# 数据源（按配置构建并缓存；测试可注入）
# =========================================================================

_source: Optional[FiveChmSource] = None


def get_source() -> FiveChmSource:
    """返回查询数据源实例（首次调用时按配置构建并缓存）。"""
    global _source
    if _source is None:
        config = get_config()
        _source = FiveChmSource(
            config.dnddicer_query_base_urls,
            timeout=config.dnddicer_query_timeout,
            cache_ttl=config.dnddicer_query_cache_ttl,
            endpoint_cooldown=config.dnddicer_query_endpoint_cooldown,
        )
    return _source


def set_source(source: Optional[FiveChmSource]) -> None:
    """替换数据源实例（测试注入用；传 None 恢复按配置构建）。"""
    global _source
    _source = source


# =========================================================================
# 候选选择：只接管「本人有未过期候选记录」且消息恰为数字 / + / - 的情形
# =========================================================================


def _selection_rule() -> Rule:
    """数字选择与翻页的匹配规则（不注册命令名，避免与聊天数字冲突）。"""

    async def _checker(event: MessageEvent) -> bool:
        token = parse_selection_token(event.get_plaintext())
        if token is None:
            return False
        return default_store.get(event.get_session_id(), event.user_id) is not None

    return Rule(_checker) & base.group_service_rule()


selection_matcher = on_message(
    _selection_rule(), priority=get_config().dnddicer_command_priority, block=True
)


# =========================================================================
# 命令处理
# =========================================================================


@query_matcher.handle()
async def handle_query(bot: Bot, event: MessageEvent) -> None:
    """``.查询``：名称优先模式。"""
    await _run_search(
        query_matcher, bot, event, mode=MODE_NAME, usage=text.TXT_QUERY_USAGE_NAME
    )


@search_matcher.handle()
async def handle_search(bot: Bot, event: MessageEvent) -> None:
    """``.搜索``：全文模式。"""
    await _run_search(
        search_matcher, bot, event, mode=MODE_FULL, usage=text.TXT_QUERY_USAGE_FULL
    )


# =========================================================================
# 图片显示的按处开关（.查询图片）
# =========================================================================


def _chat_key(event: MessageEvent) -> str:
    """本处设置键：群聊按群（对该群全员生效）、私聊按用户（仅影响本人）。"""
    group_id = getattr(event, "group_id", None)
    if group_id is not None:
        return query_settings.group_key(group_id)
    return query_settings.private_key(event.user_id)


def _where(event: MessageEvent) -> str:
    """文案中的处所代词：群聊「本群」、私聊「你」。"""
    return "本群" if getattr(event, "group_id", None) is not None else "你"


def _image_unavailable_text() -> Optional[str]:
    """图片显示当前不可用的原因文案（可用时返回 None）。

    两级判定：骰主总开关未开 → 提示去宿主 .env 开启；开关已开但渲染器
    不可用（依赖未装 / require 失败）→ 提示装 [render] extra。
    """
    if not get_config().dnddicer_query_image_enabled:
        return text.TXT_QUERY_IMAGE_DISABLED
    if not render.render_available():
        return text.TXT_QUERY_IMAGE_NOT_READY
    return None


async def _image_state_text(event: MessageEvent) -> str:
    """查看本处设置：按**实际生效**的形态回复（不可用时说明原因）。"""
    where = _where(event)
    if not await query_settings.is_image_enabled(_chat_key(event)):
        return text.TXT_QUERY_IMAGE_STATE_OFF.format(where=where)
    if _image_unavailable_text() is not None:
        # 已设为图片但骰主当前未配置（总开关被关或依赖缺失）→ 暂以文字
        return text.TXT_QUERY_IMAGE_STATE_PENDING.format(where=where)
    return text.TXT_QUERY_IMAGE_STATE_ON.format(where=where)


@image_matcher.handle()
async def handle_image_setting(event: MessageEvent) -> None:
    """``.查询图片``：查看 / 切换本处的查询图片显示（无需管理权限）。"""
    rest = (base.get_command_rest(event) or "").strip()
    where = _where(event)

    if not rest:
        await image_matcher.finish(await _image_state_text(event))

    arg = rest.lower()
    if arg == "on":
        reason = _image_unavailable_text()
        if reason is not None:
            # 骰主未配置：报错且**不写入**（不留「看起来开了、实际没生效」的设置）
            await image_matcher.finish(reason)
        await query_settings.set_image_enabled(_chat_key(event), True)
        await image_matcher.finish(text.TXT_QUERY_IMAGE_ON.format(where=where))
    if arg == "off":
        await query_settings.set_image_enabled(_chat_key(event), False)
        await image_matcher.finish(text.TXT_QUERY_IMAGE_OFF.format(where=where))
    await image_matcher.finish(
        text.TXT_QUERY_IMAGE_BAD_ARG.format(arg=rest, usage=text.TXT_QUERY_IMAGE_USAGE)
    )


async def _run_search(
    matcher: Matcher, bot: Bot, event: MessageEvent, *, mode: str, usage: str
) -> None:
    """两条查询命令的公共流程：开关 → 取词 → 检索 → 候选列表。"""
    if not get_config().dnddicer_query_enabled:
        await matcher.finish(text.TXT_QUERY_DISABLED)

    keyword = (base.get_command_rest(event) or "").strip()
    if not keyword:
        await matcher.finish(text.TXT_QUERY_USAGE.format(usage=usage))
    if len(keyword.split()) > MAX_KEYWORDS:
        await matcher.finish(
            text.TXT_QUERY_TOO_MANY_KEYWORDS.format(max=MAX_KEYWORDS)
        )

    try:
        candidates = await get_source().search(keyword, mode=mode)
    except QueryUnavailableError as exc:
        logger.warning(
            "DNDDicer 规则查询服务不可用 endpoints={} last_error={}",
            exc.attempts,
            exc.last_error,
        )
        await matcher.finish(text.TXT_QUERY_UNAVAILABLE.format(count=len(exc.attempts)))

    if not candidates:
        await matcher.finish(text.TXT_QUERY_NO_RESULT.format(keyword=keyword))

    record = default_store.put(
        event.get_session_id(),
        event.user_id,
        keyword=keyword,
        mode=mode,
        candidates=candidates,
    )
    await matcher.finish(_render_list(record))


@selection_matcher.handle()
async def handle_selection(bot: Bot, event: MessageEvent) -> None:
    """候选列表的数字选择与 ``+`` / ``-`` 翻页。"""
    token = parse_selection_token(event.get_plaintext()) or ""
    session_id = event.get_session_id()
    record = default_store.get(session_id, event.user_id)
    if record is None:
        # 规则已要求记录存在；此处为竞态兜底（超时/并发清理）
        await selection_matcher.finish()

    if token in ("+", "-"):
        record.move_page(1 if token == "+" else -1)
        default_store.touch(record)
        await selection_matcher.finish(_render_list(record))

    number = int(token)
    if number < 1 or number > len(record.candidates):
        await selection_matcher.finish(
            text.TXT_QUERY_BAD_INDEX.format(no=number, max=len(record.candidates))
        )

    candidate = record.candidates[number - 1]
    entry_text, located = locate_entry(candidate.content, record.keyword)
    default_store.touch(record)
    await _send_entry(bot, event, candidate, record.keyword, entry_text, located)
    await selection_matcher.finish()


# =========================================================================
# 渲染与发送
# =========================================================================


def _render_list(record: SelectionRecord) -> str:
    """渲染候选列表当前页。"""
    limited = (
        text.TXT_QUERY_LIST_LIMITED.format(count=len(record.candidates))
        if len(record.candidates) >= MAX_CANDIDATES
        else ""
    )
    lines = [
        text.TXT_QUERY_LIST_HEAD.format(
            keyword=record.keyword,
            count=len(record.candidates),
            limited=limited,
            page=record.page,
            pages=record.page_count,
        )
    ]
    base_no = (record.page - 1) * PAGE_SIZE
    for offset, candidate in enumerate(record.page_slice()):
        category = (
            text.TXT_QUERY_LIST_CATEGORY.format(category=candidate.category)
            if candidate.category
            else ""
        )
        lines.append(
            text.TXT_QUERY_LIST_ITEM.format(
                no=base_no + offset + 1,
                title=candidate.title or f"页面 #{candidate.index}",
                category=category,
            )
        )
    lines.append(text.TXT_QUERY_LIST_TAIL.format(seconds=int(DEFAULT_TTL)))
    return "\n".join(lines)


async def _send_entry(
    bot: Bot,
    event: MessageEvent,
    candidate: Candidate,
    keyword: str,
    entry_text: str,
    located: bool,
) -> None:
    """发送词条正文：图片模式可用时出图，否则文字分段（最多 3 段）。

    两级图片开关：骰主总开关（能不能用）× 本处设置（本处用不用，默认关）；
    正文为空（页面无可显示内容）时不出图——空白卡片无意义，走文字侧提示。
    """
    global _image_fallback_notified
    image_hint = ""
    use_image = (
        bool(entry_text.strip())
        and get_config().dnddicer_query_image_enabled
        and await query_settings.is_image_enabled(_chat_key(event))
    )
    if use_image:
        if render.render_available():
            try:
                png = await _render_entry_image(candidate, keyword, entry_text, located)
            except Exception:
                # 渲染异常：回退文字（用户无感，查询不丢），细节进日志
                logger.exception("DNDDicer 规则查询图片渲染失败，已回退文字输出")
            else:
                await bot.send(event, MessageSegment.image(png))
                return
        elif not _image_fallback_notified:
            # 依赖缺失：首次回退附一行提示（进程内只提示一次，避免刷屏）
            _image_fallback_notified = True
            image_hint = text.TXT_QUERY_IMAGE_FALLBACK

    lines: List[str] = [
        text.TXT_QUERY_ENTRY_HEAD.format(
            category=candidate.category or "未分类",
            title=candidate.title or f"页面 #{candidate.index}",
        )
    ]
    if not located:
        lines.append(text.TXT_QUERY_ENTRY_FALLBACK)
    body = entry_text.strip()
    lines.extend(body.splitlines() if body else [text.TXT_QUERY_ENTRY_EMPTY])
    if image_hint:
        lines.append(image_hint)

    chunks = [lines[i : i + _CHUNK_LINES] for i in range(0, len(lines), _CHUNK_LINES)]
    truncated = len(chunks) > _MAX_CHUNKS
    chunks = chunks[:_MAX_CHUNKS]
    for index, chunk in enumerate(chunks):
        payload = list(chunk)
        if truncated and index == len(chunks) - 1:
            payload.append(text.TXT_QUERY_TRUNCATED)
        await bot.send(event, "\n".join(payload))


async def _render_entry_image(
    candidate: Candidate, keyword: str, entry_text: str, located: bool
) -> bytes:
    """渲染词条图片卡片。

    标题取条目头名称（如「镜影术」，比页面标题「二环」更精确）；条目头未命中
    时退用关键词。分类与来源分别取候选的 category / path。
    """
    head = find_entry_head(candidate.content, keyword)
    return await render.render_rule_card(
        title=head[0] if head else keyword,
        category=candidate.category,
        body=entry_text,
        source_path=candidate.path,
        located=located,
    )
