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
import pytest
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


@pytest.fixture(autouse=True)
def _bypass_service_gate(request, monkeypatch):
    """除 ``service_gate`` 标记的测试外，旁路群聊服务门禁（默认关闭 = 白名单）。

    .bot 服务开关（2026-09-09 落地）后，未开启服务的群不响应本插件命令——若在
    测试中真实生效，既有全部群聊命令测试（各自使用不同群号、未逐个执行 .bot on）
    会集体失效。约定：
    - 普通测试：monkeypatch 数据层 ``is_service_enabled`` → 恒 True
      （等价「服务已开启」，与门禁落地前的行为一致）；
    - 服务开关/门禁本身的测试：模块级 ``pytestmark = pytest.mark.service_gate``
      （不做旁路），并自行维护所用群号的服务状态（写入落盘、可跨用例）。
    """
    if request.node.get_closest_marker("service_gate"):
        return

    from nonebot_plugin_dnddicer.data import service_state

    async def _always_enabled(group_id: int | str) -> bool:
        return True

    monkeypatch.setattr(service_state, "is_service_enabled", _always_enabled)
