<template>
  <div class="cb-grid cb-grid--3">
    <div v-for="name in skills" :key="name" class="cb-grid__cell cb-skill">
      <span class="cb-grid__label">{{ name }}</span>
      <div class="cb-inline">
        <input
          v-model="state[K.SKILLS][name].bonus"
          class="cb-input"
          placeholder="+0"
          :aria-label="`${name}加值`"
        />
        <label class="cb-check" :title="`${name}专精（双倍熟练）`">
          <input v-model="state[K.SKILLS][name].expertise" type="checkbox" />
          专精
        </label>
      </div>
    </div>
  </div>
  <p class="cb-hint">只填有值的技能；专精在卡面写 <code>*</code>。检定加值由你自己按规则算好填写。</p>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'

// $技能$：18 项技能只填有值的，尾部 * 表示专精。
defineProps({
  state: { type: Object, required: true },
  skills: { type: Array, required: true },
})
</script>
