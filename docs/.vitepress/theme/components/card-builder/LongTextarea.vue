<template>
  <div class="cb-longtext">
    <textarea
      :value="modelValue"
      class="cb-textarea"
      :rows="rows"
      :placeholder="placeholder"
      :aria-label="ariaLabel"
      wrap="soft"
      @input="$emit('update:modelValue', $event.target.value)"
    ></textarea>
    <span class="cb-inline-note">{{ count }} / {{ max }} 字</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { charLength, splitParagraphs } from '../../card-builder/core.mjs'

// 卡面长说明：多行自动折行、内容超出时可滚动，并显示字数。
const props = defineProps({
  modelValue: { type: String, default: '' },
  max: { type: Number, default: 400 },
  rows: { type: [Number, String], default: 3 },
  placeholder: { type: String, default: '' },
  ariaLabel: { type: String, default: '说明' },
  // paragraph：按换行分段后统计正文字数（不含换行），与卡文本的 // 分段一致
  countMode: { type: String, default: 'raw' },
})
defineEmits(['update:modelValue'])

const count = computed(() =>
  props.countMode === 'paragraph'
    ? splitParagraphs(props.modelValue).reduce(
        (sum, paragraph) => sum + charLength(paragraph),
        0,
      )
    : charLength(props.modelValue),
)
</script>
