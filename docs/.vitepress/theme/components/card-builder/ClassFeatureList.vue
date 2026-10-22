<template>
  <RepeaterRows
    :items="state[K.CLASS_TRAITS]"
    :max="limits.class_feature_max_count || 30"
    add-label="添加职业特性"
    :factory="factory"
  >
    <template #default="{ item }">
      <div class="cb-grid cb-grid--4">
        <label class="cb-grid__cell">
          <span class="cb-grid__label">获得等级</span>
          <input
            v-model="item.level"
            class="cb-input"
            inputmode="numeric"
            placeholder="1"
          />
        </label>
        <label class="cb-grid__cell cb-grid__cell--span2">
          <span class="cb-grid__label">名称</span>
          <input v-model="item.name" class="cb-input" placeholder="仪式学家" />
        </label>
      </div>
      <label class="cb-grid__cell">
        <span class="cb-grid__label">说明（可选，只用于卡面）</span>
        <input
          v-model="item.text"
          class="cb-input"
          :placeholder="`法术书中的仪式法术可直接以仪式施展（≤${limits.class_feature_text_max_len || 80} 字）`"
        />
      </label>
    </template>
  </RepeaterRows>
  <p class="cb-hint">
    卡面按获得等级升序显示，每条带「N级」徽标。有使用次数的职业特性同时写进「限定资源」，一处记说明、一处记次数。
  </p>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'
import RepeaterRows from './RepeaterRows.vue'

// $职业特性$：获得等级 + 名称 + 说明。
defineProps({
  state: { type: Object, required: true },
  limits: { type: Object, required: true },
})

function factory() {
  return { level: '1', name: '', text: '' }
}
</script>
