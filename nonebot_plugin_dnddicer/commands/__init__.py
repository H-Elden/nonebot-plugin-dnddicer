"""命令层：DNDDicer 全部可交互指令的注册入口。

设计约定（与 doc/骰娘插件开发计划.md 及 commands/base.py 一致）：
- 命令风格：点号前缀（`.r` / `.rh` / 后续 `.st` / `.hp` / `.init` / `.br` /
  `.ed` / `.帮助` 等），中英文别名对齐 nonebot-dicepp（DNDDicer 手感基准）；
- 起始符：默认仅英文/中文句号；宿主 COMMAND_START 兼容由配置
  ``dnddicer_use_host_command_starts`` 显式开启（默认关，见 base.py 与计划文档 8.6）；
- 协同：matcher 统一以 ``dnddicer_command_priority``（Config，默认 10）为基准
  设置优先级并 ``block=True``，与宿主 bot 其他插件（AIchat 等）协同；
- 本包**只在 NoneBot 已初始化时被导入**（由插件包根 ``__init__.py`` 在加载
  流程中导入），因此各命令模块顶层的 ``on_message`` matcher 创建是安全的。

规划拆分（第一期 = T0 + T1 + 战斗轮简化版；见 doc/骰娘插件开发计划.md 第 4 节）：
- roll.py          ★ 掷骰（.r / .rh，2026-09-02 已落地；暗骰/连掷/默认骰面/原因）
- character.py     角色卡与检定（.角色卡/.状态 + 检定/豁免/攻击 点命令，已落地）
- dnd.py           属性生成（.dnd 4D6K3 掷点，已落地；标准购点另行规划）
- hp.py            HP 管理（.hp / .长休，群内共享、多目标伤害/治疗，已落地）
- initiative.py    先攻列表（.init/.ri/.先攻 + .先攻检定 联动入表，已落地）
- battle.py        战斗轮（.br/.ed/.回合/.轮次，已落地）
- bot.py           .bot 插件信息服务与群聊服务开关（2026-09-09 宿主新需求）
- group_config.py  群配置（默认骰面 .dset，已落地）
- help.py          帮助（.帮助 / .help，已落地；须在其它命令之后导入以保持列表顺序）
"""

from . import base  # noqa: F401  # 基础设施（注册表/起始符/解析）
from . import roll  # noqa: F401  # .r / .rh 掷骰命令（模块顶层注册 matcher）
from . import character  # noqa: F401  # .角色卡/.状态 + 检定/豁免/攻击 点命令
from . import dnd  # noqa: F401  # .dnd 属性生成
from . import group_config  # noqa: F401  # .dset 群默认骰面
from . import hp  # noqa: F401  # .hp / .长休 HP 管理
from . import initiative  # noqa: F401  # .init/.ri/.先攻 先攻列表
from . import battle  # noqa: F401  # .br/.ed/.回合/.轮次 战斗轮
from . import bot  # noqa: F401  # .bot 插件信息与群聊服务开关
from . import help  # noqa: F401  # .帮助 / .help（须在其它命令之后导入以保持列表顺序）
from . import roll_parse_args  # noqa: F401  # .r 参数解析（上游迁移）
from . import text  # noqa: F401  # 反馈文案
