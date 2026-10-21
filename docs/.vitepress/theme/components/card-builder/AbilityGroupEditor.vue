<template>
  <div v-if="mode === 'ability'" class="cb-grid cb-grid--6">
    <label v-for="(name, index) in abilities" :key="name" class="cb-grid__cell">
      <span class="cb-grid__label">{{ name }}</span>
      <input
        v-model="state[K.ABILITY][index]"
        class="cb-input"
        inputmode="numeric"
        placeholder="10"
      />
    </label>
  </div>

  <div v-else-if="mode === 'display'" class="cb-grid cb-grid--3">
    <div v-for="(name, index) in abilities" :key="name" class="cb-grid__cell">
      <span class="cb-grid__label">{{ name }}</span>
      <div class="cb-inline">
        <input
          v-model="state[K.ABILITY_DISPLAY][index].score"
          class="cb-input"
          inputmode="numeric"
          placeholder="值 18"
          :aria-label="`${name}属性值`"
        />
        <input
          v-model="state[K.ABILITY_DISPLAY][index].mod"
          class="cb-input"
          placeholder="调整 +4"
          :aria-label="`${name}调整值`"
        />
      </div>
    </div>
  </div>

  <div v-else class="cb-grid cb-grid--6">
    <label v-for="(name, index) in abilities" :key="name" class="cb-grid__cell">
      <span class="cb-grid__label">{{ name }}</span>
      <input
        v-model="state[K.SAVES][index]"
        class="cb-input"
        placeholder="+0"
        :aria-label="`${name}豁免`"
      />
    </label>
  </div>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'

// 六属性的三种形态：原始值（$属性$）、展示值（$属性值$）、豁免（$豁免$）。
// 只负责录入，是否填写完整与取值范围由 core.mjs 校验。
defineProps({
  state: { type: Object, required: true },
  mode: { type: String, default: 'ability' },
  abilities: { type: Array, required: true },
})
</script>
