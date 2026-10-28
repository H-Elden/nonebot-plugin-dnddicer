<p align="center">
  <img src="https://raw.githubusercontent.com/H-Elden/nonebot-plugin-dnddicer/main/logo/dnddicer-logo.svg" alt="屠龙骰 DNDDicer" width="140">
</p>

# 屠龙骰（DNDDicer / nonebot-plugin-dnddicer）

> 专精 **DND5e / DND5r** 跑团的 [NoneBot2](https://nonebot.dev/) 骰娘插件（OneBot V11 适配器），致力于做功能最全面、体验最好的 DND 骰娘。
>
> [![PyPI](https://img.shields.io/pypi/v/nonebot-plugin-dnddicer)](https://pypi.org/project/nonebot-plugin-dnddicer/) · [![QQ群](https://img.shields.io/badge/QQ%E7%BE%A4-1107879441-12B7F5?logo=tencentqq&logoColor=white)](https://qun.qq.com/universal-share/share?ac=1&authKey=eUFiLk5ktomkYgDWCMnJnLNQW%2FJwmfR7wXKRrYyQeJy5uaYtwDsm4ABDiofKx6%2BN&busi_data=eyJncm91cENvZGUiOiIxMTA3ODc5NDQxIiwidG9rZW4iOiIvWHlQbDlNeUdBOVpQSnB1WU1RNUFmRCtBNlgwTXpnN2VOSlh6UkJ1YTFUdmREdEExYmEwSXo4SXFiR21zb0tsIiwidWluIjoiMjk4NDQ5NTc3NCJ9&data=JWJQw7qsywgzyHnQ-HJ_PzqF_Y1otBjTRkehoSmk6faB87xzjGf4PA_p1KNPhLvkkOwlLEuNH9jTN8XxNbxRPQ&svctype=4&tempid=h5_group_info)

## ✨ 简介

DNDDicer 的目标是填补「NoneBot 商店中缺少 **DND5e/5r 专业 + 现代维护 + 插件形态** 骰娘」的空位：围绕 DND 跑团全流程持续做深做全，致力于提供功能最全面、体验最好的 DND 骰娘，零配置可加载，供任何使用 OneBot V11 适配器的机器人从商店安装即用。

- **掷骰引擎**：内置 AST 表达式引擎（Lark 文法），支持 `2D20kh1`、优势/劣势、爆炸骰、连掷、暗骰等完整掷骰语法；
- **跑团全流程**：掷骰 → 属性生成 → 角色卡录入 → 检定与豁免 → 自定义武器与攻击、施法 → 先攻列表与战斗轮 → HP 结算 → 短休与长休 → 规则查询等；
- **规则范围**：仅 DND5e/5r，专精 DND 定位，不做 COC/D100 体系；
- **商店合规**：零配置可加载、本地存储走 `nonebot-plugin-localstore`、元数据完整、全程异步。

> **升级提示**：0.5.0 起角色卡改为卡库存储，段语法与分隔符有破坏性调整，旧卡不会自动迁移，需用[网页建卡器](https://dnddicer.netlify.app/guide/card-builder)重新建卡；详见[更新日志](https://dnddicer.netlify.app/guide/changelog)。

## 🚀 快速上手

命令以 `.`（或全角 `。`）开头。安装并启动机器人后：

1. 私聊机器人发送 `.bot`，确认插件已加载并查看基本信息；
2. 在群里 @ 机器人发送 `.bot on`（群主/管理员），开启本群服务；
3. 发送 `.dnd` 生成一套属性，或 `.r` 试一次掷骰。

群聊服务默认关闭（白名单），未开启的群除 `.bot` 外不会响应本插件命令；私聊不受服务开关限制，但检定、HP、先攻与战斗轮等按群归属的命令仍仅限群聊。规则查询默认关闭，开启方法见[快速开始](https://dnddicer.netlify.app/guide/quickstart)。

常用命令速览（完整命令见[命令总览](https://dnddicer.netlify.app/guide/overview)）：

| 命令 | 作用 |
| --- | --- |
| `.r1D20+5` / `.rh` | 掷骰 / 暗骰 |
| `.dndx` | 4D6K3 生成并绑定六项属性 |
| `.角色卡新建 卡名` + 完整卡面 | 新建角色卡（群聊自动绑定本群） |
| `.力量检定` / `.体质豁免` | 检定与豁免，自动代入调整值与熟练 |
| `.hp` / `.hp 20/30` | 查看或记录 HP（支持队友与 NPC） |
| `.init` / `.br` | 先攻列表 / 战斗轮 |
| `.查询法术 火球术` | 规则查询（需开启 `dnddicer_query_enabled`） |
| `.help` | 帮助入口与命令目录 |

## 📖 使用文档

完整用法、输入输出示例与常见问题见使用文档：

**文档主站** <https://h-elden.github.io/nonebot-plugin-dnddicer/>

**国内镜像** <https://dnddicer.netlify.app/> （推荐）

以下章节链接均指向国内镜像：

- 开始：[快速开始](https://dnddicer.netlify.app/guide/quickstart) · [命令总览](https://dnddicer.netlify.app/guide/overview) · [示例团与人物](https://dnddicer.netlify.app/guide/cast)
- 第一章 · 基础操作：[掷骰基础](https://dnddicer.netlify.app/guide/roll-basics) · [掷骰进阶](https://dnddicer.netlify.app/guide/roll-advanced) · [生命值管理](https://dnddicer.netlify.app/guide/hp) · [先攻列表](https://dnddicer.netlify.app/guide/initiative) · [战斗轮](https://dnddicer.netlify.app/guide/battle) · [规则查询](https://dnddicer.netlify.app/guide/query)
- 第二章 · 玩家进阶：[角色卡录入](https://dnddicer.netlify.app/guide/character-card) · [检定与豁免](https://dnddicer.netlify.app/guide/checks) · [武器与攻击](https://dnddicer.netlify.app/guide/weapons) · [休息与资源](https://dnddicer.netlify.app/guide/resources) · [HP 进阶](https://dnddicer.netlify.app/guide/hp-advanced) · [死亡豁免](https://dnddicer.netlify.app/guide/death-save) · [规则版本与击晕](https://dnddicer.netlify.app/guide/rules-version)
- 第三章 · DM 进阶：[代掷与代操作](https://dnddicer.netlify.app/guide/dm-proxy) · [血量与伤害结算](https://dnddicer.netlify.app/guide/dm-settlement) · [查询范围](https://dnddicer.netlify.app/guide/query-scope)
- 第四章 · 最佳实践：[最佳实践](https://dnddicer.netlify.app/guide/best-practices)
- 参考与工具：[网页建卡器](https://dnddicer.netlify.app/guide/card-builder) · [角色卡字段](https://dnddicer.netlify.app/guide/card-fields) · [群管理与 FAQ](https://dnddicer.netlify.app/guide/faq) · [自建查询服务（可选）](https://dnddicer.netlify.app/guide/self-host) · [更新日志](https://dnddicer.netlify.app/guide/changelog)

文档源文件在仓库 [docs/](https://github.com/H-Elden/nonebot-plugin-dnddicer/tree/main/docs)。

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

图片渲染是可选功能，需要额外安装 `[render]` 可选依赖（会安装 `nonebot-plugin-htmlkit`）：

```bash
nb plugin install "nonebot-plugin-dnddicer[render]"
# 或
pip install "nonebot-plugin-dnddicer[render]"
```

未安装时，规则查询与角色卡出图会回退为文字，不影响其他功能。装好后，规则查询图片还需把 `dnddicer_query_enabled` 与 `dnddicer_query_image_enabled` 都设为 `true`；角色卡图需把 `dnddicer_card_image_enabled` 设为 `true`。Linux 需要 glibc ≥ 2.34 与中文字体，详见[快速开始 - 可选依赖项](https://dnddicer.netlify.app/guide/quickstart#可选依赖项)。

> 依赖：Python ≥ 3.11，NoneBot2 ≥ 2.4.0，OneBot V11 适配器（`nb plugin install` 会自动安装依赖）。

## ⚙️ 配置

插件**零配置即可加载运行**，以下为常用配置项，全部可选（在 `.env` / 环境变量中设置）：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `dnddicer_command_priority` | `int` | `10` | 命令事件响应器基础优先级（越小越优先），与其他插件冲突时按需调整 |
| `dnddicer_default_face` | `int` | `20` | 全局默认骰面（DND 惯例 D20；已配置 `.dset` 的群以群配置为准，此项作兜底） |
| `dnddicer_default_rules_version` | `str` | `2024` | 默认规则版本（`2024` / `2014`，也可写 `5r` / `5e`）；群内未用 `.规则版本` 设置时按它结算 |
| `dnddicer_enabled` | `bool` | `true` | 功能总开关，`false` 时只加载骨架、不注册命令 |
| `dnddicer_use_host_command_starts` | `bool` | `false` | 是否兼容宿主 `COMMAND_START` 起始符（NoneBot 默认 `/`，开启后 `/.help` 等亦可触发）。默认只匹配 `.` / `。`，避免 `/help`、`/bot` 等常见单词命令与其他插件同时命中（冲突） |
| `dnddicer_query_enabled` | `bool` | `false` | 规则查询总开关；开启后才响应 `.查询` 等命令（群聊仍受本群服务开关限制） |
| `dnddicer_master_qq` | `str` | 空 | 骰主 QQ 号（**单个**）：`.master` 反馈的收件人，留空则 `.master` 回「骰主未配置」 |
| `dnddicer_master_contact` | `str` | 空 | 骰主联系方式（自由文本），仅用于 `.help 联系` 展示，留空不显示该行 |
| `dnddicer_master_group` | `str` | 空 | 骰主交流群群号，仅用于 `.help 联系` 展示，留空不显示该行 |
| `dnddicer_card_image_enabled` | `bool` | `false` | 角色卡图开关；需安装 `[render]` 可选依赖（`nonebot-plugin-htmlkit`），开启后 `.角色卡` 出图，未开启时输出文字卡 |

规则查询的书目、图片模式与字体等其余配置项见[快速开始](https://dnddicer.netlify.app/guide/quickstart#配置项)。

## 🛠️ 本地开发

```bash
# uv 方式（推荐；或使用 pip 安装 .[dev]）
uv sync --group dev
uv run pytest
```

测试基于 [nonebug](https://github.com/nonebot/nonebug) 做 NoneBot 加载冒烟与全命令行为回归（与 NoneFlow 商店自动加载检查同思路）。

## 🤝 许可与致谢

- 本项目（业务层与工程骨架）以 **MIT License** 发布，见 [LICENSE](https://github.com/H-Elden/nonebot-plugin-dnddicer/blob/main/LICENSE)。
- **掷骰引擎移植自 [nonebot-dicepp](https://github.com/pear-studio/nonebot-dicepp)**（Copyright (c) 2022 pear-studio，MIT License）：引擎文件头保留上游版权声明，MIT 许可全文见 [LICENSE](https://github.com/H-Elden/nonebot-plugin-dnddicer/blob/main/LICENSE)。
- 规则查询类资料内容**不随插件分发**（版权归原权利方/译者），需要时由使用者自行提供。
- 本项目与 nonebot-dicepp 无隶属关系，为独立命名的衍生/移植作品。
