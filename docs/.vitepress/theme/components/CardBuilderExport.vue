<template>
  <section id="cb-export" class="cb-export">
    <div class="cb-export__head">
      <h3 class="cb-export__title">导出命令</h3>
      <HintDot text="整卡内容较长时会自动拆成多段：第 1 部分用 .角色卡新建，后续部分用 .角色卡修改；请按顺序逐个复制。" />
      <span class="cb-export__status" :class="statusClass">{{ statusText }}</span>
    </div>

    <div class="cb-export__name">
      <label for="cb-card-name" class="cb-export__name-label">卡名</label>
      <input
        id="cb-card-name"
        v-model="cardName"
        class="cb-input"
        maxlength="20"
        placeholder="例如：矿坑"
        autocomplete="off"
      />
      <HintDot text="卡名是卡库里的标识，最多 20 字，不能包含空格、$、@；重名会被骰娘拒绝。" />
      <span v-if="cardNameError" class="cb-export__name-error">{{ cardNameError }}</span>
    </div>

    <ul v-if="validation.errors.length" class="cb-errors cb-errors--list">
      <li v-for="(error, index) in validation.errors" :key="index">
        <button type="button" class="cb-link" @click="reveal(error.key)">{{ error.label }}</button>
        ：{{ error.message }}
      </li>
    </ul>
    <ul v-if="validation.warnings.length" class="cb-warnings">
      <li v-for="(warning, index) in validation.warnings" :key="index">
        {{ warning.label }}：{{ warning.message }}
      </li>
    </ul>

    <div v-if="isSingle" class="cb-export__block">
      <div class="cb-inline cb-inline--top">
        <CopyButton
          :text="singlePart.text"
          label="复制整卡命令"
          :disabled="!canCopy"
          primary
        />
        <span class="cb-muted">{{ singlePart.length }} 字（含命令）</span>
      </div>
    </div>

    <div v-else-if="parts.length > 1" class="cb-export__block">
      <p class="cb-export__split">
        整卡命令 {{ wholeCommand.length }} 字，超过 4500 字，已自动拆成
        {{ parts.length }} 部分。请按顺序逐个复制发送。
      </p>
      <div class="cb-copy-parts">
        <CopyButton
          v-for="part in parts"
          :key="part.index"
          :text="part.text"
          :label="`${part.label}（${part.length} 字）`"
          :disabled="!canCopy"
        />
      </div>
      <p class="cb-inline-note">
        第 1 部分含姓名、等级与属性，先发它；后面的部分用 .角色卡修改 依次补充到同一张卡。
      </p>
    </div>

    <div v-else-if="tooLarge.length" class="cb-export__block">
      <p class="cb-errors">
        有段命令本身就超过 4500 字，无法自动拆分，请先精简：
        <span v-for="item in tooLarge" :key="item.key">{{ item.label }}（{{ item.length }} 字）</span>
      </p>
    </div>

    <div v-else class="cb-muted">还没有可导出的内容。</div>

    <details v-if="parts.length" class="cb-export__preview">
      <summary>查看命令文本</summary>
      <div v-for="part in parts" :key="part.index" class="cb-export__part">
        <div class="cb-export__part-label">{{ part.label }} · {{ part.length }} 字</div>
        <pre class="cb-preview">{{ part.text }}</pre>
      </div>
    </details>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import {
  canCopy,
  cardName,
  cardNameError,
  cardParts,
  validation,
  wholeCommand,
} from '../card-builder/store.mjs'
import CopyButton from './card-builder/CopyButton.vue'
import HintDot from './card-builder/HintDot.vue'

const parts = computed(() => cardParts.value.parts || [])
const tooLarge = computed(() => cardParts.value.tooLarge || [])
const isSingle = computed(
  () => parts.value.length === 1 && parts.value[0].label === '整卡',
)
const singlePart = computed(() => parts.value[0] || { text: '', length: 0 })

const statusClass = computed(() => {
  if (cardNameError.value || validation.value.errors.length > 0) {
    return 'cb-status--error'
  }
  if (validation.value.warnings.length > 0) return 'cb-status--warn'
  return 'cb-status--ok'
})
const statusText = computed(() => {
  const { errors, warnings } = validation.value
  if (cardNameError.value) return '请填写卡名'
  if (errors.length > 0) return `${errors.length} 处待修正`
  if (parts.value.length > 1) return `可以导出（拆成 ${parts.value.length} 部分）`
  if (warnings.length > 0) return `可以导出（${warnings.length} 条提醒）`
  return '可以导出'
})

function reveal(key) {
  if (!key) {
    document.getElementById('cb-export')?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
    return
  }
  document
    .querySelector(`[data-seg-key="${key}"]`)
    ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
</script>
