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
    "屠龙骰可用命令：\n"
    "· .r  掷骰：.r[掷骰表达式]([掷骰原因])\n"
    "· .角色卡  DND5e 角色卡\n"
    "· .状态  查看本角色当前 HP 与生命骰状态。\n"
    "· .设置武器  设置/修改自定义武器（供 .X攻击 / .X命中 / .X伤害 使用）：\n"
    "· .删除武器  删除自定义武器：.删除武器 短剑（多个用 / 分隔）\n"
    "· .dnd  DND5e 属性生成（4D6K3 掷点）\n"
    "· .dndx  DND5e 属性生成（4D6K3 掷点，属性名绑定）\n"
    "· .dset  设置当前群的默认掷骰表达式\n"
    "· .hp  设置生命值: .hp [对象] [=, 或空格] [当前生命值/最大生命值] [(临时生命值)]\n"
    "· .长休  进行一次长休：恢复生命值至上限、清除临时生命值、回复一半生命骰。\n"
    "· .npc  NPC血量跨战斗保持开关（按名称，作用于一整条NPC血量记录）\n"
    "· .init  显示先攻列表：.init ([可选指令]) [可选指令]:clr 清空先攻列表 del 删除指定先攻条目 first/fst 提前同值条目 swap 交换两个条目\n"
    "· .ri  投掷先攻：.ri([优劣势][加值]) ([名称][/(名称)...])\n"
    "· .br  .br 或 .战斗轮 开始新的战斗轮\n"
    "· .turn  查看或修改当前回合：.回合 / .回合+1 / .回合-1 / .回合=2 / .回合 名字 / .回合 @玩家\n"
    "· .round  查看或修改当前轮次：.轮次 / .轮次+1 / .轮次-1 / .轮次=3\n"
    "· .ed  结束当前回合，自动推进到下一位并播报；一轮走完自动进入下一轮。\n"
    "· .查询  规则查询：.查询 <关键词>（.q）\n"
    "· .搜索  全文检索：.搜索 <关键词>（.s / .检索）\n"
    "· .查询图片  查询图片显示：.查询图片（.qimg）\n"
    "· .查询范围  查询范围：.查询范围（.qscope）\n"
    "· .规则书  可查询书目：.规则书（.qbooks）\n"
    "· .bot  查看插件信息或开关本群服务：.bot on / .bot off（仅群聊，需群主或管理员权限）\n"
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
