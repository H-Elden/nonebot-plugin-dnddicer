/**
 * 网页建卡器的共享状态（模块级单例）。
 *
 * 页面拆成多个章节组件后（工具栏 / 分组 / 导出 / 预览 / 立绘），
 * 它们都从这里读写同一份 `state`，避免靠 props 层层传递。
 * 只依赖 Vue 的响应式 API，不碰 DOM，SSR 导入也不报错。
 */

import { computed, reactive, ref } from 'vue'

import spec from './card-spec.json'
import { K, createCardBuilder } from './core.mjs'

export const builder = createCardBuilder(spec)
export const enums = spec.enums || {}
export const limits = spec.limits || {}
export const abilities = enums.abilities || []
export const skills = enums.skills || []

export const state = reactive(builder.createState())
export const rulesVersion = ref('5r')
export const portraitDataUrl = ref('')

export const queryOptions = computed(() => ({ rulesVersion: rulesVersion.value }))
export const validation = computed(() =>
  builder.validateState(state, queryOptions.value),
)
export const segmentCommands = computed(() =>
  builder.buildSegmentCommands(state, queryOptions.value),
)
export const segmentCommandsByKey = computed(() =>
  Object.fromEntries(segmentCommands.value.map((item) => [item.key, item])),
)
export const cardParts = computed(() =>
  builder.buildCardParts(state, queryOptions.value),
)
export const wholeCommand = computed(() =>
  builder.buildWholeCommand(state, queryOptions.value),
)
export const canCopy = computed(
  () =>
    validation.value.errors.length === 0 &&
    validation.value.text.length > 0,
)

export const storyLength = computed(() =>
  Array.from((state[K.STORY] || '').replace(/\n/g, '')).length,
)
export const abilityModifiers = computed(() =>
  builder.deriveAbilityModifiers(state),
)
export const checkValues = computed(() => builder.deriveCheckValues(state))
export const proficiencyBonus = computed(() =>
  builder.deriveProficiencyBonus(state),
)
export const xpNextValue = computed(() => builder.deriveXpNext(state))
export const initiativeValue = computed(() => builder.deriveInitiative(state))
export const passivePerceptionValue = computed(() =>
  builder.derivePassivePerception(state),
)
export const spellStats = computed(() => builder.deriveSpellStats(state))
export const backgroundFields = computed(() =>
  builder.backgroundKeysFor(rulesVersion.value),
)
export const subclassVisible = computed(() =>
  builder.isSubclassAvailable(state, rulesVersion.value),
)
export const subclassRuleText = computed(() => {
  if (!state[K.CLASS]) return '填写职业与等级后会按规则显示'
  const level = builder.subclassLevelFor(state[K.CLASS], rulesVersion.value)
  return `${state[K.CLASS]}在 ${level} 级获得子职`
})
export const errorsByKey = computed(() => {
  const map = {}
  for (const error of validation.value.errors) {
    if (!error.key) continue
    if (!map[error.key]) map[error.key] = []
    map[error.key].push(error)
  }
  return map
})

export function applyState(nextState) {
  Object.assign(state, nextState)
}

export function resetState() {
  Object.assign(state, builder.createState())
  rulesVersion.value = '5r'
  portraitDataUrl.value = ''
}

export function setPortrait(dataUrl) {
  portraitDataUrl.value = dataUrl || ''
}
