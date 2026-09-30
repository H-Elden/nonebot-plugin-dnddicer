"""帮助命令：``.帮助`` / ``.help``（别名，均注册）。

入口（2026-09-28 重做，版式表见 ``commands/help_layout.py``）：

- 无参数：总览（版本 + 简介 + 开关骰娘 + 四个入口）；
- ``.help 命令``：7 组目录（``列表`` / ``指令`` / ``菜单`` / ``list`` 为静默别名）；
- ``.help <组名>``：该组命令清单（掷骰 / 角色 / 武器 / 生命 / 先攻 / 查询 / 管理；
  另接受少量静默别名，如 ``血量`` → 生命）；
- ``.help <命令名 / 别名>``：命令详情；
- ``.help <写法>``：只进帮助的条目（检定点 / 豁免 / 先攻检定 / 武器命令族），
  如 ``.help 力量检定``、``.help 刺剑伤害``；
- ``.help 链接 [on|off]``：相关链接与该处「文档站链接行」开关；
- ``.help 关于`` / ``.help 骰主`` / ``.help 联系``：插件信息 / 骰主指令 / 联系方式；
- 未命中：一行提示 + 指向 ``.help 命令``。

匹配顺序：专用入口 → 组名（含别名）→ 命令名（含别名，大小写不敏感）→
只进帮助的条目（先精确、再取最长包含）→ 未命中。组名优先于命令名，
因此 ``.help 查询`` 给「查询」组清单、``.help q`` 才是 ``.查询`` 命令详情。

回复末尾的文档站链接行由 ``.help 链接 on/off`` 控制：**群聊默认关、私聊默认开**，
按群 / 私聊分别持久（见 ``data/help_settings.py``）；链接地址取**条目对应的文档页
深链**（组清单与命令详情各带自己的 ``doc``，见 ``help_layout`` 与各命令模块的
注册处），没有对应页时回落站点首页；``关于`` / ``联系`` / ``链接`` 三个入口自身
带链接或联系方式，不再追加这一行。
"""

from __future__ import annotations

from nonebot.adapters.onebot.v11 import MessageEvent

from ..data import help_settings
from ..version import __version__
from . import base, help_layout, text

#: 插件元数据取不到时的仓库地址兜底（与 pyproject / __init__.py 同值）
_REPO_URL_FALLBACK = "https://github.com/H-Elden/nonebot-plugin-dnddicer"

#: 总览 / 目录入口的对应文档页（《命令总览》）
_LANDING_DOC = "guide/overview"
#: `.help 骰主` 的对应文档页（骰主指令目前只有 `.查询索引`，见站点《规则查询》）
_MASTER_DOC = "guide/query"

_HELP = (
    ".help [命令 | 分组 | 链接 | 关于 | 骰主 | 联系]\n"
    "  无参数：帮助总览；.help 命令：命令分组目录\n"
    "  .help <分组>：该组命令清单\n"
    "  .help <命令>：命令详情（如 .help r、.help hp）"
)

help_matcher = base.on_dnd_command(
    "help", _HELP, aliases=("帮助",), doc="guide/overview"
)


def _chat_key(event: MessageEvent) -> str:
    """本处设置键（群聊按群、私聊按用户），与规则查询的按处键同一约定。"""
    group_id = getattr(event, "group_id", None)
    if group_id is not None:
        return help_settings.group_key(group_id)
    return help_settings.private_key(event.user_id)


def _repo_url() -> str:
    """项目仓库地址（取插件元数据 homepage；取不到时退回常量）。"""
    try:
        from .. import __plugin_meta__
    except Exception:  # noqa: BLE001 - 元数据不可用不应影响 .help 回复
        return _REPO_URL_FALLBACK
    return getattr(__plugin_meta__, "homepage", "") or _REPO_URL_FALLBACK


async def _doc_line(event: MessageEvent, doc: str = "") -> str:
    """末尾的文档站链接行；本处开关关闭时返回空串（群聊默认关、私聊默认开）。

    ``doc`` 为条目对应的文档页站内相对路径（如 ``guide/hp``）；留空回落站点首页。
    """
    group_id = getattr(event, "group_id", None)
    enabled = await help_settings.is_link_enabled(
        _chat_key(event), default=group_id is None
    )
    if not enabled:
        return ""
    return text.TXT_HELP_DOC_LINE.format(url=_doc_url(doc))


def _doc_url(doc: str) -> str:
    """文档站地址：有对应页给深链，没有则给站点首页。"""
    page = (doc or "").strip().strip("/")
    return f"{text.TXT_HELP_DOCS_BASE}/{page}" if page else text.TXT_HELP_DOCS_BASE


async def _with_doc_line(body: str, event: MessageEvent, doc: str = "") -> str:
    """按本处开关给回复补上文档站链接行（``doc`` 为对应文档页）。"""
    line = await _doc_line(event, doc)
    return f"{body}\n{line}" if line else body


async def _handle_link(event: MessageEvent, action: str) -> str:
    """``.help 链接 [on|off]``：查看链接入口、或切换链接行开关。"""
    chat_key = _chat_key(event)
    group_id = getattr(event, "group_id", None)
    if not action:
        return text.TXT_HELP_LINK.format(url=text.TXT_HELP_DOCS_BASE)
    value = action.strip().lower()
    if value in ("on", "off"):
        await help_settings.set_link_enabled(chat_key, value == "on")
        return text.TXT_HELP_LINK_ON if value == "on" else text.TXT_HELP_LINK_OFF
    enabled = await help_settings.is_link_enabled(chat_key, default=group_id is None)
    state = text.TXT_HELP_LINK_STATE_ON if enabled else text.TXT_HELP_LINK_STATE_OFF
    return text.TXT_HELP_LINK_USAGE.format(state=state)


def _render_contact() -> str:
    """``.help 联系``：固定两行 + 两个可选行（配置为空则不显示）。

    两个可选行取自配置 ``dnddicer_master_contact``（骰主联系方式）与
    ``dnddicer_master_group``（骰主交流群），顺序固定；骰主 QQ
    （``dnddicer_master_qq``）是 ``.master`` 的投递地址，不在此展示。
    """
    from ..config import get_config

    lines = [text.TXT_HELP_CONTACT]
    config = get_config()
    contact = getattr(config, "dnddicer_master_contact", "") or ""
    group = getattr(config, "dnddicer_master_group", "") or ""
    if contact:
        lines.append(text.TXT_HELP_CONTACT_MASTER.format(value=contact))
    if group:
        lines.append(text.TXT_HELP_CONTACT_GROUP.format(value=group))
    return "\n".join(lines)


def _find_command(keyword: str) -> tuple[str, str]:
    """按命令名 / 别名查详情文案与对应文档页（大小写不敏感；骰主命令也查得到）。"""
    commands = base.get_registered_commands(include_hidden=True)
    if keyword in commands:
        return commands[keyword], base.get_command_doc(keyword)
    lowered = keyword.lower()
    for name, description in commands.items():
        if name.lower() == lowered:
            return description, base.get_command_doc(name)
    return "", ""


@help_matcher.handle()
async def handle_help(event: MessageEvent) -> None:
    """处理 .help / .帮助。"""
    keyword = (base.get_command_rest(event) or "").strip()

    # ① 无参数：总览（对应《命令总览》页）
    if not keyword:
        body = text.TXT_HELP_LANDING.format(version=__version__)
        await help_matcher.finish(await _with_doc_line(body, event, _LANDING_DOC))

    first, _, action = keyword.partition(" ")
    action = action.strip()

    # ② 专用入口：链接 / 命令目录 / 关于 / 骰主 / 联系
    if first == help_layout.LINK_KEYWORD:
        await help_matcher.finish(await _handle_link(event, action))
    if help_layout.is_catalog_keyword(first):
        await help_matcher.finish(
            await _with_doc_line(text.TXT_HELP_CATALOG, event, _LANDING_DOC)
        )
    if first == help_layout.ABOUT_KEYWORD:
        body = text.TXT_HELP_ABOUT.format(
            version=__version__,
            repo=_repo_url(),
            group=text.TXT_HELP_ABOUT_GROUP,
        )
        await help_matcher.finish(body)
    if first == help_layout.MASTER_KEYWORD:
        await help_matcher.finish(
            await _with_doc_line(text.TXT_HELP_MASTER, event, _MASTER_DOC)
        )
    if first == help_layout.CONTACT_KEYWORD:
        await help_matcher.finish(_render_contact())

    # ③ 组名 / 组别名：该组命令清单
    group = help_layout.find_group(keyword)
    if group is not None:
        name, lines, doc = group
        await help_matcher.finish(await _with_doc_line("\n".join(lines), event, doc))

    # ④ 命令名 / 别名：命令详情
    detail, doc = _find_command(keyword)
    if detail:
        await help_matcher.finish(await _with_doc_line(detail, event, doc))

    # ⑤ 只进帮助的条目（检定点 / 豁免 / 先攻检定 / 武器命令族 / .master）
    entry = help_layout.find_help_only(keyword)
    if entry is not None:
        await help_matcher.finish(await _with_doc_line(entry.text, event, entry.doc))

    # ⑥ 未命中
    await help_matcher.finish(
        "\n".join(
            (
                text.TXT_HELP_NOT_FOUND.format(keyword=keyword),
                text.TXT_HELP_NOT_FOUND_HINT,
            )
        )
    )
