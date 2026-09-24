"""掷骰命令反馈文案与状态文案逻辑。

反馈文案集中于此，便于统一校对与调整。
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
#: 非 s（有过程明细）：多行展开逐轮结果，不加外层中括号——result 内部每轮次
#: 一行，外层 [] 包裹换行内容难看；
#: s（只显数值）：单行紧凑 [v1, v2, ...]（逗号+空格，不换行）
TXT_MULTI = "{time}次 {exp}:\n{result}"
TXT_MULTI_SUM = "{time}次 {exp}: [{result}]"

# ── 唯一 d20 的大成功 / 大失败 / 档位反馈（替换模板中的 {state}）────────────
TXT_D20_SUCCESS = "好耶！大成功!"
TXT_D20_FAILURE = "哇哦！大失败!"
TXT_D20_SUCCESS_SHORT = "大成功"
TXT_D20_FAILURE_SHORT = "大失败"
TXT_D20_MULTI = "{time}次 {short}"
# 唯一 d20、无大成功/大失败时的分档反馈（默认全空，即不追加任何文字）
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

# ── 群默认骰面 .dset 文案 ───────────────────────────────────────────────
TXT_DSET_SUCCESS = "本群默认掷骰表达式已改为{expr}。"
TXT_DSET_INVALID = "默认掷骰表达式无效：{reason}"
TXT_DSET_CURRENT = "当前默认掷骰表达式为{expr}。使用 .dset [表达式] 进行修改。"
TXT_DSET_GROUP_ONLY = "该指令仅在群聊中可用。"
TXT_DSET_NO_PERMISSION = "仅群主或管理员可以设置群默认骰面。"

# ── .dnd 属性生成文案 ───────────────────────────────────────────────────
TXT_DND_RES = "{name} DND人物作成——{reason}:\n{result}"
TXT_DND_RES_NOREASON = "{name} DND人物作成:\n{result}"

# ── .dndx 属性生成（属性名绑定，2026-09-21 新增；标题加后缀便于区分）──────
TXT_DNDX_RES = "{name} DND人物作成(属性绑定)——{reason}:\n{result}"
TXT_DNDX_RES_NOREASON = "{name} DND人物作成(属性绑定):\n{result}"

# ── 通用 ────────────────────────────────────────────────────────────────
TXT_GROUP_ONLY = "该指令仅在群聊中可用。"
#: 玩家名称回退链（角色名 → 群名片 → QQ 昵称）的兜底展示名：附 QQ 号便于对不上名
#: 时定位到具体成员（2026-09-22 修订：此前仅「未知玩家」，DM 无从判断是谁；
#: 全项目玩家名称显示共用，见 commands/base.py resolve_display_name，NPC 除外）
TXT_UNKNOWN_NAME = "未知玩家（{qq}）"
# 命令处理出现未预期异常时的统一回复（详见 commands/base.py 全局兜底钩子）
TXT_UNKNOWN_ERROR = "骰娘内部发生了错误，请联系管理员反馈。"

# ── .bot 插件信息与群聊服务开关（宿主新需求 2026-09-09，自研文案）
# 群聊服务默认关闭（白名单）：未开启的群仅 .bot 命令可用，其余命令静默不响应；
# 私聊不受群聊服务开关限制
TXT_BOT_HEAD = "屠龙骰（nonebot-plugin-dnddicer）v{version}"
TXT_BOT_INTRO = (
    "专精 DND5e/5r 跑团的骰娘：掷骰表达式、角色卡与检定/豁免、"
    "自定义武器与攻击、属性生成、HP 管理、先攻列表、战斗轮、群配置。"
)
TXT_BOT_STATE_PRIVATE = (
    "私聊不受群聊服务开关限制：掷骰、属性生成等可直接使用，"
    "角色卡、HP、先攻等命令仅在群聊中可用。"
)
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

# ── DND5e 角色卡 .角色卡 / .状态 / 检定 文案 ─────────────────────────────
TXT_CHAR_SET = "角色卡已设置"
TXT_CHAR_MISS = "找不到角色卡"
TXT_CHAR_DEL = "角色卡已删除"
# 检定反馈：{name} 角色名/昵称；{check} 检定条目展示名（豁免原名、
# 属性/技能/先攻追加「检定」，见 commands/character.py）；{hint} 过程说明；
# {result} 掷骰过程
# 注：2026-09-09 验收起采用中文文案「进行【…】」
TXT_CHECK_RESULT = "{name}进行【{check}】：\n{hint}\n{result}"

# ── 自定义武器：攻击检定（.X攻击 / .X命中，2026-09-24 新增）───────────────
# 机器人不做命中判断（不判 AC）；d20 出目 20/1 用 DND 术语提示（天然20 → 重击
# 引导、天然1 → 必失），不使用 .r 的「大成功/大失败」文案
TXT_WEAPON_ATTACK = "{name}进行【{check}】：\n{hint}\n{result}"
TXT_WEAPON_NOT_FOUND = "未找到武器「{name}」。可用 .设置武器 查看已有武器或添加新武器。"
#: 天然 20/1 提示：单独一行（不加括号，2026-09-24 用户要求）
TXT_WEAPON_NAT20 = "天然20：重击！伤害用 .{weapon}重击伤害 结算"
TXT_WEAPON_NAT1 = "天然1：必失"
TXT_WEAPON_BAD_MOD = "攻击掷骰表达式无效: {mod}（{reason}）"
#: x 标记（不可攻击检定）的武器被用于攻击命令时的提示
TXT_WEAPON_NO_ATTACK = "【{weapon}】不可进行攻击检定！"

# ── 自定义武器：伤害（.X伤害，2026-09-24 新增）─────────────────────────────
# {type} 为空时自然读作「造成了 8 点伤害」；{note} 为后缀标注（重击/副手/偷袭）
TXT_WEAPON_DAMAGE = "{name}用【{weapon}】造成了 {total} 点{type}伤害{note}：\n{result}"
TXT_WEAPON_DAMAGE_TAIL = (
    "伤害命令不支持的写法: {tail}（用法：.武器名[副手/重击/偷袭]伤害[±加值]，可 @玩家）"
)
TXT_WEAPON_OFFHAND_NO_DICE = (
    "「{weapon}」的伤害没有骰子，副手后缀不适用（副手攻击不加任何加值）。"
)
TXT_WEAPON_SNEAK_NO_CLASS = (
    "「{weapon}」的偷袭后缀需要职业为游荡者：请先在角色卡设置职业（12 职业名之一）"
)
TXT_WEAPON_SNEAK_NOT_ROGUE = "当前职业「{char_class}」没有偷袭特性，偷袭后缀不适用"

# ── 自定义武器：管理命令（.设置武器 / .删除武器，2026-09-24 新增）──────
TXT_WEAPON_SET = "已设置武器：{names}（当前共 {count} 件）\n{items}"
TXT_WEAPON_LIST = (
    "当前武器（{count} 件）：\n{items}\n"
    "用法：.设置武器 短剑+6,1d4+4穿刺（多项用 / 分隔）；删除用 .删除武器 名称"
)
TXT_WEAPON_LIST_EMPTY = (
    "还没有设置武器。用法：.设置武器 短剑+6,1d4+4穿刺（多项用 / 分隔）"
)
TXT_WEAPON_DEL = "已删除武器: {deleted}"
TXT_WEAPON_DEL_PARTIAL = "已删除武器: {deleted}；未找到: {missing}"
TXT_WEAPON_DEL_MISS = "未找到武器: {missing}（可用 .设置武器 查看当前武器）"
TXT_WEAPON_DEL_USAGE = "用法：.删除武器 名称（多个用 / 分隔）"

# ── HP 管理 .hp 文案 ────────────────────────────────────────────────────
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

# ── HP 管理 .hp 文案：伤害位置的武器写法（2026-09-24 新增）────────────────
#: 伤害位置写成「武器名+攻击/命中」时的引导（攻击检定不是伤害掷骰）
TXT_HP_WEAPON_ATTACK_ONLY = "「{entry}」是攻击检定而非伤害掷骰，请用「{weapon}伤害」！"
#: 武器伤害写法尾部不合法（仅支持 ±加值与 副手/重击/偷袭 后缀，同 .X伤害）
TXT_HP_WEAPON_TAIL_BAD = (
    "武器伤害写法无效: {expr}（用法：-武器名[副手/重击/偷袭]伤害[±加值]，"
    "如 -战锤重击伤害+1d4）"
)
#: 武器伤害写法需要发送者本人有角色卡（武器项取自卡上 $武器$ 段）
TXT_HP_WEAPON_NO_CHAR = (
    "找不到角色卡：武器伤害写法读取发送者本人角色卡上的 $武器$ 项，"
    "请先 .角色卡记录 建卡（武器可用 .设置武器 登记），"
    "或改用普通掷骰表达式（如 -1d8+2）"
)
#: 武器伤害写法的表头（与 .X伤害 回复同款，随后接各目标的 HP 结算行）
TXT_HP_WEAPON_DAMAGE_HEAD = "{name}用【{weapon}】造成了 {total} 点{type}伤害{note}："
#: 括号来源未命中玩家角色卡（名称模糊搜索失败或命中 NPC 条目）
TXT_HP_WEAPON_SOURCE_MISS = (
    "找不到角色卡「{name}」：括号中请填玩家角色名（或直接 @玩家）"
)

# ── @ 提及目标（2026-09-22 新增：DM 代操作玩家角色卡）───────────────────────
# 约定：以下「无卡引导」「不在先攻表」等提示统一用真 @ 消息段回复（群里显示
# 为对方昵称），文案本身不含 @ 字样（见 platform.onebot_v11.at_reply）。
#: 提及者本群无角色卡（.ri 的引导另附临时 NPC 写法，见下条）
TXT_MENTION_NO_CHAR = "还没有在本群建立角色卡（可用 .角色卡记录 建卡后再试）"
#: .ri 的 @ 目标无卡：另附「直接写名称」的临时怪物条目写法
TXT_MENTION_NO_CHAR_RI = (
    "还没有在本群建立角色卡（可用 .角色卡记录 建卡后再试）；"
    "如需临时加同名怪物条目，可直接写名称（.ri+3 名称）"
)
#: 游离 @：@ 未落在目标位置时 .hp 的纠正提示（不执行、不结算）
TXT_MENTION_HP_POS_HINT = "未执行：目标请写在目标位置，例如 .hp @小明 -d4"
#: 同上：.ri 的 @ 落在表达式段时的纠正提示
TXT_MENTION_RI_POS_HINT = "未执行：目标请写在表达式右侧，例如 .ri+3 @小明"
#: .ri 的 @ 目标与 N# 批量写法组合时的守卫提示
TXT_MENTION_RI_BATCH = "@ 目标不支持 N# 批量写法，请直接写条目名称"
#: 提及者不在先攻列表中（真 @ 消息段 + 本句回复）
TXT_MENTION_NOT_IN_INIT = "不在先攻列表中"
#: .hp del 的 @ 目标命中玩家角色卡（@ 版本：不再连卡删除，引导移除先攻条目）
TXT_HP_DEL_PC_TARGET_AT = (
    "是玩家角色卡，.hp del/clr 仅用于删除NPC血量记录"
    "（移除玩家先攻条目请用 .init del 该玩家）"
)
#: .npc 的 @ 目标命中玩家角色卡（@ 版本）
TXT_NPC_PC_TARGET_AT = "是玩家角色卡，不是NPC"
#: 他人角色卡查看（.角色卡 @玩家 / .角色卡 名称）的标题行
TXT_CHAR_TARGET_TITLE = "{name} 的角色卡："
#: 同上：名称形式未命中任何角色卡/条目
TXT_CHAR_TARGET_MISS = "找不到{name}的角色卡"
#: 同上：名称命中的是先攻表/NPC 血量条目（NPC 没有角色卡）
TXT_CHAR_NPC_NO_CARD = "「{name}」是NPC条目，没有角色卡"
#: .状态 @玩家：他人状态加角色名前缀（自身查看保持无前缀）
TXT_STATE_TARGET = "{name}: {info}"

# ── NPC 血量跨战斗保持 .npc（群级、按名称）────────────────────────────────
TXT_NPC_PERSIST_ON = "已将NPC「{name}」设为跨战斗保持血量（.ri 再次入表时不再自动回满）"
TXT_NPC_PERSIST_OFF = "已将NPC「{name}」恢复为默认（每次新入先攻表时自动回满）"
TXT_NPC_NO_RECORD = "找不到{name}的血量记录，请先用 .hp {name} 当前血量/最大血量 记录"
TXT_NPC_PC_TARGET = "「{name}」是玩家角色卡，不是NPC"

# ── 长休 .长休 ─────────────────────────────────────────────────────────────
TXT_LONG_REST = "{result}"
TXT_LONG_REST_MISS = "找不到{name}的角色卡信息"

# ── 先攻列表 .init/.ri/.先攻 文案 ───────────────────────────────────────
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

# ── 战斗轮 .br/.ed/.回合/.轮次 文案
# 注：.br 文案不含「BUFF表」字样（BUFF 计时表本期不做）
TXT_BR_NEW = "已创建新战斗轮。清除先攻表、当前回合。"
TXT_BR_ROUND = "现在是第{round}轮第{turn}回合，{turn_name}的回合。"
TXT_BR_ROUND_MOD = "现在变成第{round}轮了。"
TXT_BR_TURN_MOD = "现在变成第{round}轮的第{turn}回合了。"
TXT_BR_ROUND_SHOW = "现在是{turn_name}的回合。"
TXT_BR_NO_INIT = "目前先攻列表为空，故不存在回合与轮次。"
TXT_BR_TURN_END = "{turn_name}的回合结束了。"
TXT_BR_ROUND_NEW = "新的一轮，现在是第{round}轮。"
TXT_BR_TURN_NEW = "现在是{turn_name}的回合。"
# @ 播报：拆为 前缀/后缀 两段，两段之间的 @ 消息段由命令层用
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
    只算大成功）。d100 等其它骰面不产生大成功/大失败（本插件不做
    COC/d100 体系，也不采用按 d100 出目 1/100 计数——RollResult 的
    success/fail 字段会混计 d20 与 d100，故这里以 d20_list 为准）。
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
    """计算掷骰结果附带的 d20 状态文案。

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


def format_nat_attack_state(res_list: List[RollResult], weapon_name: str) -> str:
    """武器攻击检定的天然 20/1 提示（DND 术语；只认被保留的 d20）。

    - 单轮：天然 20 → 重击引导（``.X重击伤害``）；天然 1 → 必失；
    - 多轮：聚合为「N次天然20、M次天然1」（只列存在的项）。

    与 ``get_roll_state_text``（大成功/大失败，用于 .r 与检定点）并存、互不干扰。
    """
    nat20 = nat1 = 0
    for res in res_list:
        for val in res.d20_list:
            if val == 20:
                nat20 += 1
            elif val == 1:
                nat1 += 1
    if not nat20 and not nat1:
        return ""
    if len(res_list) == 1:
        if nat20:
            return TXT_WEAPON_NAT20.format(weapon=weapon_name)
        return TXT_WEAPON_NAT1
    parts: List[str] = []
    if nat20:
        parts.append(f"{nat20}次天然20")
    if nat1:
        parts.append(f"{nat1}次天然1")
    return "、".join(parts)
