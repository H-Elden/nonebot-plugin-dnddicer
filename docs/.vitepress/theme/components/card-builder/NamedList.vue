<template>
  <RepeaterRows
    :items="state[fieldKey]"
    :max="max"
    :add-label="addLabel"
    :factory="factory"
  >
    <template #default="{ item }">
      <div class="cb-grid cb-grid--2">
        <label class="cb-grid__cell">
          <span class="cb-grid__label">名称</span>
          <input v-model="item.name" class="cb-input" :placeholder="namePlaceholder" />
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">说明（可选，只用于卡面）</span>
          <input v-model="item.text" class="cb-input" :placeholder="textPlaceholder" />
        </label>
      </div>
    </template>
  </RepeaterRows>
</template>

<script setup>
import RepeaterRows from './RepeaterRows.vue'

// 专长 / 特性共用的行编辑器：一行是「名称 + 可选说明」。
defineProps({
  state: { type: Object, required: true },
  fieldKey: { type: String, required: true },
  max: { type: Number, default: 20 },
  namePlaceholder: { type: String, default: '' },
  textPlaceholder: { type: String, default: '' },
  addLabel: { type: String, default: '添加一行' },
})

function factory() {
  return { name: '', text: '' }
}
</script>
