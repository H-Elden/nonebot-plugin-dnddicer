import type MarkdownIt from 'markdown-it'
import type StateBlock from 'markdown-it/lib/rules_block/state_block.mjs'

// 示例用户的 QQ 群昵称（右侧气泡）。它与角色卡姓名刻意区分：气泡上方显示的是 QQ 侧昵称，
// 骰娘文案里的名字走「角色名 → 群名片 → QQ 昵称」回退链，因此示例里会同时出现两个名字。
const USER_NAME = '阿岚'

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
  const isUser = name === USER_NAME
  const side = isUser ? 'right' : 'left'
  const role = isUser ? 'user' : 'bot'
  const avatar = escapeHtml(name.charAt(0))

  return [
    `<div class="chat-msg chat-msg--${side}">`,
    `<div class="chat-avatar chat-avatar--${role}" aria-hidden="true">${avatar}</div>`,
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
 * 阿岚 | .r 2d6+3
 * 屠龙骰 | 艾琳 的掷骰结果为 2D6+3=[5+2]+3=10
 * 注：结果文本的读法……
 * :::
 * ```
 *
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
