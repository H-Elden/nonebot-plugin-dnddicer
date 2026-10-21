<template>
  <RepeaterRows
    :items="state[K.FEATURE]"
    :max="limits.feature_max_count || 20"
    add-label="添加能力"
    :factory="factory"
  >
    <template #default="{ item }">
      <div class="cb-grid cb-grid--3">
        <label class="cb-grid__cell">
          <span class="cb-grid__label">名称</span>
          <input v-model="item.name" class="cb-input" placeholder="奥术回想" />
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">当前次数</span>
          <input v-model="item.cur" class="cb-input" inputmode="numeric" placeholder="1" />
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">次数上限</span>
          <input v-model="item.max" class="cb-input" inputmode="numeric" placeholder="1" />
        </label>
      </div>
      <div class="cb-recover">
        <span class="cb-grid__label">恢复方式</span>
        <span v-for="mode in modes" :key="mode" class="cb-recover__mode">
          <label class="cb-check">
            <input
              type="checkbox"
              :checked="item.modes[mode].on"
              @change="toggle(item, mode)"
            />
            {{ mode }}
          </label>
          <input
            v-if="item.modes[mode].on && mode !== '手动'"
            v-model="item.modes[mode].amount"
            class="cb-input cb-input--tiny"
            placeholder="满"
            :aria-label="`${mode}恢复量`"
            title="留空 = 回满；填数字表示恢复 N 次"
          />
        </span>
      </div>
      <label class="cb-grid__cell">
        <span class="cb-grid__label">说明（只用于卡面）</span>
        <input v-model="item.text" class="cb-input" placeholder="短休时回复一个已消耗的法术位" />
      </label>
    </template>
  </RepeaterRows>
  <p class="cb-hint">
    恢复档可多选；「两者」已含短休与长休，勾选它会自动取消另两项。恢复量留空表示回满。
  </p>
</template>

<script setup>
import { computed } from 'vue'
import { K } from '../../card-builder/core.mjs'
import RepeaterRows from './RepeaterRows.vue'

// $能力$：有使用次数的能力，恢复档四选（短休/长休/两者/手动）与可选恢复量。
const props = defineProps({
  state: { type: Object, required: true },
  enums: { type: Object, required: true },
  limits: { type: Object, required: true },
})

const modes = computed(() => props.enums.recover_modes || [])

function factory() {
  const values = {}
  for (const mode of modes.value) values[mode] = { on: false, amount: '' }
  return { name: '', cur: '', max: '', modes: values, text: '' }
}

function toggle(item, mode) {
  const target = item.modes[mode]
  target.on = !target.on
  if (!target.on) return
  if (mode === '两者') {
    item.modes['短休'].on = false
    item.modes['长休'].on = false
  } else if (mode === '短休' || mode === '长休') {
    item.modes['两者'].on = false
  }
}
</script>
