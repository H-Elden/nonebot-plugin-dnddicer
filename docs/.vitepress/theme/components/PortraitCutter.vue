<template>
  <div
    class="pc"
    @dragover.prevent="dragging = true"
    @dragleave="dragging = false"
    @drop.prevent="onDrop"
  >
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
      <span v-else class="cb-muted">PNG / JPG / WebP，图片只在浏览器本地处理</span>
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
        <p class="cb-hint">
          拖动图片调整取景，滚轮或滑块缩放；导出固定 512×512 PNG，方框即最终卡面比例。
        </p>

        <div class="pc-preview-block">
          <div class="pc-preview">
            <img v-if="previewUrl" :src="previewUrl" alt="角色卡立绘 146×146 预览" />
          </div>
          <div class="pc-preview-info">
            <div class="pc-preview__label">卡面 146×146 预览</div>
            <div class="cb-inline">
              <button
                type="button"
                class="cb-btn cb-btn--primary"
                :disabled="!previewReady"
                @click="copyImage"
              >复制图片</button>
              <button
                type="button"
                class="cb-btn cb-btn--ghost"
                :disabled="!previewReady"
                @click="download"
              >下载 PNG</button>
            </div>
            <p v-if="status" class="pc-status" role="status">{{ status }}</p>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="pc-empty">
      选择一张角色图开始裁切。建议用正面或半身构图；当前角色卡立绘框是 1:1 方框，非方图会被拉伸。
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref } from 'vue'

// 立绘裁切：浏览器本地 canvas 处理，固定 1:1、导出 512×512 PNG。
// 当前卡面立绘框是 146×146 方框，非方图会被插件原样拉伸，所以这里只做方图。
const STAGE = 320
const OUTPUT = 512
const MAX_INPUT_BYTES = 20 * 1024 * 1024
const ALLOWED_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp'])

const canvasRef = ref(null)
const hasImage = ref(false)
const previewReady = ref(false)
const previewUrl = ref('')
const zoom = ref(1)
const fileName = ref('')
const imageSize = ref('')
const error = ref('')
const status = ref('')
const dragging = ref(false)

let imageEl = null
let imageW = 0
let imageH = 0
let offsetX = 0
let offsetY = 0
let dragState = null
let inputUrl = ''
let previewBlob = null
let previewTimer = null

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
  out.toBlob((blob) => {
    if (!blob) return
    previewBlob = blob
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
    previewReady.value = true
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

async function copyBySelection() {
  if (!previewUrl.value) return false
  const holder = document.createElement('div')
  holder.contentEditable = 'true'
  holder.style.position = 'fixed'
  holder.style.left = '-9999px'
  holder.style.top = '0'
  const image = document.createElement('img')
  image.src = previewUrl.value
  holder.appendChild(image)
  document.body.appendChild(holder)
  try {
    if (image.decode) await image.decode()
  } catch {
    // 解码失败时仍尝试复制，失败会走下载兜底
  }
  const range = document.createRange()
  range.selectNodeContents(holder)
  const selection = window.getSelection()
  selection.removeAllRanges()
  selection.addRange(range)
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  selection.removeAllRanges()
  document.body.removeChild(holder)
  return ok
}

async function copyImage() {
  if (!previewBlob) return
  status.value = '正在复制…'
  try {
    if (
      navigator.clipboard &&
      typeof ClipboardItem !== 'undefined' &&
      navigator.clipboard.write
    ) {
      await navigator.clipboard.write([
        new ClipboardItem({ 'image/png': previewBlob }),
      ])
      status.value =
        '已复制图片。到群里粘贴图片，并在同一条消息里附上 .立绘 后发送。'
      return
    }
  } catch {
    // 剪贴板权限不足或浏览器不支持，继续降级
  }
  if (await copyBySelection()) {
    status.value =
      '已复制图片（兼容模式）。到群里粘贴图片，并在同一条消息里附上 .立绘 后发送。'
    return
  }
  download()
  status.value =
    '浏览器不允许复制图片，已改为下载 PNG；在 QQ 里选这张图发送并附上 .立绘。'
}

function download() {
  if (!previewUrl.value) return
  const link = document.createElement('a')
  link.href = previewUrl.value
  link.download = 'dnddicer-portrait-512.png'
  document.body.appendChild(link)
  link.click()
  link.remove()
  status.value = '已下载 PNG；发送图片并在同一条消息里附上 .立绘。'
}

onBeforeUnmount(() => {
  if (previewTimer) clearTimeout(previewTimer)
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  if (inputUrl) URL.revokeObjectURL(inputUrl)
})
</script>
