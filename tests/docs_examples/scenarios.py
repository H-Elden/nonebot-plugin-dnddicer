"""示例时间线：按剧情顺序排列的场景（文档示例的唯一来源）。

- 一个 ``Scene`` 对应站点里一组 `::: chat` 气泡块，``Scene.id`` 即文档引用的场景名；
- 骰值必须写死（SequenceRuntime）：该出 20/1 的示例就写 20/1，保证可复现；
- 时间线在同一示例群内顺序执行，跨场景状态自然延续——各页示例都取自这条时间线。
"""

from __future__ import annotations

import cast
from harness import Scene, Step

# ── 第一幕：开团之前 ──────────────────────────────────────────────────────

quickstart_bot_on = Scene(
    id="quickstart_bot_on",
    title="群主开启本群服务（白名单，走真实门禁）",
    steps=[
        Step("白鸦", "@屠龙骰 .bot on", gate="real"),
    ],
)

quickstart_bot_info = Scene(
    id="quickstart_bot_info",
    title="查看插件信息与本群服务状态",
    steps=[
        Step("白鸦", "@屠龙骰 .bot", gate="real"),
    ],
)

cast_setup = Scene(
    id="cast_setup",
    title="建卡：四名玩家登记角色卡",
    steps=[
        # 注：记录卡片时，带数值的 `$额外加值$` 会被引擎实际求值一次做语法校验
        #（`D20+<取值>`，校验掷骰不出现在输出里）——薇拉与布鲁姆各消费 1 颗 d20；
        # 纯「优势/劣势」前缀（塔莉）与无额外加值（洛恩）不消费骰值。
        Step("阿茶", f".角色卡记录\n{cast.CARDS['薇拉']}", dice=[10]),
        Step("小满", f".角色卡记录\n{cast.CARDS['洛恩']}"),
        Step("老猫", f".角色卡记录\n{cast.CARDS['塔莉']}"),
        Step("阿岩", f".角色卡记录\n{cast.CARDS['布鲁姆']}", dice=[10]),
    ],
)

quickstart_first_roll = Scene(
    id="quickstart_first_roll",
    title="第一条命令：掷骰",
    steps=[
        Step("阿茶", ".r2d6+3", dice=[5, 2]),
        Step("阿茶", ".rd", dice=[20]),
    ],
)

# ── 第二幕：旅店试骰（掷骰基础 / 掷骰进阶） ────────────────────────────────

roll_basics_basic = Scene(
    id="roll_basics_basic",
    title="试骰：基础表达式",
    steps=[
        Step("老猫", ".r3d8", dice=[3, 5, 1]),
        Step("阿茶", ".rd+5", dice=[10]),
    ],
)

roll_basics_plain_d = Scene(
    id="roll_basics_plain_d",
    title="省略面数：裸 d 按默认骰面掷",
    steps=[
        Step("老猫", ".rd", dice=[17]),
        Step("老猫", ".r2d+1", dice=[9, 14]),
    ],
)

roll_basics_math = Scene(
    id="roll_basics_math",
    title="运算与括号",
    steps=[
        Step("小满", ".r(d6+2)*2", dice=[4]),
        Step("小满", ".r2d6-1", dice=[3, 4]),
    ],
)

roll_basics_space_error = Scene(
    id="roll_basics_space_error",
    title="常见错误：表达式里多打空格会被当成原因",
    steps=[
        Step("阿茶", ".r3d8", dice=[2, 6, 4]),
        Step("阿茶", ".r3d 8", dice=[11, 3, 19]),
    ],
)

roll_basics_crit_20 = Scene(
    id="roll_basics_crit_20",
    title="大成功（仅 d20 播报）",
    steps=[
        Step("阿岩", ".rd+4", dice=[20]),
        Step("老猫", ".r2d6", dice=[6, 6]),
    ],
)

roll_basics_crit_1 = Scene(
    id="roll_basics_crit_1",
    title="大失败",
    steps=[
        Step("小满", ".rd", dice=[1]),
    ],
)

roll_adv_adv = Scene(
    id="roll_adv_adv",
    title="优势：两次取高",
    steps=[
        Step("老猫", ".rd优势", dice=[3, 15]),
    ],
)

roll_adv_dis = Scene(
    id="roll_adv_dis",
    title="劣势：两次取低",
    steps=[
        Step("阿岩", ".rd劣势", dice=[20, 1]),
    ],
)

roll_adv_order_error = Scene(
    id="roll_adv_order_error",
    title="书写顺序：面数写在优势/劣势之前",
    steps=[
        Step("老猫", ".rd劣势+6", dice=[15, 4]),
        Step("老猫", ".rd劣势20+6"),
    ],
)

roll_adv_keep = Scene(
    id="roll_adv_keep",
    title="取高与取低（k / kh）",
    steps=[
        Step("小满", ".r4d6k3", dice=[1, 4, 2, 6]),
        Step("小满", ".r2dkh1", dice=[7, 18]),
    ],
)

roll_adv_modifiers = Scene(
    id="roll_adv_modifiers",
    title="骰子修饰符：重掷 / 爆炸 / 最小值 / 成功计数 / 预兆 / 命运",
    steps=[
        Step("老猫", ".r2d6r1+3", dice=[1, 5, 3]),
        Step("小满", ".rd6x6", dice=[6, 3]),
        Step("小满", ".rd6xo6", dice=[6, 3]),
        Step("阿岩", ".rd6m2", dice=[1]),
        Step("老猫", ".r2d6cs>=5", dice=[5, 2]),
        Step("小满", ".rdp10", dice=[10]),
        Step("小满", ".rdf", dice=[5]),
    ],
)

roll_adv_resist = Scene(
    id="roll_adv_resist",
    title="抗性与易伤：总和减半 / 加倍",
    steps=[
        Step("白鸦", ".rd12+2d8+5抗性", dice=[8, 3, 6]),
        Step("白鸦", ".r2d6易伤", dice=[4, 2]),
    ],
)

roll_adv_multi = Scene(
    id="roll_adv_multi",
    title="连掷 3#",
    steps=[
        Step("老猫", ".r3#2d6", dice=[5, 3, 4, 2, 6, 1]),
    ],
)

roll_adv_summary = Scene(
    id="roll_adv_summary",
    title="连掷里的大成功汇总播报",
    steps=[
        Step("老猫", ".r2#d", dice=[20, 1]),
    ],
)

roll_adv_short = Scene(
    id="roll_adv_short",
    title="只显数值 s",
    steps=[
        Step("小满", ".rs2d6+3", dice=[3, 4]),
        Step("小满", ".rs2#d6", dice=[5, 2]),
    ],
)

roll_adv_dark = Scene(
    id="roll_adv_dark",
    title="暗骰：群内只见提示，结果走私聊",
    steps=[
        Step("老猫", ".rhd+5 潜行", dice=[12]),
    ],
)

roll_adv_reason = Scene(
    id="roll_adv_reason",
    title="带原因的掷骰",
    steps=[
        Step("阿茶", ".rd+2 力量检定", dice=[15]),
        Step("白鸦", ".rd8+3 哥布林弯刀", dice=[6]),
    ],
)

roll_adv_unimpl = Scene(
    id="roll_adv_unimpl",
    title="显式提示未实现的语法",
    steps=[
        Step("小满", ".rexp3d6"),
        Step("小满", ".ra3d6"),
    ],
)

# ── 第三幕：碎星隘口遭遇战（先攻列表） ──────────────────────────────────────

init_player_roll = Scene(
    id="init_player_roll",
    title="玩家掷先攻",
    steps=[
        Step("阿茶", ".ri", dice=[7]),
        Step("老猫", ".ri+7", dice=[10]),
    ],
)

init_npc_fixed = Scene(
    id="init_npc_fixed",
    title="DM 用固定值把怪物入表",
    steps=[
        Step("白鸦", ".ri20 熊地精"),
    ],
)

init_batch_split = Scene(
    id="init_batch_split",
    title="斜杠多项：各自独立掷",
    steps=[
        Step("白鸦", ".ri+1 向导/狼", dice=[11, 5]),
    ],
)

init_batch_shared = Scene(
    id="init_batch_shared",
    title="批量派生：3# 哥布林 a/b/c",
    steps=[
        Step("白鸦", ".ri-1 3#哥布林", dice=[14, 6, 3]),
    ],
)

init_view = Scene(
    id="init_view",
    title="查看先攻列表",
    steps=[
        Step("白鸦", ".init"),
    ],
)

init_dup_roll = Scene(
    id="init_dup_roll",
    title="重掷替换与相同先攻值提示",
    steps=[
        Step("白鸦", ".ri17 熊地精"),
    ],
)

init_first = Scene(
    id="init_first",
    title="相同先攻值决定先后",
    steps=[
        Step("白鸦", ".init first 塔莉"),
    ],
)

init_swap = Scene(
    id="init_swap",
    title="互换两个条目的先攻值",
    steps=[
        Step("白鸦", ".init swap 薇拉/狼"),
    ],
)

init_del_ambiguous = Scene(
    id="init_del_ambiguous",
    title="删除：歧义提示与批量写法",
    steps=[
        Step("白鸦", ".init del 哥布林"),
        # 部分匹配演示：a → 哥布林a（唯一命中）、布林b → 哥布林b、哥布林c 写全名
        Step("白鸦", ".init del a/布林b/哥布林c"),
    ],
)

init_name_roll = Scene(
    id="init_name_roll",
    title="按名称代掷：字面入表、不模糊匹配、不与玩家绑定",
    steps=[
        # 名称一律按字面处理：写「洛」不会匹配到「洛恩」，而是建出一个叫「洛」的条目
        Step("白鸦", ".ri+2 洛", dice=[7]),
        Step("白鸦", ".init del 洛"),
        # 写全名只是「与角色卡同名的条目」——不与玩家绑定，@ 按归属定位不到它
        Step("白鸦", ".ri+2 洛恩", dice=[3]),
        Step("白鸦", ".init del @小满"),
        Step("白鸦", ".init del 洛恩"),
    ],
)

init_mention_roll = Scene(
    id="init_mention_roll",
    title="DM 用 @ 代掷（条目取角色卡名并绑定）",
    steps=[
        Step("白鸦", ".ri+2 @小满", dice=[7]),
    ],
)

init_check_link = Scene(
    id="init_check_link",
    title=".先攻检定：读角色卡并直接入表",
    steps=[
        Step("阿岩", ".先攻检定", dice=[16]),
    ],
)

init_view_final = Scene(
    id="init_view_final",
    title="战斗就绪：完整先攻列表",
    steps=[
        Step("白鸦", ".init"),
    ],
)

#: 时间线末尾：群主关闭本群服务（演示收尾）。
#: 该场景必须压轴——服务关闭后本群不再响应其他命令；补新场景时请插在它之前。
quickstart_bot_off = Scene(
    id="quickstart_bot_off",
    title="群主关闭本群服务",
    steps=[
        Step("白鸦", "@屠龙骰 .bot off", gate="real"),
    ],
)

#: 时间线（顺序执行；后续按页补场景，注意保持剧情顺序）
TIMELINE = [
    quickstart_bot_on,
    quickstart_bot_info,
    cast_setup,
    quickstart_first_roll,
    # 第二幕：旅店试骰（掷骰基础 / 掷骰进阶）
    roll_basics_basic,
    roll_basics_plain_d,
    roll_basics_math,
    roll_basics_space_error,
    roll_basics_crit_20,
    roll_basics_crit_1,
    roll_adv_adv,
    roll_adv_dis,
    roll_adv_order_error,
    roll_adv_keep,
    roll_adv_modifiers,
    roll_adv_resist,
    roll_adv_multi,
    roll_adv_summary,
    roll_adv_short,
    roll_adv_dark,
    roll_adv_reason,
    roll_adv_unimpl,
    # 第三幕：碎星隘口遭遇战（先攻列表）
    init_player_roll,
    init_npc_fixed,
    init_batch_split,
    init_batch_shared,
    init_view,
    init_dup_roll,
    init_first,
    init_swap,
    init_del_ambiguous,
    init_name_roll,
    init_mention_roll,
    init_check_link,
    init_view_final,
    quickstart_bot_off,  # 压轴：服务关闭后本群不再响应其他命令
]
