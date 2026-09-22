"""命令层基础设施：DNDDicer 点前缀命令的注册、匹配与事件响应器创建。

设计（对齐 nonebot-dicepp 命令手感 + NoneBot 商店合规）：
- **命令起始符**：默认**仅**匹配本插件自带的英文句号 ``.`` 与中文句号 ``。``
  （全角输入法直发）；宿主 ``COMMAND_START``（NoneBot 默认含 ``/``）中声明的
  起始符**默认不兼容**——/.help、/bot 等常见单词命令易与宿主其他插件冲突，
  需由 ``dnddicer_use_host_command_starts`` 配置显式开启。起始符集合
  惰性读取并缓存，未初始化（引擎单测直接导入）时退化为仅中英文句号；
- **命令名注册表 + 最长前缀匹配**：命令体（起始符后的文本）以任一已注册命令名
  开头即命中、取最长者（保证 ``.ra`` 命中 ``ra`` 而不是 ``r``）；命令名后的
  剩余文本原样交给命令处理（因此 ``.r2d6+3`` 与 ``.r 2d6+3`` 等价——与
  DicePP 的 ``startswith(".r")`` 剥前缀语义一致）；
- **事件响应**：每条命令一个 ``on_message`` matcher，优先级取自
  ``dnddicer_command_priority``（Config，默认 10）并 ``block=True``——
  命中即阻断后续事件传播，与宿主 bot 其他插件（AIchat 等）协同；
- 命令模块（roll 等）在其模块顶层创建响应器即完成注册与加载。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, Sequence, Union

from nonebot import get_driver, logger
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor
from nonebot.plugin import on_message
from nonebot.rule import Rule, to_me

from ..config import get_config
from ..data import service_state
from ..data.characters import get_character
from ..platform import onebot_v11
from . import text

#: 本插件自带的命令起始符（英文/中文句号）
_BUILTIN_STARTS: tuple[str, ...] = (".", "。")

#: 已注册命令名 → 说明文案（供匹配与 .帮助 使用）
_REGISTRY: dict[str, str] = {}


def register_command(name: str, description: str = "") -> None:
    """注册一条命令名（重复注册同名时保留先注册者）。"""
    _REGISTRY.setdefault(name, description)


def get_registered_commands() -> dict[str, str]:
    """返回已注册命令名及其说明（副本）。"""
    return dict(_REGISTRY)


@lru_cache(maxsize=1)
def _compute_command_starts() -> tuple[str, ...]:
    """计算可用命令起始符：默认仅本插件自带句号；兼容开关开启时叠加宿主配置。

    NoneBot 宿主 ``COMMAND_START`` 默认含 ``/``——若无条件兼容，``/help``、
    ``/bot`` 等常见单词命令可能同时命中本插件与宿主其他插件（冲突）。
    因此默认**只匹配英文句号 ``.`` 与中文句号 ``。``**；需兼容宿主起始符
    （含环境变量 ``DNDDICER_USE_HOST_COMMAND_STARTS=true``）时由
    config.dnddicer_use_host_command_starts 开启。
    """
    starts = list(_BUILTIN_STARTS)
    try:
        if not get_config().dnddicer_use_host_command_starts:
            return tuple(starts)
        host_starts = get_driver().config.command_start
        for s in host_starts or ():
            # 空起始符（NoneBot 允许 "" = 无前缀直发命令）风险过大，不采纳
            if s and s not in starts:
                starts.append(s)
    except ValueError:
        # NoneBot 未初始化（引擎单测等直接导入场景）：仅保留内置句号
        pass
    return tuple(starts)


def get_command_starts() -> tuple[str, ...]:
    """返回当前可用的命令起始符集合（缓存）。"""
    return _compute_command_starts()


def match_command_name(body: str) -> tuple[Optional[str], str]:
    """在命令体文本上做最长命令名前缀匹配（大小写不敏感，如 ``.R`` 亦命中 ``r``）。

    Args:
        body: 命令起始符之后的文本（未 strip 亦可）。

    Returns:
        (命中的命令名, 该命令名之后的剩余文本)；未命中返回 (None, body)。
    """
    lower_body = body.lower()
    for name in sorted(_REGISTRY, key=len, reverse=True):
        if lower_body.startswith(name.lower()):
            # 返回注册表中的规范命令名与原文剩余部分
            return name, body[len(name):]
    return None, body


def parse_command_text(text: str) -> Optional[tuple[str, str, str]]:
    """解析一条候选消息文本，判断是否为 DNDDicer 命令。

    Returns:
        (起始符, 命令名, 剩余参数)；不是本插件命令时返回 None。
    """
    stripped = text.strip()
    for start in get_command_starts():
        if not stripped.startswith(start):
            continue
        name, rest = match_command_name(stripped[len(start):])
        if name is not None:
            return start, name, rest
        return None
    return None


def command_rule(*names: str) -> Rule:
    """生成匹配指定命令名集合的事件响应规则（基于纯文本，兼容所有消息事件）。

    命令名可为多个（含别名），匹配结果只需落在集合内即命中。
    """
    target = frozenset(names)

    async def _checker(event: MessageEvent) -> bool:
        parsed = parse_command_text(event.get_plaintext())
        return parsed is not None and parsed[1] in target

    return Rule(_checker)


def group_service_rule(*manage_commands: str) -> Rule:
    """群聊服务门禁规则（白名单：默认关闭，见 data/service_state.py）。

    未开启服务的群内，本插件命令不命中（matcher 不触发、无任何回复，事件继续
    交给宿主其他插件）；私聊等非群聊事件不受门禁限制。``manage_commands`` 中
    的管理命令（如 .bot）在关闭的群里始终放行——否则关闭服务的群将无法再开启。
    """

    async def _checker(event: MessageEvent) -> bool:
        group_id = getattr(event, "group_id", None)
        if group_id is None:
            return True
        if manage_commands:
            parsed = parse_command_text(event.get_plaintext())
            if parsed is not None and parsed[1].lower() in manage_commands:
                return True
        return await service_state.is_service_enabled(group_id)

    return Rule(_checker)


def on_dnd_command(
    name: str,
    description: str = "",
    *,
    aliases: tuple[str, ...] = (),
    require_to_me: bool = False,
) -> Matcher:
    """创建一条 DNDDicer 点前缀命令的事件响应器并注册命令名。

    Args:
        name: 命令名（如 "r"）；匹配为最长前缀，命令名后无需空格。
        description: 命令帮助全文（供 .帮助 使用，可为空）。
        aliases: 命令别名（同样注册进匹配表，如 ("帮助",) 使 .帮助 与 .help 等价）。
        require_to_me: 群聊中是否必须 @ 机器人（to_me）才响应。onebot v11
            群聊仅开头/结尾 @ 机器人时为 to_me（at 段被适配器剥除后命令文本
            正常解析）；私聊事件 to_me 恒为 True，不受该选项影响。

    Returns:
        可直接挂 ``@matcher.handle()`` 的 Matcher。
    """
    register_command(name, description)
    for alias in aliases:
        register_command(alias, description)

    names = (name, *aliases)
    rule = command_rule(*names)
    if require_to_me:
        rule = rule & to_me()
    # 群聊服务门禁：.bot 为服务开关管理命令，始终放行（见 commands/bot.py）
    manage = (name,) if name.lower() == "bot" else ()
    rule = rule & group_service_rule(*manage)
    priority = get_config().dnddicer_command_priority
    return on_message(rule, priority=priority, block=True)


def get_command_rest(event: MessageEvent) -> Optional[str]:
    """提取当前消息中命令名之后的剩余参数（供 handler 复用，避免二次解析）。"""
    parsed = parse_command_text(event.get_plaintext())
    return parsed[2] if parsed else None


def parse_command_with_mentions(event: MessageEvent) -> Optional[tuple[str, str, str]]:
    """命令解析的 @ 标记化版本（命令名匹配仍基于纯文本语义）。

    与 ``parse_command_text(event.get_plaintext())`` 的唯一差异：@ 段以
    ``@<qq>`` 标记保留在文本中、命令**之前**的 @ 标记先剥离（``@小明 .hp -d4``
    的命令名照常命中）；无 @ 时结果与纯文本解析完全一致。
    """
    text = onebot_v11.rebuild_text_with_mentions(event).strip()
    return parse_command_text(onebot_v11.strip_leading_mentions(text))


def get_command_rest_with_mentions(event: MessageEvent) -> Optional[str]:
    """提取命令名之后的剩余参数，@ 段以 ``@<qq>`` 标记保留在参数中。

    供支持 @ 目标的命令（.hp/.ri/.init/.回合/角色卡族）取参；无 @ 时与
    ``get_command_rest`` 结果完全一致。命令规则仍基于纯文本（规则层零改动）。
    """
    parsed = parse_command_with_mentions(event)
    return parsed[2] if parsed else None


def join_lines(parts: Sequence[Union[str, Message]]) -> Union[str, Message]:
    """把多行回复组装为一条消息（行间换行）。

    全为纯文本时返回字符串（与既有输出完全一致，便于文案断言）；含 @ 消息段
    （如无卡引导的真 @ 行）时返回 Message。供 @ 相关回复按行拼接的场合使用。
    """
    if all(isinstance(part, str) for part in parts):
        return "\n".join(parts)  # type: ignore[arg-type]  # 上面已判定全为 str
    message = Message()
    for index, part in enumerate(parts):
        if index:
            message += "\n"
        message += part
    return message


async def resolve_display_name(
    bot: Bot,
    event: MessageEvent,
    user_id: int | str | None = None,
    char_name: str = "",
) -> str:
    """统一的玩家展示名回退链：角色名 → 群名片 → QQ 昵称 → 「未知玩家（QQ号）」。

    本插件所有「查询名称用于显示」的场景共用本函数（NPC 除外——其名称由
    用户指定，不入此链，见 commands/npc.py 与 commands/hp.py 的 NPC 分支）。
    默认解析事件发送者本人；传 ``user_id`` 可解析他人（此时群名片/昵称需
    经 ``get_group_member_info`` 查询，失败则回退兜底文案）。``char_name``
    可由调用方传入已取到的角色名，避免重复查卡。

    离线可用性：本人名称取事件自带字段（零查询）；仅「查角色卡」与「查他人
    群名片」才发起 IO（角色卡走内存缓存，API 失败由适配层吞掉）。私聊无群：
    跳过角色卡与群成员查询，回退 QQ 昵称/兜底文案。
    """
    uid = str(user_id if user_id is not None else getattr(event, "user_id", ""))
    group_id = getattr(event, "group_id", None)
    if not char_name and group_id is not None and uid:
        character = await get_character(group_id, uid)
        if character is not None and character.name:
            char_name = character.name
    if char_name:
        return char_name
    # 本人：事件自带群名片/昵称（离线可用）；他人只能走群成员查询
    if uid and uid == str(getattr(event, "user_id", "")):
        name = onebot_v11.event_sender_nickname(event)
        if name:
            return name
    if group_id is not None and uid.isdigit():
        name = await onebot_v11.get_group_member_nickname(
            bot, int(group_id), int(uid)
        )
        if name:
            return name
    return text.TXT_UNKNOWN_NAME.format(qq=uid)


# =========================================================================
# 命令层全局异常兜底
# =========================================================================

#: 本插件的模块名前缀（兜底钩子只接管本插件的 matcher，不碰宿主其他插件）
_PLUGIN_MODULE_PREFIX = "nonebot_plugin_dnddicer"


@run_postprocessor
async def _unknown_error_fallback(
    matcher: Matcher,
    exception: Optional[Exception],
    bot: Bot,
    event: Event,
) -> None:
    """未预期异常统一处理：记录日志（带群/会话、不含用户原文）并回复统一文案。

    背景：命令 handler 只捕获预期错误（RollDiceError/AssertionError 等）；
    未预期异常（脏数据、引擎边界 bug）默认只进 NoneBot 日志、群里无任何回复
    ——跑团进行中骰娘沉默比报错更糟。本钩子在 NoneBot 记录异常后执行：
    本插件命令处理异常 → logger.exception（隐私：不落用户消息原文）+
    原会话统一回复；非本插件 matcher 直接放行。
    """
    if exception is None:
        return
    module = getattr(matcher, "module_name", "") or ""
    if not module.startswith(_PLUGIN_MODULE_PREFIX):
        return

    try:
        session_id = event.get_session_id()
    except Exception:  # noqa: BLE001 - 兜底自身不允许再抛异常
        session_id = "unknown"

    logger.opt(exception=exception).error(
        "DNDDicer 命令处理未知异常: matcher_module={} session={}",
        module,
        session_id,
    )
    try:
        await bot.send(event, text.TXT_UNKNOWN_ERROR)
    except Exception:  # noqa: BLE001 - 兜底自身不允许再抛异常
        logger.warning(
            "DNDDicer 未知异常兜底回复发送失败: matcher_module={} session={}",
            module,
            session_id,
        )
