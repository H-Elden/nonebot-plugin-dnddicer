#!/usr/bin/env node
// 把仓库根的 CHANGELOG.md 生成为文档站的《更新日志》页（docs/guide/changelog.md）。
//
// 为什么用生成而不是手抄：站点页要与仓库里的更新日志保持逐字一致，手抄迟早会漂。
// 生成结果照常入库（在仓库里直接读得到）。同步只在发版时进行：发版批次运行
// `npm run docs:sync-changelog` 生成并提交；docs:dev / docs:build 不自动同步，
// 开发中的「未发布」条目不会提前出现在站点上。
//
// 注意：CHANGELOG.md 的正文会原样进入 VitePress 页面，正文中不要写 `{{ }}`（会被当作 Vue 插值）。

import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

// 本文件位于 docs/.vitepress/scripts/，向上三级即仓库根
const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
const sourcePath = resolve(repoRoot, 'CHANGELOG.md')
const targetPath = resolve(repoRoot, 'docs', 'guide', 'changelog.md')

// 行尾统一 LF（仓库 .gitattributes 约定），文件末尾恰好一个换行
const body = readFileSync(sourcePath, 'utf8').replace(/\r\n/g, '\n').trimEnd() + '\n'

const frontmatter = [
  '---',
  // 生成页不提供「在 GitHub 上编辑此页」——要改的是根目录的 CHANGELOG.md
  'editLink: false',
  // 右侧目录只保留版本号（二级标题），不列「新增 / 变更 / 修复 / 文档」等三级标题
  'outline: [2, 2]',
  '---',
  '',
  '<!-- 本文件由 docs/.vitepress/scripts/sync-changelog.mjs 依据仓库根 CHANGELOG.md 生成，请勿直接编辑。 -->',
  '',
  '',
].join('\n')

writeFileSync(targetPath, frontmatter + body, 'utf8')
console.log(`已生成 ${relative(repoRoot, targetPath).replaceAll('\\', '/')}（来源：CHANGELOG.md）`)
