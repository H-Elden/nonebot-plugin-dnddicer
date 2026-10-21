<template>
  <RepeaterRows
    :items="state[K.WEAPON]"
    :max="limits.weapon_max_count || 20"
    add-label="添加武器"
    :factory="factory"
  >
    <template #default="{ item }">
      <div class="cb-grid cb-grid--3">
        <label class="cb-grid__cell">
          <span class="cb-grid__label">名称</span>
          <input v-model="item.name" class="cb-input" placeholder="长剑" />
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">命中加值</span>
          <input v-model="item.attack" class="cb-input" placeholder="+6" />
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">伤害表达式</span>
          <input v-model="item.damage" class="cb-input" placeholder="1d8+3" />
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">伤害类型</span>
          <select v-model="item.type" class="cb-select">
            <option value="">不写</option>
            <option v-for="type in enums.damage_types" :key="type" :value="type">{{ type }}</option>
          </select>
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">卡面备注</span>
          <input v-model="item.note" class="cb-input" placeholder="灵巧 · 轻型" />
        </label>
        <label class="cb-check cb-check--cell">
          <input v-model="item.noAttack" type="checkbox" />
          不做攻击检定（名称尾加 x）
        </label>
      </div>
    </template>
  </RepeaterRows>
  <p class="cb-hint">
    写法是「名称+命中,伤害+类型[,备注]」，如 <code>长剑+6,1d8+4挥砍</code>。名称尾加 x 表示只有伤害（如
    <code>火球术x,8d6火焰</code>）；备注只用于卡面图。
  </p>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'
import RepeaterRows from './RepeaterRows.vue'

// $武器$：名称、命中加值、伤害表达式、伤害类型、卡面备注与 x 标记。
defineProps({
  state: { type: Object, required: true },
  enums: { type: Object, required: true },
  limits: { type: Object, required: true },
})

function factory() {
  return { name: '', noAttack: false, attack: '', damage: '', type: '', note: '' }
}
</script>
