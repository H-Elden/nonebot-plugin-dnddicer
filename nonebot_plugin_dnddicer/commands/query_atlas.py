"""速查子命令（``.查询法术`` / ``.查询怪物`` / …，2026-09-26）。

八条命令共享同一流程：开关检查 → 关键词 → 速查索引查询（懒构建兜底 +
``.查询范围`` 过滤）→ 唯一命中直接展示 / 多候选列表（回数字查看、翻页）。

正文来源：站点页面 HTML（``query/fetch.py`` 抓取 → ``query/decode.py`` 按
锚点/容器/标题切分清洗 + 关键词高亮）。图片模式复用 ``render.render_rule_card``
（D 批升级为富文本卡片与数据卡样式）；文字模式给结构化文本并按段发送。

候选记录的 ``mode`` 为 ``atlas``（见 ``query_common.MODE_ATLAS``），选择与
翻页由 ``commands/query.py`` 的 ``selection_matcher`` 统一接管并分流到
``send_atlas_entry``。
"""

from __future__ import annotations

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.matcher import Matcher

from .. import render
from ..config import get_config
from ..data import query_settings
from ..query import atlas as atlas_mod
from ..query import decode
from ..query.atlas import AtlasEntry
from ..query.interaction import PAGE_SIZE, default_store
from ..query.models import Candidate, QueryUnavailableError
from . import atlas as atlas_cmd
from . import base, query_common
from . import query as query_cmd
from . import text as cmd_text

#: 类别 → 示例命令（帮助文案与用法提示共用）
_EXAMPLES = {
    "spell": ".查询法术 火球术",
    "monster": ".查询怪物 食人魔",
    "item": ".查询物品 龙珠",
    "feat": ".查询专长 冲锋手",
    "class": ".查询职业 野蛮人",
    "origin": ".查询起源 士兵",
    "term": ".查询术语 倒地",
    "unit": ".查询单位 货币",
}


def _register(kind: str, example: str) -> Matcher:
    """创建一条速查子命令的响应器并挂上共享流程。"""
    label = atlas_mod.KIND_LABELS[kind]
    name = f"查询{label}"
    help_text = cmd_text.TXT_ATLAS_HELP.format(kind=label, example=example)
    matcher = base.on_dnd_command(name, help_text)

    @matcher.handle()
    async def _handle(bot: Bot, event: MessageEvent) -> None:
        await _run_atlas_query(matcher, bot, event, kind=kind, label=label)

    return matcher


def _to_candidate(entry: AtlasEntry, index: int) -> Candidate:
    """索引条目 → 候选（复用候选选择/翻页机制；正文由 send_atlas_entry 获取）。"""
    return Candidate(
        index=index,
        title=entry.name,
        category=entry.category,
        path=entry.page_path,
        rank=0,
        content="",
        base_url="",
        anchor=entry.anchor,
        meta=entry.meta,
    )


def _render_list(record, label: str) -> str:
    """渲染速查候选列表当前页（只有一页时不显示页码与翻页提示）。"""
    items = record.page_slice()
    page_count = record.page_count
    page_suffix = (
        cmd_text.TXT_QUERY_LIST_PAGE_SUFFIX.format(page=record.page, pages=page_count)
        if page_count > 1
        else ""
    )
    head = cmd_text.TXT_ATLAS_LIST_HEAD.format(
        keyword=record.keyword,
        count=len(record.candidates),
        kind=label,
        page=page_suffix,
    )
    base_no = (record.page - 1) * PAGE_SIZE
    item_lines = [
        cmd_text.TXT_ATLAS_LIST_ITEM.format(
            no=base_no + offset + 1,
            title=candidate.title,
            meta=query_common.display_meta(candidate.category, candidate.meta),
        )
        for offset, candidate in enumerate(items)
    ]
    return query_common.list_frame(head=head, items=item_lines, pages=page_count)


async def _run_atlas_query(
    matcher: Matcher,
    bot: Bot,
    event: MessageEvent,
    *,
    kind: str,
    label: str,
) -> None:
    """速查子命令的公共流程。"""
    if not get_config().dnddicer_query_enabled:
        await matcher.finish(cmd_text.TXT_QUERY_DISABLED)

    keyword = (base.get_command_rest(event) or "").strip()
    if not keyword:
        await matcher.finish(
            cmd_text.TXT_QUERY_USAGE.format(
                usage=cmd_text.TXT_ATLAS_USAGE.format(
                    kind=label, example=_EXAMPLES.get(kind, "")
                )
            )
        )

    # 懒构建兜底：缓存缺失时按需构建该类（启动构建失败/首次部署的路径）
    if not await atlas_cmd.ensure_kind(kind):
        await matcher.finish(cmd_text.TXT_ATLAS_NOT_READY)

    scope = await query_settings.get_scope(query_common.chat_key(event))
    entries = atlas_cmd.get_store().lookup(kind, keyword, categories=scope or None)
    if not entries:
        if scope:
            await matcher.finish(
                cmd_text.TXT_ATLAS_NO_RESULT_SCOPED.format(
                    keyword=keyword, kind=label, scope="、".join(scope)
                )
            )
        await matcher.finish(
            cmd_text.TXT_ATLAS_NO_RESULT.format(keyword=keyword, kind=label)
        )

    candidates = [
        _to_candidate(entry, index) for index, entry in enumerate(entries, start=1)
    ]
    if len(candidates) == 1:
        # 唯一命中：直接展示正文（不写候选记录）；站点不可达时给出提示
        sent = await send_atlas_entry(
            bot, event, candidates[0], keyword=keyword, kind=kind
        )
        if not sent:
            await matcher.finish(
                cmd_text.TXT_QUERY_UNAVAILABLE.format(count=1)
            )
        await matcher.finish()

    record = default_store.put(
        event.get_session_id(),
        event.user_id,
        keyword=keyword,
        mode=query_common.MODE_ATLAS,
        candidates=candidates,
        kind=kind,
    )
    await matcher.finish(_render_list(record, label))


async def send_atlas_entry(
    bot: Bot,
    event: MessageEvent,
    candidate: Candidate,
    *,
    keyword: str,
    kind: str = "",
    name: str = "",
) -> bool:
    """抓取候选页 → 解码条目 → 按图片（富文本卡片）/ 文字（结构化文本）发送。

    Args:
        candidate: 候选（``path`` 为站点相对路径、``anchor`` 可为空）。
        keyword: 用户关键词（高亮与回退匹配用）。
        kind: 速查类别（速查子命令传入；通用检索为空串）。
        name: 无锚点时的条目名（通用检索传关键词；速查候选默认用候选标题）。

    Returns:
        是否已发送：``False`` 表示站点抓取失败（速查子命令据此提示不可用，
        通用检索据此回退服务端纯文本正文）。
    """
    # 复核范围：选择期间范围可能被改，避免展示范围外内容
    scope = await query_settings.get_scope(query_common.chat_key(event))
    if scope and candidate.category not in scope:
        await bot.send(
            event,
            cmd_text.TXT_ATLAS_OUT_OF_SCOPE.format(
                category=query_common.category_label(candidate.category)
            ),
        )
        return True

    store = atlas_cmd.get_store()
    # 路径归一：速查索引存的是 topics/ 之后的相对路径，服务端候选带 topics/ 前缀
    page_path = candidate.path.removeprefix("topics/")
    try:
        html = await store.fetcher.get_page(page_path)
    except QueryUnavailableError as exc:
        logger.warning(
            "DNDDicer 正文抓取失败 path={} attempts={}", page_path, exc.attempts
        )
        return False

    title_match = name or candidate.title or keyword
    decoded = decode.decode_entry(
        html, anchor=candidate.anchor, name=title_match, keyword=keyword
    )
    title = decoded.title or title_match
    category = query_common.display_meta(candidate.category, candidate.meta)

    # 图片模式（两级开关；富文本卡片优先，渲染不可用时回退文字并只提示一次）
    image_hint = ""
    use_image = (
        bool(decoded.text.strip())
        and get_config().dnddicer_query_image_enabled
        and await query_settings.is_image_enabled(query_common.chat_key(event))
    )
    if use_image:
        if render.rich_available():
            try:
                png = await render.render_rich_card(
                    title=title,
                    category=category,
                    body_html=decoded.fragment,
                    source_path=candidate.path,
                    located=decoded.located,
                )
            except Exception:  # noqa: BLE001 - 渲染异常回退文字（查询不丢）
                logger.exception("DNDDicer 富文本卡片渲染失败，已回退文字输出")
            else:
                await bot.send(event, MessageSegment.image(png))
                return True
        elif query_common.notify_image_fallback():
            image_hint = cmd_text.TXT_QUERY_IMAGE_FALLBACK

    lines = [cmd_text.TXT_QUERY_ENTRY_HEAD.format(category=category, title=title)]
    if not decoded.located:
        lines.append(cmd_text.TXT_QUERY_ENTRY_FALLBACK)
    body = decoded.text.strip()
    lines.extend(body.splitlines() if body else [cmd_text.TXT_QUERY_ENTRY_EMPTY])
    if image_hint:
        lines.append(image_hint)
    await query_cmd._send_chunked(bot, event, lines)
    return True


#: 八条速查子命令（模块顶层注册；顺序与「本书速查」一致）
spell_matcher = _register("spell", _EXAMPLES["spell"])
monster_matcher = _register("monster", _EXAMPLES["monster"])
item_matcher = _register("item", _EXAMPLES["item"])
feat_matcher = _register("feat", _EXAMPLES["feat"])
class_matcher = _register("class", _EXAMPLES["class"])
origin_matcher = _register("origin", _EXAMPLES["origin"])
term_matcher = _register("term", _EXAMPLES["term"])
unit_matcher = _register("unit", _EXAMPLES["unit"])
