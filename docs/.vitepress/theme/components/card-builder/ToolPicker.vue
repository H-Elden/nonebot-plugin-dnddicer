<template>
  <span class="cb-tool-picker">
    <button
      ref="trigger"
      type="button"
      class="cb-btn cb-btn--ghost cb-btn--small"
      aria-haspopup="dialog"
      :aria-expanded="open ? 'true' : 'false'"
      @click="toggle"
    >添加工具…</button>
    <Teleport to="body">
      <div
        v-if="open"
        ref="panel"
        class="cb-tool-pop"
        role="dialog"
        aria-label="选择工具熟练"
        :style="panelStyle"
        @click.stop
      >
        <div class="cb-tool-pop__head">
          <input
            ref="searchInput"
            v-model="query"
            class="cb-input"
            placeholder="搜索工具"
            aria-label="搜索工具"
            @keydown.esc.prevent="close"
          />
          <button type="button" class="cb-btn cb-btn--ghost cb-btn--small" @click="close">
            收起
          </button>
        </div>
        <div class="cb-tool-pop__list">
          <ToggleChip
            v-for="name in filtered"
            :key="name"
            :active="selected.includes(name)"
            @toggle="$emit('toggle', name)"
          >{{ name }}</ToggleChip>
          <p v-if="filtered.length === 0" class="cb-muted">没有匹配的工具</p>
        </div>
      </div>
    </Teleport>
  </span>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import ToggleChip from './ToggleChip.vue'

// 工具选择浮层：替代原生 select，支持搜索、连续点选与已选状态。
const props = defineProps({
  options: { type: Array, default: () => [] },
  selected: { type: Array, default: () => [] },
})
defineEmits(['toggle'])

const trigger = ref(null)
const panel = ref(null)
const searchInput = ref(null)
const open = ref(false)
const query = ref('')
const panelStyle = reactive({ top: '0px', left: '0px', width: '320px' })

const filtered = computed(() => {
  const keyword = query.value.trim()
  if (!keyword) return props.options
  return props.options.filter((name) => name.includes(keyword))
})

function position() {
  const el = trigger.value
  const box = panel.value
  if (!el || !box) return
  const rect = el.getBoundingClientRect()
  const width = Math.min(360, window.innerWidth - 24)
  const margin = 12
  let left = Math.min(
    Math.max(margin, rect.left),
    window.innerWidth - width - margin,
  )
  let top = rect.bottom + 6
  if (top + box.offsetHeight > window.innerHeight - margin) {
    top = Math.max(margin, rect.top - box.offsetHeight - 6)
  }
  panelStyle.left = `${Math.round(left)}px`
  panelStyle.top = `${Math.round(top)}px`
  panelStyle.width = `${Math.round(width)}px`
}

async function toggle() {
  open.value = !open.value
  if (!open.value) return
  query.value = ''
  await nextTick()
  position()
  searchInput.value?.focus()
}

function close() {
  open.value = false
}

function onPointerDown(event) {
  if (!open.value) return
  if (trigger.value?.contains(event.target)) return
  if (panel.value?.contains(event.target)) return
  close()
}

function onKeydown(event) {
  if (event.key === 'Escape') close()
}

watch(open, (value) => {
  if (typeof window === 'undefined') return
  if (value) {
    window.addEventListener('pointerdown', onPointerDown, true)
    window.addEventListener('keydown', onKeydown)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', close, true)
  } else {
    window.removeEventListener('pointerdown', onPointerDown, true)
    window.removeEventListener('keydown', onKeydown)
    window.removeEventListener('resize', close)
    window.removeEventListener('scroll', close, true)
  }
})

onBeforeUnmount(() => {
  if (typeof window === 'undefined') return
  window.removeEventListener('pointerdown', onPointerDown, true)
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', close)
  window.removeEventListener('scroll', close, true)
})
</script>
