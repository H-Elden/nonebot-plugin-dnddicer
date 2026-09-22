"""掷骰命令反馈文案与状态文案逻辑。

默认文案对齐 nonebot-dicepp ``roll_dice_command.py`` 中 ``register_loc_text``
注册的默认文本（2026-09，DicePP commit 732ff74 / v3.0.0rc23），保证手感一致；
DicePP 的本地化扩展机制不在本插件范围（不迁移其 loc 体系），文案集中于此便于
日后对照上游校对。
"""

from __future__ import annotations

from typing import List, Tuple

from ..engine.roll.result import RollResult

# ── 掷骰结果模板（{nickname}/{reason}/{final}/{state} 由命令层填充）─────────
TXT_RESULT = "{nickname} 的掷骰结果为 {final} {state}"
TXT_RESULT_REASON = "{nickname} 为 {reason} 进行的掷骰结果为 {final} {state}"
TXT_HIDE_RESULT = "{nickname} 的暗骰结果为 {final} {state}"
TXT_HIDE_RESULT_REASON = "{nickname} 为 {reason} 进行的暗骰结果为 {final} {state}"
TXT_HIDE_GROUP = "{nickname} 进行了一次暗骰"

#: 多次掷骰（#连掷）的结果块模板（分两种模式）
#: 非 s（有过程明细）：去掉 DicePP LOC_ROLL_RESULT_MULTI 原文 "{time}次 {exp}: [{result}]"
#: 的最外层中括号——result 内部多行（每轮次一行），外层 [] 包裹换行内容难看；
#: s（只显数值）：单行紧凑 [v1, v2, ...]（逗号+空格，不换行）
TXT_MULTI = "{time}次 {exp}:\n{result}"
TXT_MULTI_SUM = "{time}次 {exp}: [{result}]"

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

# ── .dndx 属性生成（属性名绑定，2026-09-21 新增；标题加后缀便于区分）──────
TXT_DNDX_RES = "{name} DND人物作成(属性绑定)——{reason}:\n{result}"
TXT_DNDX_RES_NOREASON = "{name} DND人物作成(属性绑定):\n{result}"

# ── 通用 ────────────────────────────────────────────────────────────────
TXT_GROUP_ONLY = "该指令仅在群聊中可用。"
# 命令处理出现未预期异常时的统一回复（详见 commands/base.py 全局兜底钩子）
TXT_UNKNOWN_ERROR = "骰娘内部发生了错误，请联系管理员反馈。"

# ── .bot 插件信息与群聊服务开关（宿主新需求 2026-09-09，自研文案）
# 群聊服务默认关闭（白名单）：未开启的群仅 .bot 命令可用，其余命令静默不响应；
# 私聊不受群聊服务开关限制
TXT_BOT_HEAD = "屠龙骰（nonebot-plugin-dnddicer）v{version}"
TXT_BOT_INTRO = (
    "专精 DND5e/5r 跑团的骰娘：掷骰表达式、角色卡与检定/豁免/攻击、"
    "属性生成、HP 管理、先攻列表、战斗轮、群配置，命令手感对齐 nonebot-dicepp。"
)
TXT_BOT_STATE_PRIVATE = "私聊可直接使用本插件的全部功能，不受群聊服务开关影响。"
TXT_BOT_STATE_ON = "本群服务已开启，可直接使用本插件的全部命令。"
TXT_BOT_STATE_OFF = "本群服务未开启，仅 .bot 命令可用。发送 .bot on（需群主或管理员权限）可开启。"
TXT_BOT_USAGE = "用法：.bot on / .bot off——仅限群聊，需群主或管理员权限。"
TXT_BOT_ON = "本群服务已开启。"
TXT_BOT_OFF = "本群服务已关闭，本群将不再响应本插件的其他命令（.bot 不受影响）。"
TXT_BOT_NO_PERMISSION = "仅群主或管理员可以开启或关闭本群服务。"
TXT_BOT_BAD_ARG = (
    "无效参数。用法：.bot 查看插件信息；.bot on / .bot off 开启/关闭本群服务"
    "（仅限群聊，需群主或管理员权限）。"
)

# ── DND5e 角色卡 .角色卡 / .状态 / 检定（对齐 DicePP character 默认文案）─────
TXT_CHAR_SET = "角色卡已设置"
TXT_CHAR_MISS = "找不到角色卡"
TXT_CHAR_DEL = "角色卡已删除"
# 检定反馈：{name} 角色名/昵称；{check} 检定条目展示名（攻击/豁免原名、
# 属性/技能/先攻追加「检定」，见 commands/character.py）；{hint} 过程说明；
# {result} 掷骰过程
# 注：DicePP 默认注册文本为 "{name} throw {check}"（"throw" 未本地化）；
# 2026-09-09 验收修订为中文文案
TXT_CHECK_RESULT = "{name}进行【{check}】：\n{hint}\n{result}"

# ── HP 管理 .hp（对齐 DicePP hp_command 默认文案）─────────────────────────
TXT_HP_INFO = "{name}: {hp_info}"
TXT_HP_INFO_MISS = "找不到{name}的生命值信息"
#: .hp 指定目标未命中：附 NPC 记录方式的引导（NPC 需先入先攻表，见 commands/hp.py）
TXT_HP_INFO_MISS_HINT = "找不到{name}的生命值信息\n新NPC需要先加入先攻表才可设置HP"
TXT_HP_INFO_MULTI = "存在多个匹配目标：{name_list}"
TXT_HP_INFO_NONE = "本群没有任何生命值信息"
TXT_HP_MOD = "{name}: {hp_mod}"
TXT_HP_MOD_ERR = "修改生命值时出现错误：{error}"
#: 目标名带 抗性/易伤 后缀但命令不是伤害（-）时的提示（后缀仅对伤害生效）
TXT_HP_FACTOR_DMG_ONLY = "抗性/易伤后缀仅对伤害生效（用法：.hp 目标[抗性/易伤] -伤害表达式）。"
TXT_HP_DEL = "已删除{name}的生命值信息"
#: .hp del/clr 仅作用于 NPC 血量记录：.hp del 无对象时的用法提示
TXT_HP_DEL_NO_TARGET = "请指定要删除的NPC名称（.hp del 名称）；如需删除整张角色卡请用 .角色卡清除"
#: 同上：目标解析为玩家角色卡时的引导（不再连卡删除，2026-09-21 语义修订）
TXT_HP_DEL_PC_TARGET = "「{name}」是玩家角色卡，.hp del/clr 仅用于删除NPC血量记录；如需删除整张角色卡请用 .角色卡清除"
#: .hp clr：清空本群全部 NPC 血量记录（含跨战斗保持的）
TXT_HP_CLR_DONE = "已清空{n}条NPC血量记录"
TXT_HP_CLR_NONE = "本群没有任何NPC生命值信息"
#: .hp 名称回退链的兜底展示名：附 QQ 号便于对不上名时定位到具体成员
#: （2026-09-22 修订：此前仅「未知玩家」，DM 无从判断是谁）
TXT_HP_UNKNOWN_NAME = "未知玩家（{qq}）"

# ── NPC 血量跨战斗保持 .npc（群级、按名称）────────────────────────────────
TXT_NPC_PERSIST_ON = "已将NPC「{name}」设为跨战斗保持血量（.ri 再次入表时不再自动回满）"
TXT_NPC_PERSIST_OFF = "已将NPC「{name}」恢复为默认（每次新入先攻表时自动回满）"
TXT_NPC_NO_RECORD = "找不到{name}的血量记录，请先用 .hp {name} 当前血量/最大血量 记录"
TXT_NPC_PC_TARGET = "「{name}」是玩家角色卡，不是NPC"

# ── 长休 .长休 ─────────────────────────────────────────────────────────────
TXT_LONG_REST = "{result}"
TXT_LONG_REST_MISS = "找不到{name}的角色卡信息"

# ── 先攻列表 .init/.ri/.先攻（对齐 DicePP initiative_command 默认文案）───────
TXT_INIT_ROLL = "{name}的先攻值是 {init_result}"
TXT_INIT_INFO = "先攻列表如下: \n{init_info}"
TXT_INIT_INFO_NOT_EXIST = "没有找到先攻列表"
TXT_INIT_INFO_CLR = "已清除先攻列表"
TXT_INIT_ENTITY_NOT_FOUND = "先攻里没有{name}"
TXT_INIT_ENTITY_VAGUE = "先攻对象名称{name}存在歧义，可能是{name_list}"
TXT_INIT_ENTITY_REPEAT = "你重复投掷了先攻"
TXT_INIT_ENTITY_SAME = "出现相同先攻值，请DM来决定由谁先行动，若不决定将保持默认顺序："
TXT_INIT_ENTITY_SAME_LIST = "回复.init first 名称 将该对象提前（同先攻值: {entity_list}）"
TXT_INIT_ENTITY_FIRST = "{name}的先攻已在相同先攻值中被提前"
TXT_INIT_ENTITY_SWAP = "{name1}与{name2}的先攻值已互换"
TXT_INIT_INFO_DEL = "已从先攻列表中移除 {entity_list}"
TXT_INIT_UNKNOWN = "子指令{invalid_command}无效，可用的子指令为{sub_command_list}"
TXT_INIT_ERROR = "处理先攻指令时出现错误：{error_info}"
#: .ri 入表时 NPC 血量自动回满提示（单个：名称+回满值+上次值，命令各占一行便于复制）
TXT_INIT_NPC_REFILL_ONE = (
    "注：{name} 已自动回满 {hp_info}（上次 {last_hp}）\n"
    "如需沿用上次血量:\n"
    ".hp {name} {last_hp}\n"
    "如需跨战斗保持血量:\n"
    ".npc 持久 {name}"
)
#: 同上（多个目标：聚合一行条目，命令格式各占一行）
TXT_INIT_NPC_REFILL_MULTI = (
    "注：{items} 已自动回满\n"
    "如需沿用上次血量:\n"
    ".hp 名称 当前/最大\n"
    "如需跨战斗保持血量:\n"
    ".npc 持久 名称"
)

# ── 战斗轮 .br/.ed/.回合/.轮次（对齐 DicePP battleroll_command 默认文案）
# 注：.br 文案去掉 DicePP 原版残留的「BUFF表」字样（BUFF 计时表本期不做）
TXT_BR_NEW = "已创建新战斗轮。清除先攻表、当前回合。"
TXT_BR_ROUND = "现在是第{round}轮第{turn}回合，{turn_name}的回合。"
TXT_BR_ROUND_MOD = "现在变成第{round}轮了。"
TXT_BR_TURN_MOD = "现在变成第{round}轮的第{turn}回合了。"
TXT_BR_ROUND_SHOW = "现在是{turn_name}的回合。"
TXT_BR_NO_INIT = "目前先攻列表为空，故不存在回合与轮次。"
TXT_BR_TURN_END = "{turn_name}的回合结束了。"
TXT_BR_ROUND_NEW = "新的一轮，现在是第{round}轮。"
TXT_BR_TURN_NEW = "现在是{turn_name}的回合。"
# @ 播报：原 DicePP 单模板 "现在是{turn_name}的回合。请玩家{at}开始行动。"
# 的 {at} 为 CQ 码文本占位；现拆为 前缀/后缀 两段，at 消息段由命令层用
# onebot v11 MessageSegment.at 组装（见 commands/battle.py）
TXT_BR_TURN_NEW_WITH_AT_PREFIX = "现在是{turn_name}的回合。请玩家"
TXT_BR_TURN_NEW_WITH_AT_SUFFIX = "开始行动。"
TXT_BR_ERROR_NOT_NUMBER = "这不是数字。"
TXT_BR_ERROR_TOO_SMALL = "这个数字太小了。"
TXT_BR_ERROR_TOO_BIG = "这个数字太大了。"
TXT_BR_ERROR_NOT_FOUND = "没有找到这个回合。"
TXT_BR_ERROR_TOO_MUCH_FOUND = "找到复数回合，请换一个关键词。"


def _d20_crit_counts(res_list: List[RollResult]) -> Tuple[int, int]:
    """统计被保留 d20 骰中的大成功（出目 20）与大失败（出目 1）次数。

    大成功/大失败只由 d20 产生（DND 规则唯一有该概念的骰面），且只看
    **被保留** 的骰子（kh/dl 丢弃的骰不计：优势掷出 20 与 1 保留 20 →
    只算大成功）。d100 等其它骰面不产生大成功/大失败（DNDDicer 不做
    COC/d100 体系，不再沿用上游按 d100 出目 1/100 计数——
    RollResult.success/fail 字段混计 d20 与 d100，故这里改以 d20_list 为准）。
    """
    success_time = 0
    failure_time = 0
    for res in res_list:
        for val in res.d20_list:
            if val == 20:
                success_time += 1
            elif val == 1:
                failure_time += 1
    return success_time, failure_time


def format_d20_state_text(success_time: int, failure_time: int, round_count: int) -> str:
    """把大成功/大失败次数格式化为状态文案（.r 与角色检定命令共用）。"""
    if round_count == 1 and (success_time + failure_time) != 0:
        return TXT_D20_SUCCESS if success_time else TXT_D20_FAILURE

    if round_count > 1:
        parts: List[str] = []
        if success_time:
            parts.append(TXT_D20_MULTI.format(time=success_time, short=TXT_D20_SUCCESS_SHORT))
        if failure_time:
            parts.append(TXT_D20_MULTI.format(time=failure_time, short=TXT_D20_FAILURE_SHORT))
        return " ".join(parts)

    return ""


def get_roll_state_text(res_list: List[RollResult]) -> str:
    """计算掷骰结果附带的 d20 状态文案（移植 DicePP get_roll_state_loc_text）。

    规则（大成功/大失败判定只认被保留的 d20，见 _d20_crit_counts）：
    - 1 轮且存在唯一 d20 大成功/大失败 → 「好耶！大成功!」/「哇哦！大失败!」
    - 多轮且存在大成功/大失败 → 「N次 大成功 M次 大失败」（只列存在的项）
    - 1 轮、无大成功/大失败、含唯一 d20 → 按平均出目档位返回（默认空串）
    - 其余情况 → 空串
    """
    success_time, failure_time = _d20_crit_counts(res_list)
    if success_time or failure_time:
        return format_d20_state_text(success_time, failure_time, len(res_list))

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
