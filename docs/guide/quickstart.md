# 快速开始

屠龙骰（DNDDicer）是专精 **DND5e / DND5r** 跑团的 [NoneBot2](https://nonebot.dev/) 骰娘插件（OneBot V11 适配器），命令手感对齐 [nonebot-dicepp](https://github.com/pear-studio/nonebot-dicepp)（梨骰）。
本页带你完成安装、配置与首次使用。

> 规则范围说明：本插件**只做 DND5e/5r**——不做 COC/d100 体系、不做 `.mode` 多规则切换。
> 大成功/大失败等反馈均围绕 **d20** 展开。

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

安装完成后重启机器人，私聊机器人发送 `.bot` 即可验证插件已加载。

## 群聊使用：先开启本群服务（白名单）

出于对宿主机器人其他插件的协同考虑，**群聊内的服务默认关闭（白名单）**：
未开启的群只有 `.bot` 命令可用，其余命令静默不响应（消息会继续交给宿主其他插件处理）。
私聊不受此开关限制，可直接使用全部功能。

开启方法（需**群主或管理员**，且**群聊中需先 @ 本机器人**——@ 位于消息开头或结尾均可）：

```text
你发送：@屠龙骰 .bot on
骰娘回复：本群服务已开启。
```

查看本群服务状态：

```text
你发送：@屠龙骰 .bot
骰娘回复：屠龙骰（nonebot-plugin-dnddicer）v0.2.0
专精 DND5e/5r 跑团的骰娘：掷骰表达式、角色卡与检定/豁免/攻击、属性生成、HP 管理、先攻列表、战斗轮、群配置，命令手感对齐 nonebot-dicepp。
本群服务已开启，可直接使用本插件的全部命令。
用法：.bot on / .bot off——仅限群聊，需群主或管理员权限。
```

关闭服务：

```text
你发送：@屠龙骰 .bot off
骰娘回复：本群服务已关闭，本群将不再响应本插件的其他命令（.bot 不受影响）。
```

### 群聊 / 私聊差异速查

| 场景 | 能否使用 | 条件 |
| --- | --- | --- |
| 私聊 | ✅ 全部功能 | 直接发送命令即可（`.r`、`.hp`、`.角色卡`…） |
| 群聊（服务已开启） | ✅ 全部功能 | 无需 @（`.bot` 系列除外，仍需 @） |
| 群聊（服务未开启） | ❌ 仅 `.bot` | `.bot` 系列需 @；`.bot on` 需群主/管理员 |

## 快速体验

服务开启后，先来掷个骰（发送 `.r d20` 或 `.r 2d6+3` 均可）：

```text
你发送：.r 2d6+3
骰娘回复：艾琳 的掷骰结果为 2D6+3=[5+2]+3=10
```

```text
你发送：.r d20
骰娘回复：艾琳 的掷骰结果为 1D20=[20]=20 好耶！大成功!
```

> 示例中的昵称（艾琳）为发送者在群内的显示名；`=10` 前的 `[5+2]` 为逐骰过程，
> 骰值为本次实际掷出结果。完整掷骰语法见 [掷骰语法](./roll-syntax.md)。

## 配置项（可选，全部有默认值）

插件**零配置即可运行**。如需调整，在 NoneBot 的 `.env` / 环境变量中设置：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `dnddicer_command_priority` | `int` | `10` | 命令事件响应器基础优先级（越小越优先）。与宿主其他插件（如 AIchat）在同一消息上竞争时按需调小 |
| `dnddicer_default_face` | `int` | `20` | 全局默认骰面（DND 惯例 d20）。某群设置了默认骰面（`.dset`）时以群配置为准 |
| `dnddicer_enabled` | `bool` | `true` | 功能总开关。设为 `false` 时只加载骨架、不注册任何命令（供宿主临时禁用） |
| `dnddicer_use_host_command_starts` | `bool` | `false` | 是否兼容宿主 `COMMAND_START` 起始符（NoneBot 默认含 `/`，开启后 `/.help`、`/r` 等亦可触发）。默认只匹配 `.`/`。`，见下节 |

`.env` 示例：

```bash
dnddicer_command_priority=10
dnddicer_default_face=20
```

## 命令起始符：默认只用句号

本插件命令以 **`.`（英文句号）或 `。`（中文句号）开头**，如 `.r 2d6+3`、`.帮助`。

默认**不**兼容宿主的斜杠起始符（`/help` 之类）——因为 `/help`、`/bot` 等常见单词命令容易与宿主其他插件同时命中、互相冲突。若你的机器人没有这类冲突且希望斜杠也能触发，把配置项 `dnddicer_use_host_command_starts` 设为 `true` 即可（此后 `/.help` 同样有效）。

## 数据存储

角色卡、HP、先攻、群配置等数据保存在 NoneBot 的 localstore 数据目录（默认平台数据目录下，可用 `LOCALSTORE_DATA_DIR` 环境变量调整，例如可设为 `data`），位于其中的 `nonebot_plugin_dnddicer/` 子目录，全部为本地 JSON 文件，随机器人账号隔离。

## 下一步

- 完整命令一览见 [首页命令总表](../index.md)
- 掷骰表达式语法与暗骰：[掷骰语法](./roll-syntax.md)
- 建立你的第一张 DND 角色卡：[角色卡与检定](./character-card.md)
