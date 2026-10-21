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
        :title="`${name}：未熟练 → 熟练 → 专精（点击切换）`"
        @click="cycle(name)"
      >
        {{ shortName(name) }}
        <span v-if="scaleOf(name) > 0" class="cb-chip__mark">{{ markOf(name) }}</span>
      </button>
    </div>
  </div>

  <div class="cb-subhead">展示分组（只用于卡面）</div>
  <div class="cb-grid cb-grid--2">
    <label v-for="label in groups" :key="label" class="cb-grid__cell">
      <span class="cb-grid__label">{{ label }}</span>
      <input
        v-model="state[K.PROF].groups[label]"
        class="cb-input"
        :placeholder="groupPlaceholder(label)"
      />
    </label>
  </div>
  <p class="cb-hint">
    检定条目决定 <code>.力量检定</code> 等点命令的加值（熟练 +N、专精 2×N）；展示分组用 <code>·</code>
    分隔，只出现在卡面图上。
  </p>
</template>

<script setup>
import { computed } from 'vue'
import { K } from '../../card-builder/core.mjs'

// $熟练$：30 个检定条目的三态切换（未熟练 / 熟练 / 专精）+ 四个展示分组。
const props = defineProps({
  state: { type: Object, required: true },
  enums: { type: Object, required: true },
  abilities: { type: Array, required: true },
  skills: { type: Array, required: true },
})

const groups = computed(() => props.enums.proficiency_groups || [])
const sections = computed(() => {
  const items = props.enums.check_items || []
  const abilityCount = props.abilities.length
  const skillCount = props.skills.length
  return [
    { label: '属性检定', items: items.slice(0, abilityCount) },
    { label: '技能', items: items.slice(abilityCount, abilityCount + skillCount) },
    { label: '豁免', items: items.slice(abilityCount + skillCount) },
  ]
})

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

function cycle(name) {
  const checks = props.state[K.PROF].checks
  const current = scaleOf(name)
  if (current === 0) checks[name] = 1
  else if (current === 1) checks[name] = 2
  else checks[name] = 0
}

function groupPlaceholder(label) {
  const placeholders = {
    护甲: '轻甲·中甲',
    武器: '军用武器·简易武器',
    工具: '盗贼工具',
    语言: '通用语·精灵语',
  }
  return placeholders[label] || '用 · 分隔多项'
}
</script>
