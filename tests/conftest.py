"""pytest 全局初始化：NoneBot 初始化 + 注册 OneBot V11 适配器 + 加载本插件。

关键点：必须在 **pytest 收集测试模块之前**（本 conftest 模块导入时）完成——
引擎随迁测试（tests/engine/）在收集阶段就会 import ``nonebot_plugin_dnddicer``
包（导入子模块必先导入父包）；若此时 NoneBot 尚未初始化并注册插件，
包会被当作普通模块提前装入 ``sys.modules``，导致 NoneBot 后续无法把它
注册为插件（NoneFlow 商店加载语义同样如此：先 init 再 load）。

- ``nonebot.init()`` 幂等：nonebug 的 session 级 ``_nonebot_init`` 夹具随后
  再次调用不会冲突；
- 未来的 nonebug 命令测试（``app.test_matcher``）可直接使用 nonebug 提供的
  ``app`` 夹具，无需重复初始化。
"""

import os
from pathlib import Path

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OnebotV11Adapter

if Path(".env.dev").exists():
    os.environ["ENVIRONMENT"] = "dev"
else:
    os.environ["ENVIRONMENT"] = "test"

# 本地数据目录指向仓库内 data/（已在 .gitignore）：
# - 沙箱/CI 无写系统 AppData 权限；语义与宿主月白（LOCALSTORE_DATA_DIR=data）一致；
# - 必须在 nonebot.init() / localstore 加载之前设置。
os.environ["LOCALSTORE_DATA_DIR"] = str(Path(__file__).resolve().parent.parent / "data")

# ── 收集前完成：init + 适配器 + 插件加载（与 NoneFlow 商店加载测试语义一致）──
nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(OnebotV11Adapter)
nonebot.load_from_toml("pyproject.toml")
