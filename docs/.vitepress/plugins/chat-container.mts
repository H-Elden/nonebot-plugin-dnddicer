import type MarkdownIt from 'markdown-it'
import type StateBlock from 'markdown-it/lib/rules_block/state_block.mjs'

// 骰娘昵称前缀：以此开头的昵称（含「屠龙骰（私聊）」这类变体）一律渲染为左侧气泡；
// 其余发言（DM 与所有玩家）一律渲染为右侧气泡。
const BOT_NAME = '屠龙骰'
// 骰娘头像汉字（其余发言的头像取自名册或昵称首字）
const BOT_AVATAR_CHAR = '屠'

// 示例团名册：QQ 群昵称 → 头像汉字与颜色。头像字必须显式登记——「阿茶」「阿岩」首字相同，
// 按昵称首字取会撞车；气泡上方显示的是群昵称，而骰娘文案里的名字走「角色名 → 群名片 →
// QQ 昵称」回退链，因此示例里两种名字会同时出现。
const ROSTER: Record<string, { char: string; color: string }> = {
  白鸦: { char: '鸦', color: '#f0e323' },
  阿茶: { char: '茶', color: '#16A34A' },
  小满: { char: '满', color: '#2563EB' },
  老猫: { char: '猫', color: '#EA580C' },
  阿岩: { char: '岩', color: '#BE185D' },
  小鹿: { char: '鹿', color: '#78716C' },
}

// 未登记昵称的兜底调色板：按名称哈希取色，保证同名恒定、不同名大概率可区分
// （历史页面里的旧示例昵称也走这条路径，无需改造即可渲染）
const FALLBACK_COLORS = ['#0EA5E9', '#10B981', '#F59E0B', '#8B5CF6', '#EF4444', '#14B8A6', '#D946EF']

/** 十六进制色值校验：名册与兜底调色板均为内置常量，此处只作注入前的最后一道防线 */
const COLOR_PATTERN = /^#[0-9a-fA-F]{3,8}$/

/** 名称哈希（同名恒定取色） */
function hashText(text: string): number {
  let hash = 0
  for (const char of text) hash = (hash * 31 + (char.codePointAt(0) ?? 0)) | 0
  return Math.abs(hash)
}

/** 判断昵称是否属于骰娘（含「屠龙骰（私聊）」等带后缀的变体） */
function isBotName(name: string): boolean {
  return name === BOT_NAME || name.startsWith(`${BOT_NAME}（`)
}

/**
 * 按色值亮度选头像字色：亮底用深字、暗底用白字。
 * 名册里会出现亮黄色这类浅色（白字会看不清），此处统一兜住。
 */
function readableTextColor(hex: string): string {
  const raw = hex.replace('#', '')
  const full = raw.length === 3 ? [...raw].map((c) => c + c).join('') : raw.slice(0, 6)
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16))
  // sRGB 相对亮度近似（人眼对绿色最敏感）
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.6 ? '#1f2937' : '#ffffff'
}

/** 取昵称对应的头像汉字与颜色：名册优先，未登记时回退「首字 + 哈希取色」 */
function resolveAvatar(name: string): { char: string; color: string } {
  const registered = ROSTER[name]
  if (registered) return registered
  return {
    char: [...name][0] ?? '?',
    color: FALLBACK_COLORS[hashText(name) % FALLBACK_COLORS.length],
  }
}

// 注释行：`注：……`（半角/全角冒号均可），渲染为气泡下方的注释条
const NOTE_PATTERN = /^注[:：]\s*(.*)$/
// 消息行：`昵称 | 内容`。昵称不含 | [ ] = 且较短，避免与骰子输出里的符号混淆（如 [6|3]）
const MESSAGE_PATTERN = /^([^|=[\]]{1,24}?)\s*\|\s+(.*)$/

const OPEN_PATTERN = /^:::\s*chat\s*$/
const CLOSE_PATTERN = /^:::\s*$/

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderMessage(name: string, text: string): string {
  const isBot = isBotName(name)
  const side = isBot ? 'left' : 'right'
  const role = isBot ? 'bot' : 'user'
  const avatar = isBot ? { char: BOT_AVATAR_CHAR, color: '' } : resolveAvatar(name)
  // 群友头像的色值与字色经 CSS 变量注入（字色按亮度自动选深/白）；骰娘沿用样式表里的品牌渐变
  const style =
    avatar.color && COLOR_PATTERN.test(avatar.color)
      ? ` style="--chat-avatar-color: ${avatar.color}; --chat-avatar-text: ${readableTextColor(avatar.color)}"`
      : ''

  return [
    `<div class="chat-msg chat-msg--${side}">`,
    `<div class="chat-avatar chat-avatar--${role}"${style} aria-hidden="true">${escapeHtml(avatar.char)}</div>`,
    '<div class="chat-body">',
    `<div class="chat-name">${escapeHtml(name)}</div>`,
    // 用 <pre> 承载正文：站点会把 markdown 产出的 HTML 交给 Vue 模板编译，普通文本节点里的
    // 换行与连续空格会被折叠，而 <pre> 内的空白原样保留（示例是真实输出，必须逐字保真）
    `<pre class="chat-bubble">${escapeHtml(text)}</pre>`,
    '</div>',
    '</div>',
  ].join('')
}

function renderNote(md: MarkdownIt, text: string): string {
  return [
    '<div class="chat-note">',
    '<span class="chat-note__tag" aria-hidden="true">注</span>',
    `<span class="chat-note__text">${md.renderInline(text)}</span>`,
    '</div>',
  ].join('')
}

/** 把容器内的原始文本行渲染成气泡流 */
function renderChat(md: MarkdownIt, source: string): string {
  const blocks: string[] = []
  let current: { name: string; lines: string[] } | null = null
  // 注释行须自成一段（前面空一行）：骰娘的真实输出里也会有以「注：」开头的行
  // （如 NPC 自动回满提示），紧随消息出现的「注：」一律视为该消息的续行。
  let previousBlank = true

  const flush = () => {
    if (current) {
      blocks.push(renderMessage(current.name, current.lines.join('\n')))
      current = null
    }
  }

  for (const rawLine of source.split('\n')) {
    const line = rawLine.trimEnd()
    if (!line.trim()) {
      previousBlank = true
      continue
    }

    const note = previousBlank ? line.match(NOTE_PATTERN) : null
    if (note) {
      flush()
      blocks.push(renderNote(md, note[1]))
      previousBlank = false
      continue
    }

    previousBlank = false

    const message = line.match(MESSAGE_PATTERN)
    if (message) {
      flush()
      current = { name: message[1].trim(), lines: [message[2]] }
      continue
    }

    // 其余行接续上一条消息，保留换行（连掷等多行输出）
    if (current) current.lines.push(line)
  }
  flush()

  return `<div class="chat">\n${blocks.join('\n')}\n</div>\n`
}

/**
 * 注册 `::: chat` 气泡容器：
 *
 * ```
 * ::: chat
 * 阿茶 | .r 2d6+3
 * 屠龙骰 | 薇拉 的掷骰结果为 2D6+3=[5+2]+3=10
 * 注：结果文本的读法……
 * :::
 * ```
 *
 * 渲染规则：骰娘（`屠龙骰` 及其带后缀变体）在左，其余发言（DM 与所有玩家）在右；
 * 头像汉字与颜色取自名册（未登记昵称回退「首字 + 哈希取色」）。
 * 容器内的正文按原始文本处理（不经过 markdown 解析），保证示例与真实输出逐字一致。
 */
export function chatContainer(md: MarkdownIt): void {
  md.block.ruler.before(
    'fence',
    'chat_block',
    (state: StateBlock, startLine: number, endLine: number, silent: boolean): boolean => {
      const start = state.bMarks[startLine] + state.tShift[startLine]
      const opener = state.src.slice(start, state.eMarks[startLine])
      if (!OPEN_PATTERN.test(opener)) return false
      if (silent) return true

      const content: string[] = []
      let closed = false
      let nextLine = startLine
      while (++nextLine < endLine) {
        const lineStart = state.bMarks[nextLine] + state.tShift[nextLine]
        const line = state.src.slice(lineStart, state.eMarks[nextLine])
        if (CLOSE_PATTERN.test(line)) {
          closed = true
          break
        }
        content.push(line)
      }

      const token = state.push('chat_block', '', 0)
      token.block = true
      token.markup = ':::'
      token.content = content.join('\n')
      token.map = [startLine, nextLine]
      state.line = closed ? nextLine + 1 : nextLine
      return true
    },
    { alt: [] },
  )

  md.renderer.rules.chat_block = (tokens, idx): string => renderChat(md, tokens[idx].content)
}
