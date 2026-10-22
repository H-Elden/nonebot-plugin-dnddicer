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
    点一下熟练、再点一下专精（技能）；豁免是熟练开关。数值由骰娘按等级、属性与熟练自动计算，
    额外加值里的常数已计入；骰子加值（如 +1d4）会原样附在数值后面。
  </p>
</template>

<script setup>
import { computed } from 'vue'
import { K } from '../../card-builder/core.mjs'

// $熟练$：豁免（熟练开关）与技能（未熟练 → 熟练 → 专精）的点击编辑，
// 外加四个只用于卡面的展示分组。旧卡里的属性检定熟练若存在，额外给一个
// 兼容分组，保证导入后仍可查看和清除。
const props = defineProps({
  state: { type: Object, required: true },
  enums: { type: Object, required: true },
  abilities: { type: Array, required: true },
  skills: { type: Array, required: true },
  values: { type: Object, default: () => ({}) },
})

const groups = computed(() => props.enums.proficiency_groups || [])
const sections = computed(() => {
  const legacy = props.abilities.filter((name) => scaleOf(name) > 0)
  const list = [
    { label: '豁免', items: props.enums.saving_items || [], triple: false },
    { label: '技能', items: props.skills, triple: true },
  ]
  if (legacy.length > 0) {
    list.push({ label: '属性检定（旧卡兼容）', items: legacy, triple: false })
  }
  return list
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
