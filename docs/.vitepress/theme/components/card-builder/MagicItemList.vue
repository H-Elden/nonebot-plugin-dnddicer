<template>
  <RepeaterRows
    :items="state[K.MAGIC_ITEMS]"
    :max="limits.magic_item_max_count || 20"
    add-label="添加魔法物品"
    :factory="factory"
  >
    <template #default="{ item }">
      <div class="cb-grid cb-grid--2">
        <label class="cb-grid__cell">
          <span class="cb-grid__label">名称</span>
          <input v-model="item.name" class="cb-input" placeholder="防护斗篷" />
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">标签（类型、稀有度、同调）</span>
          <input
            v-model="item.tag"
            class="cb-input"
            placeholder="奇物，非普通（需同调）"
          />
        </label>
      </div>
      <div class="cb-grid__cell">
        <span class="cb-grid__label">说明</span>
        <LongTextarea
          v-model="item.text"
          :max="limits.magic_item_text_max_len || 500"
          count-mode="paragraph"
          placeholder="着装此斗篷期间，你的 AC 和豁免获得 +1 加值。&#10;这件斗篷由银线织成，边缘绣着古老的守护符文。"
          aria-label="魔法物品说明"
        />
      </div>
    </template>
  </RepeaterRows>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'
import LongTextarea from './LongTextarea.vue'
import RepeaterRows from './RepeaterRows.vue'

// $魔法物品$：名称 + 标签 + 多段说明（每行一段，导出时转成 //）。
defineProps({
  state: { type: Object, required: true },
  limits: { type: Object, required: true },
})

function factory() {
  return { name: '', tag: '', text: '' }
}
</script>
