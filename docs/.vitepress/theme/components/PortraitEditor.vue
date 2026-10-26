<template>
  <div
    class="pc pc--embedded"
    @dragover.prevent="dragging = true"
    @dragleave="dragging = false"
    @drop.prevent="onDrop"
  >
    <div class="pc-title">
      立绘裁切
      <HintDot text="图片只在浏览器本地处理，不会上传；裁成 1:1 方框、填好卡名后复制命令，到聊天框粘贴发送。" />
    </div>

    <div class="pc-name-row">
      <label class="pc-name">
        <span>卡名</span>
        <input
          v-model="cardName"
          class="cb-input cb-input--short"
          maxlength="20"
          placeholder="例如：矿坑"
          autocomplete="off"
        />
      </label>
    </div>

    <div class="pc-toolbar">
      <label class="cb-btn cb-btn--ghost pc-file">
        选择图片
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          @change="onFileChange"
        />
      </label>
      <span v-if="fileName" class="pc-filename">
        {{ fileName }}<template v-if="imageSize"> · {{ imageSize }}</template>
      </span>
      <span v-else class="cb-muted">PNG / JPG / WebP</span>
      <button
        v-if="hasImage"
        type="button"
        class="cb-btn cb-btn--ghost cb-btn--small"
        @click="clearImage"
      >清除立绘</button>
    </div>

    <p v-if="error" class="cb-errors pc-error">{{ error }}</p>

    <div v-if="hasImage" class="pc-layout">
      <div class="pc-stage" :class="{ 'pc-stage--dragging': dragging }" @wheel.prevent="onWheel">
        <canvas
          ref="canvasRef"
          class="pc-canvas"
          aria-label="立绘裁切画布，拖动调整取景"
          @pointerdown="onPointerDown"
          @pointermove="onPointerMove"
          @pointerup="onPointerUp"
          @pointercancel="onPointerUp"
        ></canvas>
        <div class="pc-frame" aria-hidden="true"></div>
      </div>

      <div class="pc-side">
        <div class="pc-controls">
          <label class="pc-zoom">
            <span>缩放</span>
            <input
              type="range"
              min="1"
              max="4"
              step="0.01"
              :value="zoom"
              @input="onZoomInput"
            />
          </label>
          <button type="button" class="cb-btn cb-btn--ghost cb-btn--small" @click="resetView">
            居中
          </button>
        </div>

        <div class="pc-preview-block">
          <div class="pc-preview">
            <img v-if="previewUrl" :src="previewUrl" alt="角色卡立绘 146×146 预览" />
          </div>
          <div class="pc-preview-info">
            <div class="cb-inline">
              <button
                type="button"
                class="cb-btn cb-btn--primary"
                :disabled="!canCopyCommand"
                :title="cardNameError ? '请先在页面顶部填写有效卡名' : '复制命令与图片，到聊天框粘贴发送'"
                @click="copyCommand"
              >复制命令</button>
              <button
                type="button"
                class="cb-btn cb-btn--ghost"
                :disabled="!previewReady"
                @click="download"
              >下载 PNG</button>
              <button
                type="button"
                class="cb-btn cb-btn--ghost"
                :disabled="!canCopyText"
                :title="cardNameError ? '请先在页面顶部填写有效卡名' : '只复制 .立绘 命令文字'"
                @click="copyTextOnly"
              >复制文字</button>
              <button
                type="button"
                class="cb-btn cb-btn--ghost"
                :disabled="!previewReady"
                @click="copyImage"
              >复制图片</button>
            </div>
          </div>
        </div>
        <p v-if="status" class="pc-status" role="status">{{ status }}</p>
        <p v-else-if="cardNameError" class="pc-status">填写有效卡名后可复制命令或文字。</p>
      </div>
    </div>

    <div v-else class="pc-empty">
      选择一张角色图开始裁切
      <HintDot text="建议用正面或半身构图；立绘框是 1:1，非方图会被拉伸。导出为 512×512 PNG，骰娘按这张图原样保存。" />
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { cardName, cardNameError, setPortrait } from '../card-builder/store.mjs'
import HintDot from './card-builder/HintDot.vue'

// 立绘裁切：浏览器本地 canvas 处理，固定 1:1、导出 512×512 PNG。
// 作为建卡器的一部分，裁切结果直接写入共享状态，供角色卡预览使用。
const STAGE = 320
const OUTPUT = 512
const MAX_INPUT_BYTES = 20 * 1024 * 1024
const ALLOWED_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp'])

const canvasRef = ref(null)
const hasImage = ref(false)
const previewReady = ref(false)
const previewUrl = ref('')
const previewDataUrl = ref('')
const zoom = ref(1)
const fileName = ref('')
const imageSize = ref('')
const error = ref('')
const status = ref('')
const dragging = ref(false)
//: 复制到剪贴板的命令文本（卡名来自页面顶部的卡名输入框）
const command = computed(() => {
  const name = cardName.value.trim()
  return name ? `.立绘 ${name}` : ''
})
//: 立绘已裁好、卡名合法时才允许复制命令
const canCopyCommand = computed(
  () => previewReady.value && !cardNameError.value && Boolean(command.value),
)
//: 只复制命令文字时不需要图片，但同样需要合法卡名
const canCopyText = computed(
  () => !cardNameError.value && Boolean(command.value),
)

let imageEl = null
let imageW = 0
let imageH = 0
let offsetX = 0
let offsetY = 0
let dragState = null
let inputUrl = ''
let previewBlob = null
let previewTimer = null

function emitPortrait() {
  setPortrait(previewDataUrl.value || '')
}

function baseScale() {
  return Math.max(STAGE / imageW, STAGE / imageH)
}

function clampOffsets() {
  const scale = baseScale() * zoom.value
  const maxX = Math.max(0, (imageW * scale - STAGE) / 2)
  const maxY = Math.max(0, (imageH * scale - STAGE) / 2)
  offsetX = Math.min(maxX, Math.max(-maxX, offsetX))
  offsetY = Math.min(maxY, Math.max(-maxY, offsetY))
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas || !imageEl) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const pixels = Math.round(STAGE * dpr)
  if (canvas.width !== pixels || canvas.height !== pixels) {
    canvas.width = pixels
    canvas.height = pixels
  }
  const ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, STAGE, STAGE)
  const scale = baseScale() * zoom.value
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(
    imageEl,
    STAGE / 2 - (imageW * scale) / 2 + offsetX,
    STAGE / 2 - (imageH * scale) / 2 + offsetY,
    imageW * scale,
    imageH * scale,
  )
}

function schedulePreview() {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(renderPreview, 120)
}

function renderPreview() {
  if (!imageEl) return
  const out = document.createElement('canvas')
  out.width = OUTPUT
  out.height = OUTPUT
  const ctx = out.getContext('2d')
  const factor = OUTPUT / STAGE
  const scale = baseScale() * zoom.value
  ctx.imageSmoothingEnabled = true
  ctx.imageSmoothingQuality = 'high'
  ctx.drawImage(
    imageEl,
    (STAGE / 2 - (imageW * scale) / 2 + offsetX) * factor,
    (STAGE / 2 - (imageH * scale) / 2 + offsetY) * factor,
    imageW * scale * factor,
    imageH * scale * factor,
  )
  previewDataUrl.value = out.toDataURL('image/png')
  out.toBlob((blob) => {
    if (!blob) return
    previewBlob = blob
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
    previewReady.value = true
    emitPortrait()
  }, 'image/png')
}

function setZoom(value) {
  zoom.value = Math.min(4, Math.max(1, value))
  clampOffsets()
  draw()
  schedulePreview()
}

function resetView() {
  zoom.value = 1
  offsetX = 0
  offsetY = 0
  draw()
  schedulePreview()
}

function loadFile(file) {
  error.value = ''
  status.value = ''
  if (!file) return
  if (!ALLOWED_TYPES.has(file.type) && !/\.(png|jpe?g|webp)$/i.test(file.name)) {
    error.value = '只支持 PNG / JPG / WebP 图片，请换一张'
    return
  }
  if (file.size > MAX_INPUT_BYTES) {
    error.value = '图片超过 20 MB，请先压缩后再试'
    return
  }
  fileName.value = file.name
  imageSize.value = `${Math.round(file.size / 1024)} KB`
  if (inputUrl) URL.revokeObjectURL(inputUrl)
  inputUrl = URL.createObjectURL(file)
  const image = new Image()
  image.onload = () => {
    imageEl = image
    imageW = image.naturalWidth
    imageH = image.naturalHeight
    imageSize.value = `${imageW}×${imageH} · ${imageSize.value}`
    hasImage.value = true
    previewReady.value = false
    previewDataUrl.value = ''
    zoom.value = 1
    offsetX = 0
    offsetY = 0
    nextTick(() => {
      draw()
      schedulePreview()
    })
  }
  image.onerror = () => {
    error.value = '图片读取失败，请换一张试试'
  }
  image.src = inputUrl
}

function onFileChange(event) {
  loadFile(event.target.files ? event.target.files[0] : null)
  // 允许再次选择同一文件
  event.target.value = ''
}

function onDrop(event) {
  dragging.value = false
  const file = event.dataTransfer && event.dataTransfer.files
    ? event.dataTransfer.files[0]
    : null
  loadFile(file)
}

function onZoomInput(event) {
  setZoom(Number(event.target.value))
}

function onWheel(event) {
  setZoom(zoom.value * Math.exp(-event.deltaY * 0.0015))
}

function onPointerDown(event) {
  if (!imageEl) return
  event.preventDefault()
  dragState = { id: event.pointerId, x: event.clientX, y: event.clientY }
  if (canvasRef.value && canvasRef.value.setPointerCapture) {
    canvasRef.value.setPointerCapture(event.pointerId)
  }
}

function onPointerMove(event) {
  if (!dragState || event.pointerId !== dragState.id) return
  const rect = canvasRef.value.getBoundingClientRect()
  if (!rect.width) return
  const ratio = STAGE / rect.width
  offsetX += (event.clientX - dragState.x) * ratio
  offsetY += (event.clientY - dragState.y) * ratio
  dragState.x = event.clientX
  dragState.y = event.clientY
  clampOffsets()
  draw()
}

function onPointerUp(event) {
  if (!dragState) return
  dragState = null
  if (canvasRef.value && canvasRef.value.releasePointerCapture) {
    canvasRef.value.releasePointerCapture(event.pointerId)
  }
  schedulePreview()
}

function clearImage() {
  hasImage.value = false
  previewReady.value = false
  previewDataUrl.value = ''
  previewBlob = null
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  if (inputUrl) URL.revokeObjectURL(inputUrl)
  inputUrl = ''
  imageEl = null
  fileName.value = ''
  imageSize.value = ''
  status.value = ''
  error.value = ''
  emitPortrait()
}

async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // 剪贴板权限不足或浏览器不支持，继续降级
  }
  const area = document.createElement('textarea')
  area.value = text
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.top = '-1000px'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(area)
  return ok
}

async function copyCommand() {
  if (!previewBlob || cardNameError.value) return
  const text = command.value
  if (!text) return
  status.value = '正在复制…'
  // 文本与图片写入同一剪贴板：QQ 粘贴时可同时得到命令和图片。
  try {
    if (
      navigator.clipboard &&
      window.isSecureContext &&
      typeof ClipboardItem !== 'undefined' &&
      navigator.clipboard.write
    ) {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/plain': new Blob([text], { type: 'text/plain' }),
          'image/png': previewBlob,
        }),
      ])
      status.value = `已复制 ${text} 和图片。到聊天框直接粘贴发送即可。`
      return
    }
  } catch {
    // 浏览器不支持多格式剪贴板或权限不足，退回只复制命令
  }
  if (await copyText(text)) {
    status.value = `已复制 ${text}（浏览器未能同时复制图片）。请用「下载 PNG」把图片和命令放在同一条消息里发送。`
    return
  }
  status.value = `复制失败，请手动输入 ${text} 并附上图片。`
}

async function copyTextOnly() {
  const text = command.value
  if (!text || cardNameError.value) return
  status.value = '正在复制…'
  if (await copyText(text)) {
    status.value = `已复制 ${text}。到聊天框粘贴后，把裁好的图片一起发送。`
    return
  }
  status.value = `复制失败，请手动输入 ${text} 并附上图片。`
}

async function copyImage() {
  if (!previewBlob) return
  status.value = '正在复制…'
  try {
    if (
      navigator.clipboard &&
      window.isSecureContext &&
      typeof ClipboardItem !== 'undefined' &&
      navigator.clipboard.write
    ) {
      await navigator.clipboard.write([
        new ClipboardItem({ 'image/png': previewBlob }),
      ])
      status.value = command.value
        ? `已复制图片（512×512）。到聊天框粘贴图片，并在同一条消息里附上 ${command.value} 后发送。`
        : '已复制图片（512×512）。到聊天框粘贴图片，并在同一条消息里附上 .立绘 命令。'
      return
    }
  } catch {
    // 浏览器不支持图片剪贴板或权限不足，退回下载
  }
  download()
  status.value = '浏览器不允许复制图片，已改为下载 PNG；发送时把图片和 .立绘 命令放在同一条消息里。'
}

function download() {
  if (!previewUrl.value) return
  const link = document.createElement('a')
  link.href = previewUrl.value
  link.download = 'dnddicer-portrait-512.png'
  document.body.appendChild(link)
  link.click()
  link.remove()
  status.value = command.value
    ? `已下载 PNG；发送时把它和 ${command.value} 放在同一条消息里。`
    : '已下载 PNG；发送时在图片消息里附上 .立绘 命令。'
}

onBeforeUnmount(() => {
  if (previewTimer) clearTimeout(previewTimer)
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  if (inputUrl) URL.revokeObjectURL(inputUrl)
})
</script>
