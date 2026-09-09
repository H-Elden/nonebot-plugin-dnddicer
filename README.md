# 屠龙骰（DNDDicer / nonebot-plugin-dnddicer）

> 专精 **DND5e / DND5r** 跑团的 [NoneBot2](https://nonebot.dev/) 骰娘插件（OneBot V11 适配器），
> 命令手感对齐 [nonebot-dicepp](https://github.com/pear-studio/nonebot-dicepp)（梨子骰子）。
>
> ⚠️ **当前状态：开发中（第一期功能进行中）** —— 骨架、掷骰引擎（DicePP ast_engine 移植）已完成；
> `.r/.rh` 掷骰命令已可用，其余第一期功能（帮助/群配置/角色卡与检定/HP/先攻/战斗轮）按路线图逐步落地中。

## ✨ 简介

DNDDicer 的目标是填补「NoneBot 商店中缺少 **DND5e/5r 专业 + 现代维护 + 插件形态** 骰娘」的空位：
以 DicePP 掷骰引擎与命令手感为基准，做独立的、零配置可加载的 NoneBot 插件，供任何已有
机器人从商店安装即用。

- **掷骰引擎**：移植 nonebot-dicepp 的 AST 表达式引擎（Lark 文法），支持 `2d20kh1`、
  优势/劣势、爆炸骰、连掷、暗骰等 DicePP 完整语法面（规划中）；
- **规则范围**：仅 DND5e/5r——专精 DND 定位，不做 COC/d100 体系与 `.mode` 模式切换；
- **商店合规**：零配置可加载、本地存储走 `nonebot-plugin-localstore`、元数据完整、全程异步。

## 📦 安装

通过 NB-CLI（推荐，与商店安装方式一致）：

```bash
nb plugin install nonebot-plugin-dnddicer
```

或通过包管理器安装后，在 `pyproject.toml` 的 `[tool.nonebot]` 中声明加载：

```bash
pip install nonebot-plugin-dnddicer
```

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_dnddicer"]
```

> 依赖：Python ≥ 3.11，NoneBot2 ≥ 2.5.0，OneBot V11 适配器（`nb plugin install` 会自动安装依赖）。

## ⚙️ 配置

插件**零配置即可加载运行**，以下配置项全部可选（在 `.env` / 环境变量中设置）：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `dnddicer_command_priority` | int | `10` | 命令事件响应器基础优先级（越小越优先），与其他插件冲突时按需调整 |
| `dnddicer_default_face` | int | `20` | 全局默认骰面（DND 惯例 d20；群配置落地后以群配置为准） |
| `dnddicer_enabled` | bool | `true` | 功能总开关（预留，`false` 时只加载骨架、不注册命令） |
| `dnddicer_use_host_command_starts` | bool | `false` | 是否兼容宿主 `COMMAND_START` 起始符（NoneBot 默认 `/`，开启后 `/.help` 等亦可触发）。默认只匹配 `.` / `。`，避免 `/help`、`/bot` 等常见单词命令与其他插件同时命中（冲突） |

## 🎲 用法

> 指令表随功能落地逐步补充（路线图见下）。命令以 `.` 开头，中英文别名对齐 DicePP。
> 命令起始符默认仅 `.` / `。`（英文/中文句号）；如需用宿主斜杠 `/` 等起始符触发
> （如 `/.help`），请设置配置项 `dnddicer_use_host_command_starts=true`。

规划指令（第一期 = T0 + T1 + 战斗轮简化版）：

| 指令 | 说明 | 状态 |
| --- | --- | --- |
| `.r` / `.rh` | 掷骰表达式 / 暗骰（起始符为 `.` / `。`，`#`连掷、默认骰面、原因后缀、`s`只显数值、大成功/大失败播报） | ✅ 可用（第一期） |
| `.st` / `.角色卡` 系列 | 六属性建卡（模板文本 `.角色卡记录`）、检定/豁免/攻击点命令（`.力量检定`/`.智力豁免`/`.敏捷攻击优势`）、`.状态` | ✅ 可用（第一期） |
| `.dnd` | DND5e 属性生成（4D6K3 掷点，支持 `[次数]`/`[原因]`；标准购点规划中） | ✅ 可用（第一期） |
| `.hp` | HP 管理 | 🚧 规划中 |
| `.init` / `.先攻` | 先攻列表 | 🚧 规划中 |
| `.br` / `.ed` / `.回合` | 战斗轮（简化版） | 🚧 规划中 |
| `.帮助` | 帮助 | 🚧 规划中 |
| `.bot` | 插件信息查询 + 群聊服务开关（`.bot on` / `.bot off`，仅群聊、需群主/管理员；群聊中需先 @ 本机器人） | ✅ 可用（2026-09-09） |
| `.draw` / `.查询` 等 | 牌堆/随机表、规则查询（第二期 T2） | ⏳ 待排期 |
| `.ss` / `.ds` / `.buff` 等 | 法术位、死亡豁免、BUFF 表（T3 增强期，借鉴海豹骰设计） | ⏳ 待排期 |

> 一期范围外（显式提示、不静默）：`.r exp` 期望值采样、`.r a/n` 特殊判定模式。
> 功能分级与决策详见下方「📄 开发路线（里程碑）」。
>
> **群聊服务开关**：群聊内服务默认**关闭**（白名单）——需群主/管理员发送 `.bot on`
> 开启本群服务；`.bot off` 关闭后，本群不再响应本插件的任何命令（`.bot` 本身不受
> 影响，可随时查询/重新开启）。私聊不受此开关限制，可直接使用全部功能。
> **群聊中使用 `.bot` 系列命令需先 @ 本机器人**（私聊直发即可）。

## 📄 开发路线（里程碑）

1. ✅ **项目骨架**：可发布/可加载的插件工程（pyproject、元数据、零配置 Config、冒烟测试）
2. ✅ **引擎移植**：DicePP `ast_engine`（Lark AST 掷骰引擎）+ 随迁单测
3. ✅ **第一期**（T0+T1+战斗轮简化版，2026-09-09 完成，327 项测试通过）：掷骰 `.r/.rh`、帮助、群配置、角色卡与检定、`.dnd` 属性生成、HP、先攻列表、战斗轮（简化版）、`.bot` 信息服务开关（群聊需 @ 触发）
4. ⏳ **第二期 T2**：牌堆/随机表、规则查询
5. ⏳ 文档/商店整理 → 发布 GitHub + PyPI + NoneBot 商店
6. ⏳（可选）**T3 增强期**：法术位管理、死亡豁免闭环、BUFF 表等

## 📦 本地开发

```bash
# uv 方式（推荐；或使用 pip 安装 .[dev]）
uv sync --group dev
uv run pytest
```

测试基于 [nonebug](https://github.com/nonebot/nonebug) 做 NoneBot 加载冒烟
（与 NoneFlow 商店自动加载检查同思路）。

## 🤝 许可与致谢

- 本项目（业务层与工程骨架）以 **MIT License** 发布，见 [LICENSE](./LICENSE)。
- **掷骰引擎与命令语法移植自 [nonebot-dicepp](https://github.com/pear-studio/nonebot-dicepp)**
  （Copyright (c) 2022 pear-studio，MIT License）：引擎移植落地时，相关文件头将保留上游
  版权声明与 MIT 许可全文，并按 MIT 要求在本 LICENSE 中注明来源。
- 规则查询类资料内容**不随插件分发**（版权归原权利方/译者），需要时由使用者自行提供。
- 本项目与 nonebot-dicepp 无隶属关系，为独立命名的衍生/移植作品。
