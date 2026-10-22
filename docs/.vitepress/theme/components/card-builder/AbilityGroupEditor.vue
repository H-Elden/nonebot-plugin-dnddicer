<template>
  <div class="cb-grid cb-grid--6">
    <label v-for="(name, index) in abilities" :key="name" class="cb-grid__cell">
      <span class="cb-grid__label">{{ name }}</span>
      <input
        v-model="state[K.ABILITY][index]"
        class="cb-input"
        inputmode="numeric"
        placeholder="10"
      />
      <span class="cb-derived">{{ modifiers[index] || '调整 —' }}</span>
    </label>
  </div>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'

// $属性$：六个原始值；调整值由骰娘按 (值-10)//2 计算，这里只做只读预览。
defineProps({
  state: { type: Object, required: true },
  abilities: { type: Array, required: true },
  modifiers: { type: Array, default: () => [] },
})
</script>
