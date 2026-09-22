---
layout: home

hero:
  name: 屠龙骰
  text: DNDDicer 使用文档
  tagline: 专精 DND5e/5r 的 QQ 跑团骰娘插件——掷骰表达式、角色卡与检定、HP 管理、先攻列表与战斗轮
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/quickstart
    - theme: alt
      text: 命令总览
      link: /guide/overview
    - theme: alt
      text: GitHub
      link: https://github.com/H-Elden/nonebot-plugin-dnddicer

features:
  - title: 掷骰表达式
    details: d20 优势/劣势、保留最高、重掷、爆炸骰、连掷、暗骰与原因后缀；仅 d20 播报大成功/大失败
    link: /guide/roll-syntax
    linkText: 掷骰语法
  - title: 角色卡与检定
    details: 用 $…$ 模板建卡；.力量检定 .敏捷豁免 .敏捷攻击 点命令自动代入调整值、熟练与加值，也可用 @ 代掷
    link: /guide/character-card
    linkText: 角色卡与检定
  - title: 属性生成
    details: .dnd 以 4D6K3 掷点并附合计与降序；.dndx 绑定属性名不排序，可直接抄进角色卡
    link: /guide/attributes
    linkText: 属性生成
  - title: HP 管理与长休
    details: 记录、伤害/治疗（支持掷骰表达式）、临时 HP、NPC 血量跨战斗保持；.长休 一键结算
    link: /guide/hp-rest
    linkText: HP 管理与长休
  - title: 先攻与战斗轮
    details: .ri 掷先攻入表、.init/.先攻 管理条目；.br 开局、.回合/.轮次 推进，轮到玩家自动 @ 提醒
    link: /guide/initiative
    linkText: 先攻列表
  - title: 群管理与 FAQ
    details: .dset 群默认骰面、.bot 群聊服务开关（白名单）、起始符配置与常见问题排查
    link: /guide/faq
    linkText: 群管理与 FAQ
---

当前版本 **v0.2.1** · 规则范围仅 DND5e/5r · [更新日志](https://github.com/H-Elden/nonebot-plugin-dnddicer/blob/main/CHANGELOG.md)
