"""先攻/战斗轮业务模型包。

- ``models.py``：InitEntity / InitList（实体列表 + 轮次/回合指针，含入表/删除的
  回合指针自动修正），语义移植自 nonebot-dicepp core/data/models/initiative.py；
- 持久化见 data/initiative.py；命令层见 commands/initiative.py（.init/.ri/.先攻）
  与 commands/battle.py（.br/.ed/.回合/.轮次/.跳过）。
"""
