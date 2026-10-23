"""角色卡库持久化（localstore + 单 JSON 文件 + 进程内缓存）。

存储文件为 ``cards.json``，结构：

``{"schema_version": 1, "data": {"cards": {...}, "bindings": {...}}}``

- ``cards``：``<card_id>`` → ``owner`` / ``card_name`` / ``created_in`` / ``character``；
- ``bindings``：``<群号>`` → ``<QQ>`` → ``<card_id>``，每群每人至多一张；
- 不设默认卡；私聊按卡名选中，卡库只有一张时才允许省略卡名。

旧 ``characters.json``（按群 + QQ）不再读取，也不迁移；生产环境没有存量
角色卡数据（2026-10-23 用户确认）。
"""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..character.constants import (
    CARD_LIMIT,
    CARD_NAME_FORBIDDEN_CHARS,
    CARD_NAME_MAX_LEN,
    CARD_NAME_RESERVED,
)
from ..character.models import DNDCharacter
from ..data import get_data_file
from ..data.hp_records import delete_hp_record
from ..data.schema import dump_versioned_dict, load_versioned_dict

_FILENAME = "cards.json"

_cache: Optional[Dict[str, Any]] = None
_lock: Optional[asyncio.Lock] = None


class CardError(Exception):
    """角色卡库错误的基类（命令层映射为用户文案）。"""


class CardNameInvalid(CardError):
    """卡名不合法。"""


class CardNameTaken(CardError):
    """卡名在本人卡库内重复。"""


class CardLimitReached(CardError):
    """达到一个 QQ 的角色卡数量上限。"""


class CardNotFound(CardError):
    """卡不存在、不属于本人或绑定已失效。"""


class CardIncomplete(CardError):
    """卡未建完，不能绑定。"""


def _config_file() -> Path:
    return get_data_file(_FILENAME)


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _empty_store() -> Dict[str, Any]:
    return {"cards": {}, "bindings": {}}


def _normalize_store(raw: Any) -> Dict[str, Any]:
    """把读取结果规范为 cards / bindings 两段；旧结构按空库处理。"""
    if not isinstance(raw, dict):
        return _empty_store()
    cards = raw.get("cards")
    bindings = raw.get("bindings")
    if not isinstance(cards, dict) or not isinstance(bindings, dict):
        return _empty_store()
    clean_bindings: Dict[str, Dict[str, str]] = {}
    for group_id, mapping in bindings.items():
        if not isinstance(mapping, dict):
            continue
        clean_mapping = {
            str(qq): str(card_id)
            for qq, card_id in mapping.items()
            if isinstance(card_id, str)
        }
        if clean_mapping:
            clean_bindings[str(group_id)] = clean_mapping
    return {"cards": cards, "bindings": clean_bindings}


async def _load_if_needed() -> Dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = _config_file()
    raw = await asyncio.to_thread(load_versioned_dict, path)
    _cache = _normalize_store(raw)
    return _cache


async def _dump_locked(data: Dict[str, Any]) -> None:
    path = _config_file()
    await asyncio.to_thread(dump_versioned_dict, path, data)


def _owner(value: int | str) -> str:
    return str(value)


def _group(value: int | str) -> str:
    return str(value)


def validate_card_name(name: str) -> str:
    """校验并规范化玩家输入的卡名；失败抛 ``CardNameInvalid``。"""
    normalized = str(name).strip()
    if not normalized:
        raise CardNameInvalid("卡名不能为空")
    if len(normalized) > CARD_NAME_MAX_LEN:
        raise CardNameInvalid(f"卡名最多 {CARD_NAME_MAX_LEN} 个字符")
    if any(ch.isspace() for ch in normalized):
        raise CardNameInvalid("卡名不能包含空白")
    if any(ch in normalized for ch in CARD_NAME_FORBIDDEN_CHARS):
        raise CardNameInvalid("卡名不能包含 $ 或 @")
    if normalized in CARD_NAME_RESERVED:
        raise CardNameInvalid(f"卡名「{normalized}」是保留词，请换一个")
    return normalized


def _new_card_id(cards: Dict[str, Any]) -> str:
    while True:
        card_id = secrets.token_hex(6)
        if card_id not in cards:
            return card_id


def _entry_owner(entry: Any) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("owner", ""))


def _entry_name(entry: Any) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("card_name", ""))


def _entry_group(entry: Any) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("created_in", ""))


def _model_from_entry(
    card_id: str,
    entry: Any,
    *,
    group_context: Optional[int | str] = None,
) -> Optional[DNDCharacter]:
    if not isinstance(entry, dict):
        return None
    raw = entry.get("character")
    if not isinstance(raw, dict):
        return None
    try:
        character = DNDCharacter.model_validate(raw)
    except Exception:  # noqa: BLE001 - 脏数据按无效卡处理
        return None
    character.card_id = card_id
    character.user_id = _entry_owner(entry)
    character.group_id = (
        _group(group_context)
        if group_context is not None
        else (_entry_group(entry) or "private")
    )
    return character


def _find_card_by_name(
    store: Dict[str, Any], owner: str, name: str
) -> Optional[Tuple[str, Dict[str, Any]]]:
    target = str(name).strip().casefold()
    if not target:
        return None
    for card_id, entry in store["cards"].items():
        if _entry_owner(entry) != owner:
            continue
        if _entry_name(entry).strip().casefold() == target:
            return str(card_id), entry
    return None


def _count_owner_cards(store: Dict[str, Any], owner: str) -> int:
    return sum(
        1 for entry in store["cards"].values() if _entry_owner(entry) == owner
    )


def _copy_model(
    card_id: str,
    entry: Dict[str, Any],
    *,
    group_context: Optional[int | str] = None,
) -> Optional[DNDCharacter]:
    return _model_from_entry(card_id, entry, group_context=group_context)


async def create_card(
    owner: int | str,
    card_name: str,
    created_in: int | str,
    character: DNDCharacter,
) -> str:
    """新建一张卡并返回 card_id；失败抛 ``CardError`` 子类。"""
    owner_str = _owner(owner)
    name = validate_card_name(card_name)
    if not character.is_init or not character.name.strip():
        raise CardIncomplete("角色卡不完整：必须包含姓名、等级与属性")
    character.card_id = ""
    character.user_id = owner_str
    character.group_id = _group(created_in)
    async with _get_lock():
        store = await _load_if_needed()
        if _find_card_by_name(store, owner_str, name) is not None:
            raise CardNameTaken(f"卡名「{name}」已存在，请换一个")
        if _count_owner_cards(store, owner_str) >= CARD_LIMIT:
            raise CardLimitReached(
                f"角色卡最多 {CARD_LIMIT} 张，请先删除不需要的卡"
            )
        card_id = _new_card_id(store["cards"])
        character.card_id = card_id
        store["cards"][card_id] = {
            "owner": owner_str,
            "card_name": name,
            "created_in": _group(created_in),
            "character": character.model_dump(mode="json"),
        }
        await _dump_locked(store)
        return card_id


async def get_card(card_id: str) -> Optional[DNDCharacter]:
    """按 card_id 读取；不存在返回 None。"""
    card_id = str(card_id)
    async with _get_lock():
        store = await _load_if_needed()
        entry = store["cards"].get(card_id)
    return _copy_model(card_id, entry) if entry is not None else None


async def get_card_by_name(
    owner: int | str, card_name: str
) -> Optional[Tuple[str, DNDCharacter]]:
    """按本人卡名精确读取（大小写不敏感）；不存在返回 None。"""
    owner_str = _owner(owner)
    async with _get_lock():
        store = await _load_if_needed()
        found = _find_card_by_name(store, owner_str, card_name)
        if found is None:
            return None
        card_id, entry = found
        model = _copy_model(card_id, entry)
    if model is None:
        return None
    return card_id, model


async def find_cards_by_name(
    owner: int | str, query: str
) -> List[Tuple[str, str, DNDCharacter]]:
    """查看类命令的卡名查找：精确优先，其次子串；多候选原样返回。"""
    owner_str = _owner(owner)
    target = str(query).strip().casefold()
    if not target:
        return []
    async with _get_lock():
        store = await _load_if_needed()
        exact: List[Tuple[str, str, DNDCharacter]] = []
        partial: List[Tuple[str, str, DNDCharacter]] = []
        for card_id, entry in store["cards"].items():
            if _entry_owner(entry) != owner_str:
                continue
            card_name = _entry_name(entry)
            model = _copy_model(str(card_id), entry)
            if model is None:
                continue
            item = (str(card_id), card_name, model)
            folded = card_name.strip().casefold()
            if folded == target:
                exact.append(item)
            elif target in folded:
                partial.append(item)
    return exact or partial


async def list_cards_by_owner(
    owner: int | str,
) -> List[Tuple[str, str, DNDCharacter]]:
    """列出本人全部卡（按创建顺序），返回 (card_id, card_name, character)。"""
    owner_str = _owner(owner)
    async with _get_lock():
        store = await _load_if_needed()
        result: List[Tuple[str, str, DNDCharacter]] = []
        for card_id, entry in store["cards"].items():
            if _entry_owner(entry) != owner_str:
                continue
            model = _copy_model(str(card_id), entry)
            if model is None:
                continue
            result.append((str(card_id), _entry_name(entry), model))
    return result


async def count_cards(owner: int | str) -> int:
    owner_str = _owner(owner)
    async with _get_lock():
        store = await _load_if_needed()
        return _count_owner_cards(store, owner_str)


async def save_card(card_id: str, character: DNDCharacter) -> None:
    """按 card_id 保存角色内容；卡名与归属不变。"""
    card_id = str(card_id)
    async with _get_lock():
        store = await _load_if_needed()
        entry = store["cards"].get(card_id)
        if not isinstance(entry, dict):
            raise CardNotFound("找不到要保存的角色卡")
        if _entry_owner(entry) != _owner(character.user_id):
            raise CardNotFound("角色卡归属不一致")
        character.card_id = card_id
        entry["character"] = character.model_dump(mode="json")
        await _dump_locked(store)


async def save_character(character: DNDCharacter) -> None:
    """兼容业务层：按 card_id 或当前群绑定保存卡片。"""
    card_id = character.card_id
    if not card_id:
        card_id = await get_bound_card_id(character.group_id, character.user_id)
    if not card_id:
        raise CardNotFound("找不到要保存的角色卡")
    await save_card(card_id, character)


async def rename_card(card_id: str, new_name: str) -> str:
    """修改卡名（库内标识，不改 $姓名$）；返回规范化后的新卡名。"""
    card_id = str(card_id)
    name = validate_card_name(new_name)
    async with _get_lock():
        store = await _load_if_needed()
        entry = store["cards"].get(card_id)
        if not isinstance(entry, dict):
            raise CardNotFound("找不到角色卡")
        owner = _entry_owner(entry)
        found = _find_card_by_name(store, owner, name)
        if found is not None and found[0] != card_id:
            raise CardNameTaken(f"卡名「{name}」已存在，请换一个")
        entry["card_name"] = name
        await _dump_locked(store)
        return name


async def delete_card(card_id: str) -> Optional[DNDCharacter]:
    """删除卡片并清理全部绑定；返回被删除的角色（供清理立绘）。"""
    card_id = str(card_id)
    async with _get_lock():
        store = await _load_if_needed()
        entry = store["cards"].get(card_id)
        if not isinstance(entry, dict):
            raise CardNotFound("找不到角色卡")
        model = _copy_model(card_id, entry)
        del store["cards"][card_id]
        for group_id, mapping in list(store["bindings"].items()):
            for qq, bound_id in list(mapping.items()):
                if bound_id == card_id:
                    del mapping[qq]
            if not mapping:
                del store["bindings"][group_id]
        await _dump_locked(store)
    return model


async def bind_card(
    group_id: int | str, owner: int | str, card_id: str
) -> Optional[str]:
    """把本人卡绑定到群，返回被替换的旧 card_id。"""
    group_str = _group(group_id)
    owner_str = _owner(owner)
    card_id = str(card_id)
    async with _get_lock():
        store = await _load_if_needed()
        entry = store["cards"].get(card_id)
        if not isinstance(entry, dict) or _entry_owner(entry) != owner_str:
            raise CardNotFound("找不到这张卡")
        model = _copy_model(card_id, entry)
        if model is None or not model.is_init:
            raise CardIncomplete("角色卡尚未建完，不能绑定")
        mapping = store["bindings"].setdefault(group_str, {})
        previous = mapping.get(owner_str)
        mapping[owner_str] = card_id
        await _dump_locked(store)
        # 绑定后 HP 以卡面为准：丢弃该群此前记下的无卡 HP 记录
        await delete_hp_record(group_str, owner_str)
        return previous


async def unbind_card(
    group_id: int | str, owner: int | str
) -> Optional[str]:
    """解除某人在某群的绑定，返回原 card_id。"""
    group_str = _group(group_id)
    owner_str = _owner(owner)
    async with _get_lock():
        store = await _load_if_needed()
        mapping = store["bindings"].get(group_str)
        if not mapping or owner_str not in mapping:
            return None
        previous = mapping.pop(owner_str)
        if not mapping:
            del store["bindings"][group_str]
        await _dump_locked(store)
        return previous


async def get_bound_card_id(
    group_id: int | str, owner: int | str
) -> Optional[str]:
    """读取某人在某群绑定的 card_id；绑定失效返回 None。"""
    group_str = _group(group_id)
    owner_str = _owner(owner)
    async with _get_lock():
        store = await _load_if_needed()
        mapping = store["bindings"].get(group_str) or {}
        card_id = mapping.get(owner_str)
        if not card_id:
            return None
        entry = store["cards"].get(card_id)
        if not isinstance(entry, dict) or _entry_owner(entry) != owner_str:
            return None
        model = _copy_model(card_id, entry)
    if model is None or not model.is_init:
        return None
    return str(card_id)


async def get_bound_card(
    group_id: int | str, owner: int | str
) -> Optional[Tuple[str, str, DNDCharacter]]:
    """读取某人在某群绑定的 (card_id, card_name, character)。"""
    group_str = _group(group_id)
    owner_str = _owner(owner)
    async with _get_lock():
        store = await _load_if_needed()
        mapping = store["bindings"].get(group_str) or {}
        card_id = mapping.get(owner_str)
        if not card_id:
            return None
        entry = store["cards"].get(card_id)
        if not isinstance(entry, dict) or _entry_owner(entry) != owner_str:
            return None
        model = _copy_model(card_id, entry, group_context=group_str)
        card_name = _entry_name(entry)
    if model is None or not model.is_init:
        return None
    return str(card_id), card_name, model


async def list_bound_groups(card_id: str) -> List[str]:
    """列出某张卡被绑定到的群号（按群号排序）。"""
    card_id = str(card_id)
    async with _get_lock():
        store = await _load_if_needed()
        groups = [
            group_id
            for group_id, mapping in store["bindings"].items()
            if card_id in mapping.values()
        ]
    return sorted(groups)


async def get_character(
    group_id: int | str, user_id: int | str
) -> Optional[DNDCharacter]:
    """读取某人在某群绑定的角色卡（未绑定返回 None）。"""
    bound = await get_bound_card(group_id, user_id)
    if bound is None:
        return None
    _card_id, _card_name, character = bound
    return character


async def list_characters_by_group(
    group_id: int | str,
) -> List[DNDCharacter]:
    """列出某群所有已绑定的角色卡。"""
    group_str = _group(group_id)
    async with _get_lock():
        store = await _load_if_needed()
        mapping = dict(store["bindings"].get(group_str) or {})
        result: List[DNDCharacter] = []
        for qq, card_id in mapping.items():
            entry = store["cards"].get(card_id)
            if not isinstance(entry, dict) or _entry_owner(entry) != str(qq):
                continue
            model = _copy_model(str(card_id), entry, group_context=group_str)
            if model is not None and model.is_init:
                result.append(model)
    return result
