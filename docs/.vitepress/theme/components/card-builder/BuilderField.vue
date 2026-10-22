<template>
  <div class="cb-field" :data-seg-key="segmentKey">
    <div class="cb-field__head">
      <span class="cb-field__label">{{ label }}</span>
      <HintDot v-if="summary" :text="summary" />
      <span v-if="required" class="cb-badge cb-badge--required">必填</span>
      <span v-if="segmentKey" class="cb-field__key">{{ segmentKey }}</span>
      <CopyButton
        v-if="segmentKey"
        class="cb-field__copy"
        :text="copyCommand"
        label="复制本段"
        :disabled="copyDisabled"
        :title="copyHint"
      />
    </div>
    <div class="cb-field__body">
      <slot />
    </div>
    <ul v-if="errors && errors.length" class="cb-errors">
      <li v-for="(error, index) in errors" :key="index">{{ error.message }}</li>
    </ul>
  </div>
</template>

<script setup>
import CopyButton from './CopyButton.vue'
import HintDot from './HintDot.vue'

// 单个段的容器：标题、问号说明、必填标记、字段复制按钮与逐条错误。
defineProps({
  label: { type: String, required: true },
  summary: { type: String, default: '' },
  segmentKey: { type: String, default: '' },
  required: { type: Boolean, default: false },
  errors: { type: Array, default: () => [] },
  copyCommand: { type: String, default: '' },
  copyDisabled: { type: Boolean, default: false },
  copyHint: {
    type: String,
    default: '只复制这一段的命令；建卡后改这一段时用。首次建卡请先复制整卡。',
  },
})
</script>
