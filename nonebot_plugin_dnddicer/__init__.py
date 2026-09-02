"""DNDDicer（DND 骰子）：专精 DND5e / DND5r 的 NoneBot2 骰娘插件（OneBot V11）。

项目定位与决策依据见仓库根 ``doc/骰娘插件开发计划.md``：
- 掷骰引擎移植自 nonebot-dicepp 的 ast_engine（MIT，Copyright (c) 2022 pear-studio，
  移植落地时引擎文件头保留版权声明与 MIT 许可全文）；
- 业务层全部自研；范围为 DND5e/5r（不做 COC/d100 体系、不做 .mode）；
- 商店合规：零配置可加载、localstore 存储、__plugin_meta__ 完整、全程异步。
"""

from nonebot import require


def _nonebot_initialized() -> bool:
    """判断 NoneBot 是否已完成初始化（require 的前提）。

    本包可能被两种方式导入：
    - NoneBot 加载流程（NoneBot load / NoneBug 夹具）：已初始化，require 必须执行；
    - 直接导入（例如引擎随迁单测在 pytest 收集阶段 import engine 子模块）：
      尚未初始化，此时跳过 require 即可（localstore 真正缺失时，在已初始化
      场景下 require 会正常抛错，不会被此判断掩盖）。
    """
    try:
        from nonebot import get_driver

        get_driver()
        return True
    except ValueError:
        return False


# 商店合规：依赖其他插件必须先 require() 再 import()
# （本地数据存储统一走 nonebot-plugin-localstore）
if _nonebot_initialized():
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

# 子模块导入策略：
# - engine（掷骰引擎）无初始化副作用，随包导入以尽早暴露导入错误（引擎单测在
#   pytest 收集阶段直接 import 本包时也需要可用）；
# - commands（命令注册：顶层创建 on_message matcher 并读取插件配置）与 data
#   （localstore 存储）必须在 NoneBot 初始化后的加载流程中导入，否则跳过——
#   这正是 NoneBot 加载本插件时的场景（NoneFlow/宿主加载），matcher 照常注册。
if _nonebot_initialized():
    from . import commands  # noqa: E402,F401
    from . import data  # noqa: E402,F401
from . import engine  # noqa: E402,F401
