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
      <label class="cb-grid__cell">
        <span class="cb-grid__label">说明（空行分段，最多 {{ limits.magic_item_paragraph_max || 5 }} 段）</span>
        <textarea
          v-model="item.text"
          class="cb-textarea"
          rows="3"
          placeholder="着装此斗篷期间，你的 AC 和豁免获得 +1 加值。&#10;&#10;这件斗篷由银线织成，边缘绣着古老的守护符文。"
        ></textarea>
      </label>
    </template>
  </RepeaterRows>
  <p class="cb-hint">
    魔法物品不放进「物品」；卡面会单独显示名称、标签与说明段落。说明里的空行等于分段，不用手写 //。
  </p>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'
import RepeaterRows from './RepeaterRows.vue'

// $魔法物品$：名称 + 标签 + 多段说明（空行分段，导出时转成 //）。
defineProps({
  state: { type: Object, required: true },
  limits: { type: Object, required: true },
})

function factory() {
  return { name: '', tag: '', text: '' }
}
</script>
