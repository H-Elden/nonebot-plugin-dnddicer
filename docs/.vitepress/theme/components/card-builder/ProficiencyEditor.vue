<template>
  <div v-for="section in sections" :key="section.label" class="cb-prof-section">
    <div class="cb-subhead">{{ section.label }}</div>
    <div class="cb-chip-grid">
      <button
        v-for="name in section.items"
        :key="name"
        type="button"
        class="cb-chip"
        :class="chipClass(name)"
        :title="chipTitle(name, section.triple)"
        @click="cycle(name, section.triple)"
      >
        {{ shortName(name) }}
        <span class="cb-chip__value">{{ values[name] || '—' }}</span>
        <span v-if="scaleOf(name) > 0" class="cb-chip__mark">{{ markOf(name) }}</span>
      </button>
    </div>
  </div>

  <div class="cb-subhead">护甲受训</div>
  <div class="cb-check-grid">
    <label v-for="name in armorOptions" :key="name" class="cb-check">
      <input
        type="checkbox"
        :checked="hasGroupValue('护甲', name)"
        @change="toggleGroupValue('护甲', name)"
      />
      {{ name }}
    </label>
  </div>

  <div class="cb-subhead">武器熟练</div>
  <div class="cb-check-grid">
    <label v-for="name in weaponOptions" :key="name" class="cb-check">
      <input
        type="checkbox"
        :checked="hasGroupValue('武器', name)"
        @change="toggleGroupValue('武器', name)"
      />
      {{ name }}
    </label>
  </div>
  <div class="cb-inline">
    <input
      v-model="weaponCustom"
      class="cb-input"
      placeholder="特定武器（如 长剑），回车添加"
      @keyup.enter="addCustom('武器', weaponCustom); weaponCustom = ''"
    />
    <button type="button" class="cb-btn cb-btn--ghost cb-btn--small" @click="addCustom('武器', weaponCustom); weaponCustom = ''">
      添加
    </button>
  </div>

  <div class="cb-subhead">工具熟练</div>
  <div class="cb-inline">
    <select class="cb-select" @change="onToolSelect">
      <option value="">选择工具后添加…</option>
      <option v-for="name in toolOptions" :key="name" :value="name">{{ name }}</option>
    </select>
    <input
      v-model="toolCustom"
      class="cb-input"
      placeholder="自定义工具，回车添加"
      @keyup.enter="addCustom('工具', toolCustom); toolCustom = ''"
    />
    <button type="button" class="cb-btn cb-btn--ghost cb-btn--small" @click="addCustom('工具', toolCustom); toolCustom = ''">
      添加
    </button>
  </div>

  <div class="cb-subhead">语言</div>
  <div class="cb-subhead cb-subhead--minor">标准语言</div>
  <div class="cb-check-grid">
    <label v-for="name in languageOptions" :key="name" class="cb-check">
      <input
        type="checkbox"
        :checked="hasGroupValue('语言', name)"
        @change="toggleGroupValue('语言', name)"
      />
      {{ name }}
    </label>
  </div>
  <div class="cb-subhead cb-subhead--minor">稀有语言</div>
  <div class="cb-check-grid">
    <label v-for="name in exoticLanguageOptions" :key="name" class="cb-check">
      <input
        type="checkbox"
        :checked="hasGroupValue('语言', name)"
        @change="toggleGroupValue('语言', name)"
      />
      {{ name }}
    </label>
  </div>
  <div class="cb-inline">
    <input
      v-model="languageCustom"
      class="cb-input"
      placeholder="自定义语言，回车添加"
      @keyup.enter="addCustom('语言', languageCustom); languageCustom = ''"
    />
    <button type="button" class="cb-btn cb-btn--ghost cb-btn--small" @click="addCustom('语言', languageCustom); languageCustom = ''">
      添加
    </button>
  </div>

  <div v-for="label in groupLabels" :key="label" class="cb-prof-group">
    <span class="cb-grid__label">{{ label }}</span>
    <div class="cb-chip-grid">
      <span v-for="value in groupValues(label)" :key="value" class="cb-chip cb-chip--static">
        {{ value }}
        <button
          type="button"
          class="cb-chip__remove"
          title="移除"
          @click="removeGroupValue(label, value)"
        >×</button>
      </span>
      <span v-if="groupValues(label).length === 0" class="cb-muted">未选择</span>
    </div>
  </div>

  <p class="cb-hint">
    点一下熟练、再点一下专精（技能）；豁免是熟练开关。数值由骰娘按等级、属性与熟练自动计算，
    额外加值里的常数已计入；骰子加值（如 +1d4）会原样附在数值后面。
  </p>
</template>

<script setup>
import { computed, ref } from 'vue'
import { K } from '../../card-builder/core.mjs'

// $熟练$：豁免与技能的点击编辑，护甲/武器复选框，工具/语言多选 + 自定义。
const props = defineProps({
  state: { type: Object, required: true },
  enums: { type: Object, required: true },
  abilities: { type: Array, required: true },
  skills: { type: Array, required: true },
  values: { type: Object, default: () => ({}) },
})

const weaponCustom = ref('')
const toolCustom = ref('')
const languageCustom = ref('')

const sections = computed(() => [
  { label: '豁免', items: props.enums.saving_items || [], triple: false },
  { label: '技能', items: props.skills, triple: true },
])

const armorOptions = computed(() => props.enums.armor_categories || [])
const weaponOptions = computed(() => props.enums.weapon_categories || [])
const toolOptions = computed(() => props.enums.tool_options || [])
const languageOptions = computed(() => props.enums.languages_standard || [])
const exoticLanguageOptions = computed(() => props.enums.languages_exotic || [])
const groupLabels = computed(() => props.enums.proficiency_groups || [])

function scaleOf(name) {
  return Number(props.state[K.PROF].checks[name] || 0)
}

function chipClass(name) {
  const scale = scaleOf(name)
  if (scale <= 0) return ''
  return scale === 1 ? 'cb-chip--1' : 'cb-chip--2'
}

function markOf(name) {
  const scale = scaleOf(name)
  if (scale === 1) return '熟练'
  if (scale === 2) return '专精'
  return `×${scale}`
}

function shortName(name) {
  return name.endsWith('豁免') ? name.slice(0, -2) : name
}

function chipTitle(name, triple) {
  if (triple) return `${name}：未熟练 → 熟练 → 专精（点击切换）`
  return `${name}：未熟练 ↔ 熟练（点击切换）`
}

function cycle(name, triple) {
  const checks = props.state[K.PROF].checks
  const current = scaleOf(name)
  if (!triple) {
    checks[name] = current > 0 ? 0 : 1
    return
  }
  if (current === 0) checks[name] = 1
  else if (current === 1) checks[name] = 2
  else checks[name] = 0
}

function groupValues(label) {
  const raw = props.state[K.PROF].groups[label] || ''
  return raw.split('·').map((value) => value.trim()).filter((value) => value)
}

function setGroupValues(label, values) {
  props.state[K.PROF].groups[label] = [...new Set(values)].join('·')
}

function hasGroupValue(label, value) {
  return groupValues(label).includes(value)
}

function toggleGroupValue(label, value) {
  const current = groupValues(label)
  if (current.includes(value)) {
    setGroupValues(label, current.filter((item) => item !== value))
  } else {
    setGroupValues(label, [...current, value])
  }
}

function addCustom(label, value) {
  const text = value.trim()
  if (!text) return
  if (text.includes('·')) return
  const current = groupValues(label)
  if (!current.includes(text)) setGroupValues(label, [...current, text])
}

function removeGroupValue(label, value) {
  setGroupValues(label, groupValues(label).filter((item) => item !== value))
}

function onToolSelect(event) {
  const value = event.target.value
  if (value) addCustom('工具', value)
  event.target.value = ''
}
</script>
