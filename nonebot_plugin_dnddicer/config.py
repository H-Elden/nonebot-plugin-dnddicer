"""DNDDicer 插件配置。

商店合规设计（依据 NoneBot 官方发布指南）：
- **零配置可加载**：所有配置项均有默认值，缺少任何配置时插件仍能正常导入与运行；
- **前缀防冲突**：字段名统一带 ``dnddicer_`` 前缀（NoneBot 从全局配置/环境变量中读取，
  如 ``dnddicer_default_face=20``，以免与其他插件配置项冲突）；
- 官方建议发布插件提供**可配置的事件响应优先级**（见下方 ``dnddicer_command_priority``）。

新配置项按需追加，注意保持「全部有默认值」原则。
"""

from nonebot import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    """DNDDicer 插件配置模型。

    说明：NoneBot 会在插件加载期读取这些配置；获取方式统一走本模块底部的
    ``get_config()``（首次调用时执行 ``get_plugin_config`` 并缓存），
    业务子模块请勿在模块顶层调用（彼时 NoneBot 可能尚未初始化）。
    """

    #: 命令事件响应器的基础优先级（越小越优先；NoneBot 默认 1000）。
    #: 与其他插件（如宿主机器人的 AIchat）在同一消息上竞争时按需调整。
    dnddicer_command_priority: int = 10

    #: 全局默认骰面（DND 惯例 d20）。群配置功能（第一期 T1）落地后，
    #: 单群的默认骰面以群配置为准，此项作为兜底。
    dnddicer_default_face: int = 20

    #: 功能总开关（预留）。False 时仅加载最小骨架、不注册任何命令响应器，
    #: 用于宿主需要临时禁用本插件功能但保留加载的场景。
    dnddicer_enabled: bool = True

    #: 是否兼容宿主全局配置 COMMAND_START 中声明的命令起始符（NoneBot 默认
    #: 含 "/"，开启后 /.help、/bot on 等亦可触发）。默认 False：只匹配本插件
    #: 自带的 "." / "。"——避免 "/help"、"/bot" 等常见单词命令与本插件同时
    #: 命中宿主其他插件（冲突）。宿主环境明确需要时设 true。
    dnddicer_use_host_command_starts: bool = False

    # 注：更多配置项（第一期落地时逐步补充，例如连掷上限、暗骰私聊开关等）
    # 将在对应功能实现时按需追加，保持「全部有默认值」的零配置原则。


_config: Config | None = None


def get_config() -> Config:
    """获取（并缓存）DNDDicer 插件配置。

    必须在 NoneBot 初始化后调用（插件加载流程中调用即满足条件）。
    """
    global _config
    if _config is None:
        _config = get_plugin_config(Config)
    return _config
