import { defineConfig } from 'vitepress'
import { chatContainer } from './plugins/chat-container.mts'

// 屠龙骰（DNDDicer）使用文档站配置。
// 注意：站点发布在 GitHub Pages 的仓库子路径下，base 必须与实际部署路径一致，
// 本地开发地址也随之带前缀（http://localhost:5173/nonebot-plugin-dnddicer/）。
export default defineConfig({
  lang: 'zh-CN',
  title: '屠龙骰 DNDDicer',
  description:
    '专精 DND5e/5r 的 QQ 跑团骰娘插件使用文档：掷骰表达式、角色卡与检定、属性生成、HP 管理、先攻列表与战斗轮',
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
        text: '掷骰',
        items: [{ text: '掷骰语法', link: '/guide/roll-syntax' }],
      },
      {
        text: '角色与检定',
        items: [
          { text: '角色卡与检定', link: '/guide/character-card' },
          { text: '属性生成', link: '/guide/attributes' },
        ],
      },
      {
        text: '生命值',
        items: [{ text: 'HP 管理与长休', link: '/guide/hp-rest' }],
      },
      {
        text: '战斗',
        items: [
          { text: '先攻列表', link: '/guide/initiative' },
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
