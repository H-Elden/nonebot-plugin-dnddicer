<template>
  <div class="cb-grid cb-grid--3">
    <label class="cb-grid__cell">
      <span class="cb-grid__label">施法属性</span>
      <select v-model="state[K.SPELL].ability" class="cb-select">
        <option value="">未填写</option>
        <option v-for="ability in abilities" :key="ability" :value="ability">{{ ability }}</option>
      </select>
    </label>
    <label class="cb-grid__cell">
      <span class="cb-grid__label">豁免 DC</span>
      <input v-model="state[K.SPELL].dc" class="cb-input" inputmode="numeric" placeholder="15" />
    </label>
    <label class="cb-grid__cell">
      <span class="cb-grid__label">法术攻击</span>
      <input v-model="state[K.SPELL].attack" class="cb-input" placeholder="+7" />
    </label>
  </div>

  <div class="cb-subhead">法术清单</div>
  <RepeaterRows
    :items="state[K.SPELL].list"
    :max="limits.spell_max_count || 50"
    add-label="添加法术"
    :factory="factory"
  >
    <template #default="{ item }">
      <div class="cb-grid cb-grid--4">
        <label class="cb-grid__cell">
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
        <span v-if="item.level === '0'" class="cb-grid__cell cb-muted">戏法无需准备</span>
        <label v-else class="cb-check cb-check--cell">
          <input v-model="item.prepared" type="checkbox" />
          今日已准备（*）
        </label>
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
      <div class="cb-inline">
        <label class="cb-check"><input v-model="item.concentration" type="checkbox" /> 专注</label>
        <label class="cb-check"><input v-model="item.ritual" type="checkbox" /> 仪式</label>
        <label class="cb-check"><input v-model="item.material" type="checkbox" /> 材料</label>
      </div>
    </template>
  </RepeaterRows>
  <p class="cb-hint">
    时间 / 距离 / 专注 / 仪式 / 材料与备注只用于卡面图，不参与施法结算。环阶 0 = 戏法；
    <code>*</code> 表示今日已准备，可用 <code>.法术 准备/取消</code> 在群里切换。
  </p>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'
import RepeaterRows from './RepeaterRows.vue'

// $法术$：施法属性 / 豁免 DC / 法术攻击三个头键 + 法术清单（环阶、准备标记、卡面详情）。
defineProps({
  state: { type: Object, required: true },
  enums: { type: Object, required: true },
  limits: { type: Object, required: true },
  abilities: { type: Array, required: true },
})

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
