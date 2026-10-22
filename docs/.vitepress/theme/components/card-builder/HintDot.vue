<template>
  <span class="cb-help-wrap">
    <button
      ref="trigger"
      type="button"
      class="cb-help"
      :aria-label="`说明：${text}`"
      :aria-expanded="visible ? 'true' : 'false'"
      @mouseenter="open"
      @mouseleave="close"
      @focus="open"
      @blur="close"
      @click.stop="toggle"
    >?</button>
    <Teleport to="body">
      <div
        v-if="visible"
        ref="bubble"
        class="cb-help__bubble"
        role="tooltip"
        :style="bubbleStyle"
      >{{ text }}</div>
    </Teleport>
  </span>
</template>

<script setup>
import { nextTick, onBeforeUnmount, reactive, ref } from 'vue'

// 圆圈问号：悬停 / 聚焦 / 点击显示说明气泡。
// 气泡 Teleport 到 body 并固定定位，避免被表格、面板或折叠容器裁切。
const props = defineProps({
  text: { type: String, required: true },
})

const trigger = ref(null)
const bubble = ref(null)
const visible = ref(false)
const bubbleStyle = reactive({ top: '0px', left: '0px' })

function position() {
  const el = trigger.value
  const tip = bubble.value
  if (!el || !tip) return
  const rect = el.getBoundingClientRect()
  const width = tip.offsetWidth || 280
  const margin = 8
  let left = rect.left + rect.width / 2 - width / 2
  left = Math.min(Math.max(margin, left), window.innerWidth - width - margin)
  let top = rect.bottom + 8
  if (top + tip.offsetHeight > window.innerHeight - margin) {
    top = Math.max(margin, rect.top - tip.offsetHeight - 8)
  }
  bubbleStyle.left = `${Math.round(left)}px`
  bubbleStyle.top = `${Math.round(top)}px`
}

async function open() {
  if (!props.text) return
  visible.value = true
  await nextTick()
  position()
}

function close() {
  visible.value = false
}

function toggle() {
  if (visible.value) close()
  else open()
}

function onKeydown(event) {
  if (event.key === 'Escape') close()
}

function onViewportChange() {
  if (visible.value) close()
}

if (typeof window !== 'undefined') {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('scroll', onViewportChange, true)
  window.addEventListener('resize', onViewportChange)
}

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', onKeydown)
    window.removeEventListener('scroll', onViewportChange, true)
    window.removeEventListener('resize', onViewportChange)
  }
})
</script>
