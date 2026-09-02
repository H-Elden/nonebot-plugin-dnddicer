"""命令层：DNDDicer 的全部可交互指令的注册入口。

设计约定（与 doc/骰娘插件开发计划.md 一致）：
- 命令风格：点号前缀（.r / .rh / .st / .hp / .init / .br / .ed / .帮助 等），
  中英文别名对齐 nonebot-dicepp（DNDDicer 的手感基准）；
- 协同：matcher 统一以 ``dnddicer_command_priority``（Config，默认 10）为基准
  设置优先级并 ``block=True``，与宿主 bot 的其他插件（AIchat 等）协同；
- 每个功能模块一个子模块，在本包 ``__init__`` 中导入即完成注册
  （NoneBot 惯例：模块顶层定义 matcher，加载即生效）。

规划拆分（第一期 = T0 + T1 + 战斗轮简化版；见计划文档第 4 节）：
- roll.py          掷骰（.r / .rh / .ra / .dset 等；引擎移植自 DicePP ast_engine）
- character.py     角色卡与检定（六属性建卡、检定/豁免/攻击、属性生成 .dnd）
- hp.py            HP 管理（群内共享、多目标伤害/治疗）
- initiative.py    先攻列表（.init / .ri）
- battle.py        战斗轮（.br / .ed / .回合 / .轮次 / .跳过）
- group_config.py  群配置（默认骰面等）
- help.py          帮助（.帮助 / .help）
"""

# 骨架期：暂无实际命令。各功能子模块落地后在此导入，例如：
# from . import roll  # noqa: F401
