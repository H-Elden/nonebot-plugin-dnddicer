""".帮助 / .help 命令的 nonebug 测试（2026-09-28 版式重做后）。

覆盖：总览、`命令` 目录（含静默别名）、组名与组别名、命令详情、只进帮助的条目
（检定点 / 豁免 / 武器命令族）、`链接`（含 on/off 开关）、`关于` / `骰主` / `联系`、
未命中；「群聊默认不带文档站链接行、私聊默认带」这一口径；以及链接行的**文档页
深链**（每条回复指向自己的文档页，无对应页回落首页，2026-09-30 批次 A）。
"""

import pytest
from nonebug import App
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter
from nonebot.adapters.onebot.v11 import Bot, Message

from fake_event import fake_group_message_event_v11, fake_private_message_event_v11

from nonebot_plugin_dnddicer.commands import base, help_layout
from nonebot_plugin_dnddicer.commands import text as cmd_text
from nonebot_plugin_dnddicer.commands.help import help_matcher
from nonebot_plugin_dnddicer.version import __version__

#: 文档站首页链接行（无对应文档页的条目回落于此）
_HOME_LINE = f"帮助文档：{cmd_text.TXT_HELP_DOCS_BASE}"


def _doc_line(page: str) -> str:
    """指定文档页的链接行（如 ``guide/hp``）。"""
    return f"帮助文档：{cmd_text.TXT_HELP_DOCS_BASE}/{page}"


async def _expect(app: App, matcher, event, expected: str):
    """注册期望后投递事件（fake adapter 便于后续扩展）。"""
    async with app.test_matcher(matcher) as ctx:
        adapter = ctx.create_adapter(base=OnebotV11Adapter)
        bot = ctx.create_bot(base=Bot, adapter=adapter)
        ctx.should_call_send(event, expected)
        ctx.receive_event(bot, event)


async def _expect_group(app: App, message: str, expected: str):
    """群聊里发一条 .help（默认不带文档站链接行）。"""
    await _expect(
        app, help_matcher, fake_group_message_event_v11(message=Message(message)), expected
    )


async def _expect_private(app: App, message: str, expected: str):
    """私聊里发一条 .help（默认带文档站链接行）。"""
    await _expect(
        app,
        help_matcher,
        fake_private_message_event_v11(message=Message(message)),
        expected,
    )


_LANDING = (
    f"屠龙骰（DNDDicer）v{__version__}\n"
    "DND 5e/5r 跑团专用骰娘~\n"
    "@骰娘 .bot on/off 开关骰娘\n"
    ".help 命令 查看命令分组\n"
    ".help 链接 查看帮助文档\n"
    ".help 关于 查看项目地址\n"
    ".help 骰主 查看骰主指令\n"
    ".help 联系 联系骰主"
)

_CATALOG = (
    "屠龙骰命令一览\n"
    ".help 掷骰 查看掷骰相关命令\n"
    ".help 角色 查看角色卡命令\n"
    ".help 武器 查看武器使用命令\n"
    ".help 生命 查看生命值命令\n"
    ".help 先攻 查看先攻/战斗命令\n"
    ".help 查询 查看规则查询命令\n"
    ".help 管理 查看群管专用命令"
)

_LIFE_GROUP = (
    "【生命值相关命令】\n"
    ".hp　#查看当前生命值\n"
    ".hp 12/12(5)　#记录生命值和临时生命\n"
    ".hp [目标] [表达式]　#给自己或他人加减生命\n"
    ".长休 [@玩家]　#长休结算\n"
    ".npc 持久/临时 名称　#NPC血量跨战斗保持开关"
)

_QUERY_GROUP = (
    "【规则查询命令】\n"
    ".查询法术 <名称>　#法术速查（另有 7 类）\n"
    ".查询 <关键词>　#按名称检索（.q）\n"
    ".搜索 <关键词>　#全文检索（.s / .检索）\n"
    ".查询图片 [on|off]　#本处图片/文字开关\n"
    ".查询范围 [缩写|全部]　#收窄可查书目\n"
    ".规则书　#书目缩写与中文名对照"
)

_R_DETAIL = (
    ".r[标志][表达式] [原因]\n"
    "  掷骰表达式，裸 D 用本群默认骰面\n"
    "  写法：[N#][个数]D面数[优势|劣势][±加值]\n"
    "  .rh 暗骰、.rs 只显数值、4# 连掷、k/kl 取高取低\n"
    "  示例：.r2d6+3 ｜ .rd优势+4"
)

_HP_DETAIL = (
    ".hp [目标] [= / ± / ±表达式] [当前/最大] [(临时)]\n"
    "  记录 / 伤害 / 治疗 / 查看生命值\n"
    "  查看：.hp（自己）、.hp @玩家、.hp list\n"
    "  清理：.hp del 名称（NPC）、.hp clr\n"
    "  武器写法：.hp 地精 -刺剑伤害（可加后缀）"
)

_LINK_ENTRY = (
    "【相关链接】\n"
    f"{_HOME_LINE}\n"
    "5e不全书：https://5echm.kagangtuya.top\n"
    "【相关命令】\n"
    ".help 链接 on/off\n"
    "  help命令关联文档站链接开关"
)

_ABOUT = (
    "屠龙骰（DNDDicer）\n"
    "　　专精 DND 5e/5r 跑团的 NoneBot2 骰娘插件，"
    "致力于做功能最全面、体验最好的 DND 骰娘。\n"
    f"当前版本：v{__version__}\n"
    "项目地址：https://github.com/H-Elden/nonebot-plugin-dnddicer\n"
    "交流反馈：1107879441\n"
    "欢迎进群交流或提Issue，\n"
    "喜欢就点个Star吧！"
)

_MASTER = (
    "以下指令仅限骰主使用\n"
    ".查询索引 [刷新 [类型…]] 速查索引状态与手动刷新"
)

_CONTACT = "通过以下方式联系骰主反馈:\n.master 消息 给骰主发送消息"

_NOT_FOUND = "未找到「不存在」。\n.help 命令 查看命令分组"


# ── 总览 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_landing_group_without_doc_line(app: App):
    """群聊无参数 .help：总览 8 行，默认不带文档站链接行。"""
    await _expect_group(app, ".help", _LANDING)


@pytest.mark.asyncio
async def test_landing_private_with_doc_line(app: App):
    """私聊无参数 .help：默认带文档站链接行（指向《命令总览》）。"""
    await _expect_private(app, ".help", f"{_LANDING}\n{_doc_line('guide/overview')}")


@pytest.mark.asyncio
async def test_landing_chinese_start(app: App):
    """中文起始符与中文别名 .帮助 同样触发总览。"""
    await _expect_group(app, "。帮助", _LANDING)


# ── 命令目录 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("keyword", ["命令", "列表"])
async def test_catalog(app: App, keyword: str):
    """.help 命令：7 组目录（`列表` 为静默别名）。"""
    await _expect_group(app, f".help {keyword}", _CATALOG)


# ── 组清单 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("keyword", ["生命", "血量"])
async def test_group_listing(app: App, keyword: str):
    """.help 生命：该组命令清单（`血量` 为静默别名）。"""
    await _expect_group(app, f".help {keyword}", _LIFE_GROUP)


@pytest.mark.asyncio
async def test_group_takes_precedence_over_command(app: App):
    """.help 查询：组名优先于命令名，给「查询」组清单而不是 .查询 详情。"""
    await _expect_group(app, ".help 查询", _QUERY_GROUP)


@pytest.mark.asyncio
async def test_group_listing_with_doc_line_in_private(app: App):
    """私聊组清单：末尾补文档站链接行（指向该组对应的文档页）。"""
    await _expect_private(app, ".help 生命", f"{_LIFE_GROUP}\n{_doc_line('guide/hp')}")


# ── 文档页深链（批次 A）──────────────────────────────────────────────────


def _reply_body(keyword: str) -> str:
    """取该入口的期望正文（分组清单 / 命令详情 / 只进帮助条目 / 骰主入口）。

    只用于深链用例——正文本身由其它用例逐字断言；这里从注册表与版式表取，
    避免在测试里抄一遍文案（若分派走了别的分支，正文对不上即失败）。
    """
    if keyword == "骰主":
        return cmd_text.TXT_HELP_MASTER
    if help_layout.is_catalog_keyword(keyword):
        return cmd_text.TXT_HELP_CATALOG
    group = help_layout.find_group(keyword)
    if group is not None:
        return "\n".join(group[1])
    for name, description in base.get_registered_commands(include_hidden=True).items():
        if name.lower() == keyword.lower():
            return description
    entry = help_layout.find_help_only(keyword)
    assert entry is not None, f"「{keyword}」既不是分组也不是命令"
    return entry.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("keyword", "page"),
    [
        ("命令", "guide/overview"),
        ("骰主", "guide/query"),
        ("掷骰", "guide/roll-basics"),
        ("角色", "guide/character-card"),
        ("武器", "guide/weapons"),
        ("先攻", "guide/initiative"),
        ("查询", "guide/query"),
        ("管理", "guide/faq"),
        ("dnd", "guide/character-card"),
        ("状态", "guide/hp"),
        ("长休", "guide/hp-advanced"),
        ("npc", "guide/hp"),
        ("ri", "guide/initiative"),
        ("br", "guide/battle"),
        ("查询范围", "guide/query-scope"),
        ("规则书", "guide/query-scope"),
        ("dset", "guide/faq"),
        ("bot", "guide/faq"),
        ("master", "guide/faq"),
        ("查询索引", "guide/query"),
        ("检定", "guide/checks"),
        ("豁免", "guide/checks"),
        ("先攻检定", "guide/initiative"),
        ("刺剑伤害", "guide/weapons"),
    ],
)
async def test_doc_deep_link(app: App, keyword: str, page: str):
    """私聊各入口的链接行指向各自对应的文档页（2026-09-30 定稿的映射）。"""
    await _expect_private(
        app, f".help {keyword}", f"{_reply_body(keyword)}\n{_doc_line(page)}"
    )


@pytest.mark.asyncio
async def test_doc_link_falls_back_to_home():
    """未登记文档页的条目（``doc`` 为空）：链接行回落站点首页。"""
    from nonebot_plugin_dnddicer.commands import help as help_module

    assert help_module._doc_url("") == cmd_text.TXT_HELP_DOCS_BASE
    assert help_module._doc_url("guide/hp") == _doc_line("guide/hp").removeprefix(
        "帮助文档："
    )


# ── 命令详情 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("keyword", ["r", "R"])
async def test_command_detail(app: App, keyword: str):
    """.help r：命令详情（大小写不敏感）。"""
    await _expect_group(app, f".help {keyword}", _R_DETAIL)


@pytest.mark.asyncio
async def test_command_detail_alias(app: App):
    """.help q：走命令别名拿到 .查询 详情（组名优先只针对「查询」这个词本身）。"""
    await _expect_group(app, ".help q", _query_detail())


def _query_detail() -> str:
    """取 .查询 的详情文案（避免在测试里抄一遍）。"""
    from nonebot_plugin_dnddicer.commands import base

    return base.get_registered_commands()["查询"]


@pytest.mark.asyncio
async def test_hidden_command_detail(app: App):
    """.help 查询索引：骰主命令的详情也查得到（清单里不出现）。"""
    from nonebot_plugin_dnddicer.commands import base

    hidden = base.get_registered_commands(include_hidden=True)["查询索引"]
    assert "查询索引" not in base.get_registered_commands()
    await _expect_group(app, ".help 查询索引", hidden)


# ── 只进帮助的条目 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("keyword", ["检定", "力量检定", "敏捷检定优势"])
async def test_help_only_entry(app: App, keyword: str):
    """.help 检定 / .help 力量检定：检定点条目（含包含式匹配）。"""
    from nonebot_plugin_dnddicer.commands import help_layout

    entry = next(e for e in help_layout.HELP_ONLY_ENTRIES if e.name == "检定")
    await _expect_group(app, f".help {keyword}", entry.text)


@pytest.mark.asyncio
async def test_help_only_longest_token(app: App):
    """.help 先攻检定：最长 token 命中先攻检定，而不是被「检定」抢走。"""
    from nonebot_plugin_dnddicer.commands import help_layout

    entry = next(e for e in help_layout.HELP_ONLY_ENTRIES if e.name == "先攻检定")
    await _expect_group(app, ".help 先攻检定", entry.text)


@pytest.mark.asyncio
async def test_help_only_weapon_damage(app: App):
    """.help 刺剑伤害：包含「伤害」→ 武器伤害条目。"""
    from nonebot_plugin_dnddicer.commands import help_layout

    entry = next(e for e in help_layout.HELP_ONLY_ENTRIES if e.name == "武器伤害")
    await _expect_group(app, ".help 刺剑伤害", entry.text)


# ── 链接 / 关于 / 骰主 / 联系 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_link_entry(app: App):
    """.help 链接：相关链接 + 开关用法（自身不受链接开关影响）。"""
    await _expect_group(app, ".help 链接", _LINK_ENTRY)


@pytest.mark.asyncio
async def test_link_switch(app: App):
    """.help 链接 on/off：控制本处帮助回复末尾的文档站链接行（按处持久）。"""
    await _expect_group(app, ".help 链接 on", cmd_text.TXT_HELP_LINK_ON)
    try:
        await _expect_group(app, ".help r", f"{_R_DETAIL}\n{_doc_line('guide/roll-basics')}")
    finally:
        await _expect_group(app, ".help 链接 off", cmd_text.TXT_HELP_LINK_OFF)
    await _expect_group(app, ".help r", _R_DETAIL)


@pytest.mark.asyncio
async def test_link_switch_usage(app: App):
    """`.help 链接 xyz`：给用法与当前状态（群聊默认关闭）。"""
    await _expect_group(
        app, ".help 链接 xyz", cmd_text.TXT_HELP_LINK_USAGE.format(state="关闭")
    )


@pytest.mark.asyncio
async def test_about(app: App):
    """.help 关于：版本、项目地址与交流群（自身不带文档站链接行）。"""
    await _expect_group(app, ".help 关于", _ABOUT)


@pytest.mark.asyncio
async def test_master_commands(app: App):
    """.help 骰主：骰主专用指令清单。"""
    await _expect_group(app, ".help 骰主", _MASTER)


@pytest.mark.asyncio
async def test_contact_without_config(app: App):
    """.help 联系：未配置骰主联系方式 / 交流群时不显示这两行。"""
    await _expect_group(app, ".help 联系", _CONTACT)


def _patch_master_config(
    monkeypatch: pytest.MonkeyPatch, **fields: str
) -> None:
    """把插件配置替换为带指定骰主字段的真实 ``Config`` 实例。"""
    from nonebot_plugin_dnddicer import config as config_module

    monkeypatch.setattr(
        config_module, "get_config", lambda: config_module.Config(**fields)
    )


@pytest.mark.asyncio
async def test_contact_with_contact_only(app: App, monkeypatch: pytest.MonkeyPatch):
    """.help 联系：只配联系方式时只多一行。"""
    _patch_master_config(monkeypatch, dnddicer_master_contact="QQ 12345678")
    await _expect_group(app, ".help 联系", f"{_CONTACT}\n骰主联系方式：QQ 12345678")


@pytest.mark.asyncio
async def test_contact_with_group_only(app: App, monkeypatch: pytest.MonkeyPatch):
    """.help 联系：只配交流群时只多一行。"""
    _patch_master_config(monkeypatch, dnddicer_master_group="87654321")
    await _expect_group(app, ".help 联系", f"{_CONTACT}\n骰主交流群：87654321")


@pytest.mark.asyncio
async def test_contact_with_config(app: App, monkeypatch: pytest.MonkeyPatch):
    """.help 联系：两项都配时两行齐全，顺序固定（联系方式 → 交流群）。"""
    _patch_master_config(
        monkeypatch,
        dnddicer_master_contact="QQ 12345678",
        dnddicer_master_group="87654321",
    )
    await _expect_group(
        app,
        ".help 联系",
        f"{_CONTACT}\n骰主联系方式：QQ 12345678\n骰主交流群：87654321",
    )


@pytest.mark.asyncio
async def test_contact_hides_master_qq(app: App, monkeypatch: pytest.MonkeyPatch):
    """.help 联系：只配骰主 QQ 不因此多出行（QQ 是投递地址，不外显）。"""
    _patch_master_config(monkeypatch, dnddicer_master_qq="10001")
    await _expect_group(app, ".help 联系", _CONTACT)


def test_master_config_fields_default_empty() -> None:
    """三个骰主配置项存在且默认均为空（零配置可加载）。"""
    from nonebot_plugin_dnddicer.config import Config

    config = Config()
    assert config.dnddicer_master_qq == ""
    assert config.dnddicer_master_contact == ""
    assert config.dnddicer_master_group == ""


# ── 未命中 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown(app: App):
    """未命中：一行提示 + 指向 .help 命令。"""
    await _expect_group(app, ".help 不存在", _NOT_FOUND)
