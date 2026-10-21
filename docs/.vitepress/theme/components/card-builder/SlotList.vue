<template>
  <div class="cb-slot-grid">
    <div v-for="(row, index) in state[K.SPELL_SLOTS].levels" :key="index" class="cb-slot-row">
      <span class="cb-slot-row__label">{{ index + 1 }} 环</span>
      <label class="cb-slot-row__cell">
        <span>当前</span>
        <input
          v-model="row.cur"
          class="cb-input"
          inputmode="numeric"
          placeholder="0"
          :aria-label="`${index + 1}环当前法术位`"
        />
      </label>
      <label class="cb-slot-row__cell">
        <span>上限</span>
        <input
          v-model="row.max"
          class="cb-input"
          inputmode="numeric"
          placeholder="0"
          :aria-label="`${index + 1}环法术位上限`"
        />
      </label>
    </div>
  </div>

  <div class="cb-subhead">契约法术位（魔契师）</div>
  <div class="cb-grid cb-grid--3">
    <label class="cb-grid__cell">
      <span class="cb-grid__label">环阶</span>
      <input v-model="state[K.SPELL_SLOTS].pact.level" class="cb-input" inputmode="numeric" placeholder="3" />
    </label>
    <label class="cb-grid__cell">
      <span class="cb-grid__label">当前</span>
      <input v-model="state[K.SPELL_SLOTS].pact.cur" class="cb-input" inputmode="numeric" placeholder="2" />
    </label>
    <label class="cb-grid__cell">
      <span class="cb-grid__label">上限</span>
      <input v-model="state[K.SPELL_SLOTS].pact.max" class="cb-input" inputmode="numeric" placeholder="2" />
    </label>
  </div>
  <p class="cb-hint">只填有法术位的环阶；上限留空表示没有该环法术位。契约位不填则整项省略。</p>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'

// $法术位$：1~9 环的当前/上限 + 单列契约法术位。
defineProps({
  state: { type: Object, required: true },
})
</script>
