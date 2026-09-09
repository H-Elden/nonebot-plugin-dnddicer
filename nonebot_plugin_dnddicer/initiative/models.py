"""先攻列表数据模型（语义移植自 nonebot-dicepp core/data/models/initiative.py）。

- ``InitList`` 同时承载「先攻表」与「战斗轮状态机」：实体列表（按先攻值降序）
  + round/turn 两个指针（turns_in_round 为当前轮内回合数，first_turn 标记战斗
  是否已开始）——与 DicePP 一致，一个群一张表，战斗轮只是表的"进行中状态"；
- 入表/删除时自动修正 turn/round 指针（战斗开始后新增/移除实体不影响当前行动者）；
- 本实现为纯模型（不含磁盘 IO），持久化见 data/initiative.py。
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class InitiativeError(Exception):
    """先攻模块异常：说明操作失败原因，应在命令层捕获。"""

    def __init__(self, info: str):
        self.info = info

    def __str__(self) -> str:
        return f"[Initiative] [Error] {self.info}"


class InitEntity(BaseModel):
    """先攻列表中的单个实体。

    - name：展示名称（入表时快照：角色名 → 群名片/昵称 → QQ 号）；
    - owner：绑定的玩家 QQ 号，空串代表无主 NPC（与 DicePP 相同）；
    - init：先攻值。
    """

    name: str = ""
    owner: str = ""
    init: int = 0

    def get_info(self) -> str:
        """返回显示用信息，如 ``哥布林 先攻:12``。"""
        return f"{self.name} 先攻:{self.init}"


#: 单个先攻列表的容量上限（对齐 DicePP）
INIT_LIST_SIZE = 30


class InitList(BaseModel):
    """群级先攻表 + 战斗轮状态（迁移自 DicePP InitList，仅去掉 mod_time）。"""

    group_id: str = ""
    entities: List[InitEntity] = Field(default_factory=list)
    round: int = 1
    turn: int = 1
    turns_in_round: int = 1
    first_turn: bool = True

    def add_entity(self, entity_name: str, owner_id: str, init: int) -> None:
        """加入一个实体（自动按先攻降序排序；同名旧条目先删除以支持重掷）。

        Args:
            entity_name: 实体名。
            owner_id: 绑定玩家 QQ（空为 NPC）。
            init: 先攻值。

        Raises:
            InitiativeError: 先攻列表超过容量上限。
        """
        replace_same_name = sum(
            entity.name == entity_name for entity in self.entities
        )
        if replace_same_name:
            self.del_entity(entity_name)

        if len(self.entities) >= INIT_LIST_SIZE:
            raise InitiativeError(
                f"先攻列表大小超出限制, 至多存在{INIT_LIST_SIZE}个条目"
            )

        entity = InitEntity(name=entity_name, owner=owner_id, init=init)
        self.entities.append(entity)
        # 稳定排序：同先攻值保持入表先后（先入者靠前），DM 可用 first 提前
        self.entities = sorted(self.entities, key=lambda x: -x.init)
        self.turns_in_round = len(self.entities)

        if not self.first_turn:
            # 战斗进行中插入新实体：插在当前回合位及之前则回合指针后移，
            # 保证正在行动者不变（对齐 DicePP）
            for index, entity in enumerate(self.entities):
                if entity.name == entity_name and self.turn >= index + 1:
                    self.turn += 1

    def del_entity(self, entity_name: str) -> None:
        """删除指定名称的全部条目（含同名重复残留），并修正回合指针。"""
        all_index = [
            index
            for index, entity in enumerate(self.entities)
            if entity.name == entity_name
        ]
        if len(all_index) == 0:
            raise InitiativeError(f"先攻列表中不存在名称为{entity_name}的条目")
        for index in reversed(all_index):
            del self.entities[index]
        self.turns_in_round = len(self.entities)

        if not self.first_turn and self.turns_in_round > 0:
            # 按删除位置平移 turn，仍越界再回绕一轮（批量删除平移后至多越界 1）
            removed_before_turn = sum(
                1 for index in all_index if self.turn > index + 1
            )
            self.turn -= removed_before_turn
            if self.turn > self.turns_in_round:
                self.turn -= self.turns_in_round
                self.round += 1
