/**
 * 网页建卡器核心：卡文本 ⇄ 表单状态、校验、命令生成。
 *
 * 纯函数模块，不依赖 Vue / DOM / 网络，也不直接读取 JSON：
 * 段清单由调用方传入（页面读 `card-spec.json`，Node 校验脚本读同一份文件），
 * 因此浏览器与 Node 跑的是同一套逻辑。段语法的事实来源是插件的
 * `character/spec.py`，本模块只负责按清单解析与回写，不另立规则。
 *
 * 表单状态是一个以段名为键的普通对象，值的形状见 `createState()`；
 * 各段的解析/回写由 `SEGMENT_KINDS` 决定。导入时逐段解析，任一段失败都会
 * 带段名报错（不吞错）；导出时按 `output_order` 拼接，与骰娘输出的段顺序
 * 一致，因此「导入模板卡 → 导出」逐字不变。
 */

// ── 段键（与 card-spec.json 的 key 一致；Node 校验脚本断言两边对齐）────────
export const K = Object.freeze({
  NAME: '$姓名$',
  RACE: '$种族$',
  CLASS: '$职业$',
  SUBCLASS: '$子职$',
  BACKGROUND: '$背景$',
  STORY: '$故事$',
  LEVEL: '$等级$',
  HP: '$生命值$',
  HP_DICE: '$生命骰$',
  COMBAT: '$战斗$',
  PROGRESS: '$进度$',
  ABILITY: '$属性$',
  PROF: '$熟练$',
  EXT: '$额外加值$',
  FEATS: '$专长$',
  RACE_TRAITS: '$种族特性$',
  CLASS_TRAITS: '$职业特性$',
  WEAPON: '$武器$',
  ITEMS: '$物品$',
  COINS: '$钱币$',
  FEATURE: '$限定资源$',
  MAGIC_ITEMS: '$魔法物品$',
  SPELL: '$法术$',
  SPELL_SLOTS: '$法术位$',
  COMBAT_NOTES: '$战斗记录$',
})

/** 每个段对应的表单形态（`text` 等为单值，其余为结构化行）。 */
export const SEGMENT_KINDS = Object.freeze({
  [K.NAME]: 'text',
  [K.RACE]: 'text',
  [K.CLASS]: 'class',
  [K.SUBCLASS]: 'subclass',
  [K.BACKGROUND]: 'background',
  [K.STORY]: 'longtext',
  [K.LEVEL]: 'number',
  [K.HP]: 'hp',
  [K.HP_DICE]: 'hpdice',
  [K.COMBAT]: 'combat',
  [K.PROGRESS]: 'progress',
  [K.ABILITY]: 'ability',
  [K.PROF]: 'prof',
  [K.EXT]: 'ext',
  [K.FEATS]: 'feats',
  [K.RACE_TRAITS]: 'raceTraits',
  [K.CLASS_TRAITS]: 'classTraits',
  [K.WEAPON]: 'weapons',
  [K.ITEMS]: 'items',
  [K.COINS]: 'coins',
  [K.FEATURE]: 'features',
  [K.MAGIC_ITEMS]: 'magicItems',
  [K.SPELL]: 'spells',
  [K.SPELL_SLOTS]: 'slots',
  [K.COMBAT_NOTES]: 'notes',
})

/** 骰娘的记录命令（整卡与分段都以它开头）。 */
export const CARD_COMMAND = '.角色卡记录'

//: QQ 单条消息上限（用户 2026-10-22 实测群聊与私聊均为 4500 字）。
export const MESSAGE_LIMIT = 4500

const SIGNED_RE = /^[+-]?\d+$/
const WEAPON_BONUS_RE = /^[+-](\d*[dD]\d+|\d+)([+-](\d*[dD]\d+|\d+))*$/
const DAMAGE_ITEM_RE = /^[+-]?(\d*[dD]\d+|\d+)([+-](\d*[dD]\d+|\d+))*$/

function fail(message) {
  throw new Error(message)
}

function textOf(value) {
  return value === undefined || value === null ? '' : String(value)
}

function trimOf(value) {
  return textOf(value).trim()
}

function isBlank(value) {
  return trimOf(value) === ''
}

/** 字符数（按码点计，中文一字计一）。 */
export function charLength(value) {
  return Array.from(textOf(value)).length
}

/**
 * 消息长度（按 UTF-16 码元计，比码点更保守）。
 *
 * QQ 的单条上限按字符计，emoji 等补充平面字符在 UTF-16 下占两个码元；
 * 4500 字的判定用这个函数，避免「看起来 4490 字实际发不出去」。
 */
export function messageLength(value) {
  return textOf(value).length
}

function normalizeNewlines(value) {
  return textOf(value).replace(/\r\n?/g, '\n')
}

function splitSemicolon(content) {
  return content
    .split(/[;；]/)
    .map((item) => item.trim())
    .filter((item) => item !== '')
}

function partition(text, separator) {
  const index = text.indexOf(separator)
  if (index < 0) return [text, '']
  return [text.slice(0, index), text.slice(index + separator.length)]
}

function withHalfColon(text) {
  return text.replace(/：/g, ':')
}

function integerOf(value, label) {
  const raw = trimOf(value)
  if (!/^-?\d+$/.test(raw)) fail(`${label}必须是整数: ${value}`)
  return Number(raw)
}

function unsignedOf(value, label) {
  const raw = trimOf(value)
  if (!/^\d+$/.test(raw)) fail(`${label}必须是整数: ${value}`)
  return Number(raw)
}

/**
 * 创建一个空的表单状态（各段都有默认形状，列表类预置一条空行便于上手）。
 * 返回的是全新对象，可反复调用、互不共享引用。
 */
export function createEmptyState(spec) {
  const builder = createCardBuilder(spec)
  return builder.createState()
}

/**
 * 绑定一份段清单，返回这个建卡器实例的全部操作。
 * 同一份 spec 只需调用一次；页面与校验脚本各调一次即可。
 */
export function createCardBuilder(spec) {
  if (!spec || !Array.isArray(spec.segments) || spec.segments.length === 0) {
    fail('卡段清单为空或格式错误，无法创建建卡器')
  }
  const enums = spec.enums || {}
  const limits = spec.limits || {}
  const abilities = enums.abilities || []
  const skills = enums.skills || []
  const savingItems = enums.saving_items || []
  const checkItems = enums.check_items || []
  const extItems = enums.ext_items || []
  const savingAllKey = enums.saving_all_key || '豁免'
  const skillParent = enums.skill_parent || {}
  const savingParent = enums.saving_parent || {}
  const skillSynonyms = enums.skill_synonyms || {}
  const classSynonyms = enums.class_synonyms || {}
  const damageTypeSynonyms = enums.damage_type_synonyms || {}
  const damageTypes = enums.damage_types || []
  const proficiencyGroups = enums.proficiency_groups || []
  const backgroundKeys5r = enums.background_keys_5r || []
  const backgroundKeys5e = enums.background_keys_5e || backgroundKeys5r
  const backgroundKeys = enums.background_keys || [
    ...new Set([...backgroundKeys5r, ...backgroundKeys5e]),
  ]
  const subclassLevel5r = Number(enums.subclass_level_5r || 3)
  const subclassLevel5e = enums.subclass_level_5e || {}
  const defaultSubclassLevel = Number(enums.default_subclass_level || 3)
  const xpThresholds = Array.isArray(enums.xp_thresholds) ? enums.xp_thresholds : []
  const coinKeys = enums.coin_keys || []
  const recoverModes = enums.recover_modes || []
  const spellDetailKeys = enums.spell_detail_keys || []

  const segments = spec.segments.slice()
  const segmentMap = new Map(segments.map((segment) => [segment.key, segment]))
  const order =
    Array.isArray(spec.output_order) && spec.output_order.length > 0
      ? spec.output_order.slice()
      : segments.map((segment) => segment.key)
  const formOrder =
    Array.isArray(spec.form_order) && spec.form_order.length > 0
      ? spec.form_order.slice()
      : order.slice()

  // 防漂移：清单里的每个段都必须有表单形态，反之亦然（Node 校验脚本也会查）
  for (const segment of segments) {
    if (!SEGMENT_KINDS[segment.key]) {
      fail(`段清单中的 ${segment.key} 没有对应的表单形态（core.mjs）`)
    }
    if (typeof segment.example !== 'string') {
      fail(`段清单中的 ${segment.key} 缺少示例`)
    }
  }
  for (const key of Object.keys(SEGMENT_KINDS)) {
    if (!segmentMap.has(key)) fail(`表单形态 ${key} 不在段清单中（core.mjs 需要更新）`)
  }
  if (new Set(order).size !== order.length) fail('卡文本回写顺序有重复段')
  for (const key of order) {
    if (!segmentMap.has(key)) fail(`回写顺序中的 ${key} 不在段清单中`)
  }
  if (order.length !== segments.length) fail('卡文本回写顺序没有覆盖全部段')
  if (new Set(formOrder).size !== formOrder.length) fail('表单顺序有重复段')
  for (const key of formOrder) {
    if (!segmentMap.has(key)) fail(`表单顺序中的 ${key} 不在段清单中`)
  }
  if (formOrder.length !== segments.length) fail('表单顺序没有覆盖全部段')
  const formSegments = formOrder.map((key) => segmentMap.get(key))

  function labelOf(key) {
    const segment = segmentMap.get(key)
    return segment ? segment.label : key
  }

  function normalizeSkillName(name) {
    return skillSynonyms[name] || name
  }

  function normalizeClassName(name) {
    return classSynonyms[name] || name
  }

  function normalizeDamageTypeName(name) {
    if (damageTypeSynonyms[name]) return damageTypeSynonyms[name]
    return damageTypes.includes(name) ? name : ''
  }

  function backgroundKeysFor(version) {
    return version === '5e' ? backgroundKeys5e : backgroundKeys5r
  }

  /** 职业的子职等级：5r 固定 3；5e 按职业；自定义职业默认 3。 */
  function subclassLevelFor(className, version = '5r') {
    if (version !== '5e') return subclassLevel5r
    return subclassLevel5e[normalizeClassName(className)] || defaultSubclassLevel
  }

  function proficiencyBonusOfLevel(level) {
    const value = Number(level)
    if (!Number.isFinite(value) || value < 1) return ''
    return 2 + Math.floor((value - 1) / 4)
  }

  function xpNextForLevel(level) {
    const value = Number(level)
    if (!Number.isInteger(value) || value < 1 || value >= 20) return ''
    return xpThresholds[value] === undefined ? '' : String(xpThresholds[value])
  }

  function isSubclassAvailable(state, version = '5r') {
    const level = Number(trimOf(state[K.LEVEL]))
    const className = trimOf(state[K.CLASS])
    if (!Number.isFinite(level) || level < 1) return false
    return level >= subclassLevelFor(className, version)
  }

  function singleLine(value, label) {
    const text = normalizeNewlines(value).trim()
    if (text.includes('\n')) fail(`${label}内容不能换行`)
    return text
  }

  function normalizeSigned(value, label) {
    const raw = trimOf(value).replace(/＋/g, '+').replace(/－/g, '-')
    if (!SIGNED_RE.test(raw)) fail(`${label}加值无效: ${value}（示例：+7）`)
    const number = Number(raw)
    const bound = limits.signed_bonus_max || 99
    if (number < -bound || number > bound) {
      fail(`${label}加值超出范围: ${value}（-${bound}~+${bound}）`)
    }
    return `${number >= 0 ? '+' : ''}${number}`
  }

  // ── 各段解析（输入是骰娘能接受的段内容，输出是表单状态）──────────────

  function parseHp(content) {
    const matched =
      /^(-?\d+)\s*(?:\(\s*(\d+)\s*\))?\s*(?:\/\s*(\d+))?\s*(?:\(\s*(\d+)\s*\))?$/.exec(
        content.trim(),
      )
    if (!matched) {
      fail(`生命值写法无效: ${content}（示例：29/37 (5)）`)
    }
    const temp = matched[2] || matched[4] || ''
    return { cur: matched[1], max: matched[3] || '', temp }
  }

  function parseHpDice(content) {
    const matched = /^(\d+)\s*(?:\/\s*(\d+))?\s*[dD]\s*(\d+)$/.exec(
      content.trim(),
    )
    if (!matched) {
      fail(`生命骰信息不正确: ${content}（示例：5/5 D6）`)
    }
    const num = matched[1]
    return { num, max: matched[2] || num, type: matched[3] }
  }

  function parseCombat(content) {
    const result = { AC: '', 速度: '' }
    const derivedKeys = new Set(['先攻', '被动察觉'])
    for (const item of splitSemicolon(content)) {
      const normalized = withHalfColon(item)
      const [rawKey, rawValue] = partition(normalized, ':')
      let key = rawKey.trim()
      const value = rawValue.trim()
      if (key.toLowerCase() === 'ac') key = 'AC'
      // 旧卡的派生值仍可导入，但不再保留：先攻 / 被动察觉由网页与骰娘现算。
      if (derivedKeys.has(key)) continue
      if (!Object.hasOwn(result, key)) {
        fail(`战斗条目不完整: ${item}（可用：AC/速度）`)
      }
      if (result[key] !== '') fail(`战斗条目重复: ${key}`)
      if (!value) fail(`战斗条目缺少取值: ${item}`)
      if (key === '速度') {
        if (charLength(value) > (limits.combat_speed_max_len || 20)) {
          fail(`速度写法无效: ${value}（最长 20 字）`)
        }
        result[key] = value
      } else {
        const number = unsignedOf(value, key)
        if (number > 99) fail(`${key}必须是 0~99 的整数: ${value}`)
        result[key] = String(number)
      }
    }
    return result
  }

  function parseProgress(content) {
    const result = { xp: '', xpNext: '', inspiration: '' }
    for (const item of splitSemicolon(content)) {
      const [rawKey, rawValue] = partition(withHalfColon(item), ':')
      const key = rawKey.trim()
      const value = rawValue.trim()
      if (!key || !value) {
        fail(`进度条目不完整: ${item}（示例：经验:6500/14000; 激励:有）`)
      }
      if (key === '经验') {
        const parts = value.split('/').map((part) => part.trim())
        if (parts.length > 2 || parts.some((part) => !/^\d+$/.test(part))) {
          fail(`经验值写法无效: ${item}（示例：经验:6500/14000）`)
        }
        for (const part of parts) {
          if (Number(part) > (limits.xp_max || 9999999)) {
            fail(`经验值超出范围（0~${limits.xp_max || 9999999}）: ${item}`)
          }
        }
        result.xp = String(Number(parts[0]))
        result.xpNext = parts.length > 1 ? String(Number(parts[1])) : ''
      } else if (key === '激励') {
        if (['有', '是', '1'].includes(value)) result.inspiration = '有'
        else if (['无', '否', '0'].includes(value)) result.inspiration = '无'
        else fail(`激励只能写 有 或 无: ${item}`)
      } else {
        fail(`进度条目不完整: ${item}（示例：经验:6500/14000; 激励:有）`)
      }
    }
    return result
  }

  function parseAbility(content) {
    const parts = content.split('/')
    if (parts.length !== abilities.length) {
      fail(`属性段必须写全 ${abilities.length} 个数值（力量/敏捷/体质/智力/感知/魅力）`)
    }
    const values = parts.map((part, index) => {
      const value = part.trim()
      if (!/^\d+$/.test(value)) {
        fail(`${abilities[index]}属性值${value}必须为正整数`)
      }
      return String(Number(value))
    })
    return values
  }

  function parseProf(content) {
    const checks = Object.fromEntries(checkItems.map((name) => [name, 0]))
    const groups = Object.fromEntries(proficiencyGroups.map((name) => [name, '']))
    for (const rawItem of content.split('/')) {
      const item = rawItem.trim()
      if (!item) continue
      const normalized = withHalfColon(item)
      const [rawPrefix, rawRest] = partition(normalized, ':')
      const prefix = rawPrefix.trim()
      if (normalized.includes(':') && proficiencyGroups.includes(prefix)) {
        const values = rawRest
          .split(/[·、,，]/)
          .map((value) => value.trim())
          .filter((value) => value !== '')
        if (values.length === 0) {
          fail(`熟练分组「${prefix}」不能为空（示例：${prefix}:轻甲·中甲）`)
        }
        const maxLen = limits.proficiency_group_item_max_len || 20
        const current = groups[prefix]
          ? groups[prefix].split('·')
          : []
        for (const value of values) {
          if (charLength(value) > maxLen) {
            fail(`熟练分组「${prefix}」的条目长度不能超过${maxLen} 字: ${value}`)
          }
          if (current.includes(value)) {
            fail(`熟练分组「${prefix}」条目重复: ${value}`)
          }
          current.push(value)
        }
        if (current.length > (limits.proficiency_group_item_max || 20)) {
          fail(`熟练分组「${prefix}」最多 ${limits.proficiency_group_item_max || 20} 项`)
        }
        groups[prefix] = current.join('·')
        continue
      }
      let scale = 1
      let name = item
      if (item.includes('*')) {
        const starIndex = item.indexOf('*')
        const scaleText = item.slice(0, starIndex)
        name = item.slice(starIndex + 1)
        if (!/^\d+$/.test(scaleText.trim())) {
          fail(`${name}熟练加值倍数必须为非负整数`)
        }
        scale = Number(scaleText.trim())
      }
      name = normalizeSkillName(name.trim())
      if (!checkItems.includes(name)) {
        fail(`${name}为无效的检定条目（可用：六属性、18 技能、六豁免）`)
      }
      checks[name] = scale
    }
    return { checks, groups }
  }

  function parseExt(content) {
    const rows = []
    const indexByName = new Map()
    for (const item of content.split('/')) {
      const raw = item.trim()
      if (!raw) continue
      const [rawName, rawValue] = partition(withHalfColon(raw), ':')
      const name = normalizeSkillName(rawName.trim())
      let value = rawValue.trim()
      if (!value) continue
      if (!extItems.includes(name)) {
        fail(`${name}为无效条目（可用：六属性、18 技能、六豁免，以及全局「豁免」）`)
      }
      let adv = ''
      if (value.startsWith('优势') || value.startsWith('劣势')) {
        adv = value.slice(0, 2)
        value = value.slice(2).trim()
      }
      if (value && !WEAPON_BONUS_RE.test(value)) {
        fail(`调整值无效: 必须以 优势/劣势 或 +/- 开头，如 隐匿:优势+2`)
      }
      const row = { key: name, adv, bonus: value }
      if (indexByName.has(name)) rows[indexByName.get(name)] = row
      else {
        indexByName.set(name, rows.length)
        rows.push(row)
      }
    }
    return rows
  }

  function parseNamedRows(content, label, nameMax, textMax) {
    const rows = []
    const seen = new Set()
    for (const item of content.split('/')) {
      const raw = item.trim()
      if (!raw) continue
      const [rawName, rawText] = partition(withHalfColon(raw), ':')
      const name = rawName.trim()
      const text = rawText.trim()
      if (!name) fail(`${label}名称不能为空: ${item}`)
      if (charLength(name) > nameMax) {
        fail(`${label}名称过长（≤${nameMax} 字）: ${name}`)
      }
      if (charLength(text) > textMax) {
        fail(`${label}说明过长（≤${textMax} 字）: ${text}`)
      }
      if (seen.has(name)) fail(`${label}重复: ${name}`)
      seen.add(name)
      rows.push({ name, text })
    }
    return rows
  }

  function parseWeapons(content) {
    const rows = []
    const seen = new Set()
    for (const rawItem of content.split('/')) {
      const item = rawItem.trim()
      if (!item) continue
      const normalized = item.replace(/，/g, ',')
      const parts = normalized.split(',')
      if (parts.length > 3) {
        fail(`武器条目最多三段: ${item}（名称+命中,伤害+类型,备注）`)
      }
      const namePart = parts[0].trim()
      const damagePart = parts[1] === undefined ? '' : parts[1].trim()
      const note = parts[2] === undefined ? '' : parts[2].trim()
      if (!namePart || !damagePart) {
        fail(`武器条目不完整: ${item}（示例：短剑+6,1d4+4穿刺）`)
      }
      const signIndex = namePart.search(/[+-]/)
      let name = signIndex < 0 ? namePart.trim() : namePart.slice(0, signIndex).trim()
      const bonus =
        signIndex < 0 ? '' : namePart.slice(signIndex).replace(/\s+/g, '')
      let noAttack = false
      if (
        name.length > 1 &&
        /[xX]$/.test(name) &&
        !/[A-Za-z0-9]/.test(name[name.length - 2])
      ) {
        if (bonus) {
          fail(`武器条目写法无效: ${item}（x 标记表示不可攻击检定，不要再写命中加值）`)
        }
        noAttack = true
        name = name.slice(0, -1).trim()
      }
      validateWeaponName(name)
      if (bonus && !WEAPON_BONUS_RE.test(bonus)) {
        fail(`武器命中加值无效: ${name}${bonus}（仅支持骰子与常数的加减组合，如 +6）`)
      }
      if (note) {
        if (charLength(note) > (limits.weapon_note_max_len || 30)) {
          fail(`武器备注过长（≤${limits.weapon_note_max_len || 30} 字）: ${note}`)
        }
        for (const char of ['/', ';', '；', '$', '|', '｜']) {
          if (note.includes(char)) fail(`武器备注不能包含符号「${char}」: ${note}`)
        }
      }
      const damageText = damagePart.replace(/\s+/g, '')
      let damageExpr = damageText
      let damageType = ''
      const typeNames = [...damageTypes, ...Object.keys(damageTypeSynonyms)].sort(
        (left, right) => right.length - left.length,
      )
      for (const typeName of typeNames) {
        if (
          damageText.endsWith(typeName) &&
          damageText.length > typeName.length
        ) {
          damageExpr = damageText.slice(0, -typeName.length)
          damageType = normalizeDamageTypeName(typeName)
          break
        }
      }
      if (!DAMAGE_ITEM_RE.test(damageExpr)) {
        fail(`武器伤害表达式无效: ${damageExpr}（仅支持骰子与常数的加减组合，如 1d4+4）`)
      }
      if (seen.has(name)) fail(`武器名称重复: ${name}`)
      seen.add(name)
      rows.push({
        name,
        noAttack,
        attack: bonus,
        damage: damageExpr,
        type: damageType,
        note,
      })
    }
    return rows
  }

  function validateWeaponName(name) {
    if (!name) fail('武器名称不能为空')
    if (charLength(name) > (limits.weapon_name_max_len || 20)) {
      fail(`武器名称过长（≤${limits.weapon_name_max_len || 20} 字）: ${name}`)
    }
    for (const char of ['/', ',', '，', '$', '+', '-']) {
      if (name.includes(char)) fail(`武器名称不能包含符号「${char}」: ${name}`)
    }
    for (const word of ['攻击', '命中', '伤害', '检定', '豁免']) {
      if (name.includes(word)) fail(`武器名称不能包含「${word}」字样: ${name}`)
    }
    if (checkItems.includes(name)) fail(`武器名称不能与检定条目重名: ${name}`)
  }

  function parseFeatures(content) {
    const rows = []
    const seen = new Set()
    for (const item of splitSemicolon(content)) {
      const [body, textRaw] = partition(withHalfColon(item), '|')
      const text = textRaw.trim()
      if (text.includes('|')) fail(`限定资源说明不能包含符号「|」: ${item}`)
      if (charLength(text) > (limits.feature_text_max_len || 80)) {
        fail(`限定资源说明过长（≤${limits.feature_text_max_len || 80} 字）: ${item}`)
      }
      const [rawName, rawValue] = partition(body, ':')
      const name = rawName.trim()
      if (!rawValue) {
        fail(`限定资源条目不完整: ${item}（示例：引导神力:2/2短休+1,长休）`)
      }
      if (!name) fail('限定资源名称不能为空')
      if (charLength(name) > (limits.feature_name_max_len || 20)) {
        fail(`限定资源名称过长（≤${limits.feature_name_max_len || 20} 字）: ${name}`)
      }
      for (const char of [
        '/', ',', '，', ':', '：', ';', '；', '$', '+', '-', '|', '｜',
      ]) {
        if (name.includes(char)) fail(`限定资源名称不能包含符号「${char}」: ${name}`)
      }
      for (const word of ['攻击', '命中', '伤害', '检定', '豁免']) {
        if (name.includes(word)) fail(`限定资源名称不能包含「${word}」字样: ${name}`)
      }
      const matched = /^(\d+)\s*\/\s*(\d+)\s*(.*)$/.exec(rawValue.trim())
      if (!matched) {
        fail(`限定资源次数无效: ${item}（写法：当前/上限恢复档，如 2/2短休+1,长休）`)
      }
      const cur = Number(matched[1])
      const max = Number(matched[2])
      if (max <= 0) fail(`限定资源上限必须大于 0: ${item}`)
      if (cur > max) fail(`限定资源当前次数不能超过上限: ${item}`)
      const modes = parseFeatureRecover(matched[3])
      if (seen.has(name)) fail(`限定资源名称重复: ${name}`)
      seen.add(name)
      rows.push({ name, cur: String(cur), max: String(max), modes, text })
    }
    return rows
  }

  function parseFeatureRecover(source) {
    const modes = Object.fromEntries(
      recoverModes.map((mode) => [mode, { on: false, amount: '' }]),
    )
    let found = 0
    for (const piece of source.split(/[,，]/)) {
      const token = piece.trim()
      if (!token) continue
      const mode = recoverModes.find((item) => token.startsWith(item))
      if (!mode) {
        fail(`限定资源恢复方式无效: ${token}（可选：短休/长休/两者/手动，可加 +N 或 满）`)
      }
      const tail = token.slice(mode.length).trim()
      if (mode === '手动' && tail) fail(`「手动」不能带恢复量: ${token}`)
      if (modes[mode].on) fail(`限定资源恢复方式重复: ${token}`)
      if (tail && tail !== '满') {
        const matched = /^\+(\d+)$/.exec(tail)
        if (!matched || Number(matched[1]) <= 0) {
          fail(`限定资源恢复量无效: ${tail}（可写 +N 或 满，如 短休+1、长休满）`)
        }
        modes[mode] = { on: true, amount: String(Number(matched[1])) }
      } else {
        modes[mode] = { on: true, amount: '' }
      }
      found += 1
    }
    if (found === 0) {
      fail('限定资源恢复方式不能为空（可选：短休/长休/两者/手动，可加 +N 或 满）')
    }
    if (modes['两者'].on && (modes['短休'].on || modes['长休'].on)) {
      fail('「两者」已含短休与长休，不要再分别写')
    }
    return modes
  }

  function emptySpellDetail() {
    return {
      time: '',
      range: '',
      concentration: false,
      ritual: false,
      material: false,
      note: '',
    }
  }

  function parseSpellDetail(source) {
    const detail = emptySpellDetail()
    const seen = new Set()
    for (const piece of source.split(',')) {
      const text = piece.trim()
      if (!text) {
        fail('法术详情中有空项（用逗号分隔，如 时间=1动作,距离=150尺）')
      }
      const [rawKey, rawValue] = partition(text, '=')
      const key = rawKey.trim()
      const value = rawValue.trim()
      if (!spellDetailKeys.includes(key)) {
        fail(
          `法术详情写法无效: ${text}（可用：${spellDetailKeys.join('/')}，如 时间=1动作）`,
        )
      }
      if (seen.has(key)) fail(`法术详情重复: ${key}`)
      seen.add(key)
      if (key === '时间') {
        if (charLength(value) < 1 || charLength(value) > (limits.spell_time_max_len || 12)) {
          fail(`法术施法时间过长（≤${limits.spell_time_max_len || 12} 字）: ${value}`)
        }
        detail.time = value
      } else if (key === '距离') {
        if (charLength(value) < 1 || charLength(value) > (limits.spell_range_max_len || 12)) {
          fail(`法术施法距离过长（≤${limits.spell_range_max_len || 12} 字）: ${value}`)
        }
        detail.range = value
      } else if (key === '专注') {
        detail.concentration = parseSpellFlag(value, key)
      } else if (key === '仪式') {
        detail.ritual = parseSpellFlag(value, key)
      } else if (key === '材料') {
        detail.material = parseSpellFlag(value, key)
      } else {
        if (charLength(value) < 1 || charLength(value) > (limits.spell_note_max_len || 40)) {
          fail(`法术备注过长（≤${limits.spell_note_max_len || 40} 字）: ${value}`)
        }
        for (const char of [',', '，', ';', '；', '|', '｜', '$']) {
          if (value.includes(char)) fail(`法术备注不能包含符号「${char}」: ${value}`)
        }
        detail.note = value
      }
    }
    return detail
  }

  function parseSpellFlag(value, label) {
    if (['是', '有', '1'].includes(value)) return true
    if (['否', '无', '0'].includes(value)) return false
    fail(`法术「${label}」只能写 是 或 否: ${value}`)
  }

  function parseSpellEntry(item) {
    const [entryText, detailText] = partition(withHalfColon(item), '|')
    const [rawName, rawLevel] = partition(entryText, ':')
    const name = rawName.trim()
    if (!rawLevel) fail(`法术条目不完整: ${item}（示例：火球术:3*）`)
    validateSpellName(name)
    let levelText = rawLevel.trim()
    let prepared = false
    if (levelText.endsWith('*') || levelText.endsWith('＊')) {
      prepared = true
      levelText = levelText.slice(0, -1).trim()
    }
    if (!/^\d+$/.test(levelText)) {
      fail(`法术环阶无效: ${item}（写 0~9 的数字，0 = 戏法）`)
    }
    const level = Number(levelText)
    if (level > (limits.spell_level_max || 9)) {
      fail(`法术环阶无效: ${item}（写 0~9 的数字，0 = 戏法）`)
    }
    const detail = detailText === '' ? emptySpellDetail() : parseSpellDetail(detailText)
    return { name, level: String(level), prepared, ...detail }
  }

  function validateSpellName(name) {
    if (!name) fail('法术名称不能为空')
    if (charLength(name) > (limits.spell_name_max_len || 20)) {
      fail(`法术名称过长（≤${limits.spell_name_max_len || 20} 字）: ${name}`)
    }
    for (const char of ['/', ',', '，', ':', '：', ';', '；', '$', '*', '＊', '|', '｜']) {
      if (name.includes(char)) fail(`法术名称不能包含符号「${char}」: ${name}`)
    }
  }

  function parseSpells(content) {
    const result = { ability: '', dc: '', attack: '', list: [] }
    const seen = new Set()
    for (const item of splitSemicolon(content)) {
      const normalized = withHalfColon(item)
      const [rawKey, rawValue] = partition(normalized, ':')
      const key = rawKey.trim()
      if (key === '施法属性') {
        const value = rawValue.trim()
        if (!abilities.includes(value)) {
          fail(`施法属性无效: ${value}（可选：${abilities.join('/')}）`)
        }
        if (result.ability) fail('施法属性只能写一条')
        result.ability = value
        continue
      }
      if (key === '豁免DC') {
        const value = rawValue.trim()
        if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > (limits.spell_dc_max || 99)) {
          fail(`豁免DC必须是 1~${limits.spell_dc_max || 99} 的整数: ${value}`)
        }
        if (result.dc) fail('豁免DC只能写一条')
        result.dc = String(Number(value))
        continue
      }
      if (key === '法术攻击') {
        if (result.attack) fail('法术攻击只能写一条')
        result.attack = normalizeSigned(rawValue, '法术攻击')
        continue
      }
      const spell = parseSpellEntry(item)
      if (seen.has(spell.name)) fail(`法术名称重复: ${spell.name}`)
      seen.add(spell.name)
      result.list.push(spell)
    }
    return result
  }

  function parseSlots(content) {
    const levels = Array.from({ length: 9 }, () => ({ cur: '', max: '' }))
    const pact = { level: '', cur: '', max: '' }
    const seen = new Set()
    for (const raw of content.split(/[;；,，]/)) {
      const item = raw.trim()
      if (!item) continue
      const matched = /^(契约)?\s*(\d+)\s*:\s*(\d+)\s*\/\s*(\d+)$/.exec(
        withHalfColon(item),
      )
      if (!matched) {
        fail(`法术位条目不完整: ${item}（示例：1:4/4; 契约3:2/2）`)
      }
      const isPact = Boolean(matched[1])
      const level = Number(matched[2])
      const cur = Number(matched[3])
      const max = Number(matched[4])
      if (level < 1 || level > 9) fail(`法术位环阶无效: ${item}（1~9 环）`)
      if (cur < 0 || cur > 99 || max < 0 || max > 99) {
        fail(`法术位数量无效: ${item}（0~99）`)
      }
      if (cur > max) fail(`法术位当前值不能超过上限: ${item}`)
      const dedupeKey = `${isPact ? 'pact' : 'slot'}:${level}`
      if (seen.has(dedupeKey)) fail(`法术位重复: ${isPact ? '契约' : ''}${level}环`)
      seen.add(dedupeKey)
      if (isPact) {
        if (max > 0) {
          pact.level = String(level)
          pact.cur = String(cur)
          pact.max = String(max)
        }
      } else if (max > 0) {
        levels[level - 1] = { cur: String(cur), max: String(max) }
      }
    }
    return { levels, pact }
  }

  function parseItems(content) {
    const rows = []
    for (const item of splitSemicolon(content)) {
      const raw = item.trim()
      if (raw.includes('[') || raw.includes(']')) {
        fail(`物品条目写法无效: ${item}（只写 名称x数量，不再支持 [装备]）`)
      }
      const matched = /^(.+?)(?:[xX×](\d+))?$/.exec(raw)
      if (!matched) fail(`物品条目写法无效: ${item}`)
      const name = matched[1].trim()
      const quantity = matched[2] === undefined ? 1 : Number(matched[2])
      if (!name) fail(`物品名称不能为空: ${item}`)
      if (charLength(name) > (limits.item_name_max_len || 30)) {
        fail(`物品名称过长（≤${limits.item_name_max_len || 30} 字）: ${name}`)
      }
      if (quantity < 1 || quantity > (limits.item_quantity_max || 999)) {
        fail(`物品数量无效: ${item}（1~${limits.item_quantity_max || 999}）`)
      }
      rows.push({ name, qty: String(quantity) })
    }
    return rows
  }

  function parseCoins(content) {
    const result = Object.fromEntries(coinKeys.map((key) => [key, '']))
    const seen = new Set()
    for (const item of splitSemicolon(content)) {
      const [rawKey, rawValue] = partition(withHalfColon(item), ':')
      const key = rawKey.trim().toUpperCase()
      const value = rawValue.trim()
      if (!coinKeys.includes(key)) {
        fail(`钱币条目不完整: ${item}（可用：${coinKeys.join('/')}，示例：GP:18）`)
      }
      if (seen.has(key)) fail(`钱币条目重复: ${key}`)
      const number = unsignedOf(value, '钱币数值')
      if (number > (limits.coin_max || 999999)) {
        fail(`钱币数值超出范围（0~${limits.coin_max || 999999}）: ${item}`)
      }
      result[key] = String(number)
      seen.add(key)
    }
    return result
  }

  function parseBackground(content) {
    const result = Object.fromEntries(backgroundKeys.map((key) => [key, '']))
    const seen = new Set()
    for (const item of splitSemicolon(content)) {
      const [rawKey, rawValue] = partition(withHalfColon(item), ':')
      const key = rawKey.trim()
      const value = rawValue.trim()
      if (!key || !value) {
        fail(`背景条目不完整: ${item}（示例：背景:士兵; 阵营:守序善良）`)
      }
      if (!backgroundKeys.includes(key)) {
        fail(`背景键无效: ${key}（可用：${backgroundKeys.join('/')}）`)
      }
      if (charLength(value) > (limits.background_value_max_len || 100)) {
        fail(`背景内容过长（≤${limits.background_value_max_len || 100} 字）: ${key}`)
      }
      if (seen.has(key)) fail(`背景条目重复: ${key}`)
      seen.add(key)
      result[key] = value
    }
    return result
  }

  function parseNotes(content) {
    const rows = []
    for (const item of splitSemicolon(content)) {
      if (charLength(item) > (limits.combat_note_max_len || 60)) {
        fail(`战斗记录条目过长（≤${limits.combat_note_max_len || 60} 字）: ${item}`)
      }
      rows.push(item)
    }
    return rows
  }

  function parseStory(content) {
    const text = normalizeNewlines(content).trim()
    if (!text) fail('故事内容不能为空')
    if (text.includes('$')) fail('故事内容不能包含符号「$」')
    const max = limits.story_max_len || 1000
    const count = charLength(text.replace(/\n/g, ''))
    if (count > max) {
      fail(`故事内容过长（≤${max} 字，换行不计）`)
    }
    return text
  }

  function parseClassName(content) {
    const value = trimOf(content)
    if (!value) fail('职业名称不能为空')
    const name = normalizeClassName(value)
    if (/[/、+,，兼]/.test(value)) {
      fail('当前版本暂不支持兼职，请填写单一职业名（如 游荡者）')
    }
    if (charLength(name) > (limits.class_name_max_len || 20)) {
      fail(`职业名称过长（≤${limits.class_name_max_len || 20} 字）: ${name}`)
    }
    for (const char of ['$', '|', ';', '；', ':', '：']) {
      if (name.includes(char)) fail(`职业名称不能包含符号「${char}」: ${name}`)
    }
    return name
  }

  function parseClassTraits(content) {
    const rows = []
    const seen = new Set()
    for (const item of content.split('/')) {
      const raw = item.trim()
      if (!raw) continue
      const [levelText, body] = partition(withHalfColon(raw), '|')
      if (!body) fail(`职业特性缺少等级: ${raw}（示例：3|塑能学者:说明）`)
      const level = trimOf(levelText)
      if (!/^\d+$/.test(level) || Number(level) < 1 || Number(level) > 20) {
        fail(`职业特性等级无效: ${raw}（写 1~20）`)
      }
      const [rawName, rawText] = partition(body, ':')
      const name = rawName.trim()
      const text = rawText.trim()
      if (!name) fail(`职业特性名称不能为空: ${raw}`)
      if (charLength(name) > (limits.class_feature_name_max_len || 30)) {
        fail(`职业特性名称过长（≤${limits.class_feature_name_max_len || 30} 字）: ${name}`)
      }
      if (charLength(text) > (limits.class_feature_text_max_len || 80)) {
        fail(`职业特性说明过长（≤${limits.class_feature_text_max_len || 80} 字）: ${text}`)
      }
      if (seen.has(name)) fail(`职业特性重复: ${name}`)
      seen.add(name)
      rows.push({ level: String(Number(level)), name, text })
    }
    return rows
  }

  function magicParagraphsOf(text) {
    return normalizeNewlines(text)
      .split(/\n\s*\n/)
      .map((paragraph) => paragraph.replace(/\n/g, ' ').trim())
      .filter((paragraph) => paragraph !== '')
  }

  function parseMagicItems(content) {
    const rows = []
    const seen = new Set()
    for (const item of splitSemicolon(content)) {
      const parts = item.split('|').map((part) => part.trim())
      if (parts.length !== 2 && parts.length !== 3) {
        fail(`魔法物品条目不完整: ${item}（写法：名称|标签|说明，说明可省略）`)
      }
      const [name, tag] = parts
      const text = parts.length === 3 ? parts[2] : ''
      if (!name) fail(`魔法物品名称不能为空: ${item}`)
      if (!tag) fail(`魔法物品标签不能为空: ${item}`)
      if (charLength(name) > (limits.magic_item_name_max_len || 30)) {
        fail(`魔法物品名称过长（≤${limits.magic_item_name_max_len || 30} 字）: ${name}`)
      }
      if (charLength(tag) > (limits.magic_item_tag_max_len || 60)) {
        fail(`魔法物品标签过长（≤${limits.magic_item_tag_max_len || 60} 字）: ${tag}`)
      }
      for (const field of [name, tag]) {
        for (const char of ['|', ';', '；', '$']) {
          if (field.includes(char)) fail(`魔法物品名称/标签不能包含符号「${char}」: ${field}`)
        }
      }
      if (seen.has(name)) fail(`魔法物品重复: ${name}`)
      seen.add(name)
      const paragraphs = text
        .split('//')
        .map((paragraph) => paragraph.trim())
        .filter((paragraph) => paragraph !== '')
      if (paragraphs.length > (limits.magic_item_paragraph_max || 5)) {
        fail(`魔法物品说明最多 ${limits.magic_item_paragraph_max || 5} 段: ${item}`)
      }
      const total = paragraphs.reduce((sum, paragraph) => sum + charLength(paragraph), 0)
      if (total > (limits.magic_item_text_max_len || 500)) {
        fail(`魔法物品说明过长（≤${limits.magic_item_text_max_len || 500} 字）: ${item}`)
      }
      rows.push({ name, tag, text: paragraphs.join('\n\n') })
    }
    return rows
  }

  function parseSegment(key, content) {
    const kind = SEGMENT_KINDS[key]
    switch (kind) {
      case 'text':
        return singleLine(content, labelOf(key))
      case 'longtext':
        return parseStory(content)
      case 'class':
        return parseClassName(content)
      case 'subclass':
        return singleLine(content, '子职')
      case 'number': {
        const value = integerOf(content, '等级')
        if (value <= 0) fail(`等级必须为正整数: ${content}`)
        return String(value)
      }
      case 'hp':
        return parseHp(content)
      case 'hpdice':
        return parseHpDice(content)
      case 'combat':
        return parseCombat(content)
      case 'progress':
        return parseProgress(content)
      case 'ability':
        return parseAbility(content)
      case 'prof':
        return parseProf(content)
      case 'ext':
        return parseExt(content)
      case 'feats':
        return parseNamedRows(
          content,
          '专长',
          limits.feat_name_max_len || 20,
          limits.feat_text_max_len || 60,
        )
      case 'raceTraits':
        return parseNamedRows(
          content,
          '种族特性',
          limits.race_trait_name_max_len || 30,
          limits.race_trait_text_max_len || 80,
        )
      case 'classTraits':
        return parseClassTraits(content)
      case 'magicItems':
        return parseMagicItems(content)
      case 'weapons':
        return parseWeapons(content)
      case 'items':
        return parseItems(content)
      case 'coins':
        return parseCoins(content)
      case 'features':
        return parseFeatures(content)
      case 'spells':
        return parseSpells(content)
      case 'slots':
        return parseSlots(content)
      case 'notes':
        return parseNotes(content)
      case 'background':
        return parseBackground(content)
      default:
        fail(`未知的段类型: ${kind}`)
    }
  }

  // ── 表单状态 → 段内容（导出）─────────────────────────────────────────

  function createState() {
    return {
      [K.NAME]: '',
      [K.RACE]: '',
      [K.CLASS]: '',
      [K.SUBCLASS]: '',
      [K.BACKGROUND]: Object.fromEntries(backgroundKeys.map((key) => [key, ''])),
      [K.STORY]: '',
      [K.LEVEL]: '',
      [K.HP]: { cur: '', max: '', temp: '' },
      [K.HP_DICE]: { num: '', max: '', type: '' },
      [K.COMBAT]: { AC: '', 速度: '' },
      [K.PROGRESS]: { xp: '', xpNext: '', inspiration: '无' },
      [K.ABILITY]: abilities.map(() => ''),
      [K.PROF]: {
        checks: Object.fromEntries(checkItems.map((name) => [name, 0])),
        groups: Object.fromEntries(proficiencyGroups.map((name) => [name, ''])),
      },
      [K.EXT]: [{ key: '', adv: '', bonus: '' }],
      [K.FEATS]: [{ name: '', text: '' }],
      [K.RACE_TRAITS]: [{ name: '', text: '' }],
      [K.CLASS_TRAITS]: [{ level: '1', name: '', text: '' }],
      [K.WEAPON]: [
        { name: '', noAttack: false, attack: '', damage: '', type: '', note: '' },
      ],
      [K.ITEMS]: [{ name: '', qty: '1' }],
      [K.COINS]: Object.fromEntries(coinKeys.map((key) => [key, ''])),
      [K.FEATURE]: [
        {
          name: '',
          cur: '',
          max: '',
          modes: Object.fromEntries(
            recoverModes.map((mode) => [mode, { on: false, amount: '' }]),
          ),
          text: '',
        },
      ],
      [K.MAGIC_ITEMS]: [{ name: '', tag: '', text: '' }],
      [K.SPELL]: {
        ability: '',
        dc: '',
        attack: '',
        dcManual: false,
        attackManual: false,
        list: [{ name: '', level: '0', prepared: false, ...emptySpellDetail() }],
      },
      [K.SPELL_SLOTS]: {
        levels: Array.from({ length: 9 }, () => ({ cur: '', max: '' })),
        pact: { level: '', cur: '', max: '' },
      },
      [K.COMBAT_NOTES]: [''],
    }
  }

  function normalizeIntText(value) {
    const text = trimOf(value)
    if (/^-?\d+$/.test(text)) return String(Number(text))
    return text
  }

  function buildText(key, value) {
    const text = singleLine(value, labelOf(key))
    return text
  }

  function buildBackground(state, options = {}) {
    const values = state[K.BACKGROUND] || {}
    const allowed = backgroundKeysFor(options.rulesVersion || '5r')
    const items = []
    for (const key of allowed) {
      const value = trimOf(values[key])
      if (value) items.push(`${key}:${value}`)
    }
    return items.join('; ')
  }

  function buildHp(state) {
    const hp = state[K.HP]
    const cur = trimOf(hp.cur)
    const max = trimOf(hp.max)
    const temp = trimOf(hp.temp)
    if (!cur) {
      if (max || temp) fail('生命值要先填当前值（示例：29/37 (5)）')
      return ''
    }
    let text = normalizeIntText(cur)
    if (max) text += `/${normalizeIntText(max)}`
    if (temp) text += ` (${normalizeIntText(temp)})`
    return text
  }

  function buildHpDice(state) {
    const dice = state[K.HP_DICE]
    const num = trimOf(dice.num)
    const max = trimOf(dice.max)
    const type = trimOf(dice.type)
    if (!num && !max && !type) return ''
    if (!num || !type) fail('生命骰要写数量与骰面（示例：5/5 D6）')
    return `${normalizeIntText(num)}/${normalizeIntText(max || num)} D${normalizeIntText(type)}`
  }

  function deriveProficiencyBonus(state) {
    return proficiencyBonusOfLevel(trimOf(state[K.LEVEL]))
  }

  function deriveXpNext(state) {
    return xpNextForLevel(Number(trimOf(state[K.LEVEL])))
  }

  /** 先攻 = 敏捷调整值 + 先攻熟练 + 先攻额外加值；卡文本只取常数部分。 */
  function deriveInitiative(state) {
    const raw = deriveCheckValues(state)['先攻'] || ''
    const matched = /^[+-]?\d+/.exec(raw)
    return matched ? normalizeSigned(matched[0], '先攻') : ''
  }

  /**
   * 被动察觉 = 10 + 察觉检定加值；该检定有优势 +5、劣势 -5。
   *
   * 与插件侧一致：只取检定加值的常数部分（骰子项不能静态求值），
   * 技能自身与其父属性（感知）的优劣势都计入，相反时抵消。
   */
  function derivePassivePerception(state) {
    const raw = deriveCheckValues(state)['察觉'] || ''
    const matched = /^[+-]?\d+/.exec(raw)
    if (!matched) return ''
    let value = 10 + Number(matched[0])
    const adv = combinedAdvantage(state, '察觉', '感知')
    if (adv > 0) value += 5
    else if (adv < 0) value -= 5
    return String(value)
  }

  function advantageOf(state, name) {
    let value = 0
    for (const row of state[K.EXT] || []) {
      if (normalizeSkillName(trimOf(row.key)) !== name) continue
      const adv = trimOf(row.adv)
      if (adv === '优势') value += 1
      else if (adv === '劣势') value -= 1
    }
    return value
  }

  function combinedAdvantage(state, skill, parent) {
    const skillAdv = advantageOf(state, skill)
    const parentAdv = advantageOf(state, parent)
    if (skillAdv && parentAdv && skillAdv !== parentAdv) return 0
    return skillAdv || parentAdv
  }

  /**
   * 法术豁免 DC / 法术攻击的公式值：8 + 熟练 + 施法属性调整值 /
   * 熟练 + 施法属性调整值。只用于网页端预填，插件只记录卡文本里的数。
   */
  function deriveSpellStats(state) {
    const spell = state[K.SPELL] || {}
    const ability = trimOf(spell.ability)
    const index = abilities.indexOf(ability)
    const level = Number(trimOf(state[K.LEVEL]))
    const score = Number(trimOf((state[K.ABILITY] || [])[index] || ''))
    if (index < 0 || !Number.isFinite(level) || level < 1) {
      return { dc: '', attack: '', available: false }
    }
    if (!Number.isFinite(score) || score < 1) {
      return { dc: '', attack: '', available: false }
    }
    const prof = 2 + Math.floor((level - 1) / 4)
    const mod = Math.floor((score - 10) / 2)
    return {
      dc: String(8 + prof + mod),
      attack: formatSigned(prof + mod),
      available: true,
    }
  }

  function buildCombat(state) {
    const combat = state[K.COMBAT]
    const items = []
    // 先攻与被动察觉由骰娘按属性、熟练与额外加值现算，不写入卡文本。
    for (const key of ['AC', '速度']) {
      const value = trimOf(combat[key])
      if (!value) continue
      if (key === '速度') items.push(`${key}:${value}`)
      else items.push(`${key}:${normalizeIntText(value)}`)
    }
    return items.join('; ')
  }

  function buildProgress(state) {
    const progress = state[K.PROGRESS]
    const xp = trimOf(progress.xp)
    const items = []
    // 只写当前经验；下一级经验由骰娘按等级表计算，不再写进命令。
    if (xp) items.push(`经验:${normalizeIntText(xp)}`)
    if (progress.inspiration === '有' || (xp && progress.inspiration === '无')) {
      items.push(`激励:${progress.inspiration}`)
    }
    return items.join('; ')
  }

  function buildAbility(state) {
    const values = state[K.ABILITY].map((value) => trimOf(value))
    const filled = values.filter((value) => value !== '').length
    if (filled === 0) return ''
    if (filled !== abilities.length) {
      fail('属性段要写全六个数值（力量/敏捷/体质/智力/感知/魅力）')
    }
    return values.map((value) => normalizeIntText(value)).join('/')
  }

  function buildProf(state) {
    const prof = state[K.PROF]
    const items = []
    for (const name of checkItems) {
      const scale = Number(prof.checks[name] || 0)
      if (!Number.isFinite(scale) || scale <= 0) continue
      items.push(scale === 1 ? name : `${scale}*${name}`)
    }
    for (const label of proficiencyGroups) {
      const raw = trimOf(prof.groups[label])
      if (!raw) continue
      const values = raw
        .split(/[·、,，]/)
        .map((value) => value.trim())
        .filter((value) => value !== '')
      if (values.length === 0) continue
      items.push(`${label}:${values.join('·')}`)
    }
    return items.join('/')
  }

  // ── 派生值预览（与插件 AbilityInfo.get_check_display 同一套口径）─────────
  // 只用于表单展示：让玩家在点选熟练时直接看到骰娘会算出的加值；导出的卡
  // 文本不写这些派生值，插件仍按 $属性$ / $熟练$ / $额外加值$ 现算。

  function formatSigned(value) {
    return value >= 0 ? `+${value}` : String(value)
  }

  /** 把额外加值表达式拆成常数和与剩余骰子表达式（与 Python 侧一致）。 */
  function splitConstantBonus(expr) {
    let total = 0
    let extra = ''
    const pattern = /([+-])\s*([^+-]+)/g
    let match
    while ((match = pattern.exec(expr || '')) !== null) {
      const term = match[2].trim()
      if (/^\d+$/.test(term)) total += Number(`${match[1]}${term}`)
      else if (term) extra += `${match[1]}${term}`
    }
    return [total, extra]
  }

  function abilityModifierOf(score) {
    if (!/^\d+$/.test(score)) return ''
    return formatSigned(Math.floor((Number(score) - 10) / 2))
  }

  /** 六属性的调整值展示（未填/非法时为空串）。 */
  function deriveAbilityModifiers(state) {
    return abilities.map((name, index) =>
      abilityModifierOf(trimOf((state[K.ABILITY] || [])[index] || '')),
    )
  }

  /**
   * 按当前表单算出每个检定条目的展示加值。
   *
   * 公式：属性调整值 + 熟练加值 × 系数 + 额外加值；技能/豁免叠父属性
   * 额外加值，豁免再叠全局「豁免」。骰子项（+1d4）无法静态求和，原样
   * 以 `+1d4` 形式附在数值后面。等级或六属性没填全时返回空对象。
   */
  function deriveCheckValues(state) {
    const rawLevel = trimOf(state[K.LEVEL])
    const scores = (state[K.ABILITY] || []).map((value) => trimOf(value))
    if (!/^\d+$/.test(rawLevel) || Number(rawLevel) <= 0) return {}
    if (
      scores.length !== abilities.length ||
      scores.some((value) => !/^\d+$/.test(value))
    ) {
      return {}
    }
    const profBonus = 2 + Math.floor((Number(rawLevel) - 1) / 4)
    const extMap = {}
    for (const row of state[K.EXT] || []) {
      const key = normalizeSkillName(trimOf(row.key))
      const bonus = trimOf(row.bonus)
      if (!key || !bonus || !WEAPON_BONUS_RE.test(bonus)) continue
      extMap[key] = `${extMap[key] || ''}${bonus}`
    }
    const extOf = (name) => extMap[name] || ''
    const result = {}
    for (const name of checkItems) {
      const isSkill = skills.includes(name)
      const isSaving = savingItems.includes(name)
      const parent = isSkill
        ? skillParent[name]
        : isSaving
          ? savingParent[name]
          : name
      const index = abilities.indexOf(parent)
      if (index < 0) continue
      let total = Math.floor((Number(scores[index]) - 10) / 2)
      const scale = Number(state[K.PROF]?.checks?.[name] || 0)
      total += (Number.isFinite(scale) ? scale : 0) * profBonus
      let expr = extOf(name)
      if (isSkill || isSaving) expr += extOf(parent)
      if (isSaving) expr += extOf(savingAllKey)
      const [constant, extra] = splitConstantBonus(expr)
      result[name] = `${formatSigned(total + constant)}${extra}`
    }
    return result
  }

  function buildExt(state) {
    const rows = state[K.EXT].filter(
      (row) => trimOf(row.key) || trimOf(row.adv) || trimOf(row.bonus),
    )
    const indexOf = (name) => {
      const index = extItems.indexOf(name)
      return index < 0 ? extItems.length : index
    }
    const sorted = rows
      .map((row, index) => ({ row, index }))
      .sort((left, right) => indexOf(left.row.key) - indexOf(right.row.key) || left.index - right.index)
      .map((entry) => entry.row)
    const items = []
    for (const row of sorted) {
      const key = trimOf(row.key)
      const adv = trimOf(row.adv)
      const bonus = trimOf(row.bonus)
      if (!key) {
        if (adv || bonus) fail('额外加值要先写条目（如 隐匿）')
        continue
      }
      const value = `${adv}${bonus}`
      if (!value) continue
      if (bonus && !WEAPON_BONUS_RE.test(bonus)) {
        fail(`额外加值无效: ${key}:${value}（只能写 优势/劣势 或 +/- 开头的骰子与常数组合）`)
      }
      items.push(`${key}:${value}`)
    }
    return items.join('/')
  }

  function buildNamedRows(state, key, label) {
    const rows = state[key].filter(
      (row) => trimOf(row.name) || trimOf(row.text),
    )
    const items = []
    for (const row of rows) {
      const name = trimOf(row.name)
      const text = trimOf(row.text)
      if (!name) fail(`${label}要先写名称`)
      items.push(text ? `${name}:${text}` : name)
    }
    return items.join('/')
  }

  function buildWeapons(state) {
    const rows = state[K.WEAPON].filter(
      (row) =>
        trimOf(row.name) ||
        trimOf(row.attack) ||
        trimOf(row.damage) ||
        trimOf(row.type) ||
        trimOf(row.note),
    )
    const items = []
    for (const row of rows) {
      const name = trimOf(row.name)
      if (!name) fail('武器要先写名称')
      // 命中加值允许骰子与常数的加减组合（如 +6、+1d4），与插件同口径
      const attack = trimOf(row.attack).replace(/\s+/g, '')
      if (attack && !WEAPON_BONUS_RE.test(attack)) {
        fail(`武器命中加值无效: ${name}${attack}（仅支持骰子与常数的加减组合，如 +6）`)
      }
      const damage = trimOf(row.damage)
      if (!damage) fail(`武器「${name}」要写伤害表达式（如 1d8+3）`)
      let text = `${name}${row.noAttack ? 'x' : ''}${attack},${damage}${trimOf(row.type)}`
      const note = trimOf(row.note)
      if (note) text += `,${note}`
      items.push(text)
    }
    return items.join('/')
  }

  function buildItems(state) {
    // 空白行不算内容：数量默认 1 是表单初值，只有写了名称才导出
    const rows = state[K.ITEMS].filter((row) => trimOf(row.name))
    const items = []
    for (const row of rows) {
      const name = trimOf(row.name)
      const qty = trimOf(row.qty) || '1'
      items.push(`${name}x${normalizeIntText(qty)}`)
    }
    return items.join('; ')
  }

  function buildCoins(state) {
    const coins = state[K.COINS]
    const items = []
    for (const key of coinKeys) {
      const value = trimOf(coins[key])
      if (!value) continue
      items.push(`${key}:${normalizeIntText(value)}`)
    }
    return items.join('; ')
  }

  function recoverText(modes) {
    const parts = []
    for (const mode of recoverModes) {
      const state = modes[mode]
      if (!state || !state.on) continue
      parts.push(`${mode}${trimOf(state.amount) ? `+${normalizeIntText(state.amount)}` : ''}`)
    }
    return parts.join(',')
  }

  function buildFeatures(state) {
    const rows = state[K.FEATURE].filter(
      (row) =>
        trimOf(row.name) ||
        trimOf(row.cur) ||
        trimOf(row.max) ||
        trimOf(row.text) ||
        recoverModes.some((mode) => row.modes && row.modes[mode] && row.modes[mode].on),
    )
    const items = []
    for (const row of rows) {
      const name = trimOf(row.name)
      if (!name) fail('限定资源要先写名称')
      const cur = trimOf(row.cur)
      const max = trimOf(row.max)
      if (!cur || !max) fail(`限定资源「${name}」要写当前/上限（如 1/1）`)
      const recover = recoverText(row.modes)
      if (!recover) fail(`限定资源「${name}」要选恢复方式（短休/长休/两者/手动）`)
      const text = trimOf(row.text)
      items.push(
        `${name}:${normalizeIntText(cur)}/${normalizeIntText(max)}${recover}${text ? `|${text}` : ''}`,
      )
    }
    return items.join('; ')
  }

  function buildClassTraits(state) {
    const rows = state[K.CLASS_TRAITS].filter(
      (row) => trimOf(row.name) || trimOf(row.text),
    )
    const sorted = rows
      .map((row, index) => ({ row, index }))
      .sort(
        (left, right) =>
          Number(trimOf(left.row.level) || 0) - Number(trimOf(right.row.level) || 0) ||
          left.index - right.index,
      )
      .map((entry) => entry.row)
    const items = []
    for (const row of sorted) {
      const name = trimOf(row.name)
      if (!name) fail('职业特性要先写名称')
      const level = trimOf(row.level) || '1'
      if (!/^\d+$/.test(level) || Number(level) < 1 || Number(level) > 20) {
        fail(`职业特性「${name}」的等级无效: ${level}（写 1~20）`)
      }
      const text = trimOf(row.text)
      items.push(`${Number(level)}|${name}${text ? `:${text}` : ''}`)
    }
    return items.join('/')
  }

  function buildMagicItems(state) {
    const rows = state[K.MAGIC_ITEMS].filter(
      (row) => trimOf(row.name) || trimOf(row.tag) || trimOf(row.text),
    )
    const items = []
    for (const row of rows) {
      const name = trimOf(row.name)
      const tag = trimOf(row.tag)
      if (!name) fail('魔法物品要先写名称')
      if (!tag) fail(`魔法物品「${name}」要写标签（如 奇物，非普通）`)
      const paragraphs = magicParagraphsOf(row.text)
      if (paragraphs.length > (limits.magic_item_paragraph_max || 5)) {
        fail(`魔法物品「${name}」说明最多 ${limits.magic_item_paragraph_max || 5} 段`)
      }
      const body = paragraphs.join('//')
      items.push(`${name}|${tag}${body ? `|${body}` : ''}`)
    }
    return items.join('; ')
  }

  function spellDetailText(spell) {
    const parts = []
    if (trimOf(spell.time)) parts.push(`时间=${trimOf(spell.time)}`)
    if (trimOf(spell.range)) parts.push(`距离=${trimOf(spell.range)}`)
    if (spell.concentration) parts.push('专注=是')
    if (spell.ritual) parts.push('仪式=是')
    if (spell.material) parts.push('材料=是')
    if (trimOf(spell.note)) parts.push(`备注=${trimOf(spell.note)}`)
    return parts.join(',')
  }

  function buildSpells(state) {
    const spells = state[K.SPELL]
    const derived = deriveSpellStats(state)
    const dc = spells.dcManual ? trimOf(spells.dc) : derived.dc || trimOf(spells.dc)
    const attack = spells.attackManual
      ? trimOf(spells.attack)
      : derived.attack || trimOf(spells.attack)
    const items = []
    if (trimOf(spells.ability)) items.push(`施法属性:${trimOf(spells.ability)}`)
    if (dc) items.push(`豁免DC:${normalizeIntText(dc)}`)
    if (attack) items.push(`法术攻击:${normalizeSigned(attack, '法术攻击')}`)
    const rows = spells.list.filter(
      (row) =>
        trimOf(row.name) ||
        trimOf(row.time) ||
        trimOf(row.range) ||
        trimOf(row.note) ||
        row.concentration ||
        row.ritual ||
        row.material,
    )
    for (const row of rows) {
      const name = trimOf(row.name)
      if (!name) fail('法术要先写名称')
      let text = `${name}:${normalizeIntText(row.level || '0')}${row.prepared ? '*' : ''}`
      const detail = spellDetailText(row)
      if (detail) text += `|${detail}`
      items.push(text)
    }
    return items.join('; ')
  }

  function buildSlots(state) {
    const slots = state[K.SPELL_SLOTS]
    const items = []
    for (let index = 0; index < 9; index += 1) {
      const row = slots.levels[index]
      const cur = trimOf(row.cur)
      const max = trimOf(row.max)
      if (!cur && !max) continue
      if (!max) fail(`第 ${index + 1} 环法术位要写上限`)
      if (!cur) fail(`第 ${index + 1} 环法术位要写当前值`)
      items.push(`${index + 1}:${normalizeIntText(cur)}/${normalizeIntText(max)}`)
    }
    const pact = slots.pact
    const pactLevel = trimOf(pact.level)
    const pactCur = trimOf(pact.cur)
    const pactMax = trimOf(pact.max)
    if (pactLevel || pactCur || pactMax) {
      if (!pactLevel || !pactCur || !pactMax) {
        fail('契约法术位要写环阶、当前与上限（如 契约3:2/2）')
      }
      if (Number(pactMax) > 0) {
        items.push(
          `契约${normalizeIntText(pactLevel)}:${normalizeIntText(pactCur)}/${normalizeIntText(pactMax)}`,
        )
      }
    }
    return items.join('; ')
  }

  function buildNotes(state) {
    return state[K.COMBAT_NOTES]
      .map((item) => trimOf(item))
      .filter((item) => item !== '')
      .join('; ')
  }

  function buildStory(state) {
    return normalizeNewlines(state[K.STORY])
      .split('\n')
      .map((line) => line.replace(/[ \t]+$/, ''))
      .join('\n')
      .trim()
  }

  function buildContent(state, key, options = {}) {
    const kind = SEGMENT_KINDS[key]
    switch (kind) {
      case 'text':
      case 'class':
      case 'number':
        return buildText(key, state[key])
      case 'subclass': {
        const levelText = trimOf(state[K.LEVEL])
        if (
          levelText &&
          !isSubclassAvailable(state, options.rulesVersion || '5r')
        ) {
          return ''
        }
        return buildText(key, state[key])
      }
      case 'longtext':
        return buildStory(state)
      case 'background':
        return buildBackground(state, options)
      case 'hp':
        return buildHp(state)
      case 'hpdice':
        return buildHpDice(state)
      case 'combat':
        return buildCombat(state)
      case 'progress':
        return buildProgress(state)
      case 'ability':
        return buildAbility(state)
      case 'prof':
        return buildProf(state)
      case 'ext':
        return buildExt(state)
      case 'feats':
        return buildNamedRows(state, K.FEATS, '专长')
      case 'raceTraits':
        return buildNamedRows(state, K.RACE_TRAITS, '种族特性')
      case 'classTraits':
        return buildClassTraits(state)
      case 'weapons':
        return buildWeapons(state)
      case 'items':
        return buildItems(state)
      case 'coins':
        return buildCoins(state)
      case 'features':
        return buildFeatures(state)
      case 'magicItems':
        return buildMagicItems(state)
      case 'spells':
        return buildSpells(state)
      case 'slots':
        return buildSlots(state)
      case 'notes':
        return buildNotes(state)
      default:
        fail(`未知的段类型: ${kind}`)
    }
  }

  function contentFor(state, key, options = {}) {
    const content = buildContent(state, key, options)
    if (!content) return ''
    if (content.includes('$')) {
      fail(`${labelOf(key)}内容不能包含符号「$」`)
    }
    if (key !== K.STORY && (content.includes('\n') || content.includes('\r'))) {
      fail(`${labelOf(key)}内容不能换行`)
    }
    return content
  }

  // ── 导入 ──────────────────────────────────────────────────────────────

  function normalizeImportText(input) {
    let text = normalizeNewlines(textOf(input)).replace(/^\uFEFF/, '')
    const tipIndex = text.search(/\n[ \t]*——提示/)
    if (tipIndex >= 0) text = text.slice(0, tipIndex)
    // 每条记录命令（整段复制或多条分段命令粘在一起）都去掉命令前缀，
    // 只留 `$段名$ 内容`；行首与全文开头都处理。
    text = text.replace(/(^|\n)[ \t]*[.。]角色卡记录[ \t]*/g, '$1')
    return text.trim()
  }

  function parseCardText(input) {
    const state = createState()
    const errors = []
    const warnings = []
    const source = normalizeImportText(input)
    if (!source.includes('$')) {
      errors.push({
        key: '',
        label: '导入',
        message: '没有找到 $段名$，请把骰娘输出的卡文本整段粘进来',
      })
      return { state, errors, warnings, found: 0 }
    }
    const matches = [...source.matchAll(/\$([^$\n]+)\$/g)]
    const seen = new Set()
    for (let index = 0; index < matches.length; index += 1) {
      const match = matches[index]
      const key = `$${match[1]}$`
      const end =
        index + 1 < matches.length ? matches[index + 1].index : source.length
      const content = source.slice(match.index + match[0].length, end).trim()
      if (!segmentMap.has(key)) {
        errors.push({
          key,
          label: '未知段',
          message: `未知段 ${key}（不在当前段清单中，请检查是否用了旧写法）`,
        })
        continue
      }
      if (!content) continue
      if (seen.has(key)) {
        warnings.push({
          key,
          label: labelOf(key),
          message: `重复的 ${key} 段，已采用最后一条`,
        })
      }
      try {
        state[key] = parseSegment(key, content)
        seen.add(key)
      } catch (error) {
        errors.push({
          key,
          label: labelOf(key),
          message: error instanceof Error ? error.message : String(error),
        })
      }
    }
    const found = seen.size
    if (state[K.SPELL]) {
      const spell = state[K.SPELL]
      const derived = deriveSpellStats(state)
      spell.dcManual = Boolean(spell.dc) && (!derived.available || derived.dc !== spell.dc)
      spell.attackManual =
        Boolean(spell.attack) && (!derived.available || derived.attack !== spell.attack)
    }
    if (found === 0 && errors.length === 0) {
      errors.push({
        key: '',
        label: '导入',
        message: '没有识别到任何有效的 $段名$ 段，请检查粘贴内容',
      })
    }
    const extraBackground = backgroundKeys5e.filter(
      (key) =>
        !backgroundKeys5r.includes(key) &&
        trimOf(state[K.BACKGROUND] && state[K.BACKGROUND][key]),
    )
    return {
      state,
      errors,
      warnings,
      found,
      rulesVersion: extraBackground.length > 0 ? '5e' : '5r',
    }
  }

  // ── 导出 ──────────────────────────────────────────────────────────────

  /**
   * 按回写顺序产出非空段块。
   *
   * 每个块可能含换行（只有 `$故事$`），因此后续拆整卡时**按块拆**，
   * 不能按文本行拆，否则故事会被腰斩。
   */
  function buildCardBlocks(state, options = {}) {
    const blocks = []
    for (const key of order) {
      let content = ''
      try {
        content = contentFor(state, key, options)
      } catch {
        content = ''
      }
      if (!content) continue
      blocks.push({
        key,
        label: labelOf(key),
        content,
        block: `${key} ${content}`,
      })
    }
    return blocks
  }

  function serializeCard(state, options = {}) {
    return buildCardBlocks(state, options)
      .map((item) => item.block)
      .join('\n')
  }

  /** 整条 `.角色卡记录` 命令（含命令前缀与换行）及其消息长度。 */
  function buildWholeCommand(state, options = {}) {
    const text = `${CARD_COMMAND}\n${serializeCard(state, options)}`
    return { text, length: messageLength(text) }
  }

  /**
   * 按 QQ 单条上限拆整卡。
   *
   * - 整卡 ≤ limit：parts 只有一块（label「整卡」）；
   * - 超过 limit：第 1 部分固定含 `$等级$` 与 `$属性$`，其余段按回写顺序
   *   贪心装块；后续部分缺等级/属性，由插件按多段合并追加；
   * - 单个段本身就超过 limit：不拆，返回 tooLarge，让 UI 提示精简该段。
   */
  function buildCardParts(state, options = {}, limit = MESSAGE_LIMIT) {
    const blocks = buildCardBlocks(state, options)
    const prefix = `${CARD_COMMAND}\n`
    const prefixLength = messageLength(prefix)
    if (blocks.length === 0) {
      return { parts: [], tooLarge: [], limit }
    }
    const wholeText = prefix + blocks.map((item) => item.block).join('\n')
    const wholeLength = messageLength(wholeText)
    if (wholeLength <= limit) {
      return {
        parts: [
          { index: 1, label: '整卡', text: wholeText, length: wholeLength },
        ],
        tooLarge: [],
        limit,
      }
    }

    const tooLarge = blocks
      .filter((item) => messageLength(prefix + item.block) > limit)
      .map((item) => ({
        key: item.key,
        label: item.label,
        length: messageLength(prefix + item.block),
      }))
    if (tooLarge.length > 0) {
      return { parts: [], tooLarge, limit }
    }

    const requiredKeys = [K.LEVEL, K.ABILITY]
    const required = requiredKeys
      .map((key) => blocks.find((item) => item.key === key))
      .filter(Boolean)
    if (required.length !== requiredKeys.length) {
      return { parts: [], tooLarge: [], limit }
    }
    const requiredText =
      prefix + required.map((item) => item.block).join('\n')
    if (messageLength(requiredText) > limit) {
      return {
        parts: [],
        tooLarge: [
          {
            key: K.LEVEL,
            label: '等级与属性',
            length: messageLength(requiredText),
          },
        ],
        limit,
      }
    }

    const rest = blocks.filter((item) => !requiredKeys.includes(item.key))
    const parts = []
    let current = required.slice()
    let currentLength = messageLength(requiredText)
    const flush = () => {
      if (current.length === 0) return
      const text = prefix + current.map((item) => item.block).join('\n')
      parts.push({
        index: parts.length + 1,
        label: `第 ${parts.length + 1} 部分`,
        text,
        length: messageLength(text),
      })
      current = []
      currentLength = prefixLength
    }
    const add = (block) => {
      const separator = current.length > 0 ? 1 : 0
      const blockLength = messageLength(block.block)
      if (current.length > 0 && currentLength + separator + blockLength > limit) {
        flush()
      }
      currentLength += (current.length > 0 ? 1 : 0) + blockLength
      current.push(block)
    }
    for (const block of rest) add(block)
    flush()
    return { parts, tooLarge: [], limit }
  }

  function buildSegmentCommands(state, options = {}) {
    const commands = []
    for (const key of order) {
      let content = ''
      try {
        content = contentFor(state, key, options)
      } catch {
        content = ''
      }
      if (!content) continue
      const command = `${CARD_COMMAND} ${key} ${content}`
      commands.push({
        key,
        label: labelOf(key),
        content,
        command,
        length: messageLength(command),
      })
    }
    return commands
  }

  function buildExampleCard() {
    return order
      .map((key) => ({ key, example: segmentMap.get(key).example }))
      .filter(({ example }) => trimOf(example) !== '')
      .map(({ key, example }) => `${key} ${example}`)
      .join('\n')
  }

  // ── 校验 ──────────────────────────────────────────────────────────────

  function validateState(state, options = {}) {
    const errors = []
    const warnings = []
    const errorKeys = new Set()
    const pushError = (key, message) => {
      const signature = `${key}\u0000${message}`
      if (errorKeys.has(signature)) return
      errorKeys.add(signature)
      errors.push({ key, label: key ? labelOf(key) : '整卡', message })
    }
    const pushWarning = (key, message) => {
      warnings.push({ key, label: key ? labelOf(key) : '整卡', message })
    }

    if (isBlank(state[K.LEVEL])) {
      pushError(K.LEVEL, '等级为必填项：骰娘建卡要求先有等级与属性')
    }
    if (state[K.ABILITY].every((value) => isBlank(value))) {
      pushError(K.ABILITY, '属性为必填项：请填六个数值（力量/敏捷/体质/智力/感知/魅力）')
    }

    for (const key of order) {
      let content = ''
      try {
        content = contentFor(state, key, options)
      } catch (error) {
        pushError(key, error instanceof Error ? error.message : String(error))
        continue
      }
      if (!content) continue
      try {
        parseSegment(key, content)
      } catch (error) {
        pushError(key, error instanceof Error ? error.message : String(error))
      }
      const commandLength = messageLength(`${CARD_COMMAND} ${key} ${content}`)
      if (commandLength > MESSAGE_LIMIT) {
        pushError(
          key,
          `该段命令约 ${commandLength} 字，超过 QQ 单条 ${MESSAGE_LIMIT} 字上限，且无法自动拆分；请精简这一段`,
        )
      }
    }

    const level = Number(trimOf(state[K.LEVEL]))
    if (Number.isFinite(level) && level > (limits.level_max || 20)) {
      pushWarning(K.LEVEL, `等级 ${level} 超过 ${limits.level_max || 20} 级（骰娘仍会接受）`)
    }
    state[K.ABILITY].forEach((value, index) => {
      const number = Number(trimOf(value))
      if (Number.isFinite(number) && number > (limits.ability_score_max || 30)) {
        pushWarning(
          K.ABILITY,
          `${abilities[index]} ${number} 超过 ${limits.ability_score_max || 30}（骰娘仍会接受）`,
        )
      }
    })
    if (isBlank(state[K.NAME])) {
      pushWarning(K.NAME, '没写姓名时，骰娘会用群名片作为显示名')
    }
    if (isBlank(state[K.CLASS]) && !isBlank(state[K.SUBCLASS])) {
      pushWarning(K.SUBCLASS, '写了子职但没写职业，子职不会导出')
    } else if (
      !isBlank(state[K.LEVEL]) &&
      !isBlank(state[K.SUBCLASS]) &&
      !isSubclassAvailable(state, options.rulesVersion || '5r')
    ) {
      pushWarning(
        K.SUBCLASS,
        `当前等级尚未获得子职（${trimOf(state[K.CLASS]) || '自定义职业'}在 ${subclassLevelFor(trimOf(state[K.CLASS]), options.rulesVersion || '5r')} 级获得），子职不会导出`,
      )
    }

    const cardText = serializeCard(state, options)
    const cardLength = charLength(cardText)
    const commandLength = messageLength(`${CARD_COMMAND}\n${cardText}`)
    if (cardLength === 0) {
      pushWarning('', '还没有填写任何内容')
    } else if (commandLength > MESSAGE_LIMIT) {
      pushWarning(
        '',
        `整卡命令约 ${commandLength} 字，超过 QQ 单条 ${MESSAGE_LIMIT} 字上限；导出时会按段自动拆成多个部分，请按顺序复制发送`,
      )
    }
    return {
      errors,
      warnings,
      text: cardText,
      length: commandLength,
      cardLength,
      limit: MESSAGE_LIMIT,
    }
  }

  return {
    spec,
    segments,
    formOrder,
    formSegments,
    groups: spec.groups || [],
    order,
    labels: Object.fromEntries(segments.map((segment) => [segment.key, segment.label])),
    kinds: SEGMENT_KINDS,
    createState,
    parseCardText,
    parseSegment,
    contentFor,
    buildCardBlocks,
    serializeCard,
    buildWholeCommand,
    buildCardParts,
    buildSegmentCommands,
    buildExampleCard,
    validateState,
    charLength,
    messageLength,
    deriveAbilityModifiers,
    deriveCheckValues,
    deriveProficiencyBonus,
    deriveXpNext,
    deriveInitiative,
    derivePassivePerception,
    deriveSpellStats,
    backgroundKeysFor,
    subclassLevelFor,
    isSubclassAvailable,
  }
}
