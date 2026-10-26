"""HP 管理命令：``.hp`` + 休息 ``.短休`` / ``.生命骰`` / ``.长休`` + 死亡豁免 ``.死亡豁免`` / ``.ds``。

HP 与角色卡解耦（2026-10-23）：本群绑定角色卡时读写卡面 ``$生命值$``；
没有绑定卡时读写独立的群级 HP 记录（首次设置时创建，绑定卡时丢弃）。
``.hp`` 与 ``.死亡豁免`` 因此不要求建卡；``.状态``、长休 / 短休、生命骰
等需要卡面其他数据的命令仍要求绑定卡。

休息闭环（2026-10-20 批③）：``.短休`` 恢复「短休 / 两者」类能力与契约魔法
法术位、提示可用生命骰（不自动花骰）；``.生命骰 [N]`` 按卡面 ``$生命骰$``
花费 N 颗回血，2014 逐粒「骰值 + 体质调整」、2024「骰点总和 + 枚数 × 体质
调整」（群级规则版本经 ``character/rules.py`` 读取）；``.长休`` 在原有回满
HP / 清死亡豁免 / 版本化生命骰恢复之外，追加恢复能力、全部法术位与重新准备
法术提示（不自动改 ``*`` 标记）。三者都支持 ``@玩家`` 代操作。

死亡豁免闭环（2026-10-01 新增）：``.hp`` 的伤害使角色卡 HP 归 0 时自动进入濒死
（播报「请在自己回合开始时掷 .死亡豁免」），此后本人用 ``.死亡豁免`` / ``.ds``
掷 1d20（≥10 成功、≤9 失败；自然 20 回 1 点 HP、自然 1 记两次失败；3 成功稳定、
3 失败死亡）；濒死或稳定中再受伤自动记失败（武器重击 +2），单次伤害 ≥ HP 上限
直接判死；治疗把 HP 拉回正数即清空计数。手动裁决用 ``.ds 成功+1`` / ``失败+1`` /
``状态`` / ``重置``（死亡后治疗不复活，复活走重置）。**NPC 血量不做死亡豁免**
（怪物 0 HP 即昏迷倒下）；结算规则集中在 ``character/services.py::HPService``。

击晕参数（2026-10-01 新增，两版规则都有、结果不同）：伤害末尾加 ``击晕``（如
``.hp 薇拉 -20 击晕``）时留活口、不进入濒死——2014 归 0 且伤势稳定、2024 降为
1 HP；群级规则版本由 ``.规则版本`` 设置、经 ``character/rules.py`` 读取。

目标搜索覆盖三类（优先级由高到低）：PC 角色卡 → NPC 血量条目 → 先攻表；
NPC 血量条目在目标经先攻表解析时按需创建——即 NPC 需先 ``.ri`` 入先攻表
（或已存在血量记录）；先攻表联动（查看显示 / 清空与删除时清理）见
commands/initiative.py。

DM 掷伤害扩展：目标名后可带 抗性/易伤 后缀（伤害减半/加倍，仅对 - 生效），
目标以 ;（半角/全角）分隔可一次对多个目标结算 AOE；伤害表达式只掷骰一次。

伤害位置的武器写法（2026-09-24 新增）：``-`` 后除普通表达式外，支持与
``.X伤害`` 同款的 ``武器名[副手/重击/偷袭]伤害[±加值]``（如
``.hp 骷髅a易伤 -战锤重击伤害+1d4``）——武器项默认取**发送者本人**的角色卡，
尾部括号可指定来源（``-战锤伤害（布鲁姆）`` / ``-战锤伤害（@阿岩）``，
角色名支持模糊匹配），回复与 ``.X伤害`` 同款（表头「用【武器】造成了 N 点X伤害」
＋各目标的 HP 结算行）；后缀变换与临时加值语义与 ``.X伤害`` 完全一致（共用
commands/weapon.py 的 build_damage_expression）；写成 ``-武器名攻击/命中``
（攻击检定）时引导改用「武器名伤害」。武器名匹配同样支持**子串**（精确优先，
2026-09-27 起与 ``.X伤害`` 共用 resolve_weapon）。

多武器写法（2026-09-27 新增）：伤害位置也可一次写多件武器
（``.hp 骷髅 -刺剑伤害、匕首副手伤害``），逐项掷骰后报总伤害。因 ``/`` 在本命令
里另有「当前/最大」的含义，分批逻辑做了显式保护：**先判断首段是不是合法武器
伤害写法**，是则整段按多武器解析（写法有误就报错，绝不回退成改血），不是才按
原表达式处理（见 resolve_hp_damage_entries 的 has_multi_weapon_separator 判断）。

@ 提及目标（2026-09-22 新增）：``.hp @玩家 -4d6`` 直连该玩家在本群的角色卡
（不走名称模糊搜索），可查看（``.hp @玩家``）、设置/治疗、抗性/易伤后缀与
AOE 混写（``.hp @玩家;地精 -d4``）；提及者无卡时以真 @ 消息段引导建卡。
游离 @（@ 未落在目标位置，如 ``.hp -d4 @小明``）不再静默按发送者自身结算，
改为提示目标位置写法（见 handle_hp）。

删除语义（2026-09-21 修订）：``.hp del`` / ``.hp clr`` 仅作用于
**NPC 血量记录**——``del 名称``（多个用 / 分隔）删单个、``clr`` 清空本群全部
（含跨战斗保持的），形状与 .init 的 del/clr 一致；早先 del/clr 无对象时会
删除整张角色卡，粒度超出 .hp 语义且易误触，删整卡统一由 ``.角色卡清除`` 负责。
"""

from __future__ import annotations

import re
from typing import List, NamedTuple, Optional, Tuple, Union

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageEvent
from nonebot.matcher import Matcher

from ..character import rules as char_rules
from ..character.constants import ABILITY_LIST, REST_LONG, REST_SHORT
from ..character.models import DNDCharacter, HPInfo, npc_hp_info
from ..character.services import HPService, RestService, WEAPON_BONUS_RE
from ..data.characters import (
    get_character,
    list_characters_by_group,
    save_character,
)
from ..data.hp_records import (
    get_hp_record,
    list_hp_records,
    save_hp_record,
)
from ..data.initiative import get_init_list
from ..data.npc_health import (
    clear_npc_health,
    delete_npc_health,
    get_npc_health,
    list_npc_health,
    save_npc_health,
)
from ..engine.roll.ast_engine.adapter import exec_roll_exp_unified
from ..engine.roll.result import RollResult
from ..engine.roll.roll_utils import RollDiceError
from ..platform import onebot_v11
from . import base, text
from .weapon import (
    WeaponDamageRoll,
    WeaponEntry,
    append_multi_damage_lines,
    build_damage_expression,
    build_damage_note,
    has_multi_weapon_separator,
    multi_damage_head,
    parse_weapon_attack_entry,
    parse_weapon_damage_body,
    parse_weapon_damage_entries,
    parse_weapon_entry,
    resolve_weapon,
    split_weapon_segments,
)

# =========================================================================
# .hp 命令
# =========================================================================

_HELP = (
    ".hp [目标] [= / ± / ±表达式] [当前/最大] [(临时)]\n"
    "  记录 / 伤害 / 治疗 / 查看生命值（无卡也可）\n"
    "  查看：.hp（自己）、.hp @玩家、.hp list\n"
    "  清理：.hp del 名称（NPC）、.hp clr\n"
    "  武器写法：.hp 地精 -刺剑伤害（可加后缀）\n"
    "  伤害可加 击晕：留活口（5e 归 0 稳定、5r 归 1）"
)
hp_matcher = base.on_dnd_command("hp", _HELP, doc="guide/hp")


# =========================================================================
# .死亡豁免 命令（别名 .ds）
# =========================================================================

_HELP_DS = (
    ".死亡豁免 [优势|劣势][±加值]（.ds）\n"
    "  HP 为 0 时掷 1d20：≥10 成功、≤9 失败\n"
    "  3 次成功稳定、3 次失败死亡；自然 20 回 1 点 HP\n"
    "  手动裁决：.ds 成功+1 / 失败+1 / 状态 / 重置\n"
    "  进入濒死：HP 归 0 即自动开始，无需手动开启"
)
ds_matcher = base.on_dnd_command(
    "死亡豁免", _HELP_DS, aliases=("ds",), doc="guide/death-save"
)


# =========================================================================
# .长休 命令
# =========================================================================

_HELP_LONG_REST = (
    ".长休 [@玩家]\n"
    "  回满 HP、清临时 HP、清死亡豁免、回复生命骰\n"
    "  恢复长休类能力与全部法术位，并提示可重新准备法术\n"
    "  生命骰回复量按本群规则版本（5e 一半 / 5r 全满）\n"
    "  @玩家 用于 DM 替不在场玩家收尾"
)
long_rest_matcher = base.on_dnd_command("长休", _HELP_LONG_REST, doc="guide/resources")

_HELP_SHORT_REST = (
    ".短休 [@玩家]\n"
    "  恢复「短休 / 两者」类能力与契约魔法法术位\n"
    "  不自动花生命骰、不改 HP；需要回血用 .生命骰 N\n"
    "  @玩家 用于 DM 替不在场玩家操作"
)
short_rest_matcher = base.on_dnd_command(
    "短休", _HELP_SHORT_REST, doc="guide/resources"
)

_HELP_HD = (
    ".生命骰 [数量] [@玩家]\n"
    "  花费生命骰回血（缺省 1 颗）；骰面与数量按卡面录入\n"
    "  5e：每粒骰值 + 体质调整（每粒最低 0）\n"
    "  5r：骰点总和（至少 1）+ 枚数 × 体质调整\n"
)
hp_dice_matcher = base.on_dnd_command("生命骰", _HELP_HD, doc="guide/resources")


# =========================================================================
# 目标搜索（PC 角色卡 → NPC 血量 → 先攻表，优先级由高到低）
# =========================================================================

#: 目标名后缀 → 伤害折算因子（DM 掷伤害用）
_DAMAGE_MOD_SUFFIXES: Tuple[Tuple[str, float], ...] = (("抗性", 0.5), ("易伤", 2.0))


def _split_target_suffix(intent: str) -> Tuple[str, float]:
    """拆目标名后的 抗性/易伤 后缀 → (目标关键字, 伤害折算因子)。

    只对伤害（-）生效的语义由调用方校验（非伤害命令带后缀时报错）。
    """
    for suffix, factor in _DAMAGE_MOD_SUFFIXES:
        if intent.endswith(suffix):
            return intent[: -len(suffix)], factor
    return intent, 1.0


def _match_substring(substring: str, str_list: list[str]) -> list[str]:
    """找到所有包含输入字符串的字符串；存在完全匹配时只返回完全匹配。

    完全匹配优先（2026-09-21 修订）：先攻表/血量条目里同时有「地精」与
    「熊地精」时，``.hp 地精`` 应直接命中地精——与 ``.init`` 子指令的
    「精确 → 模糊 substring」两级匹配一致（只做 substring 会把两者
    都列为歧义）。
    """
    if substring in str_list:
        return [substring]
    return [s for s in str_list if substring in s]


async def search_target(
    target_intent: str, group_id: int | str
) -> Tuple[str, str]:
    """在群内 PC 角色卡 / NPC 血量 / 先攻列表中模糊搜索目标。

    返回 (source_key, target_id)：
    - ("pc", user_id) PC 角色卡（含 @ 标记直连——@<qq> 命中该玩家角色卡）
    - ("pc_hp", user_id) 无绑定卡、但有 HP 记录的玩家
    - ("npc", 名称) NPC 血量条目（或无血量、但存在于先攻表的 NPC）
    - ("at_miss", qq) @ 标记指向的玩家本群无角色卡、也无 HP 记录（由调用方决定引导）
    - ("multiple", "name1/name2") 多个匹配
    - ("", "") 未找到

    优先级：精确匹配 角色卡 > NPC > 先攻表；部分匹配同序
    取先到者，但后续来源的**精确**匹配可覆盖前序部分匹配。

    @ 标记（2026-09-22 新增）为**直连**语义：只查该 QQ 的角色卡、不进入名称
    模糊搜索——@ 本应无歧义，回填名称会重新落入「@ 指名的角色被同名 NPC 抢
    匹配」的歧义。2026-10-23 起再回退到无卡 HP 记录（HP 与角色卡解耦）。
    """
    mention_qq = onebot_v11.parse_mention_token(target_intent)
    if mention_qq is not None:
        character = await get_character(group_id, mention_qq)
        if character is not None and character.is_init:
            return "pc", mention_qq
        if await get_hp_record(group_id, mention_qq) is not None:
            return "pc_hp", mention_qq
        return "at_miss", mention_qq

    source, target_id = "", ""

    # 1. PC 角色卡
    chars = await list_characters_by_group(group_id)
    pc_name_map: dict[str, str] = {}
    for char in chars:
        pc_name_map[char.user_id] = char.name or str(char.user_id)
    matches = _match_substring(target_intent, list(pc_name_map.values()))
    if len(matches) > 1:
        return "multiple", "/".join(matches)
    if len(matches) == 1:
        for uid, name in pc_name_map.items():
            if name == matches[0]:
                source, target_id = "pc", uid
                if name == target_intent:
                    return source, target_id
                break

    # 2. NPC 血量条目
    npc_names = [npc.name for npc in await list_npc_health(group_id)]
    matches = _match_substring(target_intent, npc_names)
    if len(matches) > 1:
        return "multiple", "/".join(matches)
    if len(matches) == 1:
        if not source:
            source, target_id = "npc", matches[0]
        if matches[0] == target_intent:
            return "npc", matches[0]

    # 3. 先攻表（NPC 需先入表才能被 .hp 解析并创建血量）
    init_data = await get_init_list(group_id)
    if init_data is not None:
        entity_map: dict[str, str] = {
            entity.name: entity.owner for entity in init_data.entities
        }
        matches = _match_substring(target_intent, list(entity_map.keys()))
        if len(matches) > 1:
            return "multiple", "/".join(matches)
        if len(matches) == 1:
            name = matches[0]
            owner = entity_map[name]
            resolved = ("pc", owner) if owner else ("npc", name)
            if not source:
                source, target_id = resolved
            if name == target_intent:
                return resolved

    return source, target_id


# =========================================================================
# 参数解析
# =========================================================================

#: 全角数字 → 半角（``.死亡豁免 成功+１`` 这类全角输入容错）
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def _split_target_intents(target_part: str) -> List[str]:
    """拆分 .hp 目标段为多个目标意图。

    含 @ 标记时按空白与分号（半角/全角）拆分，支持 ``.hp @玩家 地精 -d8``
    这类 @ 与名称混写；不含 @ 时沿用既有分号语义（名称中的空白不受影响）。
    """
    if onebot_v11.iter_mentions(target_part):
        return [part for part in re.split(r"[\s;；]+", target_part) if part]
    return [part.strip() for part in re.split(r"[;；]", target_part) if part.strip()]


def _parse_mention_targets(arg_str: str) -> Optional[List[str]]:
    """目标段整体由 @ 标记与分隔符（空白/分号）组成时返回 QQ 列表，否则 None。

    对应无操作符的查看：``.hp @小明`` / ``.hp @小明 @小红``（与
    ``.hp @小明;@小红`` 等价）；含其他文本（名称/数值/表达式）时返回 None，
    继续走常规的目标与表达式解析（裸名称按值表达式处理，见模块常量约定）。
    """
    parts = [part for part in re.split(r"[\s;；]+", arg_str.strip()) if part]
    if not parts:
        return None
    qqs: List[str] = []
    for part in parts:
        qq = onebot_v11.parse_mention_token(part)
        if qq is None:
            return None
        qqs.append(qq)
    return qqs


def _parse_hp_args(arg_str: str) -> Tuple[
    Optional[RollResult],  # hp_cur
    Optional[RollResult],  # hp_max
    Optional[RollResult],  # hp_temp
    Optional[str],  # error
]:
    """解析调整表达式（不含目标前缀与操作符），返回 (cur, max, temp, error)。

    表达式规则：末尾 ``(expr)`` 为临时 HP，其余按 ``/`` 拆为 当前/最大 HP。
    """
    # 临时 HP：末尾 (expr)
    hp_temp_result: Optional[RollResult] = None
    temp_match = re.search(r"\((.*?)\)$", arg_str)
    if temp_match:
        try:
            hp_temp_result = exec_roll_exp_unified(temp_match.group(1))
        except RollDiceError as e:
            return None, None, None, e.info
        arg_str = arg_str[:temp_match.span()[0]].strip()

    if not arg_str and not temp_match:
        return None, None, None, "没有给定调整值"

    hp_cur_result: Optional[RollResult] = None
    hp_max_result: Optional[RollResult] = None
    if arg_str:
        arg_list = arg_str.split("/", 1)
        try:
            if len(arg_list) == 2:
                hp_cur_result = exec_roll_exp_unified(arg_list[0])
                hp_max_result = exec_roll_exp_unified(arg_list[1])
            else:
                hp_cur_result = exec_roll_exp_unified(arg_str)
        except RollDiceError as e:
            return None, None, None, e.info

    return hp_cur_result, hp_max_result, hp_temp_result, None


#: 击晕参数（5r「击晕」变体）：伤害表达式后的尾随关键字，可用空格分隔
_STUN_KEYWORD_RE = re.compile(r"(\s|^)击晕$")


def _split_stun_keyword(expr_str: str) -> Optional[Tuple[str, bool]]:
    """拆出伤害表达式尾部的 ``击晕`` 参数 → (剩余表达式, 是否击晕)。

    没有该关键字时返回 None（调用方沿用原有解析路径）。识别条件是「击晕」
    位于末尾、且**前一个字符不是数字或加号**——``.hp 地精 -15 击晕`` 与
    ``.hp 地精 -15击晕`` 都算关键字；``-15击晕`` 这种表达式里「5击晕」不是
    合法数值写法的情形也按关键字处理（否则引擎会报错、更难理解）。
    """
    stripped = expr_str.strip()
    if not stripped.endswith("击晕"):
        return None
    matched = _STUN_KEYWORD_RE.search(stripped)
    if matched is None:
        return None
    body = stripped[: matched.start()].strip()
    if not body:
        return None
    return body, True


# =========================================================================
# 伤害位置的武器写法（-武器名[副手/重击/偷袭]伤害[±加值]（来源））
# 2026-09-24 新增；09-25 追加来源括号与「.X伤害 同款表头」
# =========================================================================

#: 伤害位置尾部的来源括号：`（布鲁姆）` / `(@阿岩)`（中英文括号、括号前后空格皆可）
_HP_SOURCE_PATTERN = re.compile(
    r"^(?P<body>.*?)\s*[（(]\s*(?P<source>[^（）()]*?)\s*[）)]$"
)


class _WeaponPart(NamedTuple):
    """`.hp` 多武器写法的单项算式：武器名 / 掷骰表达式 / 类型 / 读数标注 / 是否无骰。"""

    weapon: str
    expression: str
    damage_type: str
    note: str
    no_dice: bool


def _combine_weapon_rolls(rolls: List[WeaponDamageRoll]) -> RollResult:
    """把逐项掷骰结果合成一个 RollResult（各项之和 + 逐项读数）。

    供 ``.hp`` 的多武器写法复用既有的「一条表达式 = 一次扣血」结算路径：
    逐项各掷一次（读数逐项展示），再合成一份总和结果交给 HP 结算，
    避免「掷两遍」导致的读数与扣血值不一致（2026-09-27）。
    """
    combined = RollResult()
    combined.val_list = [rolled.total for rolled in rolls]
    combined.info = "+".join(rolled.result.get_info() for rolled in rolls)
    return combined


class _WeaponDamageExpr(NamedTuple):
    """`.hp` 武器伤害写法的解析结果（表头信息 + 掷骰结果）。

    ``multis`` 非空表示这是**多武器写法**（一项一次掷骰，见
    ``.hp 骷髅 -刺剑伤害、匕首副手伤害``）：此时 ``expression`` 为空串、
    ``rolls`` 为逐项结果、``combined`` 为合成后的总伤害结果（HP 结算用它，
    与逐项行展示同源）；单项字段（``weapon_name``/``damage_type``/``note``）
    不参与输出。
    """

    expression: str                       # 单武器：最终掷骰表达式；多武器：空串
    weapon_name: str                      # 单武器：武器名（表头用）
    damage_type: str                      # 单武器：伤害类型（可为空）
    note: str                             # 单武器：后缀读数标注（无后缀为 ""）
    owner_qq: str                         # 武器来源者 QQ（表头落款）
    owner_name: str                       # 武器来源者角色名（表头落款首选）
    multis: Optional[List[_WeaponPart]] = None      # 多武器：逐项算式与类型
    rolls: Optional[List[WeaponDamageRoll]] = None  # 多武器：逐项掷骰结果
    combined: Optional[RollResult] = None           # 多武器：各项之和（HP 结算用）


def _looks_like_multi_weapon_damage(body: str) -> bool:
    """伤害位置是否应当按**多武器写法**解析（而非普通表达式 / 当前·最大血量）。

    分批的显式保护：``/`` 在本命令里另有「当前/最大」的含义
    （``.hp 20/30``），因此只有在「含分隔符 **且** 首段就是合法武器伤害写法」
    时才判定为多武器——是则整段交给逐项解析（写法有误就报错，**绝不**回退成
    把 ``伤害/数值`` 当分数去静默改血）；不是则原样走原有表达式路径。
    """
    if not has_multi_weapon_separator(body):
        return False
    _times_part, segments = split_weapon_segments(body)
    if len(segments) < 2:
        return False
    first = parse_weapon_entry(segments[0])
    return first is not None and first[1] == "伤害"


async def _resolve_hp_damage_expression(
    event: GroupMessageEvent, expr_text: str
) -> Optional[_WeaponDamageExpr]:
    """解析伤害位置上的武器写法；非武器写法返回 None。

    ``.hp 骷髅a易伤 -战锤重击伤害+1d4`` 与 ``.战锤伤害`` 同一套语义
    （后缀变换、±临时加值，见 commands/weapon.py 的 build_damage_expression）；
    武器项默认取**发送者本人**角色卡，用尾部括号可指定来源
    （``-战锤伤害（布鲁姆）`` / ``-战锤伤害（@阿岩）``，角色名支持模糊匹配）。
    多武器写法（``-刺剑伤害、匕首副手伤害``）逐项掷骰后返回多项结果。
    武器写法出错时直接回复引导并结束命令，而写成 ``-武器名攻击/命中``
    （攻击检定）时引导改用「武器名伤害」。
    """
    body, source_str = _split_weapon_source(expr_text)

    # 多武器写法：先试逐项解析（写法有误即报错，不回退成表达式/血量分数）
    if _looks_like_multi_weapon_damage(body):
        multi = parse_weapon_damage_entries(body)
        if multi is None:  # 理论不可达（_looks_like… 已保证首段合法），防御性兜底
            return None
        entries, error, _tail = multi
        if error is not None:
            await hp_matcher.finish(error.hp_message)
        owner_qq, character = await _resolve_weapon_owner(event, source_str)
        parts = await _plan_weapon_expressions(character, entries)
        try:
            rolls = _roll_weapon_parts(parts)
        except _WeaponRollError as exc:
            await hp_matcher.finish(
                text.TXT_WEAPON_BAD_MOD.format(mod=exc.expression, reason=exc.reason)
            )
        return _WeaponDamageExpr(
            expression="",
            weapon_name="",
            damage_type="",
            note="",
            owner_qq=owner_qq,
            owner_name=character.name,
            multis=parts,
            rolls=rolls,
            combined=_combine_weapon_rolls(rolls),
        )

    attack_entry = parse_weapon_attack_entry(body)
    if attack_entry is not None:
        name, kind = attack_entry
        await hp_matcher.finish(
            text.TXT_HP_WEAPON_ATTACK_ONLY.format(entry=f"{name}{kind}", weapon=name)
        )

    damage_entry = parse_weapon_damage_body(body)
    if damage_entry is None:
        return None
    name, suffixes, tail = damage_entry
    if tail and not WEAPON_BONUS_RE.match(tail):
        await hp_matcher.finish(text.TXT_HP_WEAPON_TAIL_BAD.format(expr=expr_text))

    owner_qq, character = await _resolve_weapon_owner(event, source_str)
    weapon = await resolve_weapon(hp_matcher, character, name)

    expression, error, sneak_dice = build_damage_expression(
        weapon, suffixes, character.ability_info.level, character.char_class, tail
    )
    if error:
        await hp_matcher.finish(error)
    return _WeaponDamageExpr(
        expression=expression,
        weapon_name=weapon.name,
        damage_type=weapon.damage_type,
        note=build_damage_note(suffixes, sneak_dice, "重击" in suffixes),
        owner_qq=owner_qq,
        owner_name=character.name,
    )


class _WeaponRollError(Exception):
    """逐项掷骰失败（携带表达式与引擎原因，由调用方转成用户提示）。"""

    def __init__(self, expression: str, reason: str) -> None:
        super().__init__(reason)
        self.expression = expression
        self.reason = reason


async def _plan_weapon_expressions(
    character: DNDCharacter, entries: List[WeaponEntry]
) -> List[_WeaponPart]:
    """多武器写法的逐项解析（解析武器 → 变换表达式）→ 单项算式列表。

    任何一项出错即回复引导并结束命令（与 ``.X伤害`` 多武器同款：全部解析完成
    后才开始掷骰，不会出现「前几项已掷、后面报错」的半截输出）。
    """
    parts: List[_WeaponPart] = []
    for entry in entries:
        weapon = await resolve_weapon(hp_matcher, character, entry.name)
        expression, error, sneak_dice = build_damage_expression(
            weapon, entry.suffixes, character.ability_info.level,
            character.char_class, entry.tail,
        )
        if error:
            await hp_matcher.finish(error)
        parts.append(_WeaponPart(
            weapon=weapon.name,
            expression=expression,
            damage_type=weapon.damage_type,
            note=build_damage_note(entry.suffixes, sneak_dice, "重击" in entry.suffixes),
            no_dice=re.search(r"\d*[dD]\d+", expression) is None,
        ))
    return parts


def _roll_weapon_parts(parts: List[_WeaponPart]) -> List[WeaponDamageRoll]:
    """按逐项算式掷骰（每项一次，顺序与 parts 一致）。

    算式已在解析阶段被校验，这里只在掷骰本身失败时抛 _WeaponRollError。
    """
    rolls: List[WeaponDamageRoll] = []
    for part in parts:
        try:
            roll_result = exec_roll_exp_unified(part.expression)
        except RollDiceError as exc:
            raise _WeaponRollError(part.expression, exc.info) from exc
        rolls.append(WeaponDamageRoll(
            weapon=part.weapon,
            damage_type=part.damage_type,
            note=part.note,
            result=roll_result,
            total=roll_result.get_val(),
            no_dice=part.no_dice,
        ))
    return rolls




def _split_weapon_source(expr_text: str) -> Tuple[str, str]:
    """拆出伤害位置尾部的来源括号 → (表达式文本, 来源文本)。

    例：``战锤伤害（布鲁姆）`` → ``("战锤伤害", "布鲁姆")``；无括号来源时
    来源为空串。括号只在整体可解析为武器伤害写法时才生效（见
    _resolve_hp_damage_expression），不会与临时 HP 的 ``(10)`` 写法相混。
    """
    matched = _HP_SOURCE_PATTERN.match(expr_text)
    if matched and matched.group("source"):
        return matched.group("body").strip(), matched.group("source").strip()
    return expr_text, ""


async def _resolve_weapon_owner(
    event: GroupMessageEvent, source_str: str
) -> Tuple[str, DNDCharacter]:
    """解析武器来源角色卡：括号指定（@玩家 / 角色名模糊匹配）或发送者本人。

    失败时直接回复引导并结束命令（无卡引导 / 歧义列表 / 找不到角色卡）。
    """
    if not source_str:
        character = await get_character(event.group_id, event.user_id)
        if character is None or not character.is_init:
            await hp_matcher.finish(text.TXT_HP_WEAPON_NO_CHAR)
        return str(event.user_id), character

    source_qq = onebot_v11.parse_mention_token(source_str)
    if source_qq is not None:
        character = await get_character(event.group_id, source_qq)
        if character is None or not character.is_init:
            await hp_matcher.finish(
                onebot_v11.at_reply(source_qq, text.TXT_MENTION_NO_CHAR)
            )
        return source_qq, character

    source_key, target_id = await search_target(source_str, event.group_id)
    if source_key == "pc":
        character = await get_character(event.group_id, target_id)
        if character is not None and character.is_init:
            return target_id, character
    elif source_key == "multiple":
        await hp_matcher.finish(
            text.TXT_HP_INFO_MULTI.format(name_list=target_id.split("/"))
        )
    await hp_matcher.finish(text.TXT_HP_WEAPON_SOURCE_MISS.format(name=source_str))




# =========================================================================
# 处理器
# =========================================================================


async def _load_player_hp(
    group_id: int | str, user_id: int | str
) -> Tuple[Optional[DNDCharacter], Optional[HPInfo]]:
    """读取玩家 HP：本群绑定卡优先，其次无卡 HP 记录。

    返回 ``(character, hp_info)``：命中卡片时 ``character`` 非空；命中无卡
    记录或都没有时 ``character`` 为 None、``hp_info`` 可能为 None。
    """
    character = await get_character(group_id, user_id)
    if character is not None and character.is_init:
        return character, character.hp_info
    return None, await get_hp_record(group_id, user_id)


async def _save_player_hp(
    group_id: int | str,
    user_id: int | str,
    hp_info: HPInfo,
    character: Optional[DNDCharacter],
) -> None:
    """写回玩家 HP：有绑定卡写卡，否则写无卡 HP 记录。"""
    if character is not None:
        character.hp_info = hp_info
        character.is_init = True
        await save_character(character)
        return
    await save_hp_record(group_id, user_id, hp_info)


def _has_hp_display(hp_info: Optional[HPInfo]) -> bool:
    """是否有可展示的 HP 信息：初始化过，或只记过损失（is_init=False）。

    无卡记录可能只经历过 ``.hp -N``（未记上限、``is_init=False``），这类
    损失记录同样要能被 ``.hp`` 查看与 ``.hp list`` 看到（2026-10-23 修订）。
    """
    return hp_info is not None and (hp_info.is_init or hp_info.hp_cur != 0)


@hp_matcher.handle()
async def handle_hp(bot: Bot, event: MessageEvent) -> None:
    """处理 .hp 命令。"""
    if not isinstance(event, GroupMessageEvent):
        await hp_matcher.finish(text.TXT_GROUP_ONLY)

    rest = base.get_command_rest_with_mentions(event)
    arg_str = (rest or "").strip()
    mentioned_qqs = onebot_v11.list_mentions(event)

    # 查看自己
    if not arg_str:
        # 游离 @（如 @小明 .hp）：不按发送者自身执行，回纠正示例
        if mentioned_qqs:
            await hp_matcher.finish(text.TXT_MENTION_HP_POS_HINT)
        character, hp_info = await _load_player_hp(
            event.group_id, event.user_id
        )
        name = await base.resolve_display_name(
            bot, event, char_name=character.name if character else ""
        )
        if _has_hp_display(hp_info):
            feedback = text.TXT_HP_INFO.format(name=name, hp_info=hp_info.get_info())
        else:
            feedback = text.TXT_HP_INFO_MISS.format(name=name)
        await hp_matcher.finish(feedback)

    # 列表（无卡记录不直接显示 QQ 号——名称解析统一走
    # base.resolve_display_name 回退链：角色卡名 → 群名片 → QQ 昵称 →
    # 「未知玩家（QQ号）」；无卡名成员需调 get_group_member_info，
    # API 失败/异常由适配层吞掉、名称回退下一级，不影响列表主流程）
    if arg_str.startswith("list"):
        chars = await list_characters_by_group(event.group_id)
        feedback = ""
        bound_users: set[str] = set()
        for char in chars:
            bound_users.add(str(char.user_id))
            if char.hp_info.is_init:
                name = await base.resolve_display_name(
                    bot, event, char.user_id, char_name=char.name
                )
                feedback += f"{name} {char.hp_info.get_info()}\n"
        # 无绑定卡、但有群级 HP 记录的玩家（PC 在前、NPC 在后）
        for user_id, hp_info in await list_hp_records(event.group_id):
            if str(user_id) in bound_users or not _has_hp_display(hp_info):
                continue
            name = await base.resolve_display_name(bot, event, user_id)
            feedback += f"{name} {hp_info.get_info()}\n"
        # NPC/怪物血量
        for npc in await list_npc_health(event.group_id):
            feedback += f"{npc.name} {npc.hp_info.get_info()}\n"
        feedback = feedback.strip()
        if not feedback:
            feedback = text.TXT_HP_INFO_NONE
        await hp_matcher.finish(feedback)

    # 删除（.hp del 名称[多个用 / 分隔] / .hp clr 清空全部）——仅作用于 NPC 血量记录
    # （2026-09-21 语义修订：不再删除自己/他人的角色卡——早先 del/clr 无对象
    #  即删除整张角色卡，粒度超出 .hp 语义且易误触；删整卡由 .角色卡清除 负责）
    if arg_str.startswith("del") or arg_str.startswith("clr"):
        del_arg = arg_str[3:].strip()
        if arg_str.startswith("clr"):
            count = await clear_npc_health(event.group_id)
            if count:
                await hp_matcher.finish(text.TXT_HP_CLR_DONE.format(n=count))
            await hp_matcher.finish(text.TXT_HP_CLR_NONE)
        if not del_arg:
            await hp_matcher.finish(text.TXT_HP_DEL_NO_TARGET)
        feedback_list: List[Union[str, Message]] = []
        for target_name in [n.strip() for n in del_arg.split("/") if n.strip()]:
            source_key, target_id = await search_target(target_name, event.group_id)
            if source_key == "multiple":
                feedback_list.append(text.TXT_HP_INFO_MULTI.format(
                    name_list=target_id.split("/")
                ))
            elif source_key == "pc":
                # @ 目标命中玩家角色卡：以真 @ 段提示（.init del 引导见 .init 的 @ 支持）
                target_qq = onebot_v11.parse_mention_token(target_name)
                if target_qq is not None:
                    feedback_list.append(
                        onebot_v11.at_reply(target_qq, text.TXT_HP_DEL_PC_TARGET_AT)
                    )
                else:
                    feedback_list.append(
                        text.TXT_HP_DEL_PC_TARGET.format(name=target_name)
                    )
            elif source_key == "pc_hp":
                # 无绑定卡、但有 HP 记录的玩家：同样不属于 NPC，不走删除
                target_qq = onebot_v11.parse_mention_token(target_name)
                if target_qq is not None:
                    feedback_list.append(
                        onebot_v11.at_reply(
                            target_qq, text.TXT_HP_DEL_PC_RECORD_AT
                        )
                    )
                else:
                    feedback_list.append(
                        text.TXT_HP_DEL_PC_RECORD.format(name=target_name)
                    )
            elif source_key == "npc":
                await delete_npc_health(event.group_id, target_id)
                feedback_list.append(text.TXT_HP_DEL.format(name=target_id))
            elif source_key == "at_miss":
                feedback_list.append(
                    onebot_v11.at_reply(target_id, text.TXT_MENTION_NO_CHAR)
                )
            else:
                feedback_list.append(
                    text.TXT_HP_INFO_MISS_HINT.format(name=target_name)
                )
        await hp_matcher.finish(base.join_lines(feedback_list))

    # 查看 @ 目标（无操作符：.hp @小明 / .hp @小明 @小红）
    view_qqs = _parse_mention_targets(arg_str)
    if view_qqs is not None:
        view_lines: List[Union[str, Message]] = []
        for qq in view_qqs:
            character, hp_info = await _load_player_hp(event.group_id, qq)
            name = await base.resolve_display_name(
                bot, event, qq, char_name=character.name if character else ""
            )
            if _has_hp_display(hp_info):
                view_lines.append(text.TXT_HP_INFO.format(
                    name=name, hp_info=hp_info.get_info()
                ))
            else:
                view_lines.append(
                    onebot_v11.at_reply(qq, text.TXT_HP_INFO_MISS.format(name=name))
                )
        await hp_matcher.finish(base.join_lines(view_lines))

    # 调整 HP（流程：先定位操作符，再剥离目标前缀，最后解析调整表达式）。
    # 操作符 = 首个 + / - / = ，或首个空格（设置目标 HP）；空格后紧跟 +/-/= 时
    # 按该符号识别（如 ".hp 爱丽丝 -d8+3+d6" 的 - 是伤害操作符，空格不视为设置符）。
    cmd_type: str = "="
    max_len = 2 ** 20
    cmd_index_eq = arg_str.find("=") if "=" in arg_str else max_len
    cmd_index_add = arg_str.find("+") if "+" in arg_str else max_len
    cmd_index_sub = arg_str.find("-") if "-" in arg_str else max_len
    cmd_index_space = arg_str.find(" ") if " " in arg_str else max_len
    if cmd_index_space != max_len:
        next_non_space = arg_str[cmd_index_space + 1:].lstrip()
        if next_non_space and next_non_space[0] in "+-=":
            cmd_index_space = max_len  # 空格不是设置符，改由符号自身定位
    cmd_index = min(cmd_index_eq, cmd_index_add, cmd_index_sub, cmd_index_space)
    if cmd_index == max_len:
        cmd_index = -1
    elif cmd_index == cmd_index_eq or cmd_index == cmd_index_space:
        cmd_type = "="
    elif cmd_index == cmd_index_add:
        cmd_type = "+"
    elif cmd_index == cmd_index_sub:
        cmd_type = "-"

    target_list: list[Tuple[str, str, float]] = []
    if cmd_index == 0:
        # 直接以操作符开头，无目标指定
        arg_str = arg_str[1:].strip()
    elif cmd_index > 0:
        target_part = arg_str[:cmd_index].strip()
        # 扩展：".hp 10/30 (5)" 这类无目标的写法，若无此判断会把 "10/30" 当
        # 目标搜索而报错；目标部分含 "/" 或 "(" 时视为表达式而非目标，不做剥离
        if target_part and "/" not in target_part and "(" not in target_part:
            arg_str = arg_str[cmd_index + 1:].strip()
            # 目标以 ;（半角/全角）分隔实现 AOE 多目标一次结算；含 @ 标记时
            # 空白也作为分隔符，支持 .hp @玩家 地精 -d4 这类 @ 与名称混写
            for target_intent in _split_target_intents(target_part):
                target_name, damage_factor = _split_target_suffix(target_intent)
                if cmd_type != "-" and damage_factor != 1.0:
                    await hp_matcher.finish(text.TXT_HP_FACTOR_DMG_ONLY)
                source_key, target_id = await search_target(target_name, event.group_id)
                if source_key in ("pc", "pc_hp", "npc"):
                    target_list.append((source_key, target_id, damage_factor))
                elif source_key == "at_miss":
                    # @ 的玩家无卡也无记录：HP 与角色卡解耦，按需建立无卡记录
                    target_list.append(("pc_hp", target_id, damage_factor))
                elif source_key == "multiple":
                    names = target_id.split("/")
                    feedback = text.TXT_HP_INFO_MULTI.format(name_list=names)
                    await hp_matcher.finish(feedback)
                else:
                    feedback = text.TXT_HP_INFO_MISS_HINT.format(name=target_name)
                    await hp_matcher.finish(feedback)

    if not target_list:
        # 游离 @（.hp -d4 @小明 / .hp 20/30 @小明 / @小明 .hp -d4）：@ 未落在
        # 目标位置时不再静默按发送者自身结算，改为提示目标位置写法、不执行
        if mentioned_qqs:
            await hp_matcher.finish(text.TXT_MENTION_HP_POS_HINT)
        target_list = [("pc", str(event.user_id), 1.0)]

    # 解析调整表达式（arg_str 已剥离目标前缀与操作符）
    # 伤害位置的 击晕 参数先摘出，其余按原有路径解析（两版规则都有击晕，
    # 只是结果不同：见下方结算分支，按群级规则版本决定归 0 还是归 1）
    stun_request = False
    if cmd_type == "-":
        stun_split = _split_stun_keyword(arg_str)
        if stun_split is not None:
            arg_str, stun_request = stun_split
    elif _split_stun_keyword(arg_str) is not None:
        # 击晕只描述「打到 0 HP 时的处置」，设置/治疗写法里没有意义
        await hp_matcher.finish(text.TXT_HP_STUN_DMG_ONLY)
    # 伤害位置的武器写法（-武器名[副手/重击/偷袭]伤害[±加值]（来源））先解析为表达式
    weapon_damage: Optional[_WeaponDamageExpr] = None
    if cmd_type == "-":
        weapon_damage = await _resolve_hp_damage_expression(event, arg_str)
        if weapon_damage is not None:
            if weapon_damage.combined is not None:
                # 多武器写法：各项已分别掷骰，直接用合成结果参与 HP 结算
                # （不再解析表达式，避免同一批骰子被掷第二遍）
                hp_cur = weapon_damage.combined
                hp_max = hp_temp = None
                error = None
                arg_str = ""
            else:
                arg_str = weapon_damage.expression
    if weapon_damage is None or weapon_damage.combined is None:
        hp_cur, hp_max, hp_temp, error = _parse_hp_args(arg_str)
    if error:
        await hp_matcher.finish(text.TXT_HP_MOD_ERR.format(error=error))

    # 应用调整
    feedback = ""
    # 武器伤害写法的表头（与 .X伤害 回复同款：掷伤与扣血一条命令）——单目标用
    # 实际结算值（含抗性/易伤折算），多目标用掷出的原始值（折算逐目标显示）；
    # 多武器写法（2026-09-27）改由逐项行 + 合计行输出（与 .X伤害 同一套组装）
    if weapon_damage is not None and hp_cur is not None:
        raw_total = hp_cur.get_val()
        # 表头数值与实际生效伤害一致（抗性/易伤只施加一次，见 HPService.effective_damage）
        total = (
            HPService.effective_damage(hp_cur, target_list[0][2])
            if len(target_list) == 1
            else max(0, raw_total)
        )
        owner_name = await base.resolve_display_name(
            bot, event, weapon_damage.owner_qq, char_name=weapon_damage.owner_name
        )
        if weapon_damage.multis:
            # 多武器：逐项行沿用 .X伤害 的同一套组装（weapon.append_multi_damage_lines），
            # 逐项读数即解析阶段掷出的结果（与参与扣血的合成值同源）
            parts = weapon_damage.multis
            damage_types = {part.damage_type for part in parts}
            feedback += text.TXT_HP_MULTI_WEAPON_DAMAGE_HEAD.format(
                name=owner_name,
                weapons="、".join(part.weapon for part in parts),
                total=total,
                type=(
                    next(iter(damage_types)) if len(damage_types) == 1 else "多类型"
                ),
            ) + "\n"
            lines: List[str] = []
            append_multi_damage_lines(lines, owner_name, weapon_damage.rolls or [])
            feedback += "\n".join(lines) + "\n"
        else:
            feedback += text.TXT_HP_WEAPON_DAMAGE_HEAD.format(
                name=owner_name,
                weapon=weapon_damage.weapon_name,
                total=total,
                type=weapon_damage.damage_type,
                note=weapon_damage.note,
            ) + "\n"
    for source_key, target_id, damage_factor in target_list:
        if source_key == "npc":
            # NPC/怪物：血量条目按需创建（目标经先攻表/已有记录解析而来）；
            # 怪物不做死亡豁免（击晕参数对 NPC 也不适用——NPC 直接被打到 0）
            hp_info = await get_npc_health(event.group_id, target_id)
            if hp_info is None:
                hp_info = npc_hp_info()
            mod_info = HPService.process_roll_result(
                hp_info, cmd_type, hp_cur, hp_max, hp_temp,
                short_feedback=(len(target_list) > 1),
                damage_factor=damage_factor,
            )
            await save_npc_health(event.group_id, target_id, hp_info)
            feedback += text.TXT_HP_MOD.format(name=target_id, hp_mod=mod_info) + "\n"
            continue

        character, hp_info = await _load_player_hp(event.group_id, target_id)
        if hp_info is None:
            # HP 与角色卡解耦：无卡玩家按需建立群级 HP 记录
            hp_info = HPInfo()

        # 击晕（留活口）：近战把目标打到 0 HP 时可改为不杀。两版都有这条规则，
        # 差别在结果（2026-10-01 修订，此前误按「仅 2024 可用」实现）：
        # - 2014：HP 降到 0、陷入昏迷，**但伤势稳定**（不再掷死亡豁免）；
        # - 2024：改为降到 1 点 HP，昏迷并开始一次短休。
        # 两版都直接结束战斗状态下的死亡豁免流程，不走濒死。
        if stun_request and cmd_type == "-" and hp_info.is_init:
            rules_version = await char_rules.rules_version(event.group_id)
            hp_info.hp_temp = 0
            hp_info.clear_death_state()
            if rules_version == char_rules.RULES_2024:
                hp_info.hp_cur = 1
                hp_info.is_alive = True
                stun_text = text.TXT_HP_STUN_2024
            else:
                hp_info.hp_cur = 0
                hp_info.is_alive = False
                hp_info.is_stable = True
                stun_text = text.TXT_HP_STUN_2014
            await _save_player_hp(event.group_id, target_id, hp_info, character)
            name = await base.resolve_display_name(
                bot, event, target_id,
                char_name=character.name if character else "",
            )
            feedback += text.TXT_HP_STUN.format(name=name, effect=stun_text) + "\n"
            continue

        # 死亡豁免联动（2026-10-01）：伤害使 HP 归 0 → 进入濒死；
        # 濒死/稳定中再受伤 → 记失败（重击 +2）、伤害 ≥ HP 上限即死。
        # 「本来就在 0 HP 挨打」与「这一击打到 0」扣血后都是 0，故在扣血前
        # 先取昏迷状态（is_alive）；治疗使 HP 回正 → heal() 内已清死亡豁免状态
        was_unconscious = not hp_info.is_alive
        mod_info = HPService.process_roll_result(
            hp_info, cmd_type, hp_cur, hp_max, hp_temp,
            short_feedback=(len(target_list) > 1),
            damage_factor=damage_factor,
        )

        death_line = ""
        if cmd_type == "-" and hp_cur is not None and hp_info.is_init:
            damage = HPService.effective_damage(hp_cur, damage_factor)
            is_critical = weapon_damage is not None and "重击" in weapon_damage.note
            transition, death_line = HPService.apply_death_save_on_damage(
                hp_info, damage,
                critical=is_critical, was_unconscious=was_unconscious,
            )
            if transition == HPService.DEATH_TRANSITION_ENTERED:
                death_line = text.TXT_DS_ENTER
            elif transition == HPService.DEATH_TRANSITION_RESTART:
                death_line = text.TXT_DS_RESTART
            if death_line:
                # HP 状态行由 process_roll_result 在死亡豁免结算**之前**生成，
                # 濒死计数会落在数值后面（如「濒死(成功0 失败0)」却已记 1 次失败）。
                # 结算完重新生成一次，状态行与播报取同一份数据（2026-10-01 修订）。
                mod_info = HPService.refresh_hp_status(
                    hp_info, mod_info, short_feedback=(len(target_list) > 1)
                )

        await _save_player_hp(event.group_id, target_id, hp_info, character)

        name = await base.resolve_display_name(
            bot, event, target_id,
            char_name=character.name if character else "",
        )
        feedback += text.TXT_HP_MOD.format(name=name, hp_mod=mod_info) + "\n"
        if death_line:
            feedback += f"{death_line}\n"

    await hp_matcher.finish(feedback.strip())


@ds_matcher.handle()
async def handle_death_save(bot: Bot, event: MessageEvent) -> None:
    """处理 .死亡豁免（.ds）：掷豁免 / 手动裁决 / 状态 / 重置。

    目标恒为发送者本人（死亡豁免是本人回合开始时的动作；DM 代掷用 @玩家
    仍可后续按需追加——当前不做，见设计文档「明确不做」）。
    """
    if not isinstance(event, GroupMessageEvent):
        await ds_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    character, hp_info = await _load_player_hp(event.group_id, event.user_id)
    name = await base.resolve_display_name(
        bot, event, char_name=character.name if character else ""
    )
    # 死亡豁免与 HP 记录绑定：计数、自然 20 回血、0 HP 受伤记失败都要读写 HP。
    # 无卡玩家先用 .hp 当前/最大 记一次即可，不要求建卡（2026-10-23 文案修订）。
    if hp_info is None:
        await ds_matcher.finish(text.TXT_DS_NO_RECORD.format(name=name))
    if not hp_info.is_init:
        await ds_matcher.finish(text.TXT_DS_NO_HP.format(name=name))

    # ── 状态查询
    if rest == "状态":
        await ds_matcher.finish(
            text.TXT_DS_STATUS.format(name=name, hp_info=hp_info.get_info())
        )

    # ── 手动裁决：成功+N / 失败+N（N 缺省 1，全角数字容错）
    manual = re.match(r"^(成功|失败)\s*\+?\s*([0-9０-９]+)?$", rest)
    if manual is not None:
        kind, count_str = manual.group(1), manual.group(2)
        count = int(count_str.translate(_FULLWIDTH_DIGITS)) if count_str else 1
        fatal = (
            hp_info.add_death_success(count) if kind == "成功"
            else hp_info.add_death_failure(count)
        )
        await _save_player_hp(
            event.group_id, event.user_id, hp_info, character
        )
        if fatal:
            message = (
                text.TXT_DS_MANUAL_STABLE if kind == "成功"
                else text.TXT_DS_MANUAL_DEATH
            )
            await ds_matcher.finish(f"{name}：{message}")
        template = (
            text.TXT_DS_MANUAL_SUCCESS if kind == "成功"
            else text.TXT_DS_MANUAL_FAILURE
        )
        await ds_matcher.finish(template.format(
            n=count, success=hp_info.ds_success, failure=hp_info.ds_failure
        ))

    # ── 重置（复活裁决）：清空计数、稳定与死亡标记
    if rest == "重置":
        hp_info.clear_death_state()
        if hp_info.hp_cur < 0:
            hp_info.hp_cur = 0
        await _save_player_hp(
            event.group_id, event.user_id, hp_info, character
        )
        await ds_matcher.finish(text.TXT_DS_RESET.format(
            name=name, hp_info=hp_info.get_info()
        ))

    # ── 掷死亡豁免：先解析修饰串（写法无效时给用法引导，不掷骰）
    advantage = 0
    if rest.startswith("优势"):
        advantage, rest = 1, rest[2:]
    elif rest.startswith("劣势"):
        advantage, rest = -1, rest[2:]
    mod_str = rest.strip()
    if mod_str and not mod_str.startswith(("+", "-")):
        await ds_matcher.finish(text.TXT_DS_USAGE)
    if mod_str and not WEAPON_BONUS_RE.match(mod_str):
        await ds_matcher.finish(text.TXT_DS_BAD_MOD.format(mod=mod_str))

    if hp_info.is_dead:
        await ds_matcher.finish(text.TXT_DS_DEAD)
    if hp_info.is_stable:
        await ds_matcher.finish(text.TXT_DS_STABLE)
    if hp_info.hp_cur > 0:
        await ds_matcher.finish(text.TXT_DS_NOT_DYING)
    # 首次调用即为「开始死亡豁免」：HP 归 0 但尚未掷过时清空残留计数
    if hp_info.ds_success == 0 and hp_info.ds_failure == 0:
        hp_info.clear_death_state(revive=False)

    try:
        result_str, state, _value, _nat20, _nat1 = HPService.roll_death_save(
            hp_info, advantage, mod_str
        )
    except AssertionError as exc:
        await ds_matcher.finish(str(exc))
    await _save_player_hp(
        event.group_id, event.user_id, hp_info, character
    )
    await ds_matcher.finish(text.TXT_DS_RESULT.format(
        name=name, result=result_str, state=state, hp_info=hp_info.get_info()
    ))


async def _load_rest_character(
    bot: Bot, event: MessageEvent, matcher: Matcher
) -> Tuple[DNDCharacter, str, str]:
    """取休息命令的目标角色卡 → ``(角色, 展示名, 去掉 @ 后的剩余文本)``。

    @ 在本群无角色卡时以真 @ 消息段引导建卡并终止；无 @ 时取发送者本人。
    目标解析对 ``.短休`` / ``.生命骰`` / ``.长休`` 三处共用。
    """
    rest = (base.get_command_rest_with_mentions(event) or "").strip()
    mentions = onebot_v11.iter_mentions(rest)
    target_qq = mentions[0] if mentions else None
    remaining = onebot_v11.strip_mentions(rest).strip()

    if target_qq is not None:
        character = await get_character(event.group_id, target_qq)
        if character is None or not character.is_init:
            await matcher.finish(
                onebot_v11.at_reply(target_qq, text.TXT_MENTION_NO_CHAR)
            )
        name = await base.resolve_display_name(
            bot, event, target_qq, char_name=character.name
        )
    else:
        character = await get_character(event.group_id, event.user_id)
        if character is None or not character.is_init:
            name = await base.resolve_display_name(bot, event)
            await matcher.finish(text.TXT_LONG_REST_MISS.format(name=name))
        name = await base.resolve_display_name(
            bot, event, char_name=character.name
        )
    return character, name, remaining


def _format_rest_changes(changes: List[Tuple[str, int, int, int]]) -> str:
    """把恢复变更列表拼成「名称 旧/上限 → 新/上限」的顿号串。"""
    return "；".join(
        text.TXT_REST_CHANGE_ITEM.format(
            label=label, old=old, new=new, max=maximum
        )
        for label, old, new, maximum in changes
    )


@long_rest_matcher.handle()
async def handle_long_rest(bot: Bot, event: MessageEvent) -> None:
    """处理 .长休：HP / 生命骰 / 能力 / 法术位 / 准备提示。"""
    if not isinstance(event, GroupMessageEvent):
        await long_rest_matcher.finish(text.TXT_GROUP_ONLY)

    character, name, _rest = await _load_rest_character(
        bot, event, long_rest_matcher
    )
    # 生命骰恢复量按群级规则版本：2024 恢复全部已消耗、2014 回复总枚数的一半
    rules_version = await char_rules.rules_version(event.group_id)
    version_2024 = rules_version == char_rules.RULES_2024
    rest_info = character.hp_info.long_rest(dice_full=version_2024)
    lines = [f"{name}进行了一次长休", rest_info or "没有需要恢复的内容"]

    feature_changes = RestService.recover_features(
        character.features, REST_LONG
    )
    if feature_changes:
        lines.append(
            text.TXT_REST_FEATURE_CHANGE.format(
                items=_format_rest_changes(feature_changes)
            )
        )
    slot_changes = RestService.restore_slots(
        character.spell_slots, REST_LONG
    )
    if slot_changes:
        lines.append(
            text.TXT_REST_SLOT_CHANGE.format(
                items=_format_rest_changes(slot_changes)
            )
        )
    # 只有「可准备法术」的职业才提示重新准备（2014 已知型施法者不提示）
    if character.spells and RestService.should_remind_preparation(
        version_2024, character.char_class
    ):
        lines.append(text.TXT_LONG_REST_PREPARE_HINT)

    await save_character(character)
    await long_rest_matcher.finish("\n".join(lines))


@short_rest_matcher.handle()
async def handle_short_rest(bot: Bot, event: MessageEvent) -> None:
    """处理 .短休：恢复短休类能力与契约魔法法术位，提示可用生命骰。"""
    if not isinstance(event, GroupMessageEvent):
        await short_rest_matcher.finish(text.TXT_GROUP_ONLY)

    character, name, _rest = await _load_rest_character(
        bot, event, short_rest_matcher
    )
    hp_info = character.hp_info
    if hp_info.is_init and hp_info.is_dead:
        await short_rest_matcher.finish(text.TXT_SHORT_REST_DEAD)
    if hp_info.is_init and hp_info.hp_cur <= 0:
        await short_rest_matcher.finish(text.TXT_SHORT_REST_ZERO_HP)

    lines = [text.TXT_SHORT_REST.format(name=name)]
    feature_changes = RestService.recover_features(
        character.features, REST_SHORT
    )
    if feature_changes:
        lines.append(
            text.TXT_REST_FEATURE_CHANGE.format(
                items=_format_rest_changes(feature_changes)
            )
        )
    slot_changes = RestService.restore_slots(
        character.spell_slots, REST_SHORT
    )
    if slot_changes:
        lines.append(
            text.TXT_REST_SLOT_CHANGE.format(
                items=_format_rest_changes(slot_changes)
            )
        )
    if not feature_changes and not slot_changes:
        lines.append(text.TXT_SHORT_REST_NOTHING)

    if hp_info.is_init and hp_info.hp_dice_type > 0 and hp_info.hp_dice_max > 0:
        if hp_info.hp_dice_num <= 0:
            lines.append(
                text.TXT_SHORT_REST_DICE_EMPTY.format(max=hp_info.hp_dice_max)
            )
        else:
            lines.append(
                text.TXT_SHORT_REST_DICE.format(num=hp_info.hp_dice_num)
            )
    else:
        lines.append(text.TXT_SHORT_REST_NO_DICE)

    if feature_changes or slot_changes:
        await save_character(character)
    await short_rest_matcher.finish("\n".join(lines))


@hp_dice_matcher.handle()
async def handle_hp_dice(bot: Bot, event: MessageEvent) -> None:
    """处理 .生命骰：按卡面骰面与群级规则版本花费生命骰回血。"""
    if not isinstance(event, GroupMessageEvent):
        await hp_dice_matcher.finish(text.TXT_GROUP_ONLY)

    character, name, remaining = await _load_rest_character(
        bot, event, hp_dice_matcher
    )
    amount = 1
    if remaining:
        if not remaining.isdigit():
            await hp_dice_matcher.finish(text.TXT_HD_USAGE)
        amount = int(remaining)
    if amount < 1:
        await hp_dice_matcher.finish(text.TXT_HD_AMOUNT_INVALID)

    hp_info = character.hp_info
    if hp_info.is_init and hp_info.is_dead:
        await hp_dice_matcher.finish(text.TXT_HD_DEAD)
    if hp_info.is_init and hp_info.hp_cur <= 0:
        await hp_dice_matcher.finish(text.TXT_HD_ZERO_HP)

    rules_version = await char_rules.rules_version(event.group_id)
    con_mod = character.ability_info.get_modifier(
        ABILITY_LIST.index("体质")
    )
    ok, mod_info = HPService.use_hp_dice_ex(
        hp_info,
        amount,
        con_mod,
        version_2024=rules_version == char_rules.RULES_2024,
    )
    if not ok:
        await hp_dice_matcher.finish(mod_info)
    await save_character(character)
    await hp_dice_matcher.finish(
        text.TXT_HD_RESULT.format(name=name, result=mod_info)
    )
