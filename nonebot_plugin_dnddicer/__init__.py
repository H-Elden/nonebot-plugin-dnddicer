"""DNDDicer（DND 骰子）：专精 DND5e / DND5r 的 NoneBot2 骰娘插件（OneBot V11）。

项目定位与决策依据见仓库根 ``doc/骰娘插件开发计划.md``：
- 掷骰引擎移植自 nonebot-dicepp 的 ast_engine（MIT，Copyright (c) 2022 pear-studio，
  移植落地时引擎文件头保留版权声明与 MIT 许可全文）；
- 业务层全部自研；范围为 DND5e/5r（不做 COC/d100 体系、不做 .mode）；
- 商店合规：零配置可加载、localstore 存储、__plugin_meta__ 完整、全程异步。
"""

from nonebot import require

# 商店合规：依赖其他插件必须先 require() 再 import()
# （本地数据存储统一走 nonebot-plugin-localstore）
require("nonebot_plugin_localstore")

from nonebot.plugin import PluginMetadata  # noqa: E402

from .config import Config  # noqa: E402
from .version import __version__  # noqa: E402

# 插件元数据必须位于 __init__.py 最外层（NoneFlow 商店自动检查要求）
__plugin_meta__ = PluginMetadata(
    # 基本信息
    name="DND 骰子",
    description=(
        "专精 DND5e/5r 跑团的骰娘：掷骰表达式（d20/优势劣势/爆炸骰等）、"
        "角色卡与检定/豁免/攻击、属性生成、HP 管理、先攻列表、战斗轮（.br/.ed）、"
        "群配置、牌堆与规则查询（规划中）。命令手感对齐 nonebot-dicepp。"
    ),
    usage=(
        "发送 .r 2d20kh1+4 掷骰（.rh 为暗骰）；.帮助 查看全部指令。"
        "详细指令表随功能落地逐步补充，见 README「用法」节。"
    ),
    # 发布额外信息
    type="application",
    # TODO: GitHub 仓库创建后替换为真实主页
    homepage="https://github.com/<your-github>/nonebot-plugin-dnddicer",
    config=Config,
    # 仅支持 OneBot V11 适配器（~ 代表前缀 nonebot.adapters.）
    supported_adapters={"~onebot.v11"},
    extra={"version": __version__},
)

# 命令层 / 数据层子模块随插件加载一并导入：
# - 保证包结构完整、尽早暴露导入错误；
# - 各功能 matcher 在 commands 子模块中注册（骨架期暂未注册任何命令响应器，
#   里程碑 2 起按 doc/骰娘插件开发计划.md 的分期逐模块落地）。
from . import commands, data  # noqa: E402,F401
