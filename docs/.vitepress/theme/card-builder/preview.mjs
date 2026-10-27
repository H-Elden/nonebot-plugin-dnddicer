/**
 * 角色卡预览：把建卡器表单状态转成与 `character/card_view.py` 一致的视图，
 * 再按 `render/templates/char_card.html` 的结构拼出静态 HTML。
 *
 * 纯函数模块，不依赖 Vue / DOM / 网络；CSS 由调用方传入（构建时从插件
 * `char_card.css` 同步）。所有用户文本都经过 HTML 转义。
 */

import { K, splitParagraphs } from './core.mjs'

function textOf(value) {
  return value === undefined || value === null ? '' : String(value)
}

function trimOf(value) {
  return textOf(value).trim()
}

function thousands(value) {
  const text = trimOf(value)
  return /^\d+$/.test(text) ? Number(text).toLocaleString('en-US') : text
}

function escapeHtml(value) {
  return textOf(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function batchPairs(items) {
  const rows = []
  for (let index = 0; index < items.length; index += 2) {
    rows.push(items.slice(index, index + 2))
  }
  return rows
}

function recoverText(modes, modeOrder) {
  const parts = []
  for (const mode of modeOrder) {
    const state = modes && modes[mode]
    if (!state || !state.on) continue
    if (mode === '两者') {
      parts.push('短休回满，长休回满')
      continue
    }
    const amount = trimOf(state.amount)
    if (mode === '手动' || amount === '满') {
      parts.push(mode === '手动' ? '手动' : `${mode}回满`)
      continue
    }
    parts.push(`${mode}${amount ? `+${amount}` : '回满'}`)
  }
  return parts.join('，')
}

/**
 * 表单状态 → 预览视图（字段名与 `CharacterCardView` 对齐，便于对照）。
 */
export function buildPreviewView(builder, state, options = {}, portraitDataUrl = '') {
  const enums = builder.spec.enums || {}
  const abilities = enums.abilities || []
  const skills = enums.skills || []
  const skillParent = enums.skill_parent || {}
  const coinKeys = enums.coin_keys || []
  const recoverModes = enums.recover_modes || []
  const level = Number(trimOf(state[K.LEVEL]))
  const levelReady = /^\d+$/.test(trimOf(state[K.LEVEL])) && level > 0
  const scores = (state[K.ABILITY] || []).map((value) => trimOf(value))
  const abilityReady =
    scores.length === abilities.length && scores.every((value) => /^\d+$/.test(value))
  const infoReady = levelReady && abilityReady
  const proficiencyBonus = infoReady ? 2 + Math.floor((level - 1) / 4) : 0
  const modifiers = builder.deriveAbilityModifiers(state)
  const values = builder.deriveCheckValues(state)
  const scaleOf = (name) => Number(state[K.PROF]?.checks?.[name] || 0)

  const abilityViews = abilities.map((name, index) => {
    const score = abilityReady ? scores[index] : '—'
    const mod = abilityReady ? modifiers[index] || '—' : '—'
    const saveName = `${name}豁免`
    const saveScale = scaleOf(saveName)
    const save = infoReady
      ? {
          label: '豁免',
          value: values[saveName] || '—',
          proficient: saveScale > 0,
        }
      : null
    const rows = []
    for (const skill of skills) {
      if (skill === '先攻' || skillParent[skill] !== name) continue
      const scale = scaleOf(skill)
      rows.push({
        name: skill,
        value: infoReady ? values[skill] || '—' : '—',
        proficient: scale >= 1,
        expertise: scale >= 2,
        half: scale === 0 && builder.halfProfBonusOf(state, skill) > 0,
      })
    }
    return { name, score, mod, save, skills: rows }
  })

  const name = trimOf(state[K.NAME]) || '未命名'
  const subtitleParts = []
  if (trimOf(state[K.RACE])) subtitleParts.push(trimOf(state[K.RACE]))
  const className = trimOf(state[K.CLASS])
  const subclass = trimOf(state[K.SUBCLASS])
  if (className || subclass) {
    subtitleParts.push(
      subclass ? `${className || '自定义职业'}（${subclass}）` : className,
    )
  }
  if (infoReady) subtitleParts.push(`${level} 级`)

  const hpCur = trimOf(state[K.HP]?.cur)
  const hpMax = trimOf(state[K.HP]?.max)
  const hpTemp = trimOf(state[K.HP]?.temp)
  const hp = hpCur
    ? hpMax
      ? `${hpCur}/${hpMax}`
      : hpCur
    : '—'
  const hpState =
    hpCur && Number(hpCur) <= 0 && Number(hpMax || 0) > 0 ? '昏迷' : ''
  const diceType = trimOf(state[K.HP_DICE]?.type)
  const diceNum = trimOf(state[K.HP_DICE]?.num)
  const diceMax = trimOf(state[K.HP_DICE]?.max) || diceNum
  const hitDice = diceType
    ? `${diceNum || '—'}/${diceMax || diceNum || '—'} D${diceType}`
    : '—'

  const combat = state[K.COMBAT] || {}
  const initiative = infoReady ? values['先攻'] || '—' : '—'
  const passivePerception = infoReady
    ? builder.derivePassivePerception(state) || '—'
    : '—'
  const coreStats = [
    { label: 'AC', value: trimOf(combat.AC) || '—' },
    { label: '先攻', value: initiative },
    { label: '速度', value: trimOf(combat.速度) || '—' },
    { label: '被动察觉', value: passivePerception },
  ]
  if (infoReady) coreStats.push({ label: '熟练', value: `+${proficiencyBonus}` })

  const xp = trimOf(state[K.PROGRESS]?.xp)
  const xpNext = builder.deriveXpNext(state)
  const inspiration =
    trimOf(state[K.PROGRESS]?.inspiration) === '有'

  const proficiencies = []
  for (const label of enums.proficiency_groups || []) {
    const raw = trimOf(state[K.PROF]?.groups?.[label])
    if (!raw) continue
    const items = raw
      .split('·')
      .map((value) => value.trim())
      .filter((value) => value !== '')
    if (items.length) proficiencies.push(`${label}：${items.join('、')}`)
  }

  const combatNotes = (state[K.COMBAT_NOTES] || [])
    .map((item) => trimOf(item))
    .filter((item) => item !== '')

  const weapons = (state[K.WEAPON] || [])
    .filter((row) => trimOf(row.name))
    .map((row) => ({
      name: trimOf(row.name),
      hit: row.noAttack ? '—' : trimOf(row.attack) || '—',
      damage: trimOf(row.damage) || '—',
      damageType: trimOf(row.type) || '—',
      note: trimOf(row.note),
    }))

  const namedRows = (rows) =>
    (rows || [])
      .filter((row) => trimOf(row.name) || trimOf(row.text))
      .map((row) => ({
        name: trimOf(row.name) || '—',
        text: trimOf(row.text),
      }))

  const classTraits = (state[K.CLASS_TRAITS] || [])
    .filter((row) => trimOf(row.name))
    .slice()
    .sort((left, right) => Number(trimOf(left.level) || 0) - Number(trimOf(right.level) || 0))
    .map((row) => ({
      level: Number(trimOf(row.level) || 0),
      name: trimOf(row.name),
      text: trimOf(row.text),
    }))

  const resources = (state[K.FEATURE] || [])
    .filter((row) => trimOf(row.name))
    .map((row) => {
      const cur = trimOf(row.cur)
      const max = trimOf(row.max)
      const uses = Number(max) > 0
        ? `${cur}/${max}${recoverText(row.modes, recoverModes) ? ` ${recoverText(row.modes, recoverModes)}` : ''}`
        : ''
      return { name: trimOf(row.name), uses, text: trimOf(row.text) }
    })

  const magicItems = (state[K.MAGIC_ITEMS] || [])
    .filter((row) => trimOf(row.name))
    .map((row) => ({
      name: trimOf(row.name),
      tag: trimOf(row.tag),
      paragraphs: splitParagraphs(row.text),
    }))

  const items = (state[K.ITEMS] || [])
    .filter((row) => trimOf(row.name))
    .map((row) => {
      const qty = Number(trimOf(row.qty) || 1)
      return qty > 1 ? `${trimOf(row.name)} ×${qty}` : trimOf(row.name)
    })

  const coinValues = coinKeys.map((key) => trimOf(state[K.COINS]?.[key]))
  const hasCoins = coinValues.some((value) => value !== '')
  const coins = hasCoins
    ? coinKeys.map((key, index) => ({
        label: key,
        value: coinValues[index] || '0',
      }))
    : []

  const backgrounds = []
  for (const key of builder.backgroundKeysFor(options.rulesVersion || '5r')) {
    const value = trimOf(state[K.BACKGROUND]?.[key])
    if (value) backgrounds.push({ key, value })
  }
  const backgroundRows = batchPairs(backgrounds).map((cells) => ({
    cells: cells.map((cell) => [cell.key, cell.value]),
  }))

  const story = textOf(state[K.STORY])
  const storyLines = story ? story.split('\n') : []

  const spell = state[K.SPELL] || {}
  const derivedSpell = builder.deriveSpellStats(state)
  const spellDc = spell.dcManual
    ? trimOf(spell.dc)
    : derivedSpell.dc || trimOf(spell.dc)
  const spellAttack = spell.attackManual
    ? trimOf(spell.attack)
    : derivedSpell.attack || trimOf(spell.attack)

  const grouped = new Map()
  for (const row of spell.list || []) {
    if (!trimOf(row.name)) continue
    const levelValue = Number(trimOf(row.level) || 0)
    if (!grouped.has(levelValue)) grouped.set(levelValue, [])
    grouped.get(levelValue).push({
      name: trimOf(row.name),
      prepared: Boolean(row.prepared),
      isCantrip: levelValue === 0,
      time: trimOf(row.time),
      range: trimOf(row.range),
      concentration: Boolean(row.concentration),
      ritual: Boolean(row.ritual),
      material: Boolean(row.material),
      note: trimOf(row.note),
    })
  }
  const spellGroups = [...grouped.keys()]
    .sort((left, right) => left - right)
    .map((levelValue) => ({
      label: levelValue === 0 ? '戏法' : `${levelValue} 环`,
      spells: grouped.get(levelValue),
    }))

  const slotLevels = (state[K.SPELL_SLOTS]?.levels || []).map((row, index) => {
    const cur = Number(trimOf(row.cur) || 0)
    const max = Number(trimOf(row.max) || 0)
    const total = max > 0 && max <= 9 ? max : 0
    return {
      label: `${index + 1}环`,
      value: max > 0 ? `${cur}/${max}` : '—',
      filled: total ? Math.min(cur, total) : 0,
      total,
      empty: max <= 0,
    }
  })
  const slotRows = [
    slotLevels.slice(0, 3),
    slotLevels.slice(3, 6),
    slotLevels.slice(6, 9),
  ]
  const pact = state[K.SPELL_SLOTS]?.pact || {}
  const pactMax = Number(trimOf(pact.max) || 0)
  const pactSlot = pactMax > 0
    ? {
        label: `契约${trimOf(pact.level) || '?'}环`,
        value: `${trimOf(pact.cur) || 0}/${pactMax}`,
        filled: Math.min(Number(trimOf(pact.cur) || 0), pactMax <= 9 ? pactMax : 0),
        total: pactMax <= 9 ? pactMax : 0,
      }
    : null
  const hasSlots = Boolean(pactSlot) || slotLevels.some((slot) => !slot.empty)

  return {
    name,
    subtitle: subtitleParts.length ? subtitleParts.join(' · ') : '未记录身份',
    portraitDataUri: portraitDataUrl || '',
    portraitInitial: name ? Array.from(name)[0] : '?',
    hasPortrait: Boolean(portraitDataUrl),
    coreStats,
    xp: thousands(xp),
    xpNext: thousands(xpNext),
    hp,
    hpState,
    tempHp: hpTemp && Number(hpTemp) > 0 ? hpTemp : '—',
    hitDice,
    deathSuccess: 0,
    deathFailure: 0,
    deathState: '',
    inspiration,
    abilities: abilityViews,
    proficiencies,
    combatNotes,
    weapons,
    feats: namedRows(state[K.FEATS]),
    raceTraits: namedRows(state[K.RACE_TRAITS]),
    classTraits,
    resources,
    magicItems,
    items,
    coins,
    backgroundRows,
    story,
    storyLines,
    spellcasting: trimOf(spell.ability) || '—',
    spellDc,
    spellAttack,
    slotRows,
    pactSlot,
    hasSlots,
    spellGroups,
  }
}

function featurePanel(title, items) {
  return `<div class="panel"><div class="panel-title">${escapeHtml(title)}</div>${items
    .map(
      (item) =>
        `<div class="feature"><table class="f-head"><tr><td class="f-title">${
          item.level ? `<span class="f-level">${item.level}级</span>` : ''
        }<span class="f-name">${escapeHtml(item.name)}</span></td>${
          item.uses
            ? `<td class="f-uses-cell"><span class="f-uses">${escapeHtml(item.uses)}</span></td>`
            : ''
        }</tr></table>${
          item.text ? `<div class="f-text">${escapeHtml(item.text)}</div>` : ''
        }</div>`,
    )
    .join('')}</div>`
}

function magicPanel(items) {
  return `<div class="panel magic-panel"><div class="panel-title">魔法物品</div>${items
    .map(
      (item) =>
        `<div class="magic-item"><div class="m-head"><span class="m-name">${escapeHtml(
          item.name,
        )}</span><span class="m-tag">${escapeHtml(item.tag)}</span></div>${item.paragraphs
          .map((paragraph) => `<div class="m-text">${escapeHtml(paragraph)}</div>`)
          .join('')}</div>`,
    )
    .join('')}</div>`
}

function linesPanel(title, lines, className) {
  return `<div class="panel"><div class="panel-title">${escapeHtml(title)}</div>${lines
    .map((line) => `<div class="${className}">${escapeHtml(line)}</div>`)
    .join('')}</div>`
}

function itemPanel(items) {
  const rows = batchPairs(items)
    .map(
      (row) =>
        `<tr>${row
          .map((item) => `<td class="item-line">${escapeHtml(item)}</td>`)
          .join('')}${row.length < 2 ? '<td class="item-line"></td>' : ''}</tr>`,
    )
    .join('')
  return `<div class="panel"><div class="panel-title">装备</div><table class="item-grid">${rows}</table></div>`
}

function coinPanel(coins) {
  return `<div class="panel"><div class="panel-title">钱币</div><table class="coins"><tr>${coins
    .map((coin) => `<th width="20%">${escapeHtml(coin.label)}</th>`)
    .join('')}</tr><tr>${coins
    .map((coin) => `<td width="20%">${escapeHtml(coin.value)}</td>`)
    .join('')}</tr></table></div>`
}

function backgroundPanel(rows) {
  const body = rows
    .map(
      (row) =>
        `<tr>${row.cells
          .map(
            (cell) =>
              `<td><span class="bg-key">${escapeHtml(cell[0])}</span>${escapeHtml(cell[1])}</td>`,
          )
          .join('')}${row.cells.length < 2 ? '<td></td>' : ''}</tr>`,
    )
    .join('')
  return `<div class="panel"><div class="panel-title">背景与个性</div><table class="bg-grid">${body}</table></div>`
}

function box(filled) {
  return `<span class="box${filled ? ' filled' : ''}"></span>`
}

function pips(filled, total) {
  let html = ''
  for (let index = 0; index < total; index += 1) html += box(index < filled)
  return html
}

function coreStats(stats) {
  return `<tr>${stats
    .map(
      (stat) =>
        `<td><span class="stat-label">${escapeHtml(stat.label)}</span><span class="stat-value">${escapeHtml(
          stat.value,
        )}</span></td>`,
    )
    .join('')}</tr>`
}

function abilityBlock(ability) {
  const save = ability.save
    ? `<div class="ab-save">${box(ability.save.proficient)}豁免 <span class="skv">${escapeHtml(
        ability.save.value,
      )}</span></div>`
    : ''
  const skills = ability.skills
    .map(
      (skill) =>
        `<div class="ab-skill">${
          skill.expertise ? '<span class="star">✦</span>' : box(skill.proficient)
        }${escapeHtml(skill.name)} <span class="skv">${escapeHtml(skill.value)}</span>${
          skill.half ? '<span class="half-mark">半</span>' : ''
        }</div>`,
    )
    .join('')
  return `<table class="ability"><tr><td class="ab-name" colspan="2"><table class="ab-head"><tr><td class="ab-head-name">${escapeHtml(
    ability.name,
  )}</td><td class="ab-head-mod">${escapeHtml(
    ability.mod,
  )}</td></tr></table></td></tr><tr><td class="ab-score-cell"><div class="ab-circle">${escapeHtml(
    ability.score,
  )}</div><div class="ab-mod-line">调整 ${escapeHtml(
    ability.mod,
  )}</div></td><td class="ab-list">${save}${skills}</td></tr></table>`
}

/**
 * 预览视图 → 完整 HTML（结构与 `char_card.html` 对齐）。
 */
export function renderPreviewHtml(view, css) {
  const leftPanels = [
    view.resources.length ? featurePanel('限定资源', view.resources) : '',
    view.items.length ? itemPanel(view.items) : '',
    view.magicItems.length ? magicPanel(view.magicItems) : '',
    view.coins.length ? coinPanel(view.coins) : '',
    view.backgroundRows.length ? backgroundPanel(view.backgroundRows) : '',
  ].join('')
  const rightPanels = [
    view.feats.length ? featurePanel('专长', view.feats) : '',
    view.raceTraits.length ? featurePanel('种族特性', view.raceTraits) : '',
    view.classTraits.length ? featurePanel('职业特性', view.classTraits) : '',
  ].join('')
  const leftAny = Boolean(leftPanels)
  const rightAny = Boolean(rightPanels)
  let subTwo = ''
  if (leftAny || rightAny) {
    let body = ''
    if (leftAny && rightAny) {
      body = `<td class="sub-col sub-col-left">${leftPanels}</td><td class="sub-col sub-col-right">${rightPanels}</td>`
    } else if (leftAny) {
      body = `<td class="sub-col-full" colspan="2">${leftPanels}</td>`
    } else {
      body = `<td class="sub-col-full" colspan="2">${rightPanels}</td>`
    }
    subTwo = `<table class="sub-two"><tr>${body}</tr></table>`
  }

  const abilities = view.abilities.map(abilityBlock).join('')
  const proficiencyPanel = view.proficiencies.length
    ? linesPanel('熟练与语言', view.proficiencies, 'plain-line')
    : ''
  const combatNotePanel = view.combatNotes.length
    ? linesPanel('战斗记录', view.combatNotes, 'note-line')
    : ''

  const weaponPanel = view.weapons.length
    ? `<div class="panel weapon-panel"><div class="panel-title">武器与伤害</div><table class="weapons"><thead class="weapons-head"><tr><th class="w-name">名称</th><th class="w-hit">命中/DC</th><th class="w-dmg">伤害</th><th class="w-type">类型</th><th class="w-note">备注</th></tr></thead><tbody>${view.weapons
        .map(
          (weapon) =>
            `<tr><td class="w-name">${escapeHtml(weapon.name)}</td><td class="w-hit">${escapeHtml(
              weapon.hit,
            )}</td><td class="w-dmg">${escapeHtml(weapon.damage)}</td><td class="w-type">${escapeHtml(
              weapon.damageType,
            )}</td><td class="w-note">${escapeHtml(weapon.note || '—')}</td></tr>`,
        )
        .join('')}</tbody></table></div>`
    : ''

  const storyPanel = view.story
    ? `<div class="panel"><div class="panel-title">背景故事</div><div class="story-text">${view.storyLines
        .map((line) => `<div class="story-line">${escapeHtml(line || ' ')}</div>`)
        .join('')}</div></div>`
    : ''

  const slots = view.slotRows
    .map(
      (row) =>
        `<tr>${row
          .map(
            (slot) =>
              `<td class="slot"><span class="slot-label">${escapeHtml(
                slot.label,
              )}</span><span class="slot-value">${escapeHtml(slot.value)}</span><span class="slot-pips">${
                slot.total ? pips(slot.filled, slot.total) : '—'
              }</span></td>`,
          )
          .join('')}</tr>`,
    )
    .join('')
  const pact = view.pactSlot
    ? `<tr><td class="slot slot-pact" colspan="3"><span class="slot-label">${escapeHtml(
        view.pactSlot.label,
      )}</span><span class="slot-value">${escapeHtml(
        view.pactSlot.value,
      )}</span><span class="slot-pips">${
        view.pactSlot.total ? pips(view.pactSlot.filled, view.pactSlot.total) : '—'
      }</span></td></tr>`
    : ''

  const spellTable = view.spellGroups.length
    ? `<table class="spell-table"><tr><th class="s-name">法术名</th><th class="s-prep">准备</th><th class="s-time">施法时间</th><th class="s-range">施法距离</th><th class="s-conc">专注C</th><th class="s-ritual">仪式R</th><th class="s-material">材料M</th><th class="s-note">备注</th></tr>${view.spellGroups
        .map(
          (group) =>
            `<tr class="level-row"><td colspan="8">${escapeHtml(group.label)}</td></tr>${group.spells
              .map(
                (spell) =>
                  `<tr><td class="s-name">${escapeHtml(spell.name)}</td><td class="s-prep">${
                    spell.isCantrip ? '—' : spell.prepared ? '●' : '○'
                  }</td><td class="s-time">${escapeHtml(
                    spell.time || '—',
                  )}</td><td class="s-range">${escapeHtml(
                    spell.range || '—',
                  )}</td><td class="s-conc">${box(spell.concentration)}C</td><td class="s-ritual">${box(
                    spell.ritual,
                  )}R</td><td class="s-material">${box(spell.material)}M</td><td class="s-note">${escapeHtml(
                    spell.note || '—',
                  )}</td></tr>`,
              )
              .join('')}`,
        )
        .join('')}</table>`
    : ''

  const spellPanel = view.spellGroups.length || view.hasSlots
    ? `<div class="panel spell-panel"><div class="panel-title">戏法与已准备法术</div><table class="spell-head"><tr><td class="spell-cast"><table class="casting"><tr><td><div class="c-label">施法属性</div><div class="c-value">${escapeHtml(
        view.spellcasting,
      )}</div></td><td><div class="c-label">豁免 DC</div><div class="c-value">${escapeHtml(
        view.spellDc || '—',
      )}</div></td><td><div class="c-label">法术攻击</div><div class="c-value">${escapeHtml(
        view.spellAttack || '—',
      )}</div></td></tr></table></td><td class="spell-slots"><table class="slot-grid">${slots}${pact}</table></td></tr></table>${spellTable}</div>`
    : ''

  const portrait = view.hasPortrait
    ? `<img class="photo" src="${escapeHtml(view.portraitDataUri)}" alt="">`
    : `<div class="photo placeholder">${escapeHtml(view.portraitInitial)}</div>`

  return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>${css}</style></head><body><div class="sheet card"><table class="top"><tr><td class="photo-cell">${portrait}</td><td class="identity"><div class="name">${escapeHtml(
    view.name,
  )}</div><div class="subtitle">${escapeHtml(
    view.subtitle,
  )}</div><table class="core-stats">${coreStats(
    view.coreStats,
  )}</table>${
    view.xp
      ? `<div class="xp-line"><span class="xp-label">经验值</span><span class="xp-value">${escapeHtml(
          view.xp,
        )}</span>${
          view.xpNext
            ? `<span class="xp-next">下一级 ${escapeHtml(view.xpNext)}</span>`
            : ''
        }</div>`
      : ''
  }</td><td class="hp-cell"><table class="hp-grid"><tr class="hp-row"><td class="hp-label">生命值</td><td class="hp-value">${escapeHtml(
    view.hp,
  )}${
    view.hpState ? `<span class="hp-state">${escapeHtml(view.hpState)}</span>` : ''
  }</td></tr><tr class="hp-row"><td class="hp-label">临时生命</td><td class="hp-value-small">${escapeHtml(
    view.tempHp,
  )}</td></tr><tr class="hp-row"><td class="hp-label">生命骰</td><td class="hp-value-small">${escapeHtml(
    view.hitDice,
  )}</td></tr><tr class="hp-row hp-ds"><td class="hp-label">死亡豁免</td><td><div>成功 ${pips(
    view.deathSuccess,
    3,
  )}</div><div>失败 ${pips(
    view.deathFailure,
    3,
  )}</div></td></tr><tr class="hp-row hp-last"><td class="hp-label">英雄激励</td><td>${box(
    view.inspiration,
  )}</td></tr></table></td></tr></table><table class="main"><tr><td class="left-col">${abilities}${proficiencyPanel}${combatNotePanel}</td><td class="right-col">${weaponPanel}${subTwo}${storyPanel}</td></tr></table>${spellPanel}<div class="legend">□ 熟练　✦ 专精　● 已准备　○ 未准备　— 戏法无需准备　｜　DNDDicer · 屠龙骰</div></div></body></html>`
}
