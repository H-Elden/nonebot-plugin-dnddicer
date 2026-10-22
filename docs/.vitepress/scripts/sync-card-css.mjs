/**
 * 把插件的角色卡样式表同步到文档站，供网页建卡器的角色卡预览使用。
 *
 * 源文件是唯一事实来源；站点副本只是构建产物，测试会断言两者逐字一致。
 * 运行：node docs/.vitepress/scripts/sync-card-css.mjs
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..', '..', '..')
const source = path.join(
  root,
  'nonebot_plugin_dnddicer',
  'render',
  'templates',
  'char_card.css',
)
const target = path.join(
  root,
  'docs',
  '.vitepress',
  'theme',
  'card-builder',
  'char-card.css',
)

const css = fs.readFileSync(source, 'utf8')
fs.mkdirSync(path.dirname(target), { recursive: true })
fs.writeFileSync(target, css, 'utf8')
console.log(`角色卡 CSS 已同步：${path.relative(root, target)}`)
