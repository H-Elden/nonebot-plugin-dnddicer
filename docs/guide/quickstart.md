# 快速开始

屠龙骰（DNDDicer）是专精 **DND5e / DND5r** 跑团的 [NoneBot2](https://nonebot.dev/) 骰娘插件（OneBot V11 适配器）。

> 规则范围：本插件**只做 DND5e/5r**，不做 COC/D100 体系、不做 `.mode` 多规则切换。大成功/大失败等反馈均围绕 **D20** 展开。

## 安装

依赖：**Python ≥ 3.11**，NoneBot2 ≥ 2.4.0，OneBot V11 适配器。

通过 NB-CLI 安装（与 NoneBot 插件商店安装方式一致，推荐）：

```bash
nb plugin install nonebot-plugin-dnddicer
```

或使用包管理器安装后，在 `pyproject.toml` 的 `[tool.nonebot]` 中声明加载：

```bash
pip install nonebot-plugin-dnddicer
```

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_dnddicer"]
```

安装完成后重启机器人，私聊机器人发送 `.bot` 即可验证插件已加载。需要词条卡片图（图片模式）的宿主，见下节[可选依赖项](#可选依赖项)。

### 可选依赖项

> 可选依赖**默认不安装**，请骰主按需补充，未装不影响基础功能。

**图片模式所需的渲染依赖**：`[render]`，即 `nonebot-plugin-htmlkit` 插件，未安装时无法渲染查询词条的图片，查询结果只能显示为文字。同样可以通过以下两种方式进行安装：

使用 NB-CLI 直接安装（同时包含本插件和渲染依赖插件）：

```bash
nb plugin install "nonebot-plugin-dnddicer[render]"
```

对于用包管理器直接安装的情况，在项目环境里通过以下命令补装（下为 pip 示例）：

```bash
pip install "nonebot-plugin-dnddicer[render]"
```

> **平台要求（只影响出图）**：
> 
> - Linux 需要 glibc ≥ 2.34，即：
>     - Ubuntu 22.04+ / Debian 12+ 可用；
>     - CentOS 7/8、Ubuntu 20.04 等不可用。
> - 成图需要系统字体（fontconfig），请确认系统已装有中文字体（如 `fonts-noto-cjk`），否则中文可能显示为方框。

该依赖由插件按需加载，不必写进宿主 `[tool.nonebot]` 的 `plugins` 列表；装好后还需把 `dnddicer_query_image_enabled` 设为 `true` 才会出图，详见下文「[规则查询](#规则查询)」一节。

## 配置项

插件**零配置即可运行**，以下配置项均为可选配置。

### 基础配置

如需调整，在 NoneBot 的 `.env` 文件或环境变量中设置：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `dnddicer_command_priority` | `int` | `10` | 命令事件响应器基础优先级，与宿主其他插件在同一消息上竞争时可按需调整（越小越优先） |
| `dnddicer_default_face` | `int` | `20` | 全局默认骰面（DND 惯例 D20）。当某群设置了默认骰面（`.dset`）时以群配置为准 |
| `dnddicer_enabled` | `bool` | `true` | 插件功能总开关。设为 `false` 时只加载骨架、不注册任何命令<br>（供开发者临时禁用本插件） |
| `dnddicer_use_host_command_starts` | `bool` | `false` | 是否兼容宿主 `COMMAND_START` 起始符，详见下文「[命令起始符](#命令起始符)」一节 |

### 规则查询

规则查询功能**默认关闭**：开启后群聊仍受本群服务开关管辖，私聊直接可用。命令使用方式见[规则查询](./query.md)页面。

此处仅面向骰主给出配置方法：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `dnddicer_query_enabled` | `bool` | `false` | 规则查询总开关，关闭时不对查询服务发起任何请求 |
| `dnddicer_query_base_urls` | `list` | 在线服务 | 查询服务端点，按顺序尝试，失败则自动尝试下一个 |
| `dnddicer_query_image_enabled` | `bool` | `false` | 图片模式总开关，决定各处**能不能**出图；<br>需先安装[可选依赖项](#可选依赖项)中的 `[render]` |
| `dnddicer_query_timeout` | `float` | `8.0` | 单个端点的请求超时（秒） |
| `dnddicer_query_cache_ttl` | `float` | `600.0` | 同一关键词的结果缓存时长（秒） |
| `dnddicer_query_endpoint_cooldown` | `float` | `60.0` | 端点失败后的冷却时长（秒） |

默认端点是公开的在线服务：`https://5echmsearch.kagangtuya.top`，开箱无需部署；图片模式各群/私聊的启用方式见[规则查询](./query.md#图片显示-查询图片)页面。

推荐全部开启以获得最佳体验，开启配置示例：

```bash
DNDDICER_QUERY_ENABLED=TRUE
DNDDICER_QUERY_IMAGE_ENABLED=TRUE
DNDDICER_QUERY_BASE_URLS=["http://127.0.0.1:13000", "https://5echmsearch.kagangtuya.top"]
```

> **自建查询服务**是可选路线：自建实例与插件之间只用 `dnddicer_query_base_urls` 对接，部署建议与步骤见[自建查询服务](./self-host.md)。

### 完整配置示例

这里给出全部可配置项及其默认值，供骰主复制修改；键名统一用大写（插件读取不区分大小写），布尔量写 `TRUE` / `FALSE`。

如需调整，把下面的配置复制进 `.env` 文件并修改，保持默认的项可以不填。

::: details 点击展开查看并复制

```bash
# ----- DNDDicer 插件 -----
# 基础配置
# # 命令事件响应器基础优先级
DNDDICER_COMMAND_PRIORITY=10
# # 全局默认骰面
DNDDICER_DEFAULT_FACE=20
# # 插件功能总开关
DNDDICER_ENABLED=TRUE
# # 是否兼容宿主 COMMAND_START 起始符
DNDDICER_USE_HOST_COMMAND_STARTS=FALSE

# 规则查询
# # 规则查询总开关
DNDDICER_QUERY_ENABLED=FALSE
# # 查询服务端点
DNDDICER_QUERY_BASE_URLS=["https://5echmsearch.kagangtuya.top"]
# # 图片模式总开关
DNDDICER_QUERY_IMAGE_ENABLED=FALSE
# # 单个端点的请求超时（秒）
DNDDICER_QUERY_TIMEOUT=8.0
# # 同一关键词的结果缓存时长（秒）
DNDDICER_QUERY_CACHE_TTL=600.0
# # 端点失败后的冷却时长（秒）
DNDDICER_QUERY_ENDPOINT_COOLDOWN=60.0
# --------------------------
```

:::

## 开启本群服务

出于对宿主机器人其他插件的协同考虑，**群聊内的服务默认关闭**：未开启服务的群只有 `.bot` 命令可用，其余命令静默不响应（消息会继续交给宿主其他插件处理）。

私聊不受此开关限制，但**可用命令与群聊不完全相同**，差异详见下文「[群聊 / 私聊差异速查](#群聊-私聊差异速查)」一节。

开启方法：由**群主或管理员**在群聊中 **@机器人**（@ 位于消息开头或结尾均可）后发送 `.bot on`：

::: chat
白鸦 | @屠龙骰 .bot on
屠龙骰 | 本群服务已开启。
:::

> 注：如果开发者在环境变量中配置过宿主机器人的[昵称](https://nonebot.dev/docs/api/config#Config-nickname)，那么此处及后文中 @机器人 的操作均可用昵称来代替，不再赘述。

开启后随时可以用 `.bot` 查看插件版本、简介与当前服务状态：

::: chat
白鸦 | @屠龙骰 .bot
屠龙骰 | 屠龙骰（nonebot-plugin-dnddicer）v0.4.0
专精 DND5e/5r 跑团的骰娘：掷骰表达式、角色卡与检定/豁免、自定义武器与攻击、属性生成、HP 管理、先攻列表、战斗轮、规则查询、群配置。
本群服务已开启，可直接使用本插件的全部命令。
用法：.bot on / .bot off——仅限群聊，需群主或管理员权限。
:::

需要临时停用时（比如 DM 需要关闭骰娘服务），同权限发送 `.bot off`：

::: chat
白鸦 | @屠龙骰 .bot off
屠龙骰 | 本群服务已关闭，本群将不再响应本插件的其他命令（.bot 不受影响）。
:::

> 关闭只是把本群从白名单里摘出去，管理员或群主随时可以再次 `@机器人 .bot on` 加回来；`.bot` 系列命令在任何状态下都可用。

## 第一条命令

服务开启后，群聊中直接发送 `.r` 即可掷骰（无需 @）：

::: chat
小鹿 | .r
屠龙骰 | 小鹿 的掷骰结果为 1D20=[20]=20 好耶！大成功!
小鹿 | .r2d6+3
屠龙骰 | 小鹿 的掷骰结果为 2D6+3=[5+2]+3=10
:::

> 读法：`2D6+3=[5+2]+3=10` 依次是表达式原文、逐骰过程与合计。
>
> 示例中骰娘回复的「小鹿」为玩家的群昵称，当玩家绑定自己角色卡后，将默认回复角色卡，详见[名称显示规则](./overview.md#名称显示规则)。

完整掷骰语法见[掷骰基础](./roll-basics.md)与[掷骰进阶](./roll-advanced.md)。

## 群聊 / 私聊差异速查

服务开关只决定「**群聊里**响不响应」。除此之外，**私聊可用的命令比群聊少**，角色卡、HP、先攻表、默认骰面等设置都按「群」存放，即同一个人的卡在不同群里互不相通。

私聊没有「本群」这一上下文，且不存在私聊跑团的需求，因此许多命令不支持私聊。具体区别详见下表：

| 场景 | 可用范围 | 说明 |
| --- | --- | --- |
| 群聊（服务已开启） | ✅ 全部命令 | 直接发送即可（`.bot` 系列命令需 @） |
| 群聊（服务未开启） | 仅 `.bot` | `.bot` 系列需 @；`.bot on` / `.bot off` 需群主或管理员 |
| 私聊 | 掷骰、属性生成与规则查询等 | `.r` / `.rh`、`.dnd` / `.dndx`、`.查询` / `.搜索`（及 `.查询图片` / `.查询范围` / `.规则书`）、`.帮助`、`.bot` 可用；<br>**角色卡、检定、HP、先攻与战斗轮、群配置等命令仅限群聊** |

仅限群聊的命令在私聊里发送，会收到明确提示：

::: chat
注：以下内容发生在私聊对话框

小满 | .角色卡
屠龙骰（私聊） | 该指令仅在群聊中可用。
:::

## 命令起始符

本插件命令以 **`.`（英文句号）或 `。`（中文句号）开头**，如 `.r2d6+3`、`.帮助`、`。角色卡`。

NoneBot 默认 `/` 作为命令起始符，而本插件默认**不**兼容宿主的斜杠起始符（`/help` 之类），因为 `/help`、`/bot` 等常见单词命令容易与宿主其他插件同时命中、互相冲突。

若你的机器人没有这类冲突且希望斜杠也能触发，把配置项 `dnddicer_use_host_command_starts` 设为 `true` 即可，此后 `/help`、`/r2d6+3` 等斜杠写法同样有效（点号开头的写法不受影响）；协同与排查的完整说明见[群管理与 FAQ](./faq.md#命令起始符-骰主可改)。

## 数据存储

角色卡、HP、先攻、群配置等数据保存在 NoneBot 的 [localstore](https://nonebot.dev/docs/best-practice/data-storing) 数据目录（默认平台数据目录下，可用 `LOCALSTORE_DATA_DIR` 环境变量调整，例如可设为 `data`）。

所有数据全部为本地 JSON 文件，随机器人账号隔离；数据归属与备份、隐私细节见[群管理与 FAQ](./faq.md#数据存储与隐私)。

## 开发与致谢

- 本项目以 MIT License 发布；**掷骰引擎移植自 [nonebot-dicepp](https://github.com/pear-studio/nonebot-dicepp)**（Copyright (c) 2022 pear-studio，MIT），业务层为独立实现；
- 规则查询类资料内容不随插件分发，需要时由使用者自行提供；
- 发布、配置与开发信息见仓库 README。

## 下一步

- 认识贯穿全站的示例团：[示例团与人物](./cast.md)
- 全部命令一览：[命令总览](./overview.md)
- 掷骰表达式、优势劣势与暗骰：[掷骰基础](./roll-basics.md)与[掷骰进阶](./roll-advanced.md)
- 建一张规则完整的角色卡：[角色卡与属性](./character-card.md)
- DM 的代掷与代操作（@ 指定玩家结算）：[代掷与代操作](./dm-proxy.md)
- 从开团前到游戏后的完整流程：[最佳实践](./best-practices.md)
