<template>
  <button
    type="button"
    class="cb-btn"
    :class="primary ? 'cb-btn--primary' : 'cb-btn--ghost'"
    :disabled="disabled || !text"
    :title="title"
    @click="copy"
  >{{ status === 'ok' ? '已复制' : status === 'fail' ? '复制失败' : label }}</button>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'

// 复制按钮：优先 Clipboard API（两站均为 HTTPS），失败退回 execCommand，
// 两者都失败时按钮显示「复制失败」，用户可手动从预览框选中复制。
const props = defineProps({
  text: { type: String, default: '' },
  label: { type: String, default: '复制' },
  disabled: { type: Boolean, default: false },
  primary: { type: Boolean, default: false },
  title: { type: String, default: '' },
})

const status = ref('')
let timer = null

async function copy() {
  if (props.disabled || !props.text) return
  let ok = false
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(props.text)
      ok = true
    }
  } catch {
    ok = false
  }
  if (!ok) {
    const area = document.createElement('textarea')
    area.value = props.text
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.top = '-1000px'
    area.style.opacity = '0'
    document.body.appendChild(area)
    area.select()
    try {
      ok = document.execCommand('copy')
    } catch {
      ok = false
    }
    document.body.removeChild(area)
  }
  status.value = ok ? 'ok' : 'fail'
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    status.value = ''
  }, 2000)
}

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>
