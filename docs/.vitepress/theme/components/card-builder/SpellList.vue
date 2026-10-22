<template>
  <div class="cb-grid cb-grid--3">
    <label class="cb-grid__cell">
      <span class="cb-grid__label">施法属性</span>
      <select v-model="state[K.SPELL].ability" class="cb-select">
        <option value="">未选择</option>
        <option v-for="ability in abilities" :key="ability" :value="ability">{{ ability }}</option>
      </select>
    </label>
    <div class="cb-grid__cell">
      <span class="cb-grid__label">
        豁免 DC
        <HintDot text="公式：8 + 熟练 + 施法属性调整值；勾选手动后可覆盖公式值。" />
      </span>
      <input
        v-model="state[K.SPELL].dc"
        class="cb-input"
        :class="{ 'cb-input--readonly': !state[K.SPELL].dcManual && derived.available }"
        inputmode="numeric"
        placeholder="15"
      />
      <span v-if="derived.available" class="cb-formula">= {{ derived.dc }}</span>
      <div class="cb-inline">
        <ToggleChip
          :active="state[K.SPELL].dcManual"
          @toggle="state[K.SPELL].dcManual = !state[K.SPELL].dcManual"
        >手动</ToggleChip>
        <button
          v-if="state[K.SPELL].dcManual && derived.available"
          type="button"
          class="cb-link"
          @click="restoreDc"
        >恢复公式</button>
      </div>
    </div>
    <div class="cb-grid__cell">
      <span class="cb-grid__label">
        法术攻击
        <HintDot text="公式：熟练 + 施法属性调整值；勾选手动后可覆盖公式值。" />
      </span>
      <input
        v-model="state[K.SPELL].attack"
        class="cb-input"
        :class="{ 'cb-input--readonly': !state[K.SPELL].attackManual && derived.available }"
        placeholder="+8"
      />
      <span v-if="derived.available" class="cb-formula">= {{ derived.attack }}</span>
      <div class="cb-inline">
        <ToggleChip
          :active="state[K.SPELL].attackManual"
          @toggle="state[K.SPELL].attackManual = !state[K.SPELL].attackManual"
        >手动</ToggleChip>
        <button
          v-if="state[K.SPELL].attackManual && derived.available"
          type="button"
          class="cb-link"
          @click="restoreAttack"
        >恢复公式</button>
      </div>
    </div>
  </div>

  <div class="cb-subhead">
    法术清单
    <HintDot text="环阶选「戏法」或对应环数；准备状态与时间、距离、专注等标记只影响卡面显示。" />
  </div>
  <RepeaterRows
    :items="state[K.SPELL].list"
    :max="limits.spell_max_count || 50"
    add-label="添加法术"
    :factory="factory"
  >
    <template #default="{ item }">
      <div class="cb-grid cb-grid--5">
        <label class="cb-grid__cell cb-grid__cell--span2">
          <span class="cb-grid__label">法术名</span>
          <input v-model="item.name" class="cb-input" placeholder="火球术" />
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">环阶</span>
          <select v-model="item.level" class="cb-select">
            <option v-for="level in 10" :key="level" :value="String(level - 1)">
              {{ levelLabel(level - 1) }}
            </option>
          </select>
        </label>
        <div class="cb-grid__cell cb-grid__cell--span2">
          <span class="cb-grid__label">准备状态</span>
          <div class="cb-inline">
            <span v-if="item.level === '0'" class="cb-muted">戏法无需准备</span>
            <ToggleChip
              v-else
              :active="item.prepared"
              @toggle="item.prepared = !item.prepared"
            >今日已准备</ToggleChip>
            <ToggleChip
              :active="item.concentration"
              @toggle="item.concentration = !item.concentration"
            >专注</ToggleChip>
            <ToggleChip :active="item.ritual" @toggle="item.ritual = !item.ritual">仪式</ToggleChip>
            <ToggleChip :active="item.material" @toggle="item.material = !item.material">材料</ToggleChip>
          </div>
        </div>
      </div>
      <div class="cb-grid cb-grid--3">
        <label class="cb-grid__cell">
          <span class="cb-grid__label">施法时间</span>
          <input v-model="item.time" class="cb-input" placeholder="1动作" />
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">距离</span>
          <input v-model="item.range" class="cb-input" placeholder="150尺" />
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">备注</span>
          <input v-model="item.note" class="cb-input" placeholder="8d6 火焰 / 敏捷" />
        </label>
      </div>
    </template>
  </RepeaterRows>
</template>

<script setup>
import { watch } from 'vue'
import { K } from '../../card-builder/core.mjs'
import HintDot from './HintDot.vue'
import RepeaterRows from './RepeaterRows.vue'
import ToggleChip from './ToggleChip.vue'

// $法术$：施法属性 + 自动/手动 DC 与攻击 + 法术清单。
const props = defineProps({
  state: { type: Object, required: true },
  enums: { type: Object, required: true },
  limits: { type: Object, required: true },
  abilities: { type: Array, required: true },
  derived: { type: Object, default: () => ({ dc: '', attack: '', available: false }) },
})

watch(
  () => [props.derived.dc, props.derived.attack, props.derived.available],
  () => {
    const spell = props.state[K.SPELL]
    if (!spell) return
    if (!spell.dcManual && props.derived.available) spell.dc = props.derived.dc
    if (!spell.attackManual && props.derived.available) {
      spell.attack = props.derived.attack
    }
  },
  { immediate: true },
)

function restoreDc() {
  props.state[K.SPELL].dcManual = false
  if (props.derived.available) props.state[K.SPELL].dc = props.derived.dc
}

function restoreAttack() {
  props.state[K.SPELL].attackManual = false
  if (props.derived.available) props.state[K.SPELL].attack = props.derived.attack
}

function factory() {
  return {
    name: '',
    level: '0',
    prepared: false,
    time: '',
    range: '',
    concentration: false,
    ritual: false,
    material: false,
    note: '',
  }
}

function levelLabel(level) {
  return level === 0 ? '戏法' : `${level}环`
}
</script>
