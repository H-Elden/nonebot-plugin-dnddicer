<template>
  <div v-for="section in sections" :key="section.label" class="cb-prof-section">
    <div class="cb-subhead">
      {{ section.label }}
    </div>
    <div class="cb-chip-grid">
      <button
        v-for="name in section.items"
        :key="name"
        type="button"
        class="cb-chip"
        :class="chipClass(name)"
        :title="chipTitle(name, section.triple)"
        :aria-pressed="scaleOf(name) > 0 ? 'true' : 'false'"
        @click="cycle(name, section.triple)"
      >
        {{ shortName(name) }}
        <span class="cb-chip__value">{{ values[name] || '—' }}</span>
        <span v-if="scaleOf(name) > 0" class="cb-chip__mark">{{ markOf(name) }}</span>
      </button>
    </div>
  </div>

  <div class="cb-subhead">
    护甲受训
  </div>
  <div class="cb-chip-grid">
    <ToggleChip
      v-for="name in armorOptions"
      :key="name"
      :active="hasGroupValue('护甲', name)"
      @toggle="toggleGroupValue('护甲', name)"
    >{{ name }}</ToggleChip>
  </div>

  <div class="cb-subhead">
    武器熟练
  </div>
  <div class="cb-chip-grid">
    <ToggleChip
      v-for="name in weaponOptions"
      :key="name"
      :active="hasGroupValue('武器', name)"
      @toggle="toggleGroupValue('武器', name)"
    >{{ name }}</ToggleChip>
    <span
      v-for="name in customValues('武器', weaponOptions)"
      :key="name"
      class="cb-chip cb-chip--1 cb-chip--static"
    >
      {{ name }}
      <button
        type="button"
        class="cb-chip__remove"
        title="移除"
        @click="removeGroupValue('武器', name)"
      >×</button>
    </span>
  </div>
  <div class="cb-inline">
    <input
      v-model="weaponCustom"
      class="cb-input"
      placeholder="特定武器（如 长剑），回车添加"
      @keyup.enter="addWeapon"
    />
    <button
      type="button"
      class="cb-btn cb-btn--ghost cb-btn--small"
      @click="addWeapon"
    >添加</button>
  </div>

  <div class="cb-subhead">
    工具熟练
  </div>
  <div class="cb-chip-grid">
    <span
      v-for="name in groupValues('工具')"
      :key="name"
      class="cb-chip cb-chip--1 cb-chip--static"
    >
      {{ name }}
      <button
        type="button"
        class="cb-chip__remove"
        title="移除"
        @click="removeGroupValue('工具', name)"
      >×</button>
    </span>
    <span v-if="groupValues('工具').length === 0" class="cb-muted">未选择</span>
  </div>
  <div class="cb-inline">
    <ToolPicker
      :options="toolOptions"
      :selected="groupValues('工具')"
      @toggle="toggleGroupValue('工具', $event)"
    />
    <input
      v-model="toolCustom"
      class="cb-input"
      placeholder="自定义工具，回车添加"
      @keyup.enter="addTool"
    />
    <button
      type="button"
      class="cb-btn cb-btn--ghost cb-btn--small"
      @click="addTool"
    >添加</button>
  </div>

  <div class="cb-subhead">
    语言
  </div>
  <div class="cb-subhead cb-subhead--minor">标准语言</div>
  <div class="cb-chip-grid">
    <ToggleChip
      v-for="name in languageOptions"
      :key="name"
      :active="hasGroupValue('语言', name)"
      @toggle="toggleGroupValue('语言', name)"
    >{{ name }}</ToggleChip>
  </div>
  <div class="cb-subhead cb-subhead--minor">稀有语言</div>
  <div class="cb-chip-grid">
    <ToggleChip
      v-for="name in exoticLanguageOptions"
      :key="name"
      :active="hasGroupValue('语言', name)"
      @toggle="toggleGroupValue('语言', name)"
    >{{ name }}</ToggleChip>
  </div>
  <div class="cb-chip-grid">
    <span
      v-for="name in customValues('语言', [...languageOptions, ...exoticLanguageOptions])"
      :key="name"
      class="cb-chip cb-chip--1 cb-chip--static"
    >
      {{ name }}
      <button
        type="button"
        class="cb-chip__remove"
        title="移除"
        @click="removeGroupValue('语言', name)"
      >×</button>
    </span>
  </div>
  <div class="cb-inline">
    <input
      v-model="languageCustom"
      class="cb-input"
      placeholder="自定义语言，回车添加"
      @keyup.enter="addLanguage"
    />
    <button
      type="button"
      class="cb-btn cb-btn--ghost cb-btn--small"
      @click="addLanguage"
    >添加</button>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { K } from '../../card-builder/core.mjs'
import ToggleChip from './ToggleChip.vue'
import ToolPicker from './ToolPicker.vue'

// $熟练$：豁免/技能点击熟练与专精；护甲/武器/语言 chip；工具浮层 + 自定义。
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
  {
    label: '豁免',
    items: props.enums.saving_items || [],
    triple: false,
  },
  {
    label: '技能',
    items: props.skills,
    triple: true,
  },
])

const armorOptions = computed(() => props.enums.armor_categories || [])
const weaponOptions = computed(() => props.enums.weapon_categories || [])
const toolOptions = computed(() => props.enums.tool_options || [])
const languageOptions = computed(() => props.enums.languages_standard || [])
const exoticLanguageOptions = computed(() => props.enums.languages_exotic || [])

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

function customValues(label, options) {
  return groupValues(label).filter((value) => !options.includes(value))
}

function addCustom(label, value) {
  const text = value.trim()
  if (!text) return
  if (text.includes('·')) return
  const current = groupValues(label)
  if (!current.includes(text)) setGroupValues(label, [...current, text])
}

function addWeapon() {
  addCustom('武器', weaponCustom.value)
  weaponCustom.value = ''
}

function addTool() {
  addCustom('工具', toolCustom.value)
  toolCustom.value = ''
}

function addLanguage() {
  addCustom('语言', languageCustom.value)
  languageCustom.value = ''
}

function removeGroupValue(label, value) {
  setGroupValues(label, groupValues(label).filter((item) => item !== value))
}
</script>
