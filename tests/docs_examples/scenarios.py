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

# ── 第三幕之前：出发整备（角色卡与属性） ────────────────────────────────────

char_template = Scene(
    id="char_template",
    title="查看示例模板（小鹿问怎么建卡）",
    steps=[
        Step("小鹿", ".角色卡模板"),
    ],
)

char_view_self = Scene(
    id="char_view_self",
    title="查看自己的角色卡",
    steps=[
        Step("阿茶", ".角色卡"),
        Step("老猫", ".状态"),
    ],
)

char_view_other = Scene(
    id="char_view_other",
    title="查看他人：@ 玩家 / 角色名两种写法",
    steps=[
        Step("白鸦", ".角色卡 @阿茶"),
        Step("白鸦", ".角色卡 洛恩"),
        Step("白鸦", ".状态 @小满"),
    ],
)

hp_set = Scene(
    id="hp_set",
    title="记录与查看血量（无卡成员也能记录）",
    steps=[
        Step("小鹿", ".hp 20/30"),
        Step("小鹿", ".hp"),
    ],
)

dnd_roll = Scene(
    id="dnd_roll",
    title="掷点法：只出数值（.dnd）与多次带原因",
    steps=[
        Step("白鸦", ".dnd", dice=[6, 6, 6, 1, 5, 5, 4, 2, 5, 4, 4, 3,
                                   4, 4, 3, 2, 3, 3, 2, 1, 5, 3, 2, 1]),
        Step("白鸦", ".dnd2 替补", dice=[
            4, 4, 4, 2, 6, 6, 5, 1, 5, 4, 4, 4, 3, 3, 1, 1, 6, 5, 3, 2, 4, 2, 1, 1,
            5, 5, 5, 5, 6, 6, 6, 2, 5, 5, 4, 3, 4, 3, 2, 2, 3, 3, 2, 1, 6, 4, 2, 1,
        ]),
    ],
)

dndx_record = Scene(
    id="dndx_record",
    title="掷点法：绑定属性名（.dndx）并抄进角色卡",
    steps=[
        # 小鹿 试掷一张卡：.dndx 的顺序与 $属性$ 行一致，按序抄写即可
        Step("小鹿", ".dndx", dice=[4, 3, 2, 1, 6, 5, 4, 3, 5, 5, 5, 2,
                                    6, 6, 3, 2, 4, 4, 4, 1, 3, 3, 3, 3]),
        Step("小鹿", (
            ".角色卡记录\n"
            "$姓名$ 小鹿\n"
            "$等级$ 1\n"
            "$生命值$ 8/8\n"
            "$属性$ 9/15/15/15/12/9"
        )),
        Step("小鹿", ".角色卡"),
        Step("小鹿", ".角色卡清除"),
    ],
)

char_record_error = Scene(
    id="char_record_error",
    title="记录失败：漏必填、属性个数不对、额外加值少冒号",
    steps=[
        Step("小鹿", ".角色卡记录\n$姓名$ 小鹿\n$属性$ 10/10/10/10/10/10"),
        Step("小鹿", ".角色卡记录\n$等级$ 1\n$属性$ 10/10/10"),
        Step("小鹿", (
            ".角色卡记录\n"
            "$等级$ 1\n"
            "$属性$ 10/10/10/10/10/10\n"
            "$额外加值$ 敏捷攻击+1d4"
        )),
    ],
)

# ── 探路检定（检定与豁免） ────────────────────────────────────────────────

check_skill_expertise = Scene(
    id="check_skill_expertise",
    title="技能检定：专精与卡上自带优势（塔莉 隐匿）",
    steps=[
        Step("老猫", ".隐匿检定", dice=[15, 4]),
    ],
)

check_cancel = Scene(
    id="check_cancel",
    title="命令侧的临时优劣势：两个优势 / 优劣抵消",
    steps=[
        # 塔莉的卡自带「隐匿:优势」——再给一次优势不叠加（仍是一颗优势骰），
        # 给一次劣势则与卡上优势抵消、回到普通掷。
        Step("老猫", ".隐匿检定优势", dice=[13, 7]),
        Step("老猫", ".隐匿检定劣势", dice=[9]),
    ],
)

check_attr = Scene(
    id="check_attr",
    title="属性检定：无熟练加值（布鲁姆 感知）",
    steps=[
        Step("阿岩", ".感知检定", dice=[12]),
    ],
)

check_save_bonus = Scene(
    id="check_save_bonus",
    title="豁免检定：卡上的「豁免:+1」也进算式（布鲁姆 感知豁免）",
    steps=[
        Step("阿岩", ".感知豁免", dice=[11]),
    ],
)

check_crit_fail = Scene(
    id="check_crit_fail",
    title="大失败：检定同样播报（布鲁姆 力量检定）",
    steps=[
        Step("阿岩", ".力量检定", dice=[1]),
    ],
)

check_multi = Scene(
    id="check_multi",
    title="连掷 N#：逐次独立、逐次显示",
    steps=[
        Step("小满", ".2#察觉检定", dice=[15, 3]),
    ],
)

check_mention = Scene(
    id="check_mention",
    title="DM 代掷：表达式右侧 @玩家",
    steps=[
        Step("白鸦", ".敏捷攻击 @小满", dice=[13]),
    ],
)

check_no_card = Scene(
    id="check_no_card",
    title="无角色卡时的引导（小鹿）",
    steps=[
        Step("小鹿", ".敏捷检定"),
    ],
)

# ── 第三幕：碎星隘口遭遇战（先攻列表） ──────────────────────────────────────

battle_open = Scene(
    id="battle_open",
    title="开局：先 .br 新建战斗轮，再掷先攻入表",
    steps=[
        Step("白鸦", ".br"),
    ],
)

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

# ── 第四幕：战斗推进（战斗轮 / HP 与长休） ──────────────────────────────────

battle_round1 = Scene(
    id="battle_round1",
    title="第一轮：查回合、攻击、伤害、治疗与临时 HP",
    steps=[
        Step("白鸦", ".回合"),
        # 怪物血量：DM 先记录上限（公开 HP:x/y）
        Step("白鸦", ".hp 熊地精 27/27"),
        Step("老猫", ".敏捷攻击+1d4", dice=[20, 3]),   # 临时的祝福术 +1d4
        Step("白鸦", ".hp 熊地精 -d8+4", dice=[6]),
        Step("老猫", ".ed"),
        # 熊地精 的回合：晨星加上侧翼的冷箭，一发合并结算
        Step("白鸦", ".hp 薇拉 -d8+3+d6", dice=[7, 4]),
        Step("白鸦", ".ed"),
        Step("阿岩", ".hp 薇拉 +2d8+4", dice=[3, 4]),
        Step("阿岩", ".ed"),
        Step("白鸦", ".ed"),
        Step("小满", ".hp (10)"),                      # 临时的虚假生命
        Step("小满", ".ed"),
        Step("白鸦", ".hp 洛恩 -13"),                  # 临时 HP 先吸收
        Step("白鸦", ".ed"),
        Step("阿茶", ".ed"),                           # 一轮走完，自动进位
    ],
)

hp_expr_paren = Scene(
    id="hp_expr_paren",
    title="伤害表达式的语义：-8-5 / -(8+5) / -8+5",
    steps=[
        # 操作符后的整段是一个表达式：「-8-5」只扣 8-5=3，不是「先扣 8 再扣 5」
        Step("白鸦", ".hp 薇拉 -8-5"),
        # 尾括号在 .hp 里是**临时 HP 槽位**（.hp (10)）：这一发被当成「减少临时
        # HP」，HP 纹丝不动、也不会报错
        Step("白鸦", ".hp 薇拉 -(8+5)"),
        # 要让 8 和 5 都算伤害：- 已代表扣血，其后接整段算式
        Step("白鸦", ".hp 薇拉 -8+5"),
    ],
)

battle_guide_hit = Scene(
    id="battle_guide_hit",
    title="NPC 队友记录血量并受伤（向导）",
    steps=[
        Step("白鸦", ".hp 向导 22/22"),
        Step("白鸦", ".hp 向导 -8"),
    ],
)

battle_zero_down = Scene(
    id="battle_zero_down",
    title="倒地与唤醒（薇拉）",
    steps=[
        # DM 直接结算一记致命伤害（数值由 DM 按桌面裁定输入），正好打到 0
        Step("白鸦", ".hp 薇拉 -51"),
        Step("阿岩", ".hp 薇拉 +15"),
    ],
)

battle_reinforce = Scene(
    id="battle_reinforce",
    title="增援：战斗中把新敌人入表并记录血量",
    steps=[
        Step("白鸦", ".ri+1 2#哥布林", dice=[12, 4]),
        Step("白鸦", ".hp 哥布林a 7/7"),
        Step("白鸦", ".hp 哥布林b 7/7"),
        Step("阿茶", ".力量攻击", dice=[11]),          # 薇拉 迎击（含长剑 +1）
        Step("白鸦", ".hp 哥布林b -d8+4", dice=[2]),
    ],
)

hp_target_search = Scene(
    id="hp_target_search",
    title="目标怎么找：部分匹配、歧义、找不到与 @ 指定",
    steps=[
        Step("白鸦", ".hp 熊 -8"),            # 简称命中「熊地精」
        Step("白鸦", ".hp 大魔头 -8"),         # 找不到 + 新 NPC 提示
        Step("白鸦", ".hp 哥布林 -8"),         # 命中两只 → 歧义
        Step("白鸦", ".hp @小满 -2d6", dice=[4, 3]),
        Step("白鸦", ".hp -d6 @小满"),         # 游离 @：不执行并回纠正示例
    ],
)

battle_aoe = Scene(
    id="battle_aoe",
    title="AOE 一发多目标（洛恩的火球术）",
    steps=[
        # 哥布林a 有公开血量、狼只有受损记录——一发两种读数
        Step("白鸦", ".hp 哥布林a;狼 -8d6",
             dice=[3, 5, 2, 6, 4, 1, 5, 3]),
    ],
)

battle_tower = Scene(
    id="battle_tower",
    title="哨塔亡灵：只记损失 / 抗性与易伤",
    steps=[
        Step("白鸦", ".ri18 骷髅"),
        Step("白鸦", ".hp 布鲁姆抗性 -2d6", dice=[5, 3]),  # 毒雾：矮人的毒素抗性
        # 初见之敌：不设上限、只记损失（读数是「掉了多少」而非「还剩多少」）
        Step("老猫", ".敏捷攻击", dice=[13]),          # 塔莉的匕首
        Step("白鸦", ".hp 骷髅 -d8+4", dice=[5]),
        Step("阿岩", ".力量攻击", dice=[14]),          # 战锤
        Step("白鸦", ".hp 骷髅易伤 -d8+2", dice=[6]),  # 钝击易伤加倍
    ],
)

hp_resist_forms = Scene(
    id="hp_resist_forms",
    title="抗性与易伤：AOE 逐目标声明 / 表达式内后缀",
    steps=[
        # 一发多目标：每个目标各挂各的承伤后缀（; 全角 / 半角皆可）
        Step("白鸦", ".hp 布鲁姆抗性；洛恩 -2d6", dice=[5, 3]),
        Step("白鸦", ".hp 布鲁姆抗性;洛恩易伤 -2d6", dice=[5, 3]),
        # 引擎也认写在表达式里的后缀（整段算式减半）——读作 [5+3]/2=4
        Step("白鸦", ".hp 布鲁姆 -2d6抗性", dice=[5, 3]),
    ],
)

battle_shield = Scene(
    id="battle_shield",
    title="洛恩补上一层虚假生命（临时 HP 留到长休）",
    steps=[
        Step("小满", ".hp (10)"),
    ],
)

battle_adjust = Scene(
    id="battle_adjust",
    title="DM 手动调整回合与轮次",
    steps=[
        Step("白鸦", ".回合-1"),
        Step("白鸦", ".回合 熊地精"),
        Step("白鸦", ".回合 @小满"),
        Step("白鸦", ".回合+2"),
        Step("白鸦", ".轮次+1"),
    ],
)

battle_errors = Scene(
    id="battle_errors",
    title="战斗轮的常见提示",
    steps=[
        Step("白鸦", ".回合=99"),
        Step("白鸦", ".回合=0"),
        Step("白鸦", ".回合+abc"),
        Step("白鸦", ".回合 不存在的东西"),
        Step("白鸦", ".回合 哥布林"),
    ],
)

# ── 第五幕：战后与收尾（HP 与长休 / 清理） ──────────────────────────────────

rest_after = Scene(
    id="rest_after",
    title="长休：本人收尾与 DM 代收尾",
    steps=[
        Step("阿茶", ".长休"),
        Step("白鸦", ".长休 @小满"),
    ],
)

npc_persist = Scene(
    id="npc_persist",
    title="为向导标记跨战斗保持血量",
    steps=[
        Step("白鸦", ".npc 持久 向导"),
    ],
)

npc_refill_next = Scene(
    id="npc_refill_next",
    title="下一场遭遇：同名 NPC 自动回满、持久 NPC 保持",
    steps=[
        Step("白鸦", ".br"),
        Step("白鸦", ".ri-1 哥布林b", dice=[4]),      # 新个体：自动回满
        Step("白鸦", ".ri+1 向导", dice=[9]),          # 持久：保持 14/22
        Step("白鸦", ".init"),
    ],
)

battle_cleanup = Scene(
    id="battle_cleanup",
    title="清空先攻表与空表提示",
    steps=[
        Step("白鸦", ".init clr"),
        Step("白鸦", ".回合"),
        Step("白鸦", ".ed"),
    ],
)

hp_cleanup = Scene(
    id="hp_cleanup",
    title="查看列表与清理 NPC 血量记录",
    steps=[
        Step("白鸦", ".hp list"),
        Step("白鸦", ".hp del 哥布林a"),
        Step("白鸦", ".hp clr"),
        Step("白鸦", ".hp list"),
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
    # 第三幕之前：出发整备（角色卡与属性 / 检定与豁免）
    char_template,
    char_view_self,
    char_view_other,
    hp_set,
    dnd_roll,
    dndx_record,
    char_record_error,
    check_skill_expertise,
    check_cancel,
    check_attr,
    check_save_bonus,
    check_crit_fail,
    check_multi,
    check_mention,
    check_no_card,
    # 第三幕：碎星隘口遭遇战（先攻列表）
    battle_open,
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
    # 第四幕：战斗推进（战斗轮 / HP 与长休）
    battle_round1,
    hp_expr_paren,
    battle_guide_hit,
    battle_zero_down,
    battle_reinforce,
    hp_target_search,
    battle_aoe,
    battle_tower,
    hp_resist_forms,
    battle_shield,
    battle_adjust,
    battle_errors,
    # 第五幕：战后与收尾
    rest_after,
    npc_persist,
    npc_refill_next,
    battle_cleanup,
    hp_cleanup,
    quickstart_bot_off,  # 压轴：服务关闭后本群不再响应其他命令
]
