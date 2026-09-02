"""帮助命令：``.帮助`` / ``.help``（别名，均注册）。

- 无参数：列出本插件已注册命令（名称 + 首行说明）；
- 带参数：``.help r`` / ``.帮助 dset`` —— 显示指定命令的完整帮助文本
  （大小写不敏感，中文命令名直接输入即可）。
"""

from __future__ import annotations

from nonebot.adapters.onebot.v11 import MessageEvent

from . import base

_HELP = (
    "帮助：.help / .帮助\n"
    "- 无参数：列出全部命令\n"
    "- .help <命令名>：查看指定命令的详细用法\n"
    "示例：.help r"
)

help_matcher = base.on_dnd_command(
    "help",
    _HELP,
    aliases=("帮助",),
)


def _summary_line(description: str) -> str:
    """取帮助全文的第一行作为总览说明。"""
    first = description.strip().splitlines()[0] if description.strip() else ""
    return first


@help_matcher.handle()
async def handle_help(event: MessageEvent) -> None:
    """处理 .help / .帮助。"""
    rest = (base.get_command_rest(event) or "").strip()

    if not rest:
        # 无参数：总览全部命令（保持注册顺序；同帮助文本的别名只显示首条，
        # 如 .帮助 是 .help 的别名，避免列表重复）
        lines = ["DNDDicer 可用命令："]
        seen_docs: set[str] = set()
        for name, description in base.get_registered_commands().items():
            if description in seen_docs:
                continue
            seen_docs.add(description)
            summary = _summary_line(description)
            lines.append(f"· .{name}  {summary}" if summary else f"· .{name}")
        await help_matcher.finish("\n".join(lines))

    # 带参数：查指定命令的完整帮助
    keyword = rest
    commands = base.get_registered_commands()
    # 大小写不敏感查找；直接命中优先
    match = commands.get(keyword) or next(
        (doc for name, doc in commands.items() if name.lower() == keyword.lower()),
        None,
    )
    if match:
        await help_matcher.finish(match)
    await help_matcher.finish(f"未找到命令「{keyword}」。发送 .help 查看全部命令。")
