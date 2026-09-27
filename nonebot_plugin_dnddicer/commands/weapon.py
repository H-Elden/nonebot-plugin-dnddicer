"""自定义武器/法术命令：``.X攻击`` / ``.X命中``（攻击检定）与 ``.X伤害``。

命令面（非固定命令名，按消息模式触发，与检定点命令同款机制）：

- ``.短剑攻击`` / ``.短剑命中``：以角色卡 ``$武器$`` 段中该武器的命中加值掷
  攻击检定（如 ``1D20+6``）；支持 ``N#`` 批量（``.2#短剑攻击``）、``优势`` /
  ``劣势``、``±`` 临时加值（可组合）与 ``@玩家``（DM 代掷）；
- ``.短剑伤害``：掷伤害骰并提示伤害类型（``造成了 8 点穿刺伤害``）；后缀
  ``副手`` / ``重击`` / ``偷袭`` 写在「伤害」之前、可任意组合
  （如 ``.短剑重击偷袭伤害``）——
  副手 = 剔除伤害表达式中全部常数项（不加任何加值）；重击 = 所有骰子项骰数
  ×2（固定加值不变、偷袭骰同样翻倍）；偷袭 = 按角色卡职业（游荡者）与整体
  等级自动附加 N 颗 d6（暂不支持兼职，见角色卡职业段校验）。

**机器人不做命中判断**（不判 AC，由玩家/DM 自行比较）；攻击检定 d20 出目
20/1 追加 DND 术语提示（``天然20：重击！`` 引导 ``.X重击伤害``、``天然1：必失``），
不使用 .r 的「大成功/大失败」文案。

匹配与让位：

- 固定命令（``match_command_name`` 命中，如 ``.角色卡攻击``）让位、不接管；
- 属性攻击检定点已退役（2026-09-24）：``.力量攻击`` 一类输入不再有检定点语义，
  按武器命令处理、落回「未找到武器」的默认提示（武器名经录入校验不得与检定
  条目重名，两者天然互斥）。

武器名对照发送者（或 @ 目标）当前角色卡的武器列表；查无该武器给出引导提示。

名称匹配支持**模糊匹配（子串）**（2026-09-27 新增）：``.短剑攻击`` 可命中卡上
的「精灵短剑」、``.匕首`` 可命中「+1匕首」——匹配顺序与 ``.init`` / ``.hp``
的目标搜索一致，**精确匹配（大小写不敏感）优先**，其次子串匹配；子串同时落在
多件武器上时报歧义并列出候选（``.长攻击`` 命中「长剑」「长弓」时不猜），
``.删除武器`` 同样支持子串，``.设置武器`` 保持精确名称（同名覆盖判定不做模糊，
避免「短剑」误覆盖「精灵短剑」）。

**多武器一次结算**（2026-09-27 新增，双武器战斗的常见打法）：一条命令写多件
武器、用 ``、`` / ``，`` / ``/`` 分隔（``.刺剑伤害、匕首副手伤害``、
``.刺剑攻击优势、匕首攻击+2``），逐件结算后汇总——伤害给出「共计造成了 N 点X伤害」
（类型不同则逐类型列出再合计），攻击按武器逐个给出命中加值与掷骰块。约定：

- 除第一项以外的每一项都要写全「武器名[后缀]伤害」/「武器名[后缀]攻击」——
  ``.刺剑、匕首伤害`` 不成立（否则无法与武器名里的分隔符区分，武器名本身禁含
  ``/`` 与逗号）；
- 后缀与 ``±`` 临时加值**各写各的**，只作用于该项（``.刺剑伤害+1d6、匕首伤害``）；
- ``@玩家`` 只写在末尾，对全部项生效；
- 多项时**不支持 ``N#`` 批量**（``.2#短剑攻击、匕首攻击``），会提示拆成两条命令；
- 单项命令的解析与文案逐字不变（多武器是叠加能力、不是替换）。
"""

from __future__ import annotations

import re
from typing import Dict, List, NamedTuple, Optional, Tuple

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher
from nonebot.plugin import on_message
from nonebot.rule import Rule

from ..character.constants import WEAPON_DAMAGE_SUFFIX_LIST, WEAPON_MAX_COUNT
from ..character.models import DNDCharacter, WeaponInfo
from ..character.services import (
    WEAPON_BONUS_RE,
    apply_critical_to_damage,
    get_sneak_attack_dice,
    parse_weapon_list,
    strip_damage_constants,
)
from ..config import get_config
from ..data.characters import get_character, save_character
from ..engine.roll.ast_engine.adapter import exec_roll_exp_unified
from ..engine.roll.roll_utils import RollDiceError
from ..engine.roll.result import RollResult
from ..platform import onebot_v11
from . import base, text

#: 攻击命令体模式：([1-9]#)? 武器名 (攻击|命中) 剩余(优劣势/加值/@)
_WEAPON_ATTACK_PATTERN = re.compile(r"^([1-9]#)?(.+?)(攻击|命中)(.*)$")
#: 伤害命令体模式：名称与后缀 伤害 剩余(@)
_WEAPON_DAMAGE_PATTERN = re.compile(r"^(.+?)伤害(.*)$")
#: 伤害关键词（与 _WEAPON_DAMAGE_PATTERN 同字面量；多项写法的逐项判定共用）
WEAPON_DAMAGE_SUFFIX = "伤害"
#: 攻击/命中关键词（多项写法的逐项判定共用）
WEAPON_ATTACK_KEYWORDS = ("攻击", "命中")


def parse_weapon_attack_body(body: str) -> Optional[Tuple[int, str, str]]:
    """解析武器攻击命令体 → (次数, 武器名, 修正串)；无效返回 None。

    修正串可含 优势/劣势 前缀、±临时加值与 @ 标记（由 handler 处理）。
    """
    matched = _WEAPON_ATTACK_PATTERN.match(body)
    if not matched:
        return None
    time_part, name_part, _kind, tail = matched.groups()
    if not name_part.strip():
        return None
    times = int(time_part[:-1]) if time_part else 1
    return times, name_part.strip(), tail.strip()


def parse_weapon_attack_entry(body: str) -> Optional[Tuple[str, str]]:
    """识别「[N#]武器名(攻击|命中)…」形态 → (武器名, 关键词)；否则 None。

    供 ``.hp`` 伤害位置上的误用引导（攻击检定不是伤害掷骰，应改用
    「武器名伤害」，见 commands/hp.py）；与 parse_weapon_attack_body 共用
    同一模式，区别只在返回内容。
    """
    matched = _WEAPON_ATTACK_PATTERN.match(body)
    if not matched:
        return None
    _time_part, name_part, kind, _tail = matched.groups()
    if not name_part.strip():
        return None
    return name_part.strip(), kind


def _strip_damage_suffixes(entry_part: str) -> Tuple[str, List[str]]:
    """从「名称+后缀」段自右向左逐个剥出伤害后缀 → (名称, 后缀列表)。

    保证剥完名称非空（名为「重击」的武器不会被剥空误判）；单项解析与多武器
    逐项解析共用（2026-09-27 抽出）。
    """
    suffixes: List[str] = []
    name = entry_part.strip()
    while name:
        for word in WEAPON_DAMAGE_SUFFIX_LIST:
            if name.endswith(word) and len(name) > len(word):
                name = name[: -len(word)].strip()
                suffixes.append(word)
                break
        else:
            break
    return name, suffixes


def parse_weapon_damage_body(body: str) -> Optional[Tuple[str, List[str], str]]:
    """解析武器伤害命令体 → (武器名, 后缀列表, 剩余文本)；无效返回 None。

    后缀（副手/重击/偷袭）写在「伤害」之前、可任意组合；名称段从右向左逐个
    剥后缀，且保证剥完名称非空（名为「重击」的武器不会被剥空误判）。
    「伤害」之后的剩余文本仅允许 @ 标记与 ±临时加值（由 handler 校验其余内容）。
    """
    matched = _WEAPON_DAMAGE_PATTERN.match(body)
    if not matched:
        return None
    entry_part, tail = matched.groups()
    name, suffixes = _strip_damage_suffixes(entry_part)
    if not name:
        return None
    return name, suffixes, tail.strip()


def _is_weapon_body(body: str) -> bool:
    """命令体是否是武器命令（攻击/命中/伤害之一，供 rule 使用）。"""
    return (
        parse_weapon_attack_body(body) is not None
        or parse_weapon_damage_body(body) is not None
    )


# =========================================================================
# 多武器一次结算（2026-09-27）：分隔符切分与逐项解析
# =========================================================================


class WeaponEntry(NamedTuple):
    """武器命令单项：武器名 / 攻击-命中关键词（伤害项为空串）/ 后缀 / 修正串。

    ``tail`` 对攻击项是「优劣势 + ±加值」、对伤害项是「±加值」；两者都由
    handler 按同一套 ``WEAPON_BONUS_RE`` 校验（优劣势前缀先摘除）。
    """

    name: str
    kind: str
    suffixes: List[str]
    tail: str


class MultiWeaponError(NamedTuple):
    """多项写法不合法：出错的项 + 由调用方按场景取提示。

    ``message`` 为武器命令的提示（附「多项怎么写」示例）；``hp_message`` 为
    ``.hp`` 伤害位置的提示（写法要带 ``-`` 前缀）；``segment`` 供调用方另拼提示。
    """

    segment: str
    message: str
    hp_message: str


#: 单项武器命令体：名称段（含后缀）与关键词（攻击/命中/伤害）与修正串
#: 注：名称段**整段**捕获（不在这里剥后缀）——后缀由调用方用
#: _strip_damage_suffixes 处理，规则与单项解析完全一致（2026-09-27）
_WEAPON_ENTRY_PATTERN = re.compile(r"^(.+?)(攻击|命中|伤害)(.*)$")
#: 多项写法的分隔符：中文顿号 / 全角逗号 / 半角逗号 / 斜杠（含其全角同形写法）
_MULTI_WEAPON_SEPARATOR_PATTERN = re.compile(r"[、，,/\uFF0C]")
#: 切分时把分隔符统一归一为半角逗号的映射（含全角逗号与斜杠的同形写法）
_SEPARATOR_CANONICAL = {"、": ",", "，": ",", "､": ",", "/": ",", "／": ","}
#: N# 次数前缀（多项写法不支持批量，需先摘出以便给出专门提示）
_WEAPON_TIMES_PATTERN = re.compile(r"^([1-9]#)")

#: 多项写法的正确写法示例（错误提示与文档共用）
MULTI_WEAPON_EXAMPLE = ".刺剑伤害、匕首副手伤害"
#: 多项写法的用法说明（错误提示里附在示例之后）
MULTI_WEAPON_USAGE = (
    f"用法：{MULTI_WEAPON_EXAMPLE}"
    "（多项用 、、，、/ 分隔；除第一件外每件都要写全「武器名[副手/重击/偷袭]伤害[±加值]」，"
    "后缀与加值各写各的）"
)


def multi_weapon_error(segment: str) -> MultiWeaponError:
    """多项写法里某一项不合法的错误（附正确写法示例，用户可直接照抄改正）。"""
    return MultiWeaponError(
        segment=segment,
        message=text.TXT_WEAPON_MULTI_BAD_ENTRY.format(
            entry=segment, usage=MULTI_WEAPON_USAGE
        ),
        hp_message=text.TXT_HP_WEAPON_MULTI_BAD_ENTRY.format(entry=segment),
    )


def has_multi_weapon_separator(body: str) -> bool:
    """命令体是否含多武器分隔符（供 ``.hp`` 的伤害位置判断是否尝试多项写法）。

    只作「是否值得一试」的判断：分隔符可以落在武器名里（如 ``.设置武器 短剑,匕首+4,1d6``
    的伤害执行写法），真正的判定是逐项能否解析成功（见 resolve_weapon_damage_entries）。
    """
    return _MULTI_WEAPON_SEPARATOR_PATTERN.search(body) is not None


def split_weapon_segments(body: str) -> Tuple[Optional[str], List[str]]:
    """按多武器分隔符切分命令体（``、`` / 全角逗号 / 半角逗号 / 斜杠）。

    Returns:
        (N# 前缀，段列表)：段为**未**归一化的原始文本（供错误提示显示用户所写），
        切分后再统一归一化后解析；空段被丢弃。
    """
    times_part = ""
    matched_times = _WEAPON_TIMES_PATTERN.match(body)
    if matched_times:
        times_part = matched_times.group(1)
        body = body[len(times_part):]
    segments = [
        part.strip() for part in _normalize_separators(body).split(",")
    ]
    return (times_part or None), [part for part in segments if part]


def _normalize_separators(text: str) -> str:
    """把 ``、`` / 全角逗号 / 斜杠统一成半角逗号，便于按同一分隔符切分。"""
    return "".join(_SEPARATOR_CANONICAL.get(char, char) for char in text)


def parse_weapon_entry(segment: str) -> Optional[Tuple[str, str, str]]:
    """解析单项武器命令体 → (名称段含后缀, 关键词, 修正串)；不匹配返回 None。

    「武器名[后缀]伤害」与「武器名[后缀]攻击/命中」共用本形态（关键词区分）；
    名称段的**显示口径**由调用方决定：攻击显示用卡上的武器名、多武器伤害保留
    用户输入（与既有的 ``.X伤害`` 提示一致）。后缀由调用方用
    ``_strip_damage_suffixes`` 剥离（与单项解析同一套规则）。
    """
    matched = _WEAPON_ENTRY_PATTERN.match(segment)
    if not matched:
        return None
    name_part, kind, tail = matched.groups()
    name = name_part.strip()
    if not name:
        return None
    return name, kind, tail.strip()


def _split_entry_tail(entry_tail: str) -> Tuple[str, str]:
    """把关键词之后的剩余文本拆成 (项内 ±加值, 其余文本)。

    ``+1d6`` / ``-2`` 这类**末尾**的 ±加值即该项的临时加值（各写各的）；
    其余（如 ``@玩家`` 标记、错写的 ``优势``）留给调用方判定。
    """
    matched = re.search(r"([+-](?:\d*[dD]\d+|\d+))+$", entry_tail)
    if matched is None:
        return "", entry_tail
    return matched.group(0), entry_tail[: matched.start()]


def _pull_mentions(text: str) -> Tuple[str, str]:
    """抽出文本里的 ``@<qq>`` 标记 → (去掉标记后的文本, 标记文本)。

    ``@玩家`` 由 onebot 事件重建为 ``@<qq>`` 文本，可能落在某一项之内
    （``.短剑伤害、匕首伤害 @123``）也可能自成一段；多项写法先整体摘出标记、
    再逐项校验，因此 @目标写在命令末尾即可，不必抠它在哪一项之后。
    """
    mentions = onebot_v11.iter_mentions(text)
    if not mentions:
        return text, ""
    return onebot_v11.strip_mentions(text), "".join(f"@{qq}" for qq in mentions)


def _is_weapon_keyword_entry(segment: str, keyword: str) -> bool:
    """该段是否是「武器名[后缀]关键词[±加值]」形态（只看到关键词与加值，不看名称）。"""
    parsed = parse_weapon_entry(segment)
    return (
        parsed is not None
        and parsed[1] == keyword
        and _split_entry_tail(parsed[2])[1] == ""
    )


def parse_weapon_damage_entries(
    body: str,
) -> Optional[Tuple[List[WeaponEntry], Optional[MultiWeaponError], str]]:
    """解析多项伤害写法（``.刺剑伤害+1d6、匕首副手伤害``）→ (项列表, 错误, 末尾剩余)。

    返回 None 表示「不是多项写法」——没有任何分隔符，或分隔符只落在一项里，
    或没有一项以「…伤害[±加值]」收尾（这些都交给单项解析处理，行为同从前）。
    返回三元组表示已确认是多项写法：error 非 None 时写法不合法（如
    ``.刺剑伤害、匕首``），由调用方给出可读提示；末尾剩余只保留 ``@玩家``
    标记（各项加值已并入各自项），由 handler 按单项同款拆目标。
    """
    body, mentions = _pull_mentions(body)
    _times, segments = split_weapon_segments(body)
    if len(segments) < 2:
        return None
    if not any(
        _is_weapon_keyword_entry(segment, WEAPON_DAMAGE_SUFFIX)
        for segment in segments
    ):
        # 没有任何一项是「…伤害」写法（分隔符只落在别的写法上）：交给单项解析，不接管
        return None
    if not _is_weapon_keyword_entry(segments[-1], WEAPON_DAMAGE_SUFFIX):
        # 末项不是「…伤害」写法：仍判为多项写法，但报专门的写法提示
        return [], multi_weapon_error(segments[-1]), ""

    entries: List[WeaponEntry] = []
    tail = ""
    for segment in segments:
        parsed = parse_weapon_entry(segment)
        if parsed is None or parsed[1] != WEAPON_DAMAGE_SUFFIX:
            return [], multi_weapon_error(segment), ""
        name, _kind, entry_tail = parsed
        name, suffixes = _strip_damage_suffixes(name)
        if not name:
            return [], multi_weapon_error(segment), ""
        bonus, rest = _split_entry_tail(entry_tail)
        entries.append(WeaponEntry(
            name=name, kind="", suffixes=suffixes, tail=bonus
        ))
        tail = rest
    return entries, None, f"{tail}{mentions}"


def parse_weapon_attack_entries(
    body: str,
) -> Optional[Tuple[List[WeaponEntry], Optional[MultiWeaponError], Optional[str], str]]:
    """解析多项攻击写法（``.刺剑攻击优势、匕首攻击+2``）→ (项, 错误, N# 前缀, 剩余)。

    返回 None 表示「不是多项写法」（无分隔符、或没有一项以「…攻击/命中」+可选
    优劣势与加值 收尾），交给单项解析；其余约定与 parse_weapon_damage_entries
    一致，另把 ``N#`` 前缀单独摘出——多项写法不支持批量
    （``.2#短剑攻击、匕首攻击``），由调用方提示。
    """
    body, mentions = _pull_mentions(body)
    times_part, segments = split_weapon_segments(body)
    if len(segments) < 2:
        return None
    if not any(
        _is_weapon_keyword_entry(segment, "攻击")
        or _is_weapon_keyword_entry(segment, "命中")
        for segment in segments
    ):
        return None

    entries: List[WeaponEntry] = []
    tail = ""
    for segment in segments:
        parsed = parse_weapon_entry(segment)
        if parsed is None or parsed[1] == WEAPON_DAMAGE_SUFFIX:
            return [], multi_weapon_error(segment), times_part, ""
        name, kind, entry_tail = parsed
        # 优劣势前缀与检定点同款：写在「攻击」之后、±加值之前（各写各的）
        suffixes: List[str] = []
        mod_str = entry_tail
        for word in ("优势", "劣势"):
            if mod_str.startswith(word):
                suffixes.append(word)
                mod_str = mod_str[len(word):].strip()
                break
        bonus, rest = _split_entry_tail(mod_str)
        entries.append(WeaponEntry(
            name=name, kind=kind, suffixes=suffixes, tail=bonus
        ))
        tail = rest
    return entries, None, times_part, f"{tail}{mentions}"


def _weapon_command_rule() -> Rule:
    async def _checker(event: MessageEvent) -> bool:
        plain = event.get_plaintext().strip()
        if not plain:
            return False
        # 必须以本插件起始符开头，且非已注册固定命令（固定命令优先）
        starts = base.get_command_starts()
        matched_start = next((s for s in starts if plain.startswith(s)), None)
        if matched_start is None:
            return False
        body = plain[len(matched_start):]
        fixed_name, _ = base.match_command_name(body)
        if fixed_name is not None:
            return False
        if _is_weapon_body(body):
            return True
        # 多项写法（2026-09-27）：任一项可解析即接管，具体错误由 handler 给提示
        # （含 N# 批量 + 多项的专门提示；单项的 N# 仍走上面的单项解析）
        _times_part, segments = split_weapon_segments(body)
        if len(segments) < 2:
            return False
        return all(parse_weapon_entry(segment) is not None for segment in segments)

    # 群聊服务门禁（与固定命令一致：未开启服务的群不响应）
    return Rule(_checker) & base.group_service_rule()


def _make_weapon_matcher() -> Matcher:
    priority = get_config().dnddicer_command_priority
    return on_message(_weapon_command_rule(), priority=priority, block=True)


weapon_matcher = _make_weapon_matcher()


def find_exact_weapon(
    weapons: List[WeaponInfo], name: str
) -> Optional[WeaponInfo]:
    """在武器列表中按名称精确查找（大小写不敏感）。

    ``.设置武器`` 的同名覆盖判定专用——**不做模糊匹配**：写成名称的一部分时
    （卡上「精灵短剑」、输入「短剑」）若按子串命中就会覆盖别人的条目。
    """
    lowered = name.lower()
    for weapon in weapons:
        if weapon.name.lower() == lowered:
            return weapon
    return None


def match_weapons(weapons: List[WeaponInfo], name: str) -> List[WeaponInfo]:
    """按名称匹配武器项：精确（大小写不敏感）优先，其次子串模糊匹配。

    2026-09-27 起 ``.X攻击`` / ``.X命中`` / ``.X伤害``、``.hp`` 的武器写法与
    ``.删除武器`` 都可用名称的一部分发起（卡上「精灵短剑」→ ``.短剑攻击``）；
    两级顺序与 ``.init`` / ``.hp`` 的目标搜索同款——先找完全相同的名字
    （大小写不敏感），没有再找包含输入的名字。精确优先保证卡上同时有
    「短剑」与「精灵短剑」时 ``.短剑攻击`` 打的是「短剑」。

    返回候选列表：空 = 未找到、多项 = 歧义（由调用方提示、不猜）。
    """
    lowered = name.lower()
    for weapon in weapons:
        if weapon.name.lower() == lowered:
            return [weapon]
    return [weapon for weapon in weapons if lowered in weapon.name.lower()]


async def resolve_weapon(
    matcher: Matcher, character: DNDCharacter, name: str
) -> WeaponInfo:
    """按名称解析出唯一武器（精确 → 子串）；未找到 / 多件匹配时报错终止命令。

    使用侧（``.X攻击`` / ``.X伤害`` / ``.hp`` 武器写法）共用本实现，
    保证三处口径一致；提示文案里的名称一律用**用户输入**（更便于对照自己写了什么）。
    """
    candidates = match_weapons(character.weapons, name)
    if not candidates:
        await matcher.finish(text.TXT_WEAPON_NOT_FOUND.format(name=name))
    if len(candidates) > 1:
        await matcher.finish(
            text.TXT_WEAPON_VAGUE.format(
                name=name, weapons="/".join(item.name for item in candidates)
            )
        )
    return candidates[0]


def build_damage_expression(
    weapon: WeaponInfo,
    suffixes: List[str],
    level: int,
    char_class: str,
    tail: str = "",
) -> Tuple[str, Optional[str], int]:
    """按后缀（副手 / 重击 / 偷袭）把武器伤害项变换为最终掷骰表达式。

    2026-09-24 起由 ``.X伤害`` 与 ``.hp`` 的伤害位置共用，保证两处语义一致
    （临时加值并入表达式、参与后缀变换：重击时同样翻倍、副手时同样剔常数）。

    Returns:
        (表达式, 错误文案, 偷袭骰数)：错误文案非 None 时表达式不可用，
        由调用方直接回复给用户；偷袭骰数供 ``.X伤害`` 的读数标注使用。
    """
    expression = weapon.damage_expr + tail
    if "副手" in suffixes:
        expression = strip_damage_constants(expression)
        if not expression:
            return "", text.TXT_WEAPON_OFFHAND_NO_DICE.format(weapon=weapon.name), 0

    sneak_dice = 0
    if "偷袭" in suffixes:
        sneak_dice = get_sneak_attack_dice(level, char_class)
        if sneak_dice <= 0:
            error = (
                text.TXT_WEAPON_SNEAK_NO_CLASS.format(weapon=weapon.name)
                if not char_class
                else text.TXT_WEAPON_SNEAK_NOT_ROGUE.format(char_class=char_class)
            )
            return "", error, 0
        expression += f"+{sneak_dice}d6"

    if "重击" in suffixes:
        expression = apply_critical_to_damage(expression)
    return expression, None, sneak_dice


def _format_weapon_lines(weapons: List[WeaponInfo]) -> str:
    """武器列表的编号多行展示（.设置武器 反馈用，2026-09-24 用户要求格式化）。"""
    return "\n".join(
        f"{index}. {weapon.get_info()}"
        for index, weapon in enumerate(weapons, start=1)
    )


def build_damage_note(suffixes: List[str], sneak_dice: int, is_crit: bool) -> str:
    """伤害后缀的读数标注（如「（重击）」「（含偷袭3D6）」）；无后缀返回空串。

    由 ``.X伤害`` 与 ``.hp`` 武器伤害写法的表头共用（偷袭骰重击时同样翻倍）。
    """
    note_parts: List[str] = []
    if "副手" in suffixes:
        note_parts.append("副手：不加任何加值")
    if is_crit:
        note_parts.append("重击")
    if "偷袭" in suffixes:
        actual_dice = sneak_dice * (2 if is_crit else 1)
        note_parts.append(f"含偷袭{actual_dice}D6")
    return f"（{'，'.join(note_parts)}）" if note_parts else ""


async def _load_target_character(
    event: MessageEvent, target_qq: Optional[str]
) -> DNDCharacter:
    """取 @ 目标（无 @ 时取发送者）的角色卡；无卡给引导提示并终止本命令。"""
    if target_qq is not None:
        character = await get_character(event.group_id, target_qq)
        if character is None or not character.is_init:
            await weapon_matcher.finish(
                onebot_v11.at_reply(target_qq, text.TXT_MENTION_NO_CHAR)
            )
    else:
        character = await get_character(event.group_id, event.user_id)
        if character is None or not character.is_init:
            await weapon_matcher.finish(text.TXT_CHAR_MISS)
    return character


async def _handle_attack(
    bot: Bot, event: MessageEvent, times: int, weapon_name: str, mod_str: str
) -> None:
    """攻击检定：D20（可优劣势）+ 武器命中加值 + 临时加值。"""
    # 修正串中的 @ 目标（DM 代掷，与检定点同规则）
    target_qq, mod_str = base.split_target_mention(mod_str)
    character = await _load_target_character(event, target_qq)

    weapon = await resolve_weapon(weapon_matcher, character, weapon_name)
    if weapon.no_attack:
        # x 标记：纯伤害法术（如 火球术），不做攻击检定
        await weapon_matcher.finish(
            text.TXT_WEAPON_NO_ATTACK.format(weapon=weapon.name)
        )

    # 解析临时优劣势（修正串开头的 优势/劣势；与检定点同款）
    advantage = 0
    if mod_str.startswith("优势"):
        advantage = 1
        mod_str = mod_str[2:]
    elif mod_str.startswith("劣势"):
        advantage = -1
        mod_str = mod_str[2:]
    mod_str = mod_str.strip()

    roll_exp = "D20"
    if advantage > 0:
        roll_exp += "优势"
    elif advantage < 0:
        roll_exp += "劣势"
    roll_exp += weapon.attack_bonus + mod_str

    # 注：不做「预校验掷骰」——那会额外消耗一次随机数；表达式问题走下面的
    # 正式掷骰错误路径（归因到用户输入的修正串或武器加值，给出可读提示）
    results: List[str] = []
    roll_results: List[RollResult] = []
    for _ in range(times):
        try:
            roll_result = exec_roll_exp_unified(roll_exp)
        except RollDiceError as exc:
            bad = mod_str if mod_str else weapon.attack_bonus
            await weapon_matcher.finish(
                text.TXT_WEAPON_BAD_MOD.format(mod=bad, reason=exc.info)
            )
        results.append(roll_result.get_complete_result())
        roll_results.append(roll_result)

    name = await base.resolve_display_name(
        bot, event, target_qq, char_name=character.name
    )
    display_check = f"{weapon.name}攻击检定"
    if times > 1:
        display_check = f"{times}次{display_check}"

    nat_state = text.format_nat_attack_state(roll_results, weapon.name)
    if nat_state:
        # 天然 20/1 提示单独成行（2026-09-24 用户要求）
        results.append(nat_state)

    await weapon_matcher.finish(
        text.TXT_WEAPON_ATTACK.format(
            name=name,
            check=display_check,
            hint=text.format_weapon_attack_hint(weapon.attack_bonus, advantage),
            result="\n".join(results),
        )
    )


async def _handle_damage(
    bot: Bot,
    event: MessageEvent,
    weapon_name: str,
    suffixes: List[str],
    tail: str,
) -> None:
    """伤害结算：伤害表达式 + 临时加值 + 后缀变换（副手 / 重击 / 偷袭）。"""
    # 「伤害」之后的剩余文本：允许 @ 标记与 ± 临时加值（如升环火球术 .火球术伤害+1d6）
    target_qq, mod_str = base.split_target_mention(tail)
    if mod_str and not WEAPON_BONUS_RE.match(mod_str):
        await weapon_matcher.finish(text.TXT_WEAPON_DAMAGE_TAIL.format(tail=mod_str))
    character = await _load_target_character(event, target_qq)

    weapon = await resolve_weapon(weapon_matcher, character, weapon_name)

    is_off_hand = "副手" in suffixes
    is_crit = "重击" in suffixes
    is_sneak = "偷袭" in suffixes

    # 后缀变换与 .hp 的伤害位置共用同一实现（临时加值并入表达式、参与后缀变换）
    expression, error, sneak_dice = build_damage_expression(
        weapon, suffixes, character.ability_info.level, character.char_class, mod_str
    )
    if error:
        await weapon_matcher.finish(error)

    try:
        roll_result = exec_roll_exp_unified(expression)
    except RollDiceError as exc:
        await weapon_matcher.finish(
            text.TXT_WEAPON_BAD_MOD.format(mod=expression, reason=exc.info)
        )
    total = roll_result.get_val()

    note = build_damage_note(suffixes, sneak_dice, is_crit)

    name = await base.resolve_display_name(
        bot, event, target_qq, char_name=character.name
    )
    await weapon_matcher.finish(
        text.TXT_WEAPON_DAMAGE.format(
            name=name,
            weapon=weapon.name,
            total=total,
            type=weapon.damage_type,
            note=note,
            result=roll_result.get_complete_result(),
        )
    )


# =========================================================================
# 多武器一次结算（2026-09-27）：逐项结算 + 汇总
# =========================================================================


class WeaponDamageRoll(NamedTuple):
    """单项结算结果：展示名 / 伤害类型 / 读数标注 / 掷骰结果 / 伤害值 / 是否无骰。

    ``no_dice`` 为「该项没有任何骰子」（后手后缀剔除全部固定加值后只剩常数）
    ——读数行仍逐项照常展示，但该行数值不计入合计（见 build_multi_damage_summary）。
    """

    weapon: str
    damage_type: str
    note: str
    result: RollResult
    total: int
    no_dice: bool


def _has_dice(expression: str) -> bool:
    """表达式是否含骰子（后手后缀剔除固定加值后可能只剩常数）。"""
    return re.search(r"\d*[dD]\d+", expression) is not None


def append_multi_damage_lines(
    lines: List[str], owner_name: str, rolls: List[WeaponDamageRoll]
) -> None:
    """把多项伤害的逐项行 + 合计行追加到反馈行列表（``.X伤害`` 与 ``.hp`` 共用）。

    行形态（2026-09-27 用户定稿）::

        1. 塔莉用【刺剑】造成了 10 点穿刺伤害：
        1D8+4=[6]+4=10
        2. 塔莉用【匕首】造成了 3 点穿刺伤害（副手：不加任何加值）：
        1D4=[3]=3

        共计造成了 13 点穿刺伤害
    """
    for index, rolled in enumerate(rolls, start=1):
        lines.append(
            text.TXT_WEAPON_DAMAGE_ITEM.format(
                no=index,
                name=owner_name,
                weapon=rolled.weapon,
                total=rolled.total,
                type=rolled.damage_type,
                note=rolled.note,
                result=rolled.result.get_complete_result(),
            )
        )
    lines.append("")
    lines.append(build_multi_damage_summary(rolls))


def build_multi_damage_summary(rolls: List[WeaponDamageRoll]) -> str:
    """多项伤害的合计行：类型相同一句合计，类型不同则逐类型列出再合计。

    只统计**掷了骰**的项（后手后缀会剔除全部固定加值，只剩常数、无骰可掷的项
    不进类型合计，其数值仍照常展示在逐项行里）；没有可计入项时只报总伤害。
    类型不同时按类型连接（顿号分隔，三项以上同样可读）。
    """
    total = sum(rolled.total for rolled in rolls)
    ordered: List[Tuple[str, int]] = []
    for rolled in rolls:
        if rolled.no_dice:
            continue
        for index, (damage_type, value) in enumerate(ordered):
            if damage_type == rolled.damage_type:
                ordered[index] = (damage_type, value + rolled.total)
                break
        else:
            ordered.append((rolled.damage_type, rolled.total))
    if not ordered:
        return text.TXT_WEAPON_MULTI_TOTAL_PLAIN.format(total=total)
    if len(ordered) == 1:
        return text.TXT_WEAPON_MULTI_TOTAL_ONE.format(type=ordered[0][0], total=total)
    parts = "、".join(
        text.TXT_DAMAGE_PART.format(total=value, type=damage_type)
        for damage_type, value in ordered
    )
    return text.TXT_WEAPON_MULTI_TOTAL_MIXED.format(parts=parts, total=total)


def multi_damage_head(owner_name: str, rolls: List[WeaponDamageRoll], total: int) -> str:
    """多项伤害的标题行（类型相同报类型；多类型时报「多类型」，明细见逐项行）。"""
    damage_types = {rolled.damage_type for rolled in rolls}
    return text.TXT_WEAPON_MULTI_DAMAGE_HEAD.format(
        name=owner_name,
        weapons="、".join(rolled.weapon for rolled in rolls),
        total=total,
        type=next(iter(damage_types)) if len(damage_types) == 1 else "多类型",
    )


async def _handle_multi_damage(
    bot: Bot, event: MessageEvent, entries: List[WeaponEntry], tail: str
) -> None:
    """多武器伤害：逐项解析 + 逐项掷骰 + 合计（见 append_multi_damage_lines）。

    ``tail`` 由解析层收窄为「仅末项的 @目标标记」（各项加值已并入各自项，
    见 parse_weapon_damage_entries）。
    """
    target_qq, mod_str = base.split_target_mention(tail)
    if mod_str:
        await weapon_matcher.finish(text.TXT_WEAPON_MULTI_TAIL.format(tail=mod_str))
    character = await _load_target_character(event, target_qq)

    # 先全部解析、全部变换表达式，最后才掷骰：任一项不合法时不消耗随机数、
    # 也不会出现「前几项已掷、后面报错」的半截输出
    plan: List[Tuple[WeaponInfo, str, str]] = []  # 武器 / 表达式 / 读数标注
    for entry in entries:
        weapon = await resolve_weapon(weapon_matcher, character, entry.name)
        expression, error, sneak_dice = build_damage_expression(
            weapon, entry.suffixes, character.ability_info.level,
            character.char_class, entry.tail,
        )
        if error:
            await weapon_matcher.finish(error)
        plan.append((
            weapon,
            expression,
            build_damage_note(
                entry.suffixes, sneak_dice, "重击" in entry.suffixes
            ),
        ))

    rolls: List[WeaponDamageRoll] = []
    for weapon, expression, note in plan:
        try:
            roll_result = exec_roll_exp_unified(expression)
        except RollDiceError as exc:
            await weapon_matcher.finish(
                text.TXT_WEAPON_BAD_MOD.format(mod=expression, reason=exc.info)
            )
        rolls.append(WeaponDamageRoll(
            weapon=weapon.name,
            damage_type=weapon.damage_type,
            note=note,
            result=roll_result,
            total=roll_result.get_val(),
            no_dice=not _has_dice(expression),
        ))

    name = await base.resolve_display_name(
        bot, event, target_qq, char_name=character.name
    )
    total = sum(rolled.total for rolled in rolls)
    lines = [multi_damage_head(name, rolls, total)]
    append_multi_damage_lines(lines, name, rolls)
    await weapon_matcher.finish("\n".join(lines))


async def _handle_multi_attack(
    bot: Bot,
    event: MessageEvent,
    entries: List[WeaponEntry],
    tail: str,
    times_part: Optional[str],
) -> None:
    """多武器攻击：逐项攻击检定 + 逐项武器行 + 汇总掷骰块。

    多项写法**不支持 ``N#`` 批量**（每项各自的命中加值与优劣势都要落到对应武器上，
    ``N#`` 与多项同写没有明确语义），报提示引导拆成两条命令。``tail`` 由解析层
    收窄为「仅末项的 @目标标记」（各项加值已并入各自项）。
    """
    if times_part:
        await weapon_matcher.finish(text.TXT_WEAPON_MULTI_TIMES.format(times=times_part))

    target_qq, mod_str = base.split_target_mention(tail)
    if mod_str:
        await weapon_matcher.finish(text.TXT_WEAPON_MULTI_TAIL.format(tail=mod_str))
    character = await _load_target_character(event, target_qq)

    plan: List[Tuple[WeaponInfo, int, str, str]] = []  # 武器 / 优劣势 / 修正串 / 表达式
    for entry in entries:
        weapon = await resolve_weapon(weapon_matcher, character, entry.name)
        if weapon.no_attack:
            await weapon_matcher.finish(
                text.TXT_WEAPON_NO_ATTACK.format(weapon=weapon.name)
            )
        advantage = 1 if "优势" in entry.suffixes else (
            -1 if "劣势" in entry.suffixes else 0
        )
        expression = "D20"
        if advantage > 0:
            expression += "优势"
        elif advantage < 0:
            expression += "劣势"
        expression += weapon.attack_bonus + entry.tail
        plan.append((weapon, advantage, entry.tail, expression))

    lines: List[str] = []
    for index, (weapon, advantage, mod_str, expression) in enumerate(plan, start=1):
        try:
            roll_result = exec_roll_exp_unified(expression)
        except RollDiceError as exc:
            bad = mod_str if mod_str else weapon.attack_bonus
            await weapon_matcher.finish(
                text.TXT_WEAPON_BAD_MOD.format(mod=bad, reason=exc.info)
            )
        lines.append(
            text.TXT_WEAPON_MULTI_ATTACK_ITEM.format(
                no=index,
                weapon=weapon.name,
                hint=text.format_weapon_attack_hint(weapon.attack_bonus, advantage),
            )
        )
        lines.append(roll_result.get_complete_result())
        nat_state = text.format_nat_attack_state([roll_result], weapon.name)
        if nat_state:
            # 天然 20/1 提示单独成行（2026-09-24 用户要求），紧随该武器的掷骰行
            lines.append(nat_state)

    name = await base.resolve_display_name(
        bot, event, target_qq, char_name=character.name
    )
    check = "、".join(f"{weapon.name}攻击检定" for weapon, *_ in plan)
    await weapon_matcher.finish(
        text.TXT_WEAPON_MULTI_ATTACK.format(
            name=name, check=check, result="\n".join(lines)
        )
    )


@weapon_matcher.handle()
async def handle_weapon(bot: Bot, event: MessageEvent) -> None:
    """处理 .X攻击 / .X命中 / .X伤害（rule 已确保命中且参数可解析）。"""
    if not isinstance(event, GroupMessageEvent):
        await weapon_matcher.finish(text.TXT_GROUP_ONLY)

    # 用带标记文本解析：@ 目标保留在修正串中（规则层仍基于纯文本）
    text_body = onebot_v11.strip_leading_mentions(
        onebot_v11.rebuild_text_with_mentions(event)
    ).strip()
    start = next(
        (s for s in base.get_command_starts() if text_body.startswith(s)), None
    )
    if start is None:  # 理论不可达（rule 已过滤），防御性兜底
        return
    body = text_body[len(start):]

    # 多武器写法优先（项数 ≥ 2 且逐项可解析时才算命中，否则回落到单项路径）
    multi_attack = parse_weapon_attack_entries(body)
    if multi_attack is not None:
        entries, error, times_part, multi_tail = multi_attack
        if error is not None:
            await weapon_matcher.finish(error.message)
        await _handle_multi_attack(bot, event, entries, multi_tail, times_part)
        return
    multi_damage = parse_weapon_damage_entries(body)
    if multi_damage is not None:
        entries, error, multi_tail = multi_damage
        if error is not None:
            await weapon_matcher.finish(error.message)
        await _handle_multi_damage(bot, event, entries, multi_tail)
        return

    attack = parse_weapon_attack_body(body)
    if attack is not None:
        await _handle_attack(bot, event, *attack)
        return
    damage = parse_weapon_damage_body(body)
    if damage is not None:
        await _handle_damage(bot, event, *damage)
        return
    # 理论不可达（rule 已过滤）：不响应


# =========================================================================
# 武器管理命令（.设置武器 / .删除武器，2026-09-24 拍板新增）
# =========================================================================

_HELP_SET_WEAPON = (
    "设置/修改自定义武器（供 .X攻击 / .X命中 / .X伤害 使用）：\n"
    "用法：.设置武器 短剑+6,1d4+4穿刺（名称+命中加值,伤害表达式+类型；多项用 / 分隔）\n"
    "同名武器会被覆盖；无参数时查看当前武器列表"
)
set_weapon_matcher = base.on_dnd_command("设置武器", _HELP_SET_WEAPON)

_HELP_DEL_WEAPON = (
    "删除自定义武器：.删除武器 短剑（支持模糊匹配，多个用 / 分隔）"
)
del_weapon_matcher = base.on_dnd_command("删除武器", _HELP_DEL_WEAPON)


@set_weapon_matcher.handle()
async def handle_set_weapon(event: MessageEvent) -> None:
    """处理 .设置武器（增/改/列出；仅操作本人角色卡）。"""
    if not isinstance(event, GroupMessageEvent):
        await set_weapon_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await set_weapon_matcher.finish(text.TXT_CHAR_MISS)

    if not rest:
        if not character.weapons:
            await set_weapon_matcher.finish(text.TXT_WEAPON_LIST_EMPTY)
        await set_weapon_matcher.finish(
            text.TXT_WEAPON_LIST.format(
                count=len(character.weapons),
                items=_format_weapon_lines(character.weapons),
            )
        )

    try:
        new_weapons = parse_weapon_list(rest, tuple(base.get_registered_commands()))
    except AssertionError as exc:
        await set_weapon_matcher.finish(str(exc))

    merged: List[WeaponInfo] = list(character.weapons)
    set_names: List[str] = []
    for weapon in new_weapons:
        # 同名覆盖判定走精确匹配（与使用/删除的模糊匹配区分，见 find_exact_weapon）
        existing = find_exact_weapon(merged, weapon.name)
        if existing is not None:
            merged[merged.index(existing)] = weapon
        else:
            merged.append(weapon)
        set_names.append(weapon.name)
    if len(merged) > WEAPON_MAX_COUNT:
        await set_weapon_matcher.finish(f"武器数量最多 {WEAPON_MAX_COUNT} 件")

    character.weapons = merged
    await save_character(character)
    await set_weapon_matcher.finish(
        text.TXT_WEAPON_SET.format(
            names="/".join(set_names),
            count=len(merged),
            items=_format_weapon_lines(merged),
        )
    )


@del_weapon_matcher.handle()
async def handle_del_weapon(event: MessageEvent) -> None:
    """处理 .删除武器（支持 / 分隔多个、名称可只写一部分；仅操作本人角色卡）。

    名称匹配与使用侧同款（精确优先 → 子串）：三项结果分别聚合——已删除 /
    未找到 / 名称不明确（命中多件，列候选、不删）；已有删除动作时才落盘。
    """
    if not isinstance(event, GroupMessageEvent):
        await del_weapon_matcher.finish(text.TXT_GROUP_ONLY)

    rest = (base.get_command_rest(event) or "").strip()
    if not rest:
        await del_weapon_matcher.finish(text.TXT_WEAPON_DEL_USAGE)
    character = await get_character(event.group_id, event.user_id)
    if character is None or not character.is_init:
        await del_weapon_matcher.finish(text.TXT_CHAR_MISS)

    names = [item.strip() for item in rest.split("/") if item.strip()]
    remained: List[WeaponInfo] = list(character.weapons)
    deleted: List[str] = []
    missing: List[str] = []
    vague: List[str] = []
    for name in names:
        candidates = match_weapons(remained, name)
        if not candidates:
            missing.append(name)
        elif len(candidates) > 1:
            vague.append(text.TXT_WEAPON_DEL_VAGUE_ITEM.format(
                name=name, weapons="/".join(item.name for item in candidates)
            ))
        else:
            remained.remove(candidates[0])
            deleted.append(candidates[0].name)

    lines: List[str] = []
    if deleted:
        if missing:
            lines.append(text.TXT_WEAPON_DEL_PARTIAL.format(
                deleted="/".join(deleted), missing="/".join(missing)
            ))
        else:
            lines.append(text.TXT_WEAPON_DEL.format(deleted="/".join(deleted)))
    elif missing:
        lines.append(text.TXT_WEAPON_DEL_MISS.format(missing="/".join(missing)))
    if vague:
        lines.append(text.TXT_WEAPON_DEL_VAGUE.format(items="；".join(vague)))
    if not lines:  # 理论不可达（names 非空时必有结论），防御性兜底
        lines.append(text.TXT_WEAPON_DEL_MISS.format(missing="/".join(names)))

    if deleted:
        character.weapons = remained
        await save_character(character)
    await del_weapon_matcher.finish("\n".join(lines))
