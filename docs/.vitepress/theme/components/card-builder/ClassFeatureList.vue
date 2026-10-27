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
          <span class="cb-grid__label">
            获得等级
            <HintDot text="卡面按等级排序；需要记录使用次数的特性，再到「限定资源」里填次数。" />
          </span>
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
      <div class="cb-grid__cell">
        <span class="cb-grid__label">说明（可选，只用于卡面）</span>
        <LongTextarea
          v-model="item.text"
          count-mode="paragraph"
          :max="limits.class_feature_text_max_len || 400"
          placeholder="法术书中的仪式法术可直接以仪式施展"
          aria-label="职业特性说明"
        />
      </div>
    </template>
  </RepeaterRows>
</template>

<script setup>
import { K } from '../../card-builder/core.mjs'
import HintDot from './HintDot.vue'
import LongTextarea from './LongTextarea.vue'
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
