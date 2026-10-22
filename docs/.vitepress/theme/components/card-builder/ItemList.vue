<template>
  <div class="cb-item-head cb-item-head--plain">
    <span>名称</span>
    <span>数量</span>
  </div>
  <RepeaterRows
    :items="state[K.ITEMS]"
    :max="limits.item_max_count || 50"
    add-label="添加物品"
    :factory="factory"
    compact
  >
    <template #default="{ item }">
      <div class="cb-item-row cb-item-row--plain">
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
      </div>
    </template>
  </RepeaterRows>
  <p class="cb-hint">
    没写数量按 1 件记录。物品只记名称与数量；魔法物品请写到「魔法物品」，那里有标签与说明。
  </p>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'
import RepeaterRows from './RepeaterRows.vue'

// $物品$：名称与数量（单行紧凑布局，背包件数多时不占太多纵向空间）。
defineProps({
  state: { type: Object, required: true },
  limits: { type: Object, required: true },
})

function factory() {
  return { name: '', qty: '1' }
}
</script>
