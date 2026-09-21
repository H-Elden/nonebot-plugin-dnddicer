"""先攻列表命令：``.init`` / ``.ri`` / ``.先攻``。

迁移自 nonebot-dicepp ``module/initiative/initiative_command.py``（commit
732ff74）的命令语法与反馈手感，数据落 localstore（data/initiative.py）：
- ``.ri``：投掷先攻入表——``.ri`` 自己、``.ri(+|-|=)调整``、``.ri 表达式 名称``
  （空格分隔）、``.ri20 地精`` 固定值、``.ri 地精/兽人`` 复数同掷、
  ``.ri 3#地精`` 批量（a/b/c 后缀）、名称内可带 优势/劣势/±额外加值
  （如 ``.ri+2 地精优势/灵活地精+1``）；
- ``.init`` / ``.先攻``：无参数或 list/列表 查看；clr/清除 清空；del/删除
  删除条目（支持 A/B 多删与部分匹配）；first/fst/提前 同值条目提前；
  swap/交换 互换两个条目（单参数时与自己换）；
- ``.先攻检定``（角色卡检定点命令）掷出结果自动入表——联动入口在本文件
  ``add_initiative_entities``。

与 DicePP 的差异（已注于各函数）：
- 不迁移 DicePP 的 get_nickname API 刷新：实体名称为入表时快照（角色名 →
  群名片/昵称 → QQ 号），离线可用；绑定 QQ 的实体重掷时会替换旧条目；
- 不迁移 import 子指令（解析 ".xxx 先攻: N" 文本批量导入，格式晦涩、价值低）。

NPC 血量联动（2026-09-14，对齐 DicePP npc_health 语义）：
- 先攻列表展示 NPC 血量（`.hp 名称 ...` 记录，见 commands/hp.py）；
- 清空（.init clr / .br）时清理「未设最大值」的 NPC 临时血量；
- 删除 NPC 条目（.init del）时一并删除其血量记录。

NPC 血量自动回满（2026-09-21，DicePP 所无的有意新增）：
- NPC 以**新条目**加入先攻表时，若其血量记录未标记跨战斗保持且已设上限，
  自动回满并在回复中给出「沿用上次血量 / 跨战斗保持血量」的写法——同名
  NPC 在新一场战斗中通常视为新个体（如多只「地精」）；
- 跨战斗保持（``.npc 持久``，见 commands/npc.py）的条目跳过回满；
- 同名条目在同一场战斗中重掷不触发（避免误清已受伤害）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.matcher import Matcher
from nonebot.plugin import on_message
from nonebot.rule import Rule

from ..character.models import HPInfo
from ..config import get_config
from ..data.characters import list_characters_by_group
from ..data.initiative import clear_init_list, get_init_list, save_init_list
from ..data.npc_health import (
    delete_npc_health,
    get_npc_record,
    list_npc_health,
    save_npc_health,
)
from ..engine.roll.ast_engine.adapter import exec_roll_exp_unified, sift_roll_exp_and_reason
from ..engine.roll.roll_utils import RollDiceError
from ..initiative.models import InitiativeError, InitList
from . import base, text

_HELP_INIT = (
    "显示先攻列表：.init ([可选指令]) [可选指令]:clr 清空先攻列表 del 删除指定"
    "先攻条目 first/fst 提前同值条目 swap 交换两个条目\n"
    "del指令支持部分匹配\n"
    "hp信息也会在先攻列表上显示\n"
    "NPC血量（.hp 名称 ...）随条目展示；清空/删除条目时自动清理\n"
    "示例:\n"
    ".先攻 //查看先攻列表\n"
    ".先攻清除 //清空先攻列表\n"
    ".先攻删除地精 //在先攻列表中删除地精\n"
    ".init del 地精a/地精b/地精c //在先攻列表中删除地精abc\n"
    ".init first 地精 //将地精在相同先攻值中提前\n"
    ".init swap 地精/兽人 //互换地精与兽人的先攻值与位置\n"
    "如需查看投掷先攻相关的指令请输入.help ri\n"
    "如需查看回合与轮次相关的指令请输入.help 战斗轮"
)
_HELP_RI = (
    "投掷先攻：.ri([优劣势][加值]) ([名称][/(名称)...])\n"
    "示例:\n"
    ".ri优势+1 //让自己加入先攻列表\n"
    ".ri20 地精 //将地精以固定先攻20加入先攻列表\n"
    ".ri+2 地精/灵活地精+1/笨拙地精-1 //将3个地精分别加入先攻列表\n"
    ".ri-2 2#食人魔僵尸 //将2个食人魔僵尸(a,b)以相同掷骰加入先攻列表\n"
    "如需查看先攻表格相关的指令请输入.help init\n"
    "如需查看回合与轮次相关的指令请输入.help 战斗轮"
)

# 子指令前缀 → (mode, 剥除长度)；顺序保证前缀无歧义
_SUB_COMMANDS: Tuple[Tuple[str, str, int], ...] = (
    ("clr", "clear", 3),
    ("清除", "clear", 2),
    ("del", "delete", 3),
    ("刪除", "delete", 2),
    ("删除", "delete", 2),
    ("first", "first", 5),
    ("fst", "first", 3),
    ("提前", "first", 2),
    ("swap", "swap", 4),
    ("交换", "swap", 2),
    ("list", "inspect", 4),
    ("列表", "inspect", 2),
)


def _initiative_rule() -> Rule:
    """命中 .init/.先攻/.ri；.先攻检定 交给角色卡检定点命令（对齐 DicePP）。

    群聊服务门禁与固定命令一致（未开启服务的群不响应，见 base.group_service_rule）。
    """

    async def _checker(event: MessageEvent) -> bool:
        parsed = base.parse_command_text(event.get_plaintext())
        if parsed is None:
            return False
        name, rest = parsed[1], parsed[2]
        if name not in ("init", "先攻", "ri"):
            return False
        if name == "先攻" and rest.lstrip().startswith("检定"):
            return False
        return True

    return Rule(_checker) & base.group_service_rule()


for _name in ("init", "先攻"):
    base.register_command(_name, _HELP_INIT)
base.register_command("ri", _HELP_RI)
base.register_command("投掷先攻", _HELP_RI)  # 帮助关键字别名（同文不重复列表）

initiative_matcher: Matcher = on_message(
    _initiative_rule(), priority=get_config().dnddicer_command_priority, block=True
)


# =========================================================================
# 名称解析与目标搜索
# =========================================================================


async def resolve_self_name(
    event: MessageEvent, group_id: int | str, user_id: int | str
) -> str:
    """返回绑定玩家自身的先攻展示名：角色卡姓名 → 事件群名片/昵称 → QQ 号。

    先攻检定与 .ri（无显式名称）共用本解析，保证同一玩家的条目名一致；
    与 DicePP 的差异：不调用 get_nickname API 实时刷新，取入表时快照。
    """
    from ..data.characters import get_character

    character = await get_character(group_id, user_id)
    if character is not None and character.is_init and character.name:
        return character.name
    return base.get_display_name(event)


def find_valid_entities(name_list: List[str], global_list: List[str]) -> Tuple[List[str], str]:
    """大小写无关的条目名匹配（精确 → 模糊 substring），返回 (有效名列表, 错误文案)。

    移植 DicePP initiative_command.find_valid_entities（含同名残留去重语义）。
    """
    result_list: List[str] = []
    feedback: str = ""
    lower_to_origs: Dict[str, List[str]] = {}
    for orig in global_list:
        lower_to_origs.setdefault(orig.lower(), []).append(orig)

    for name in name_list:
        name_lower = name.lower()
        if name_lower in lower_to_origs:
            origs = lower_to_origs[name_lower]
            if len(set(origs)) == 1:
                result_list.append(origs[0])
            else:
                feedback += text.TXT_INIT_ERROR.format(
                    error_info=f"列表中存在大小写不同的同名条目 {origs}, 联系开发者"
                ) + "\n"
        else:
            possible_res: List[str] = list(dict.fromkeys(
                orig for orig in global_list if name_lower in orig.lower()
            ))
            if len(possible_res) == 0:
                feedback += text.TXT_INIT_ENTITY_NOT_FOUND.format(name=name) + "\n"
            elif len(possible_res) > 1:
                feedback += text.TXT_INIT_ENTITY_VAGUE.format(
                    name=name, name_list=possible_res
                ) + "\n"
            else:
                result_list.append(possible_res[0])
    return result_list, feedback


# =========================================================================
# 入表（.ri 与 .先攻检定 共用）
# =========================================================================


async def add_initiative_entities(
    result_dict: Dict[str, Tuple[int, str]],
    owner_id: str,
    group_id: int | str,
) -> str:
    """把掷骰结果加入先攻表，返回反馈文案。

    Args:
        result_dict: 条目名 → (先攻值, 掷骰过程文本)（key 为 "" 时绑定 owner）。
        owner_id: 非空代表这些条目绑定的玩家 QQ（无显式名称的 .ri 本人掷骰）；
            DicePP 的语义为整个请求一个 owner（NPC 显式命名时传 ""）。
        group_id: 目标群号。

    行为（对齐 DicePP add_initiative_entities）：
    - 同先攻值可并存，输出提示让 DM 用 .init first 决定先后；
    - 同名条目重掷：旧条目被替换，并提示"你重复投掷了先攻"；
    - 绑定 QQ 的玩家重掷：替换该玩家旧条目（DicePP 依赖 get_nickname 改名
      判重，本插件直接用 owner 判重，效果一致且离线可用）。
    - 本插件新增：NPC 以新条目入表时按需自动回满血量并给出提示
      （DicePP 所无，见模块头「NPC 血量自动回满」）。
    """
    init_data = await get_init_list(group_id)
    if init_data is None:
        init_data = InitList(group_id=str(group_id))

    # 相同掷骰过程文本的条目合并播报（.ri 3#地精 只报一次掷骰结果）
    final_result_dict: Dict[str, Tuple[List[str], int]] = {}
    for name, (roll_val, roll_str) in result_dict.items():
        if roll_str not in final_result_dict:
            final_result_dict[roll_str] = ([], roll_val)
        final_result_dict[roll_str][0].append(name)

    repeatted = False
    same_warn = ""
    feedback_list: List[str] = []
    #: NPC 自动回满条目：(名称, 回满值, 上次值)
    refill_list: List[Tuple[str, str, str]] = []
    for roll_str, (name_list, roll_val) in final_result_dict.items():
        for name in name_list:
            # 按现状（含将被替换的旧条目）扫描重复/同值提示
            has_same = False
            same: List[str] = []
            already_present = any(e.name == name for e in init_data.entities)
            for entity in init_data.entities:
                if (owner_id and entity.owner == owner_id) or entity.name == name:
                    repeatted = True
                if entity.init == roll_val:
                    has_same = True
                    same.append(entity.name)
            # 绑定玩家旧条目先删（名字可能不同源），再入新条目
            if owner_id:
                for stale in [
                    e for e in init_data.entities
                    if e.owner == owner_id and e.name != name
                ]:
                    try:
                        init_data.del_entity(stale.name)
                    except InitiativeError:
                        pass
            try:
                init_data.add_entity(name, owner_id, roll_val)
            except InitiativeError as exc:
                feedback_list.append(
                    text.TXT_INIT_ERROR.format(error_info=exc.info)
                )
                continue
            if has_same:
                sames = "".join(f" / {same_name}" for same_name in same)
                same_warn += "\n" + text.TXT_INIT_ENTITY_SAME_LIST.format(
                    entity_list=name + sames
                )
            # NPC 新条目入表：按需自动回满（同名重掷不触发）
            if not owner_id and not already_present:
                refilled = await _auto_refill_npc_health(name, group_id)
                if refilled is not None:
                    refill_list.append(refilled)
        feedback_list.append(text.TXT_INIT_ROLL.format(
            name=", ".join(name_list), init_result=roll_str
        ))

    feedback = ""
    roll_feedback = "\n".join(feedback_list)
    if repeatted:
        # 注：DicePP 原版此处直接拼接会缺换行，这里补上
        feedback += text.TXT_INIT_ENTITY_REPEAT + ("\n" if roll_feedback else "")
    feedback += roll_feedback
    if same_warn:
        feedback += "\n" + text.TXT_INIT_ENTITY_SAME + same_warn
    if refill_list:
        if len(refill_list) == 1:
            refill_name, now_hp, last_hp = refill_list[0]
            feedback += "\n" + text.TXT_INIT_NPC_REFILL_ONE.format(
                name=refill_name, hp_info=now_hp, last_hp=last_hp
            )
        else:
            items = "、".join(
                f"{name} {now_hp}（上次 {last_hp}）"
                for name, now_hp, last_hp in refill_list
            )
            feedback += "\n" + text.TXT_INIT_NPC_REFILL_MULTI.format(items=items)

    await save_init_list(init_data)
    return feedback


async def _auto_refill_npc_health(
    name: str, group_id: int | str
) -> Optional[Tuple[str, str, str]]:
    """NPC 以新条目入先攻表时按需回满血量，返回 (名称, 回满值, 上次值)。

    仅处理「未标记跨战斗保持、已设最大值、当前值低于最大值」的记录——默认
    语义为同名 NPC 在新一场战斗中视为新个体；``.npc 持久`` 标记的记录跳过。
    未回满（无记录 / 已保持 / 已满 / 纯损失记录）返回 None。
    """
    record = await get_npc_record(group_id, name)
    if record is None or record.persistent:
        return None
    hp_info = record.hp_info
    if hp_info.hp_max <= 0 or hp_info.hp_cur >= hp_info.hp_max:
        return None
    last_hp = f"{hp_info.hp_cur}/{hp_info.hp_max}"
    hp_info.hp_cur = hp_info.hp_max
    hp_info.hp_temp = 0
    hp_info.is_alive = True
    await save_npc_health(group_id, name, hp_info)
    return name, f"{hp_info.hp_cur}/{hp_info.hp_max}", last_hp


# =========================================================================
# .ri 参数解析与掷骰
# =========================================================================


def _parse_ri_arg(arg_str: str) -> Tuple[str, str]:
    """把 .ri 的参数拆成 (掷骰表达式, 条目名段)；移植 DicePP 同名单函数语义。"""
    exp_str = arg_str.strip()
    name = ""
    if len(exp_str) > 0:
        if exp_str[0] in ["+", "-", "*", "/"]:
            exp_str = "D20" + exp_str
        elif exp_str[0] == "=":
            exp_str = exp_str[1:]
        elif "优势" in exp_str or "劣势" in exp_str:
            exp_str = "D20" + exp_str
    if " " in exp_str:
        exp_str, name = exp_str.split(" ", 1)
        name = name.strip()
    elif "#" in exp_str:
        hash_idx = exp_str.index("#")
        num_start = hash_idx
        while num_start > 0 and exp_str[num_start - 1].isdigit():
            num_start -= 1
        name = exp_str[num_start:]
        exp_str = exp_str[:num_start].strip()
        if not exp_str:
            exp_str = "D20"
        elif exp_str[0] in ["+", "-", "*", "/"]:
            exp_str = "D20" + exp_str
    else:
        exp_str, name = sift_roll_exp_and_reason(exp_str)
    return exp_str, name


def _roll_once(exp_str: str) -> Tuple[int, str]:
    """掷一次骰，返回 (数值, 完整过程文本)；失败抛 ValueError（文案面向用户）。"""
    try:
        res = exec_roll_exp_unified(exp_str)
    except RollDiceError as exc:
        raise ValueError(exc.info)
    return res.get_val(), res.get_complete_result()


async def _roll_initiative(event: GroupMessageEvent, arg_str: str) -> None:
    """执行 .ri：掷骰并把结果加入先攻表；失败以用户可见文案直接回复。"""
    exp_str, name = _parse_ri_arg(arg_str)
    owner_id = ""
    if not name:
        name = "self"
        owner_id = str(event.user_id)
    if not exp_str:
        exp_str = "D20"

    name_dict: Dict[str, Tuple[int, str]] = {}
    for n in name.split("/"):
        n = n.strip()
        if not n:
            continue
        final_exp_str = exp_str.lower()
        # 名称内附带 优势/劣势/±加值（对齐 DicePP）
        if ("优势" in n and not n.startswith("优势")) or (
            "劣势" in n and not n.startswith("劣势")
        ):
            if "优势" in n:
                if "d20劣势" in final_exp_str:
                    final_exp_str = final_exp_str.replace("d20劣势", "d20", 1)
                elif "d20" in final_exp_str:
                    final_exp_str = final_exp_str.replace("d20", "d20优势", 1)
            elif "劣势" in n:
                if "d20优势" in final_exp_str:
                    final_exp_str = final_exp_str.replace("d20优势", "d20", 1)
                elif "d20" in final_exp_str:
                    final_exp_str = final_exp_str.replace("d20", "d20劣势", 1)
            n = n.replace("优势", "").replace("劣势", "")
        if "+" in n or "-" in n:
            add_index = n.find("+") if "+" in n else 2 ** 20
            sub_index = n.find("-") if "-" in n else 2 ** 20
            split_index = min(add_index, sub_index)
            final_exp_str = final_exp_str + n[split_index:]
            n = n[:split_index]

        if "#" in n:
            num_str, n = n.split("#", 1)
            try:
                num = int(num_str)
                assert 1 <= num <= 10
            except (ValueError, AssertionError):
                await initiative_matcher.finish(
                    f"{num_str}不是一个有效的数字 (1~10)"
                )
            for i in range(num):
                try:
                    val, display = _roll_once(final_exp_str)
                except ValueError as exc:
                    await initiative_matcher.finish(str(exc))
                name_dict[n + chr(ord("a") + i)] = (val, display)
        else:
            try:
                val, display = _roll_once(final_exp_str)
            except ValueError as exc:
                await initiative_matcher.finish(str(exc))
            name_dict[n] = (val, display)

    result_dict: Dict[str, Tuple[int, str]] = {}
    for n, (val, display) in name_dict.items():
        if n == "self" or n == "我":
            n = await resolve_self_name(event, event.group_id, event.user_id)
        result_dict[n] = (val, display)

    feedback = await add_initiative_entities(
        result_dict, owner_id, event.group_id
    )
    await initiative_matcher.finish(feedback)
    return None


# =========================================================================
# 处理器
# =========================================================================


async def _get_existing(event: GroupMessageEvent) -> InitList:
    """取本群先攻表；不存在则回复并结束。"""
    init_data = await get_init_list(event.group_id)
    if init_data is None or len(init_data.entities) == 0:
        await initiative_matcher.finish(text.TXT_INIT_INFO_NOT_EXIST)
    return init_data  # type: ignore[return-value]  # finish 已抛异常


async def cleanup_temp_npc_health(group_id: int | str) -> None:
    """清空先攻表/新建战斗轮前，删除 NPC 的「临时血量」条目（对齐 DicePP）。

    仅清理先攻表中无主（NPC）、未设置最大值（hp_max==0）且**未标记跨战斗
    保持**的临时血量——多为伤害记录中途留下的条目；已设置最大值的怪物血量
    与 ``.npc 持久`` 标记的条目均保留（跨战斗复用）。.init clr 与 .br 共用
    本函数（.br 与 .init clr 语义等价，仅播报不同）。
    """
    init_data = await get_init_list(group_id)
    if init_data is None:
        return
    for entity in init_data.entities:
        if entity.owner:
            continue
        try:
            record = await get_npc_record(group_id, entity.name)
            if (
                record is not None
                and record.hp_info.hp_max == 0
                and not record.persistent
            ):
                await delete_npc_health(group_id, entity.name)
        except Exception:  # noqa: BLE001 - 清理失败不阻塞清空流程（对齐 DicePP）
            pass


@initiative_matcher.handle()
async def handle_initiative(event: MessageEvent) -> None:
    """处理 .init/.先攻/.ri 命令族。"""
    if not isinstance(event, GroupMessageEvent):
        await initiative_matcher.finish(text.TXT_GROUP_ONLY)

    parsed = base.parse_command_text(event.get_plaintext())
    if parsed is None:
        return  # 理论不可达（rule 已过滤）
    name, rest = parsed[1], parsed[2]

    # .ri：投掷先攻入表
    if name == "ri":
        arg_str = rest.strip()
        await _roll_initiative(event, arg_str)
        return

    # .init/.先攻 子指令
    arg_str = rest.strip()
    mode = "inspect"
    sub_arg = ""
    if arg_str:
        matched = False
        for prefix, sub_mode, length in _SUB_COMMANDS:
            if arg_str.startswith(prefix):
                mode, sub_arg = sub_mode, arg_str[length:]
                matched = True
                break
        if not matched:
            await initiative_matcher.finish(text.TXT_INIT_UNKNOWN.format(
                invalid_command=arg_str,
                sub_command_list="list/列表, clr/清除, del/删除, first/fst/提前, swap/交换",
            ))

    # ── 查看
    if mode == "inspect":
        init_data = await _get_existing(event)
        hp_map: Dict[str, HPInfo] = {}
        for char in await list_characters_by_group(event.group_id):
            if char.hp_info.is_init:
                hp_map[char.user_id] = char.hp_info
        # NPC 血量（无主条目按名称匹配，对齐 DicePP）
        npc_hp_map: Dict[str, HPInfo] = {
            npc.name: npc.hp_info
            for npc in await list_npc_health(event.group_id)
        }

        turn_index = max(0, min(len(init_data.entities) - 1, init_data.turn - 1))
        current = init_data.entities[turn_index]
        init_info = f"当前是第{init_data.round}轮,{current.name}的回合\n"
        for index, entity in enumerate(init_data.entities):
            hp_str = ""
            if entity.owner and entity.owner in hp_map:
                hp_str = hp_map[entity.owner].get_info()
            elif not entity.owner and entity.name in npc_hp_map:
                hp_str = npc_hp_map[entity.name].get_info()
            init_info += f"{index + 1}.{entity.get_info()} {hp_str}\n"
        await initiative_matcher.finish(text.TXT_INIT_INFO.format(
            init_info=init_info.strip()
        ))

    # ── 清空（先清理 NPC 临时血量：未设最大值的条目，对齐 DicePP）
    if mode == "clear":
        await cleanup_temp_npc_health(event.group_id)
        await clear_init_list(event.group_id)
        await initiative_matcher.finish(text.TXT_INIT_INFO_CLR)

    init_data = await _get_existing(event)
    entity_names = [entity.name for entity in init_data.entities]

    # ── 删除（NPC 条目一并删除其血量记录，对齐 DicePP）
    if mode == "delete":
        name_list = [n.strip() for n in sub_arg.split("/")]
        valid_list, feedback = find_valid_entities(name_list, entity_names)
        deleted: List[str] = []
        for valid_name in valid_list:
            entity = next(
                (e for e in init_data.entities if e.name == valid_name), None
            )
            if entity is not None and not entity.owner:
                await delete_npc_health(event.group_id, valid_name)
            try:
                init_data.del_entity(valid_name)
                deleted.append(valid_name)
            except InitiativeError as exc:
                feedback += text.TXT_INIT_ERROR.format(error_info=exc.info) + "\n"
        if deleted:
            for name_del in deleted:
                feedback += text.TXT_INIT_INFO_DEL.format(entity_list=name_del) + "\n"
            await save_init_list(init_data)
        await initiative_matcher.finish(feedback.strip())

    # ── first：同先攻值内提前
    if mode == "first":
        valid_list, feedback = find_valid_entities([sub_arg.strip()], entity_names)
        if feedback:
            await initiative_matcher.finish(feedback.strip())
        name_first = valid_list[0]
        index = init_val = 0
        for i, entity in enumerate(init_data.entities):
            if entity.name == name_first:
                index, init_val = i, entity.init
                break
        for i, entity in enumerate(init_data.entities):
            if i <= index and entity.init == init_val:
                init_data.entities[i], init_data.entities[index] = (
                    init_data.entities[index],
                    init_data.entities[i],
                )
        await save_init_list(init_data)
        await initiative_matcher.finish(text.TXT_INIT_ENTITY_FIRST.format(
            name=name_first
        ))

    # ── swap：互换两个条目（单目标时与自己换）
    if mode == "swap":
        swap_arg = sub_arg.strip()
        if "/" in swap_arg:
            target_l, target_r = (p.strip() for p in swap_arg.split("/", 1))
        elif " " in swap_arg:
            target_l, target_r = (p.strip() for p in swap_arg.split(" ", 1))
        else:
            target_l = await resolve_self_name(event, event.group_id, event.user_id)
            target_r = swap_arg
        name_l, feedback_l = find_valid_entities([target_l], entity_names)
        name_r, feedback_r = find_valid_entities([target_r], entity_names)
        if feedback_l or feedback_r:
            await initiative_matcher.finish(
                (feedback_l + feedback_r).strip()
            )
        l_index = r_index = 0
        for i, entity in enumerate(init_data.entities):
            if entity.name == name_l[0]:
                l_index = i
            elif entity.name == name_r[0]:
                r_index = i
        init_data.entities[l_index].init, init_data.entities[r_index].init = (
            init_data.entities[r_index].init,
            init_data.entities[l_index].init,
        )
        init_data.entities[l_index], init_data.entities[r_index] = (
            init_data.entities[r_index],
            init_data.entities[l_index],
        )
        await save_init_list(init_data)
        await initiative_matcher.finish(text.TXT_INIT_ENTITY_SWAP.format(
            name1=name_l[0], name2=name_r[0]
        ))
