<template>
  <button
    type="button"
    class="cb-chip"
    :class="{ 'cb-chip--1': active }"
    :aria-pressed="active ? 'true' : 'false'"
    @click="$emit('toggle')"
  >
    <slot />
  </button>
</template>

<script setup>
// 统一的圆角矩形选择按钮：护甲/武器/语言/法术标记/恢复档都用它。
defineProps({
  active: { type: Boolean, default: false },
})
defineEmits(['toggle'])
</script>
