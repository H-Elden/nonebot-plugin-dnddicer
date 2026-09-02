""".帮助 / .help 命令的 nonebug 测试。"""

import nonebot
import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11

from nonebot_plugin_dnddicer.commands.help import help_matcher


async def _expect(app: App, matcher, event, expected: str):
    """注册期望后投递事件（fake adapter 便于后续扩展）。"""
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


_R_HELP_FULL = (
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

_OVERVIEW = (
    "DNDDicer 可用命令：\n"
    "· .r  掷骰：.r[掷骰表达式]([掷骰原因])\n"
    "· .角色卡  DND5e 角色卡\n"
    "· .状态  查看本角色当前 HP 与生命骰状态。\n"
    "· .dset  设置当前群的默认掷骰表达式\n"
    "· .help  帮助：.help / .帮助"
)


@pytest.mark.asyncio
async def test_help_overview(app: App):
    """无参数 .help：总览含 .r 掷骰与 .help（别名 .帮助 去重不重复列出）。"""
    event = fake_group_message_event_v11(message=Message(".help"))
    await _expect(app, help_matcher, event, _OVERVIEW)


@pytest.mark.asyncio
async def test_help_chinese_alias_overview(app: App):
    """中文别名 .帮助 同样触发。"""
    event = fake_group_message_event_v11(message=Message("。帮助"))
    await _expect(app, help_matcher, event, _OVERVIEW)


@pytest.mark.asyncio
async def test_help_detail(app: App):
    """.help r：显示 .r 完整帮助（含示例行）。"""
    event = fake_group_message_event_v11(message=Message(".help r"))
    await _expect(app, help_matcher, event, _R_HELP_FULL)


@pytest.mark.asyncio
async def test_help_detail_case_insensitive(app: App):
    """.help R（大写）也能查到 .r。"""
    event = fake_group_message_event_v11(message=Message(".help R"))
    await _expect(app, help_matcher, event, _R_HELP_FULL)


@pytest.mark.asyncio
async def test_help_unknown(app: App):
    """未知命令：给出提示。"""
    event = fake_group_message_event_v11(message=Message(".help 不存在"))
    await _expect(app, help_matcher, event, "未找到命令「不存在」。发送 .help 查看全部命令。")
