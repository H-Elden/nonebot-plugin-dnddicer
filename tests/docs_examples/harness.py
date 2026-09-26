"""文档站示例取证：把示例时间线喂给真实插件，记录骰娘的全部回复。

本模块是「示例转录」的唯一生产端——docs/ 页面里的气泡示例全部取自这里的输出，
禁止手编（纪律见 AGENTS.md 开发约定）。

机制（与既有测试同一套语义，但不使用 nonebug 的断言夹具）：

- ``bootstrap()`` 幂等：沿用 tests/conftest.py 的做法（``nonebot.init`` + 注册适配器 +
  ``load_from_toml``），因此本模块既能在 pytest 下用，也能由 doc/tools 的脚本独立运行；
- 事件经 onebot v11 的真实入口 ``Bot.handle_event`` 分发（含 @ 检测与消息规整），
  规则、群聊服务门禁、命令层全部是真实行为；
- 记录式 Bot：覆盖 ``send``（群消息）与 ``call_api``（私聊 ``send_private_msg``、
  群名片 ``get_group_member_info``），不产生任何真实网络调用；
- 骰值走 SequenceRuntime 固定序列，每步断言「恰好耗尽」——多掷少掷都会失败；
- 时间线在同一示例群里顺序执行，跨步骤状态（角色卡 / HP / 先攻表）自然延续。
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Literal, Tuple

_PACKAGE_DIR = Path(__file__).resolve().parent
_TESTS_DIR = _PACKAGE_DIR.parent
REPO_ROOT = _TESTS_DIR.parent

for _path in (_TESTS_DIR, _PACKAGE_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import cast  # noqa: E402  （同目录模块：pytest 与独立脚本两种入口都要能 import）
from transcript import Line  # noqa: E402

_BOOTSTRAPPED = False


def bootstrap() -> None:
    """初始化 NoneBot 并加载本插件（幂等；语义同 tests/conftest.py）。"""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("LOCALSTORE_DATA_DIR", str(REPO_ROOT / "data"))

    import nonebot
    from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter

    try:
        driver = nonebot.get_driver()
    except ValueError:
        nonebot.init()
        driver = nonebot.get_driver()
        driver.register_adapter(OnebotV11Adapter)
        nonebot.load_from_toml(str(REPO_ROOT / "pyproject.toml"))

    _BOOTSTRAPPED = True


@dataclass
class Step:
    """时间线的一步：某人发出一段消息。"""

    speaker: str  # cast 名册里的群昵称（如「阿茶」）
    text: str  # 输入原文；`@名字` 会转成真实 at 段
    dice: List[int] = field(default_factory=list)  # 本步消费的骰值（恰好耗尽）
    gate: Literal["real", "bypass"] = "bypass"  # real=走真实群聊服务门禁
    channel: Literal["group", "private"] = "group"  # private=私聊（答复落「屠龙骰（私聊）」）


@dataclass
class Scene:
    """一个场景 = 文档里的一组气泡块（id 即文档引用的场景名）。"""

    id: str
    title: str
    steps: List[Step]


class Recorder:
    """记录骰娘的全部输出（群消息、私聊）与底层 API 调用。"""

    def __init__(self) -> None:
        self.lines: List[Line] = []
        self.api_calls: List[Tuple[str, dict]] = []
        self._message_id = 0

    def next_message_id(self) -> int:
        self._message_id += 1
        return self._message_id

    def group(self, speaker: str, text: str) -> None:
        self.lines.append(Line(speaker, text))

    def private(self, speaker: str, text: str) -> None:
        self.lines.append(Line(speaker, text))


def _format_message(message) -> str:
    """把（可能是富文本的）消息渲染成文档形态：at 段 → ``@昵称``。"""
    from nonebot.adapters.onebot.v11 import Message, MessageSegment

    if isinstance(message, str):
        return message
    if isinstance(message, MessageSegment):
        message = Message(message)

    parts: List[str] = []
    for segment in message:
        if segment.type == "text":
            parts.append(str(segment.data.get("text", "")))
        elif segment.type == "at":
            parts.append("@" + cast.display_for_qq(segment.data.get("qq", "")))
        elif segment.type == "image":
            parts.append("[图片]")
        else:
            parts.append(f"[{segment.type}]")
    return "".join(parts)


def _create_bot_type():
    """构造记录式 Bot 类型（覆盖 send / call_api，全部拦下不联网）。"""
    from nonebot.adapters.onebot.v11 import Bot

    class RecordingBot(Bot):
        async def send(self, event, message, **kwargs):  # type: ignore[override]
            body = _format_message(message)
            if getattr(event, "message_type", "group") == "private":
                self.recorder.private(cast.PRIVATE_BOT_NAME, body)
            else:
                self.recorder.group(cast.BOT_NAME, body)
            return {"message_id": self.recorder.next_message_id()}

        async def call_api(self, api: str, **data):  # type: ignore[override]
            self.recorder.api_calls.append((api, data))
            if api == "send_private_msg":
                self.recorder.private(
                    cast.PRIVATE_BOT_NAME, str(data.get("message", ""))
                )
                return {"message_id": self.recorder.next_message_id()}
            if api == "get_group_member_info":
                return cast.member_info(data.get("user_id", ""))
            # 示例时间线不依赖其他 API；返回空结果即可（真实调用会被记录）
            return {}

    return RecordingBot


class TimelineRunner:
    """在同一示例群内顺序跑时间线；跨步骤状态自然延续。"""

    def __init__(self) -> None:
        bootstrap()

        import nonebot
        from nonebot.adapters.onebot.v11 import Adapter

        self.recorder = Recorder()
        bot_type = _create_bot_type()
        adapter = Adapter(nonebot.get_driver())
        self.bot = bot_type(adapter, self_id=str(cast.BOT_QQ))
        self.bot.recorder = self.recorder  # type: ignore[attr-defined]

    async def reset_group_state(self) -> None:
        """重置示例群状态（服务关闭、清空角色卡 / NPC 血量 / 先攻表 / 群配置 / 查询设置）。

        规则查询场景另装**合成数据源**（见 query_demo.py）与**演示速查索引**
        （见 query_atlas_demo.py）：查询行为真实执行，词条内容为自写演示文本
        （文档页不能转录规则原文）。
        """
        from nonebot_plugin_dnddicer.commands import atlas as atlas_cmd
        from nonebot_plugin_dnddicer.commands import query as query_cmd
        from nonebot_plugin_dnddicer.data import (
            characters,
            group_config,
            initiative,
            npc_health,
            query_settings,
            service_state,
        )
        from nonebot_plugin_dnddicer.query import default_store

        import query_atlas_demo
        import query_demo

        await service_state.set_service_enabled(cast.GROUP_ID, False)
        for persona in cast.PERSONAS:
            await characters.delete_character(cast.GROUP_ID, persona.qq)
        await npc_health.clear_npc_health(cast.GROUP_ID)
        await initiative.clear_init_list(cast.GROUP_ID)
        await group_config.set_group_config_field(cast.GROUP_ID, "default_dice", "D20")
        # 查询：本处设置回到默认（文字、全部书目），候选记录与数据源一并复位
        chat_key = query_settings.group_key(cast.GROUP_ID)
        await query_settings.set_image_enabled(chat_key, False)
        await query_settings.set_scope(chat_key, None)
        default_store.reset()
        query_cmd.set_source(query_demo.build_demo_source())
        # 速查子命令：装入演示索引（条目内置、详情页由假传输返回）
        atlas_cmd.set_store(query_atlas_demo.build_demo_store())

    async def run_scene(self, scene: Scene) -> List[Line]:
        """跑一个场景，返回本场景产生的消息行。"""
        start = len(self.recorder.lines)
        for index, step in enumerate(scene.steps, start=1):
            with self._query_enabled():
                await self.run_step(step, label=f"{scene.id}#{index}")
        return self.recorder.lines[start:]

    @contextmanager
    def _query_enabled(self) -> Iterator[None]:
        """场景执行期间开启规则查询（骰主配置默认关闭）；结束后还原。

        规则查询与图片模式的总开关默认关（零配置可加载）：文档要演示查询行为，
        故在场景内临时打开——单步收敛，不影响其他测试与示例场景。
        """
        from nonebot_plugin_dnddicer.config import get_config

        config = get_config()
        original = config.dnddicer_query_enabled
        config.dnddicer_query_enabled = True
        try:
            yield
        finally:
            config.dnddicer_query_enabled = original

    async def run_step(self, step: Step, *, label: str) -> None:
        """执行一步：记录输入 → 真实分发 → 校验骰值恰好耗尽。"""
        from nonebot_plugin_dnddicer.engine.roll.karma_runtime import (
            reset_runtime,
            set_runtime,
        )
        from nonebot_plugin_dnddicer.engine.roll.sequence_runtime import SequenceRuntime

        persona = cast.BY_NAME[step.speaker]
        message = cast.parse_mentions(step.text)
        # 输入行在分发前记录：onebot v11 入口会剥离「@机器人」段，分发后就看不到了
        self.recorder.group(persona.nickname, _format_message(message))
        event = self._build_event(persona, message, step.channel)

        runtime = SequenceRuntime(step.dice)
        token = set_runtime(runtime)
        try:
            with self._gate(step.gate):
                await self.bot.handle_event(event)
        finally:
            reset_runtime(token)

        remaining = runtime.get_remaining_count()
        if remaining:
            first_line = step.text.splitlines()[0]
            raise AssertionError(
                f"{label}「{first_line}」骰值未耗尽：剩余 {remaining} 个"
                f"（{step.dice[runtime.get_consumed_count():]}）"
            )

    @staticmethod
    def _build_event(persona: cast.Persona, message, channel: str = "group"):
        from nonebot.adapters.onebot.v11.event import Sender

        from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

        sender = Sender(
            card=persona.card_name,
            nickname=persona.qq_nickname,
            role=persona.role,
        )
        if channel == "private":
            return fake_private_message_event_v11(
                self_id=cast.BOT_QQ,
                user_id=persona.qq,
                message=message,
                raw_message=str(message),
                sender=sender,
            )
        return fake_group_message_event_v11(
            self_id=cast.BOT_QQ,
            user_id=persona.qq,
            group_id=cast.GROUP_ID,
            message=message,
            raw_message=str(message),
            sender=sender,
            to_me=False,
        )

    @contextmanager
    def _gate(self, mode: str) -> Iterator[None]:
        """群聊服务门禁：real 走真实状态，bypass 等价「服务已开启」（同 conftest）。"""
        if mode == "real":
            yield
            return

        from nonebot_plugin_dnddicer.data import service_state

        original = service_state.is_service_enabled

        async def _always_enabled(group_id: int | str) -> bool:
            return True

        service_state.is_service_enabled = _always_enabled  # type: ignore[assignment]
        try:
            yield
        finally:
            service_state.is_service_enabled = original  # type: ignore[assignment]
