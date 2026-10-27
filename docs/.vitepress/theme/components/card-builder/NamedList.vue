<template>
  <RepeaterRows
    :items="state[fieldKey]"
    :max="max"
    :add-label="addLabel"
    :factory="factory"
  >
    <template #default="{ item }">
      <label class="cb-grid__cell">
        <span class="cb-grid__label">名称</span>
        <input v-model="item.name" class="cb-input" :placeholder="namePlaceholder" />
      </label>
      <div class="cb-grid__cell">
        <span class="cb-grid__label">说明（可选，只用于卡面）</span>
        <LongTextarea
          v-model="item.text"
          count-mode="paragraph"
          :max="textMax"
          :placeholder="textPlaceholder"
          aria-label="说明"
        />
      </div>
    </template>
  </RepeaterRows>
</template>

<script setup>
import LongTextarea from './LongTextarea.vue'
import RepeaterRows from './RepeaterRows.vue'

// 专长 / 特性共用的行编辑器：名称 + 可选说明（多行输入）。
defineProps({
  state: { type: Object, required: true },
  fieldKey: { type: String, required: true },
  max: { type: Number, default: 20 },
  namePlaceholder: { type: String, default: '' },
  textPlaceholder: { type: String, default: '' },
  textMax: { type: Number, default: 400 },
  addLabel: { type: String, default: '添加一行' },
})

function factory() {
  return { name: '', text: '' }
}
</script>
