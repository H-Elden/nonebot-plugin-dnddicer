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
        Step("阿茶", ".r 2d6+3", dice=[5, 2]),
        Step("阿茶", ".r d20", dice=[20]),
    ],
)

#: 时间线（顺序执行；后续按页补场景，注意保持剧情顺序）
TIMELINE = [
    quickstart_bot_on,
    cast_setup,
    quickstart_first_roll,
]
