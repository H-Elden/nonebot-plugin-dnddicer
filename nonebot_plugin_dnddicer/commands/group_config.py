"""群默认骰面命令：``.dset``（设置/查询当前群的默认掷骰表达式）。

语义：
- 仅群聊可用（私聊提示不可用）；仅群主/管理员可修改（查询无权限限制）；
- 无参数 → 查询当前群默认（未设置时回退全局默认 D20）；
- ``.dset <表达式>`` → 校验并保存（复用 default_dice.format_default_expr_from_input，
  支持纯数字面数 ``.dset 100`` 或表达式 ``.dset 2d6+3``）；
- 掷骰（.r）时若本群设置了默认骰面则优先使用（见 roll.py）。
"""

from __future__ import annotations

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from ..data.group_config import get_group_config, set_group_config_field
from ..engine.roll.ast_engine.errors import RollEngineError
from ..engine.roll.default_dice import format_default_expr_from_input, format_default_expr_from_storage
from ..engine.roll.roll_utils import RollDiceError
from ..platform import onebot_v11
from . import base, text

_HELP = (
    "设置当前群的默认掷骰表达式\n"
    "用法：.dset [表达式]（如 .dset 100、.dset 2d6+3）；无参数查看当前默认。\n"
    "仅群主或管理员可修改；掷骰（.r）中裸 D 将使用本群默认骰面。"
)

dset_matcher = base.on_dnd_command("dset", _HELP)


@dset_matcher.handle()
async def handle_dset(event: MessageEvent) -> None:
    """处理 .dset。"""
    if not isinstance(event, GroupMessageEvent):
        await dset_matcher.finish(text.TXT_DSET_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()

    # 查询当前默认（任何群成员可查）
    if not rest:
        cfg = await get_group_config(event.group_id)
        current_expr = format_default_expr_from_storage(cfg.get("default_dice"))
        await dset_matcher.finish(
            text.TXT_DSET_CURRENT.format(expr=current_expr)
        )

    # 修改默认：需群主/管理员权限
    if not onebot_v11.is_group_manager(event):
        await dset_matcher.finish(text.TXT_DSET_NO_PERMISSION)

    try:
        new_expr = format_default_expr_from_input(rest)
    except (RollDiceError, RollEngineError) as exc:
        # 引擎错误（如优势/劣势粘连检查）同样回可读原因，避免落入全局异常兜底
        await dset_matcher.finish(text.TXT_DSET_INVALID.format(reason=exc.info))

    await set_group_config_field(event.group_id, "default_dice", new_expr)
    await dset_matcher.finish(text.TXT_DSET_SUCCESS.format(expr=new_expr))
