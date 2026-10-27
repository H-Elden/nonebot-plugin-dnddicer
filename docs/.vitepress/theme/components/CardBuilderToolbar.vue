<template>
  <div class="cb-toolbar-wrap">
    <div class="cb-rules">
      <span class="cb-rules__label">规则版本</span>
      <div class="cb-rules__switch">
        <button
          type="button"
          class="cb-rules__btn"
          :class="{ 'cb-rules__btn--active': rulesVersion === '5r' }"
          @click="rulesVersion = '5r'"
        >5r（2024）</button>
        <button
          type="button"
          class="cb-rules__btn"
          :class="{ 'cb-rules__btn--active': rulesVersion === '5e' }"
          @click="rulesVersion = '5e'"
        >5e（2014）</button>
      </div>
      <HintDot text="只影响建卡器显示的字段与子职门槛，不改变群内已经生效的规则版本。" />
    </div>

    <div class="cb-toolbar">
      <label class="cb-inline">
        <span class="cb-rules__label">卡名</span>
        <input
          v-model="cardName"
          class="cb-input cb-input--short"
          maxlength="20"
          placeholder="例如：矿坑"
          autocomplete="off"
        />
      </label>
      <HintDot text="卡名是卡库里的标识，最多 20 字，不能包含空格、$、@；群聊新建会自动绑定本群。" />
      <button type="button" class="cb-btn cb-btn--ghost" @click="loadExample">载入示例卡</button>
      <button type="button" class="cb-btn cb-btn--ghost" @click="importOpen = !importOpen">
        导入卡文本
      </button>
      <button type="button" class="cb-btn cb-btn--ghost" @click="clearAll">清空</button>
      <span class="cb-status" :class="statusClass">{{ statusText }}</span>
      <a class="cb-btn cb-btn--ghost" href="#角色卡预览">预览角色卡</a>
    </div>

    <p v-if="notice" class="cb-notice" :class="`cb-notice--${noticeKind}`">{{ notice }}</p>

    <section v-if="importOpen" class="cb-panel">
      <h3 class="cb-panel__title">
        导入卡文本
        <HintDot text="把骰娘发来的角色卡或 .角色卡新建 / .角色卡修改 命令整段粘贴进来；末尾提示会自动忽略，解析失败会指出是哪一段。导入会覆盖当前表单。" />
      </h3>
      <textarea
        v-model="importText"
        class="cb-textarea"
        rows="8"
        placeholder=".角色卡新建 伊瑟兰&#10;$姓名$ 伊瑟兰·晨星&#10;$等级$ 5&#10;$属性$ 8/14/16/18/11/8"
      ></textarea>
      <div class="cb-inline cb-inline--top">
        <button type="button" class="cb-btn cb-btn--primary" @click="doImport">解析并填入</button>
        <button type="button" class="cb-btn cb-btn--ghost" @click="importText = ''">清空文本框</button>
        <button type="button" class="cb-btn cb-btn--ghost" @click="importOpen = false">收起</button>
      </div>
      <ul v-if="importErrors.length" class="cb-errors">
        <li v-for="(error, index) in importErrors" :key="index">
          <strong>{{ error.label }}</strong>：{{ error.message }}
        </li>
      </ul>
      <ul v-if="importWarnings.length" class="cb-warnings">
        <li v-for="(warning, index) in importWarnings" :key="index">
          {{ warning.label }}：{{ warning.message }}
        </li>
      </ul>
    </section>

    <datalist id="cb-class-options">
      <option v-for="name in enums.classes" :key="name" :value="name" />
    </datalist>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { K } from '../card-builder/core.mjs'
import {
  builder,
  cardName,
  cardNameError,
  enums,
  resetState,
  rulesVersion,
  state,
  validation,
} from '../card-builder/store.mjs'
import HintDot from './card-builder/HintDot.vue'

const importOpen = ref(false)
const importText = ref('')
const importErrors = ref([])
const importWarnings = ref([])
const notice = ref('')
const noticeKind = ref('ok')
let noticeTimer = null

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
  if (warnings.length > 0) return `可以导出（${warnings.length} 条提醒）`
  return '可以导出'
})

function showNotice(message, kind = 'ok') {
  notice.value = message
  noticeKind.value = kind
  if (noticeTimer) clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => {
    notice.value = ''
  }, 4000)
}

onBeforeUnmount(() => {
  if (noticeTimer) clearTimeout(noticeTimer)
})

function loadExample() {
  rulesVersion.value = '5r'
  const previousName = state[K.NAME]
  const autoName = !cardName.value.trim() || cardName.value === previousName
  const parsed = builder.parseCardText(builder.buildExampleCard())
  if (parsed.errors.length > 0) {
    showNotice('示例卡载入失败，请反馈这个问题', 'error')
    return
  }
  Object.assign(state, parsed.state)
  // 卡名是卡库标识，示例卡固定用「矿坑」，不与卡内 $姓名$ 相同
  if (autoName) cardName.value = '矿坑'
  showNotice('已载入示例卡（5 级高等精灵法师），可以直接改；也可以从「导入卡文本」粘自己的卡。')
}

function doImport() {
  const previousName = state[K.NAME]
  const autoName = !cardName.value.trim() || cardName.value === previousName
  const result = builder.parseCardText(importText.value)
  importErrors.value = result.errors
  importWarnings.value = result.warnings
  if (result.errors.length > 0) {
    showNotice(`导入失败：${result.errors.length} 处需要修正`, 'error')
    return
  }
  Object.assign(state, result.state)
  rulesVersion.value = result.rulesVersion || '5r'
  if (autoName) cardName.value = result.state[K.NAME] || ''
  importOpen.value = false
  showNotice(`已导入 ${result.found} 个段`)
}

function clearAll() {
  if (
    typeof window !== 'undefined' &&
    !window.confirm('确定清空当前表单？已填写的内容不会保留。')
  ) {
    return
  }
  resetState()
  importErrors.value = []
  importWarnings.value = []
  showNotice('已清空')
}
</script>
