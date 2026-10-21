<template>
  <div class="cb-item-head">
    <span>名称</span>
    <span>数量</span>
    <span>已装备</span>
  </div>
  <RepeaterRows
    :items="state[K.ITEMS]"
    :max="limits.item_max_count || 50"
    add-label="添加物品"
    :factory="factory"
    compact
  >
    <template #default="{ item }">
      <div class="cb-item-row">
        <input
          v-model="item.name"
          class="cb-input"
          placeholder="治疗药水"
          aria-label="物品名称"
        />
        <input
          v-model="item.qty"
          class="cb-input"
          inputmode="numeric"
          placeholder="1"
          aria-label="物品数量"
        />
        <label class="cb-check">
          <input v-model="item.equipped" type="checkbox" />
          装备
        </label>
      </div>
    </template>
  </RepeaterRows>
  <p class="cb-hint">没写数量按 1 件记录；勾选「装备」会在卡面标记。</p>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'
import RepeaterRows from './RepeaterRows.vue'

// $物品$：名称、数量与装备标记（单行紧凑布局，背包件数多时不占太多纵向空间）。
defineProps({
  state: { type: Object, required: true },
  limits: { type: Object, required: true },
})

function factory() {
  return { name: '', qty: '1', equipped: false }
}
</script>
