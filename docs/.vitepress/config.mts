import { defineConfig } from 'vitepress'
import { chatContainer } from './plugins/chat-container.mts'

// 屠龙骰（DNDDicer）使用文档站配置。
// 注意：站点发布在 GitHub Pages 的仓库子路径下，base 必须与实际部署路径一致，
// 本地开发地址也随之带前缀（http://localhost:5173/nonebot-plugin-dnddicer/）。
export default defineConfig({
  lang: 'zh-CN',
  title: '屠龙骰 DNDDicer',
  description:
    '专精 DND5e/5r 的 QQ 跑团骰娘插件使用文档：掷骰表达式、角色卡与属性、检定与豁免、HP 管理、先攻列表与战斗轮',
  base: '/nonebot-plugin-dnddicer/',
  cleanUrls: true,
  lastUpdated: true,

  markdown: {
    config: (md) => {
      // `::: chat` 聊天气泡容器（示例渲染）
      md.use(chatContainer)
    },
  },

  themeConfig: {
    nav: [
      { text: '使用文档', link: '/guide/overview' },
      { text: '快速开始', link: '/guide/quickstart' },
      { text: 'GitHub', link: 'https://github.com/H-Elden/nonebot-plugin-dnddicer' },
      { text: 'PyPI', link: 'https://pypi.org/project/nonebot-plugin-dnddicer/' },
    ],

    sidebar: [
      {
        text: '开始',
        items: [
          { text: '快速开始', link: '/guide/quickstart' },
          { text: '示例团与人物', link: '/guide/cast' },
          { text: '命令总览', link: '/guide/overview' },
        ],
      },
      {
        text: '第一章 · 基础操作',
        items: [
          { text: '掷骰基础', link: '/guide/roll-basics' },
          { text: '掷骰进阶', link: '/guide/roll-advanced' },
          { text: '先攻列表', link: '/guide/initiative' },
        ],
      },
      {
        text: '第二章 · 进阶操作',
        items: [
          { text: '角色卡与属性', link: '/guide/character-card' },
          { text: '检定与豁免', link: '/guide/checks' },
          { text: 'HP 与长休', link: '/guide/hp-rest' },
          { text: '战斗轮', link: '/guide/battle' },
        ],
      },
      {
        text: '参考',
        items: [{ text: '群管理与 FAQ', link: '/guide/faq' }],
      },
    ],

    search: {
      provider: 'local',
    },

    outline: { level: [2, 3], label: '本页目录' },
    docFooter: { prev: '上一篇', next: '下一篇' },
    lastUpdated: { text: '最后更新于' },
    editLink: {
      pattern: 'https://github.com/H-Elden/nonebot-plugin-dnddicer/edit/main/docs/:path',
      text: '在 GitHub 上编辑此页',
    },
    returnToTopLabel: '回到顶部',
    sidebarMenuLabel: '目录',
    darkModeSwitchLabel: '外观',
    footer: {
      message: '以 MIT 许可发布 · 掷骰引擎与命令语法移植自 nonebot-dicepp（MIT）',
      copyright: 'Copyright © 2026 DNDDicer contributors',
    },
  },
})
