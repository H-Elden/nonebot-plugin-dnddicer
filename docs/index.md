---
layout: home

hero:
  name: 屠龙骰
  text: DNDDicer 使用文档
  tagline: 专精 DND5e/5r 的 QQ 跑团骰娘插件——掷骰表达式、角色卡与属性、检定与豁免、HP 管理、先攻列表与战斗轮
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
    details: D20 优势/劣势、保留最高、重掷、爆炸骰、连掷、暗骰与原因后缀；仅 D20 播报大成功/大失败
    link: /guide/roll-basics
    linkText: 掷骰基础
  - title: 角色卡与属性
    details: 用 $…$ 模板建卡，或 .dnd/.dndx 以 4D6K3 掷点；额外加值只装算得进检定的部分
    link: /guide/character-card
    linkText: 角色卡与属性
  - title: 检定与豁免
    details: .力量检定 .敏捷豁免 .隐匿检定 自动代入调整值、熟练与卡上加值，也可用 @ 代掷
    link: /guide/checks
    linkText: 检定与豁免
  - title: HP 与长休
    details: 记录、伤害/治疗（支持掷骰表达式）、临时 HP、NPC 血量跨战斗保持；.长休 一键结算
    link: /guide/hp-rest
    linkText: HP 与长休
  - title: 先攻列表
    details: .ri 掷先攻入表、.init/.先攻 管理条目；支持 @ 代掷与批量入表，列表联动 NPC 血量
    link: /guide/initiative
    linkText: 先攻列表
  - title: 战斗轮
    details: .br 开局、.回合/.轮次 推进回合；轮到玩家自动 @ 提醒，怪物回合由 DM 的 .ed 推进
    link: /guide/battle
    linkText: 战斗轮
  - title: DM 实战指南
    details: 一次开团的完整流程：开团前整备与入表、三种伤害结算、回合推进、暗骰与速查表
    link: /guide/dm-guide
    linkText: DM 实战指南
  - title: 群管理与 FAQ
    details: .dset 群默认骰面、.bot 群聊服务开关（白名单）、起始符配置与常见问题排查
    link: /guide/faq
    linkText: 群管理与 FAQ
---

当前版本 **v0.2.2** · 规则范围仅 DND5e/5r · [更新日志](/guide/changelog)
