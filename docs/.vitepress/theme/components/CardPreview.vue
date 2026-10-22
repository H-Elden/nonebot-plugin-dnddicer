<template>
  <section id="cb-preview" class="cb-preview-section">
    <div class="cb-preview__head">
      <span class="cb-preview__title">角色卡预览</span>
      <HintDot text="与骰娘生成的角色卡图使用同一套版式；浏览器字体可能有细微差异，最终以骰娘出图为准。" />
      <button
        v-if="ready"
        type="button"
        class="cb-btn cb-btn--ghost cb-btn--small"
        @click="openFullscreen"
      >全屏预览</button>
    </div>

    <p v-if="!ready" class="cb-muted">填好等级与六属性后显示预览。</p>
    <div
      v-else
      ref="wrapRef"
      class="cb-preview-frame"
      :style="{ height: `${wrapHeight}px` }"
    >
      <iframe
        ref="frameRef"
        class="cb-preview__iframe"
        :style="{ transform: `scale(${scale})`, height: `${contentHeight}px` }"
        :srcdoc="debouncedHtml"
        title="角色卡预览"
        @load="measure"
      ></iframe>
    </div>

    <Teleport to="body">
      <div v-if="fullscreen" class="cb-modal" @click.self="closeFullscreen">
        <div class="cb-modal__panel">
          <div class="cb-modal__bar">
            <span>角色卡预览</span>
            <button type="button" class="cb-btn cb-btn--ghost cb-btn--small" @click="closeFullscreen">
              关闭
            </button>
          </div>
          <div class="cb-modal__scroll">
            <div
              class="cb-modal__frame"
              :style="{ width: `${940 * fullScale}px`, height: `${fullHeight}px` }"
            >
              <iframe
                ref="fullFrameRef"
                class="cb-modal__iframe"
                :style="{ transform: `scale(${fullScale})`, height: `${fullHeight / fullScale}px` }"
                :srcdoc="debouncedHtml"
                title="角色卡全屏预览"
                @load="measureFull"
              ></iframe>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<script setup>
import {
  computed,
  nextTick,
  onBeforeUnmount,
  ref,
  watch,
} from 'vue'

import cardCss from '../card-builder/char-card.css?raw'
import { buildPreviewView, renderPreviewHtml } from '../card-builder/preview.mjs'
import {
  builder,
  portraitDataUrl,
  queryOptions,
  state,
} from '../card-builder/store.mjs'
import HintDot from './card-builder/HintDot.vue'

const CARD_WIDTH = 940

const wrapRef = ref(null)
const frameRef = ref(null)
const fullFrameRef = ref(null)
const contentHeight = ref(600)
const wrapHeight = ref(380)
const scale = ref(0.55)
const fullscreen = ref(false)
const fullScale = ref(0.8)
const fullHeight = ref(600)
const debouncedHtml = ref('')
let timer = null
let observer = null

const ready = computed(() => {
  const level = String(state['$等级$'] || '').trim()
  if (!/^\d+$/.test(level) || Number(level) <= 0) return false
  const scores = state['$属性$'] || []
  return (
    scores.length === 6 &&
    scores.every((value) => /^\d+$/.test(String(value || '').trim()))
  )
})

const html = computed(() =>
  renderPreviewHtml(
    buildPreviewView(builder, state, queryOptions.value, portraitDataUrl.value),
    cardCss,
  ),
)

watch(
  html,
  (value) => {
    if (!value) return
    if (timer) clearTimeout(timer)
    timer = setTimeout(() => {
      debouncedHtml.value = value
      nextTick(() => {
        setTimeout(() => {
          measure()
          if (fullscreen.value) measureFull()
        }, 60)
      })
    }, 200)
  },
  { immediate: true },
)

function measure() {
  const frame = frameRef.value
  const wrap = wrapRef.value
  if (!frame || !wrap) return
  try {
    const doc = frame.contentDocument
    if (doc) {
      const height = Math.max(
        doc.documentElement.scrollHeight,
        doc.body ? doc.body.scrollHeight : 0,
      )
      if (height > 0) contentHeight.value = height
    }
  } catch {
    // 取不到高度时保留上一次值
  }
  const width = wrap.clientWidth || 0
  if (width > 0) scale.value = Math.min(1, width / CARD_WIDTH)
  wrapHeight.value = Math.max(120, contentHeight.value * scale.value)
}

function measureFull() {
  const frame = fullFrameRef.value
  if (!frame) return
  try {
    const doc = frame.contentDocument
    if (doc) {
      const height = Math.max(
        doc.documentElement.scrollHeight,
        doc.body ? doc.body.scrollHeight : 0,
      )
      if (height > 0) fullHeight.value = height
    }
  } catch {
    // 保留上一次值
  }
  const available = Math.max(320, window.innerWidth - 48)
  fullScale.value = Math.min(1, available / CARD_WIDTH)
}

function openFullscreen() {
  fullscreen.value = true
  if (typeof document !== 'undefined') document.body.classList.add('cb-modal-open')
  nextTick(() => {
    setTimeout(measureFull, 80)
  })
}

function closeFullscreen() {
  fullscreen.value = false
  if (typeof document !== 'undefined') document.body.classList.remove('cb-modal-open')
}

function onKeydown(event) {
  if (event.key === 'Escape' && fullscreen.value) closeFullscreen()
}

function onResize() {
  measure()
  if (fullscreen.value) measureFull()
}

if (typeof window !== 'undefined') {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', onResize)
}

watch(wrapRef, (element) => {
  if (observer) observer.disconnect()
  if (typeof ResizeObserver === 'undefined' || !element) return
  observer = new ResizeObserver(() => measure())
  observer.observe(element)
})

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
  if (observer) observer.disconnect()
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', onKeydown)
    window.removeEventListener('resize', onResize)
    document.body.classList.remove('cb-modal-open')
  }
})
</script>
