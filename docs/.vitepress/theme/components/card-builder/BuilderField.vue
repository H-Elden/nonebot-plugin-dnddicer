<template>
  <div class="cb-field" :data-seg-key="segmentKey">
    <div class="cb-field__head">
      <span class="cb-field__label">{{ label }}</span>
      <span v-if="required" class="cb-badge cb-badge--required">必填</span>
      <span v-if="segmentKey" class="cb-field__key">{{ segmentKey }}</span>
    </div>
    <p v-if="summary" class="cb-field__summary">{{ summary }}</p>
    <div class="cb-field__body">
      <slot />
    </div>
    <ul v-if="errors && errors.length" class="cb-errors">
      <li v-for="(error, index) in errors" :key="index">{{ error.message }}</li>
    </ul>
  </div>
</template>

<script setup>
// 单个段的容器：标题、说明、必填标记与逐条错误。表单控件由父组件按段类型填入。
defineProps({
  label: { type: String, required: true },
  summary: { type: String, default: '' },
  segmentKey: { type: String, default: '' },
  required: { type: Boolean, default: false },
  errors: { type: Array, default: () => [] },
})
</script>
