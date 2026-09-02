"""pytest 全局夹具：NoneBot 初始化后注册 OneBot V11 适配器并加载本插件。

写法对齐官方 uv 模板（fllesser/nonebot-plugin-template）：
- nonebug 提供 session 级 autouse 夹具 ``after_nonebot_init``（NoneBot 已初始化）；
- 在此之后注册适配器、并按 pyproject.toml 的 [tool.nonebot] 声明加载插件——
  与 NoneFlow 商店加载测试语义一致。
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


@pytest.fixture(scope="session", autouse=True)
async def after_nonebot_init(after_nonebot_init: None) -> None:
    """NoneBot 初始化完成后：注册 OneBot V11 适配器并加载本插件。"""
    driver = nonebot.get_driver()
    driver.register_adapter(OnebotV11Adapter)
    nonebot.load_from_toml("pyproject.toml")
