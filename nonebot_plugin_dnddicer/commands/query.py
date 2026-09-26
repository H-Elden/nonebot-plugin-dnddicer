"""规则查询命令：``.查询`` / ``.q``（名称优先）与 ``.搜索`` / ``.s`` / ``.检索``（全文）。

流程：解析关键词 → 数据源检索（多端点顺序回退，见 query/source.py）→ 候选列表
→ 回复数字查看词条正文（条目级定位，见 query/locating.py）、``+`` / ``-`` 翻页。
展示形态（2026-09-26 用户要求）：**唯一候选**时跳过列表直接展示词条正文；
候选只有一页时不显示页码与翻页提示（那两样只在多于一页时才有意义）。

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
- 查询范围（``.查询范围``，2026-09-25）：按处（群按群、私聊按用户）把可查询的
  书目收窄为若干本/若干整目录，**未设置 = 全部开放**；设置只接受书目缩写（见
  ``.规则书`` 与 ``query/books.py``），无权限限制；检索时对范围内的每个目录各发
  一次请求（服务端 ``category`` 只支持单目录）再合并排序；
- 书目表（``.规则书``）：列出可设置的书目缩写与中文名对照，**默认出图**（骰主
  开启图片模式且渲染可用时），否则回退文字；该命令**不受** ``.查询图片`` 的按处
  开关影响（书目表是给骰主/群管理查阅的参考页，不随查询结果的显示形态走）；
- 群聊受 .bot 群聊服务开关（白名单）管辖，与其它命令一致；私聊可用；
- 功能默认关闭（``dnddicer_query_enabled``）：未开启时不外呼、仅回一条提示。
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

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
from ..query import books
from . import base, query_common, text

#: 单次查询允许的最大关键词组数（与服务端语义一致：空格分隔为 AND）
MAX_KEYWORDS = 5

#: 正文分段发送的行数与段数上限。
#: 词条正文的定位上限（`query/locating.py` 的 BODY_MAX_LINES/CHARS = 3 段 × 20 行）
#: 与这里对应：定位层负责「最多给多少」，本层负责「怎么分」；定位层截断时正文
#: 自带省略号，本层超段时追加截断提示（双保险）。
_CHUNK_LINES = 20
_MAX_CHUNKS = 3

def reset_image_fallback_notice() -> None:
    """重置「图片模式回退提示已发出」标记（测试清理用；全插件共用发出口）。"""
    query_common.reset_image_fallback()


_HELP_QUERY = (
    "规则查询：.查询 <关键词>（.q）\n"
    "- 按名称检索规则内容（标题与词条名优先）\n"
    "- 多关键词用空格分隔（需同时满足），| 表示或（如 火焰|闪电）\n"
    "- 返回候选后：多条时回复数字查看详情，多于一页可 + / - 翻页（60 秒内有效）\n"
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

_HELP_SCOPE = (
    "查询范围：.查询范围（.qscope）\n"
    "- 无参数：查看本处当前的查询范围\n"
    "- <缩写>：只用指定的书目（逗号或空格分隔，如 .查询范围 PHB24,MM25）\n"
    "- 全部：恢复为全部书目（未设置即全部开放）\n"
    "- 群聊设置对该群全员生效，私聊仅影响本人；无需管理权限，设置持久保存\n"
    "示例：.查询范围 PHB24,MM25,XGE（缩写见 .规则书）"
)

_HELP_BOOKS = (
    "可查询书目：.规则书（.qbooks）\n"
    "- 列出可设置的书目缩写与中文名对照（按书架分组）\n"
    "- 合作内容、冒险模组等以整目录缩写设置（3PP / ADV / FR / MISC）\n"
    "示例：.规则书"
)

query_matcher = base.on_dnd_command("查询", _HELP_QUERY, aliases=("q",))
search_matcher = base.on_dnd_command("搜索", _HELP_SEARCH, aliases=("s", "检索"))
image_matcher = base.on_dnd_command("查询图片", _HELP_IMAGE, aliases=("qimg",))
scope_matcher = base.on_dnd_command("查询范围", _HELP_SCOPE, aliases=("qscope",))
books_matcher = base.on_dnd_command("规则书", _HELP_BOOKS, aliases=("qbooks",))


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
    """本处设置键（群聊按群、私聊按用户）——见 ``query_common.chat_key``。"""
    return query_common.chat_key(event)


def _where(event: MessageEvent) -> str:
    """文案中的处所代词（群聊「本群」、私聊「你」）——见 ``query_common.where``。"""
    return query_common.where(event)


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


# =========================================================================
# 查询范围（.查询范围）与书目表（.规则书）
# =========================================================================


def _scope_items(categories: Sequence[str]) -> str:
    """范围条目的展示串（「键 中文名」顿号相连）。"""
    return "、".join(books.category_display(category) for category in categories)


def _unknown_detail(token: str) -> str:
    """未知缩写的提示片段：能定位到整目录的给出对应键，否则标为无此项。"""
    entry = books.umbrella_hint(token)
    if entry is not None:
        return f"{token}（请用 {entry.key}）"
    return f"{token}（无此项）"


async def _scope_state_text(chat_key: str, where: str) -> str:
    """查看本处查询范围：未设置 = 全部开放。"""
    scope = await query_settings.get_scope(chat_key)
    if not scope:
        return text.TXT_QUERY_SCOPE_CURRENT_ALL.format(where=where)
    return text.TXT_QUERY_SCOPE_CURRENT.format(where=where, items=_scope_items(scope))


@scope_matcher.handle()
async def handle_scope(bot: Bot, event: MessageEvent) -> None:
    """``.查询范围``：查看 / 设置本处的可查询书目（无需管理权限）。"""
    rest = (base.get_command_rest(event) or "").strip()
    where = _where(event)
    chat_key = _chat_key(event)

    if not rest:
        await scope_matcher.finish(await _scope_state_text(chat_key, where))

    if books.is_all_word(rest):
        # 恢复全部：任何时候都放行（清理动作不应被功能开关挡住）
        await query_settings.set_scope(chat_key, None)
        await scope_matcher.finish(text.TXT_QUERY_SCOPE_RESET.format(where=where))

    if not get_config().dnddicer_query_enabled:
        await scope_matcher.finish(text.TXT_QUERY_DISABLED)

    tokens = [token for token in re.split(r"[,，、\s]+", rest) if token]
    entries, unknown = [], []
    for token in tokens:
        entry = books.find_entry(token)
        if entry is None:
            unknown.append(token)
        elif entry not in entries:
            entries.append(entry)
    if unknown:
        await scope_matcher.finish(
            text.TXT_QUERY_SCOPE_UNKNOWN.format(
                details="、".join(_unknown_detail(token) for token in unknown)
            )
        )

    categories = [entry.category for entry in entries]
    await query_settings.set_scope(chat_key, categories)
    await scope_matcher.finish(
        text.TXT_QUERY_SCOPE_SET.format(where=where, items=_scope_items(categories))
    )


def _books_sections() -> List[dict]:
    """书目表的分组数据（图片与文字形态共用同一份内容）。"""
    return [
        {
            "title": title,
            "rows": [
                {"key": entry.key, "name": entry.title, "note": entry.note}
                for entry in entries
            ],
        }
        for title, entries in books.sections_for_display()
    ]


def _books_lines() -> List[str]:
    """书目表的文字形态（分组标题 + 每项一行 + 整目录说明）。"""
    lines = [text.TXT_QUERY_BOOKS_HEAD]
    total = 0
    for title, entries in books.sections_for_display():
        lines.append(text.TXT_QUERY_BOOKS_SECTION.format(title=title))
        for entry in entries:
            total += 1
            lines.append(
                text.TXT_QUERY_BOOKS_ROW.format(key=entry.key, name=entry.title)
            )
            if entry.note:
                lines.append(text.TXT_QUERY_BOOKS_NOTE.format(note=entry.note))
    lines.append(text.TXT_QUERY_BOOKS_TAIL.format(count=total))
    return lines


@books_matcher.handle()
async def handle_books(bot: Bot, event: MessageEvent) -> None:
    """``.规则书``：列出可设置的书目（默认出图，渲染不可用则回退文字）。"""
    if render.books_available():
        try:
            png = await render.render_books_card(
                _books_sections(),
                title=text.TXT_QUERY_BOOKS_CARD_TITLE,
                hint=text.TXT_QUERY_BOOKS_CARD_HINT,
                footer=text.TXT_QUERY_BOOKS_TAIL.format(count=len(books.SCOPE_ENTRIES)),
            )
        except Exception:
            logger.exception("DNDDicer 书目表图片渲染失败，已回退文字输出")
        else:
            await bot.send(event, MessageSegment.image(png))
            return
    await _send_chunked(bot, event, _books_lines())


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

    scope = await query_settings.get_scope(_chat_key(event))
    try:
        candidates = await get_source().search(keyword, mode=mode, categories=scope)
    except QueryUnavailableError as exc:
        logger.warning(
            "DNDDicer 规则查询服务不可用 endpoints={} last_error={}",
            exc.attempts,
            exc.last_error,
        )
        await matcher.finish(text.TXT_QUERY_UNAVAILABLE.format(count=len(exc.attempts)))

    if not candidates:
        if scope:
            # 范围生效时说明「为什么没有」——并给出自行放开的路子；
            # 「.查询」再附一句可改用「.搜索」全文检索（.搜索 自身即全文检索，不再提示）
            await matcher.finish(
                text.TXT_QUERY_NO_RESULT_SCOPED.format(
                    keyword=keyword,
                    where=_where(event),
                    scope="、".join(scope),
                    hint=(
                        text.TXT_QUERY_NO_RESULT_SCOPED_HINT
                        if mode == MODE_NAME
                        else ""
                    ),
                )
            )
        await matcher.finish(text.TXT_QUERY_NO_RESULT.format(keyword=keyword))

    if len(candidates) == 1:
        # 唯一候选：跳过候选列表直接展示词条正文（选号失去意义，也不再写短时记录）
        candidate = candidates[0]
        entry_text, located = locate_entry(candidate.content, keyword)
        await _send_entry(bot, event, candidate, keyword, entry_text, located)
        await matcher.finish()

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
    default_store.touch(record)
    if record.mode == query_common.MODE_ATLAS:
        # 速查子命令候选：正文来自站点页面（抓取 + 解码），与检索候选分流
        from . import query_atlas

        await query_atlas.send_atlas_entry(
            bot, event, candidate, keyword=record.keyword, kind=record.kind
        )
        await selection_matcher.finish()

    entry_text, located = locate_entry(candidate.content, record.keyword)
    await _send_entry(bot, event, candidate, record.keyword, entry_text, located)
    await selection_matcher.finish()


# =========================================================================
# 渲染与发送
# =========================================================================


def _render_list(record: SelectionRecord) -> str:
    """渲染候选列表当前页（只有一页时不显示页码与翻页提示，2026-09-26）。"""
    items = record.page_slice()
    page_count = record.page_count
    limited = (
        text.TXT_QUERY_LIST_LIMITED.format(count=len(record.candidates))
        if len(record.candidates) >= MAX_CANDIDATES
        else ""
    )
    page_suffix = (
        text.TXT_QUERY_LIST_PAGE_SUFFIX.format(page=record.page, pages=page_count)
        if page_count > 1
        else ""
    )
    head = text.TXT_QUERY_LIST_HEAD.format(
        keyword=record.keyword,
        count=len(record.candidates),
        limited=limited,
        page=page_suffix,
    )
    base_no = (record.page - 1) * PAGE_SIZE
    item_lines = []
    for offset, candidate in enumerate(items):
        category = (
            text.TXT_QUERY_LIST_CATEGORY.format(category=candidate.category)
            if candidate.category
            else ""
        )
        item_lines.append(
            text.TXT_QUERY_LIST_ITEM.format(
                no=base_no + offset + 1,
                title=candidate.title or f"页面 #{candidate.index}",
                category=category,
            )
        )
    return query_common.list_frame(head=head, items=item_lines, pages=page_count)


async def _send_entry(
    bot: Bot,
    event: MessageEvent,
    candidate: Candidate,
    keyword: str,
    entry_text: str,
    located: bool,
) -> None:
    """发送词条正文：**优先站点页面**（富文本卡片 / 结构化文本），失败回退
    服务端纯文本（``locate_entry`` 的三级定位）。

    站点页面路径取自候选的 ``path``（``topics/`` 前缀剥离）；抓取失败（站点
    不可达、自建服务只提供接口等）时走下方回退路径，查询不中断。
    """
    from . import query_atlas

    if await query_atlas.send_atlas_entry(
        bot, event, candidate, keyword=keyword, name=keyword
    ):
        return

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
        elif query_common.notify_image_fallback():
            # 依赖缺失：首次回退附一行提示（全插件只提示一次，避免刷屏）
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

    await _send_chunked(bot, event, lines)


async def _send_chunked(bot: Bot, event: MessageEvent, lines: List[str]) -> None:
    """按 20 行分段发送，最多 3 段（超出时在末段追加截断提示）。"""
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
