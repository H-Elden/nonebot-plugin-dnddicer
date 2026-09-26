"""DNDDicer 插件配置。

商店合规设计（依据 NoneBot 官方发布指南）：
- **零配置可加载**：所有配置项均有默认值，缺少任何配置时插件仍能正常导入与运行；
- **前缀防冲突**：字段名统一带 ``dnddicer_`` 前缀（NoneBot 从全局配置/环境变量中读取，
  如 ``dnddicer_default_face=20``，以免与其他插件配置项冲突）；
- 官方建议发布插件提供**可配置的事件响应优先级**（见下方 ``dnddicer_command_priority``）。

新配置项按需追加，注意保持「全部有默认值」原则。
"""

from typing import List

from nonebot import get_plugin_config
from pydantic import BaseModel, Field


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

    # ── 规则查询（.查询 / .搜索，T2）────────────────────────────────────
    #: 规则查询总开关。默认 False：不做任何外呼（不给第三方服务造成默认压力）；
    #: 开启后群聊仍受 .bot 群聊服务开关（白名单）管辖。
    dnddicer_query_enabled: bool = False

    #: 查询服务端点列表：按顺序优先使用，失败自动回退下一个。
    #: 默认值为公开在线服务；自建查询服务的骰主把本机地址放首位即可
    #: （如 ["http://127.0.0.1:13000", "https://5echmsearch.kagangtuya.top"]）。
    dnddicer_query_base_urls: List[str] = Field(
        default_factory=lambda: ["https://5echmsearch.kagangtuya.top"]
    )

    #: 单个端点的请求超时（秒）
    dnddicer_query_timeout: float = 8.0

    #: 关键词结果缓存时长（秒）：同一关键词在此窗口内不重复外呼
    dnddicer_query_cache_ttl: float = 600.0

    #: 端点失败后的冷却时长（秒）：冷却期内跳过该端点，
    #: 避免自建实例重启/更新索引的几秒窗口里每次查询都先撞一次
    dnddicer_query_endpoint_cooldown: float = 60.0

    #: 规则查询图片模式开关。默认 False（文字输出）；开启后词条正文以图片卡片
    #: 返回（仿 5e 不全书站点样式），候选列表仍为文字。需安装 [render] extra
    #: （nonebot-plugin-htmlkit），未装时自动回退文字。
    dnddicer_query_image_enabled: bool = False

    # ── 规则查询：速查索引（.查询法术 等子命令，2026-09-26）──────────────
    #: **页面抓取**的站点地址（正文层抓 HTML 用；与上面的检索端点分开）。
    #: 实测（2026-09-26）：在线检索服务域名只覆盖部分静态页，正文抓取须用
    #: 站点主域名；自建部署的骰主把这里设为你的站点地址（自建站含完整页面）。
    dnddicer_query_site_urls: List[str] = Field(
        default_factory=lambda: ["https://5echm.kagangtuya.top"]
    )

    #: 页面抓取的最小请求间隔（秒）：两次实际外呼之间至少间隔这么多秒
    #: （缓存命中不经过此处）。索引构建会连续抓取数十页，单独限流避免对
    #: 个人站点突发轰炸。
    dnddicer_query_page_interval: float = 0.5

    #: 抓取页面的内存缓存时长（秒）：同一页在此时长内重复查询零外呼
    #: （默认 24 小时；站点内容更新低频）。
    dnddicer_query_page_cache_ttl: float = 86400.0

    #: 「速查索引」启动构建开关：默认开启（仅当 dnddicer_query_enabled 开启时
    #: 生效）。索引只存站点速查表的条目名与元数据（环阶/CR/稀有度/出处）及
    #: 页面路径与锚点，存插件本地缓存目录、不随插件分发；站点内容更新低频，
    #: 运行中不自动重建，需要时骰主用 .查询索引 手动刷新。
    dnddicer_query_atlas_build_on_startup: bool = True

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
