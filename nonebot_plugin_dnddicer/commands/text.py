"""掷骰命令反馈文案与状态文案逻辑。

默认文案对齐 nonebot-dicepp ``roll_dice_command.py`` 中 ``register_loc_text``
注册的默认文本（2026-09，DicePP commit 732ff74 / v3.0.0rc23），保证手感一致；
DicePP 的本地化扩展机制不在本插件范围（不迁移其 loc 体系），文案集中于此便于
日后对照上游校对。
"""

from __future__ import annotations

from typing import List

from ..engine.roll.result import RollResult

# ── 掷骰结果模板（{nickname}/{reason}/{final}/{state} 由命令层填充）─────────
TXT_RESULT = "{nickname} 的掷骰结果为 {final} {state}"
TXT_RESULT_REASON = "{nickname} 为 {reason} 进行的掷骰结果为 {final} {state}"
TXT_HIDE_RESULT = "{nickname} 的暗骰结果为 {final} {state}"
TXT_HIDE_RESULT_REASON = "{nickname} 为 {reason} 进行的暗骰结果为 {final} {state}"
TXT_HIDE_GROUP = "{nickname} 进行了一次暗骰"

#: 多次掷骰（#连掷）的最终结果块格式
TXT_MULTI = "{time}次 {exp}: [{result}]"

# ── 唯一 d20 的大成功 / 大失败 / 档位反馈（替换模板中的 {state}）────────────
TXT_D20_SUCCESS = "好耶！大成功!"
TXT_D20_FAILURE = "哇哦！大失败!"
TXT_D20_SUCCESS_SHORT = "大成功"
TXT_D20_FAILURE_SHORT = "大失败"
TXT_D20_MULTI = "{time}次 {short}"
# 唯一 d20、无大成功/大失败时的分档反馈（DicePP 默认全空，即不追加任何文字）
TXT_D20_2 = ""          # 平均出目档 <10%（即骰面约 1~2）
TXT_D20_3_5 = ""        # <25%
TXT_D20_6_10 = ""       # <50%
TXT_D20_11_15 = ""      # <75%
TXT_D20_16_18 = ""      # <90%
TXT_D20_19 = ""         # <=100%

# ── 范围外功能占位文案（第一期未实现，先显式提示而非静默）────────────────────
TXT_EXP_UNIMPLEMENTED = "「期望值计算」(.r exp) 尚未实现，敬请期待。"
TXT_SPECIAL_MODE_UNIMPLEMENTED = "该掷骰模式（{mode}）尚未实现，敬请期待。"
TXT_NOT_IMPLEMENTED = "该功能尚未实现，敬请期待。"

# ── 群默认骰面 .dset（对齐 DicePP dice_set_command 默认文案）───────────────
TXT_DSET_SUCCESS = "本群默认掷骰表达式已改为{expr}。"
TXT_DSET_INVALID = "默认掷骰表达式无效：{reason}"
TXT_DSET_CURRENT = "当前默认掷骰表达式为{expr}。使用 .dset [表达式] 进行修改。"
TXT_DSET_GROUP_ONLY = "该指令仅在群聊中可用。"
TXT_DSET_NO_PERMISSION = "仅群主或管理员可以设置群默认骰面。"

# ── .dnd 属性生成（对齐 DicePP misc/dnd_command 默认文案）─────────────────
TXT_DND_RES = "{name} DND人物作成——{reason}:\n{result}"
TXT_DND_RES_NOREASON = "{name} DND人物作成:\n{result}"

# ── 通用 ────────────────────────────────────────────────────────────────
TXT_GROUP_ONLY = "该指令仅在群聊中可用。"

# ── DND5e 角色卡 .角色卡 / .状态 / 检定（对齐 DicePP character 默认文案）─────
TXT_CHAR_SET = "角色卡已设置"
TXT_CHAR_MISS = "找不到角色卡"
TXT_CHAR_DEL = "角色卡已删除"
# 检定反馈：{name} 角色名/昵称；{check} 检定条目；{hint} 过程说明；{result} 掷骰过程
# 注：文案保留 DicePP 默认注册文本（"throw" 为其原样，未本地化，忠实对齐）
TXT_CHECK_RESULT = "{name} throw {check}\n{hint}\n{result}"


def get_roll_state_text(res_list: List[RollResult]) -> str:
    """计算掷骰结果附带的 d20 状态文案（移植 DicePP get_roll_state_loc_text）。

    规则（对齐上游）：
    - 1 轮且存在唯一 d20 大成功/大失败 → 「好耶！大成功!」/「哇哦！大失败!」
    - 多轮且存在大成功/大失败 → 「N次 大成功 M次 大失败」（只列存在的项）
    - 1 轮、无大成功/大失败、含唯一 d20 → 按平均出目档位返回（默认空串）
    - 其余情况 → 空串
    """
    success_time = sum(res.success for res in res_list)
    failure_time = sum(res.fail for res in res_list)

    if len(res_list) == 1 and (success_time + failure_time) != 0:
        if success_time:
            return TXT_D20_SUCCESS
        if failure_time:
            return TXT_D20_FAILURE

    if len(res_list) > 1:
        parts: List[str] = []
        if success_time:
            parts.append(TXT_D20_MULTI.format(time=success_time, short=TXT_D20_SUCCESS_SHORT))
        if failure_time:
            parts.append(TXT_D20_MULTI.format(time=failure_time, short=TXT_D20_FAILURE_SHORT))
        return " ".join(parts)

    if len(res_list) == 1 and res_list[0].d20_num > 0:
        average = round(sum(res_list[0].average_list) / res_list[0].dice_num)
        if average < 10:
            return TXT_D20_2
        if average < 25:
            return TXT_D20_3_5
        if average < 50:
            return TXT_D20_6_10
        if average < 75:
            return TXT_D20_11_15
        if average < 90:
            return TXT_D20_16_18
        return TXT_D20_19

    return ""
