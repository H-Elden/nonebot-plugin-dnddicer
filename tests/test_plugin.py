"""插件冒烟测试：可加载、元数据完整、零配置默认值。

覆盖 NoneFlow 商店自动检查的核心场景（插件能被 NoneBot 正确加载），
随功能落地再补充各命令/模块的行为测试。
"""

import nonebot
import pytest

PLUGIN_ID = "nonebot_plugin_dnddicer"


def test_plugin_loaded() -> None:
    """插件能被 NoneBot 正确加载（商店自动检查的核心场景）。"""
    plugin = nonebot.get_plugin(PLUGIN_ID)
    assert plugin is not None, "插件未被加载"


def test_plugin_metadata() -> None:
    """__plugin_meta__ 完整（商店审核必填字段齐全）。"""
    plugin = nonebot.get_plugin(PLUGIN_ID)
    assert plugin is not None
    meta = plugin.metadata
    assert meta is not None
    assert meta.name == "屠龙骰"
    assert meta.description
    assert meta.usage
    assert meta.type == "application"
    # TODO: GitHub 仓库创建后替换为真实主页并去掉占位断言
    assert meta.homepage.startswith("https://github.com/")
    assert meta.config is not None
    assert meta.supported_adapters == {"~onebot.v11"}


def test_config_zero_config_defaults() -> None:
    """零配置可加载：不提供任何配置项时，全部默认值生效。"""
    from nonebot_plugin_dnddicer.config import Config

    cfg = Config()
    assert cfg.dnddicer_command_priority == 10
    assert cfg.dnddicer_default_face == 20
    assert cfg.dnddicer_enabled is True


def test_version_consistency() -> None:
    """版本号存在且格式合法（与 pyproject 同源：hatchling 动态读取 version.py）。"""
    from nonebot_plugin_dnddicer.version import __version__

    assert __version__
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_data_layer_paths() -> None:
    """数据层使用 localstore 目录（商店合规硬性要求）。"""
    from nonebot_plugin_dnddicer.data import get_data_dir, get_data_file

    data_dir = get_data_dir()
    assert data_dir.exists() and data_dir.is_dir()
    f = get_data_file("smoke.json")
    assert f.parent == data_dir
    # localstore 数据目录名应包含本插件名（nonebot_plugin_dnddicer）
    assert "nonebot_plugin_dnddicer" in str(data_dir)


def test_version_module_standalone_import() -> None:
    """无状态子模块（version）可被独立导入（不依赖 NoneBot 初始化流程）。"""
    import importlib

    # 注意：完整包（含 __init__.py 的 require/PluginMetadata）必须经 NoneBot
    # 加载流程导入（NoneFlow 商店检查即如此），此处只验证无依赖的子模块。
    mod = importlib.import_module("nonebot_plugin_dnddicer.version")
    assert mod.__version__
