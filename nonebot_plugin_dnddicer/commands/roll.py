"""掷骰命令：``.r``（普通掷骰）与 ``.rh``（暗骰）。

命令面（第一期，对齐 nonebot-dicepp ``.r`` 的常用语义）：
- ``.r [表达式] [原因]``：如 ``.r 2d6+3 力量检定``、``.r d20优势+4``；
- ``.r N#表达式``：连掷 N 次（1≤N≤10，越界回退 1，与 roll_const 一致）；
- ``.r h 表达式`` / ``.rh 表达式``：暗骰——群内只播报提示，结果私聊掷骰者；
- ``.r s 表达式``：只显示最终数值，不展示逐骰过程；
- 默认骰面：表达式中的裸 ``D`` / ``3D`` 注入默认骰面（Config
  ``dnddicer_default_face``，默认 20；群配置落地前为全局默认）；
- 原因后缀、中英文句号/宿主 COMMAND_START 起始符、大小写不敏感命令名见 base.py。

暂未实现（第一期范围外，显式提示而非静默）：``exp`` 期望值采样（待上游
``test_rexp_sampling_optimization`` 随迁一并落地）、``a/n`` 特殊判定模式。
"""

from __future__ import annotations

from typing import Any, List, Optional

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent

from ..config import get_config
from ..engine.roll.ast_engine import exec_roll_exp_unified
from ..engine.roll.ast_engine.adapter import preprocess_roll_exp
from ..engine.roll.ast_engine.errors import RollEngineError
from ..engine.roll.default_dice import apply_default_expr, format_default_expr_from_storage
from ..engine.roll.result import RollResult
from ..engine.roll.roll_utils import RollDiceError
from . import text
from .base import get_command_rest, get_display_name, on_dnd_command
from .roll_parse_args import RollParseArgs, _parse_roll_args

#: 命令说明（供 .帮助 使用；文案对齐 DicePP .r 帮助）
_HELP = (
    "掷骰：.r[掷骰表达式]([掷骰原因])\n"
    "[掷骰表达式]：([轮数]#)[个数]d面数(优/劣势)(k[取点数最大的骰子数])"
    "不带面数时视为掷一个默认的20面骰\n"
    "r后加h即为暗骰\n"
    "示例:\n"
    ".rd20+1d4+4\n"
    ".r4#d    //投4次d20\n"
    ".rd20劣势+4 //带劣势攻击\n"
    ".r2#d优势+4 攻击被束缚的地精 //两次有加值的优势攻击\n"
    ".r1d12+2d8+5抗性 //得到减半向下取整的投骰总值"
)

roll_matcher = on_dnd_command("r", _HELP)


def _render_roll_result(res_list: List[RollResult], is_show_info: bool) -> str:
    """渲染最终结果块（非特殊模式；对齐 DicePP process_msg 分支）。"""
    if len(res_list) > 1:
        # 多次掷骰：#连掷，模板为 DicePP 的 LOC_ROLL_RESULT_MULTI
        exp = res_list[0].get_exp()
        if is_show_info:
            body = "\n" + ",\n".join(res.get_result() for res in res_list)
        else:
            body = "\n" + ",\n".join(str(res.get_val()) for res in res_list)
        return text.TXT_MULTI.format(time=len(res_list), exp=exp, result=body)
    if is_show_info:
        return res_list[0].get_complete_result()
    return res_list[0].get_exp_val()


async def _roll_and_render(args: RollParseArgs, group_id: Optional[int] = None) -> str:
    """执行掷骰并渲染结果块；语法/引擎错误时抛出对应异常由调用方处理。

    默认骰面优先级：本群配置 ``default_dice``（.dset 设置）→ 插件全局配置
    ``dnddicer_default_face``（群配置落地前为默认 d20）。

    Raises:
        RollDiceError / RollEngineError: 表达式解析或求值错误（含用户可见信息）。
    """
    stored_default: Any = get_config().dnddicer_default_face
    if group_id is not None:
        from ..data.group_config import get_group_config

        cfg = await get_group_config(group_id)
        if cfg.get("default_dice"):
            stored_default = cfg["default_dice"]
    default_expr = format_default_expr_from_storage(stored_default)

    exp_str = preprocess_roll_exp(args.exp_str)
    exp_str = apply_default_expr(exp_str, default_expr)

    res_list: List[RollResult] = []
    for _ in range(args.times):
        res_list.append(exec_roll_exp_unified(exp_str))

    final = _render_roll_result(res_list, args.is_show_info)
    state = text.get_roll_state_text(res_list)
    return f"{final} {state}".rstrip()


async def _compose_reply(args: RollParseArgs, nickname: str, final_with_state: str) -> str:
    """按 DicePP 模板组装含昵称/原因/结果的完整回复文案。

    说明：final_with_state 已含 d20 状态文案；模板末段的 ``{state}`` 置空，
    拼接后去除末尾空白（state 为空时不留尾随空格）。
    """
    if args.is_hidden:
        if args.reason_str:
            return text.TXT_HIDE_RESULT_REASON.format(
                nickname=nickname, reason=args.reason_str,
                final=final_with_state, state="",
            ).rstrip()
        return text.TXT_HIDE_RESULT.format(
            nickname=nickname, final=final_with_state, state="",
        ).rstrip()
    if args.reason_str:
        return text.TXT_RESULT_REASON.format(
            nickname=nickname, reason=args.reason_str,
            final=final_with_state, state="",
        ).rstrip()
    return text.TXT_RESULT.format(nickname=nickname, final=final_with_state, state="").rstrip()


@roll_matcher.handle()
async def handle_roll(bot: Bot, event: MessageEvent) -> None:
    """处理 .r 掷骰命令。"""
    rest = get_command_rest(event)
    args = _parse_roll_args(rest or "")

    # 第一期范围外功能的显式提示
    if args.compute_exp:
        await roll_matcher.finish(text.TXT_EXP_UNIMPLEMENTED)
    if args.special_mode:
        await roll_matcher.finish(
            text.TXT_SPECIAL_MODE_UNIMPLEMENTED.format(mode=args.special_mode)
        )

    try:
        group_id = getattr(event, "group_id", None)
        final_with_state = await _roll_and_render(args, group_id=group_id)
    except (RollDiceError, RollEngineError) as e:
        # 语法/引擎错误：直接回显用户可见错误信息（DicePP 同款行为）
        await roll_matcher.finish(e.info if isinstance(e, RollDiceError) else e.message)

    nickname = get_display_name(event)
    reply = await _compose_reply(args, nickname, final_with_state)

    # 暗骰：群内只播报提示，结果私聊掷骰者（与 DicePP 端口语义一致）
    if args.is_hidden and isinstance(event, GroupMessageEvent):
        await roll_matcher.send(
            text.TXT_HIDE_GROUP.format(nickname=nickname)
        )
        try:
            # onebot v11 无 send_private_msg 便捷方法，走通用 call_api
            await bot.call_api(
                "send_private_msg",
                user_id=event.user_id,
                message=reply,
            )
        except Exception as exc:  # noqa: BLE001 - 私聊失败不应影响命令主流程
            logger.warning(f"[DNDDicer] 暗骰私聊发送失败 user_id={event.user_id}: {exc}")
        return

    await roll_matcher.finish(reply)
