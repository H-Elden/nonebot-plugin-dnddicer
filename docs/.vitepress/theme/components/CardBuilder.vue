<template>
  <div class="cb">
    <p class="cb-intro">
      在浏览器里填写，内容不会上传；填完复制命令到群里发送。首次建卡先复制「整卡」，以后只改某一段时复制对应的分段命令。
      也可以把骰娘输出的卡整段粘进「导入卡文本」，表单会自动回填。
    </p>

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
      <span class="cb-rules__hint">
        只影响表单字段与子职门槛，不写入卡文本；群内结算请在群里用 <code>.规则版本</code> 设置。
      </span>
    </div>

    <div class="cb-toolbar">
      <button type="button" class="cb-btn cb-btn--ghost" @click="loadExample">载入示例卡</button>
      <button type="button" class="cb-btn cb-btn--ghost" @click="importOpen = !importOpen">
        导入卡文本
      </button>
      <button type="button" class="cb-btn cb-btn--ghost" @click="clearAll">清空</button>
      <span class="cb-toolbar__spacer"></span>
      <span class="cb-status" :class="statusClass">{{ statusText }}</span>
      <button type="button" class="cb-btn cb-btn--ghost" @click="scrollToExport">跳到导出</button>
    </div>

    <p v-if="notice" class="cb-notice" :class="`cb-notice--${noticeKind}`">{{ notice }}</p>

    <section v-if="importOpen" class="cb-panel">
      <h3 class="cb-panel__title">导入卡文本</h3>
      <p class="cb-hint">
        把 <code>.角色卡</code>、<code>.角色卡模板</code> 的回复整段粘进来，或粘一条 / 多条
        <code>.角色卡记录</code> 命令。模板末尾的提示文字会自动忽略；解析失败时会指出是哪一段。
        导入成功会覆盖当前表单，需要保留的内容请先复制命令。
      </p>
      <textarea
        v-model="importText"
        class="cb-textarea"
        rows="8"
        placeholder=".角色卡记录&#10;$姓名$ 伊瑟兰·晨星&#10;$等级$ 5&#10;$属性$ 8/14/16/18/11/8"
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

    <details
      v-for="group in groups"
      :key="group.id"
      class="cb-group"
      :open="openGroups[group.id]"
      @toggle="onToggle(group.id, $event)"
    >
      <summary class="cb-group__summary">
        <span class="cb-group__title">{{ group.label }}</span>
        <span class="cb-group__summary-text">{{ group.summary }}</span>
        <span class="cb-group__count">{{ groupCount(group) }}</span>
      </summary>
      <div class="cb-group__body">
        <BuilderField
          v-for="segment in group.segments"
          :key="segment.key"
          :label="segment.label"
          :summary="segment.summary"
          :segment-key="segment.key"
          :required="segment.required"
          :errors="errorsByKey[segment.key]"
        >
          <input
            v-if="kindOf(segment.key) === 'text'"
            v-model="state[segment.key]"
            class="cb-input"
            :placeholder="placeholder(segment)"
          />

          <input
            v-else-if="kindOf(segment.key) === 'class'"
            v-model="state[segment.key]"
            class="cb-input"
            list="cb-class-options"
            placeholder="法师（可手填扩展职业）"
          />

          <template v-else-if="kindOf(segment.key) === 'subclass'">
            <input
              v-if="subclassVisible"
              v-model="state[segment.key]"
              class="cb-input"
              placeholder="塑能师"
            />
            <p v-else class="cb-hint">
              当前等级还没有获得子职（{{ subclassRuleText }}），这里不需要填写。
            </p>
          </template>

          <template v-else-if="kindOf(segment.key) === 'longtext'">
            <textarea
              v-model="state[segment.key]"
              class="cb-textarea"
              rows="4"
              :placeholder="placeholder(segment)"
            ></textarea>
            <p class="cb-hint">
              {{ storyLength }} / {{ limits.story_max_len || 1000 }} 字（换行不计）；可多行、多段，换行会保留。
            </p>
          </template>

          <div v-else-if="kindOf(segment.key) === 'number'" class="cb-inline">
            <input
              v-model="state[segment.key]"
              class="cb-input cb-input--short"
              inputmode="numeric"
              placeholder="5"
            />
            <span class="cb-inline-note">
              熟练加值 {{ proficiencyBonus !== '' ? `+${proficiencyBonus}` : '—' }}
            </span>
          </div>

          <div v-else-if="kindOf(segment.key) === 'hp'" class="cb-grid cb-grid--3">
            <label class="cb-grid__cell">
              <span class="cb-grid__label">当前 HP</span>
              <input v-model="state[K.HP].cur" class="cb-input" inputmode="numeric" placeholder="29" />
            </label>
            <label class="cb-grid__cell">
              <span class="cb-grid__label">最大 HP</span>
              <input v-model="state[K.HP].max" class="cb-input" inputmode="numeric" placeholder="37" />
            </label>
            <label class="cb-grid__cell">
              <span class="cb-grid__label">临时 HP</span>
              <input v-model="state[K.HP].temp" class="cb-input" inputmode="numeric" placeholder="5" />
            </label>
          </div>

          <div v-else-if="kindOf(segment.key) === 'hpdice'" class="cb-grid cb-grid--3">
            <label class="cb-grid__cell">
              <span class="cb-grid__label">剩余生命骰</span>
              <input v-model="state[K.HP_DICE].num" class="cb-input" inputmode="numeric" placeholder="5" />
            </label>
            <label class="cb-grid__cell">
              <span class="cb-grid__label">生命骰总数</span>
              <input v-model="state[K.HP_DICE].max" class="cb-input" inputmode="numeric" placeholder="5" />
            </label>
            <label class="cb-grid__cell">
              <span class="cb-grid__label">骰面（D 后面）</span>
              <input v-model="state[K.HP_DICE].type" class="cb-input" inputmode="numeric" placeholder="6" />
            </label>
          </div>

          <div v-else-if="kindOf(segment.key) === 'combat'" class="cb-grid cb-grid--4">
            <label v-for="key in combatKeys" :key="key" class="cb-grid__cell">
              <span class="cb-grid__label">{{ key }}</span>
              <input
                v-if="key === '先攻'"
                class="cb-input cb-input--readonly"
                :value="initiativeValue || state[K.COMBAT].先攻"
                readonly
                title="先攻由敏捷调整值、先攻熟练与额外加值自动算出"
                placeholder="+2"
              />
              <input
                v-else
                v-model="state[K.COMBAT][key]"
                class="cb-input"
                :placeholder="combatPlaceholder(key)"
              />
            </label>
            <p class="cb-hint cb-grid__full">
              先攻只读：敏捷调整值 + 先攻熟练 + 额外加值里的「先攻」项；骰子加值不写入卡面。
            </p>
          </div>

          <div v-else-if="kindOf(segment.key) === 'progress'" class="cb-grid cb-grid--3">
            <label class="cb-grid__cell">
              <span class="cb-grid__label">经验（当前）</span>
              <input v-model="state[K.PROGRESS].xp" class="cb-input" inputmode="numeric" placeholder="6500" />
            </label>
            <label class="cb-grid__cell">
              <span class="cb-grid__label">经验（下一级，自动）</span>
              <input
                class="cb-input cb-input--readonly"
                :value="xpNextValue"
                readonly
                placeholder="14000"
              />
            </label>
            <label class="cb-grid__cell">
              <span class="cb-grid__label">英雄激励</span>
              <select v-model="state[K.PROGRESS].inspiration" class="cb-select">
                <option value="有">有</option>
                <option value="无">无</option>
              </select>
            </label>
            <p class="cb-hint cb-grid__full">
              下一级经验按等级自动生成，不能手填；20 级没有下一级。
            </p>
          </div>

          <AbilityGroupEditor
            v-else-if="kindOf(segment.key) === 'ability'"
            :state="state"
            :abilities="abilities"
            :modifiers="abilityModifiers"
          />

          <ProficiencyEditor
            v-else-if="kindOf(segment.key) === 'prof'"
            :state="state"
            :enums="enums"
            :abilities="abilities"
            :skills="skills"
            :values="checkValues"
          />

          <RepeaterRows
            v-else-if="kindOf(segment.key) === 'ext'"
            :items="state[K.EXT]"
            :max="30"
            add-label="添加额外加值"
            :factory="extFactory"
          >
            <template #default="{ item }">
              <div class="cb-grid cb-grid--3">
                <label class="cb-grid__cell">
                  <span class="cb-grid__label">条目</span>
                  <select v-model="item.key" class="cb-select">
                    <option value="">未选择</option>
                    <option v-for="name in enums.ext_items" :key="name" :value="name">{{ name }}</option>
                  </select>
                </label>
                <label class="cb-grid__cell">
                  <span class="cb-grid__label">优劣势</span>
                  <select v-model="item.adv" class="cb-select">
                    <option value="">不写</option>
                    <option value="优势">优势</option>
                    <option value="劣势">劣势</option>
                  </select>
                </label>
                <label class="cb-grid__cell">
                  <span class="cb-grid__label">加值 / 掷骰</span>
                  <input v-model="item.bonus" class="cb-input" placeholder="+2 或 +1d4" />
                </label>
              </div>
            </template>
          </RepeaterRows>

          <NamedList
            v-else-if="kindOf(segment.key) === 'feats'"
            :state="state"
            :field-key="K.FEATS"
            :max="limits.feat_max_count || 20"
            name-placeholder="战法师"
            text-placeholder="专注豁免具有优势（≤60 字）"
            add-label="添加专长"
          />

          <NamedList
            v-else-if="kindOf(segment.key) === 'raceTraits'"
            :state="state"
            :field-key="K.RACE_TRAITS"
            :max="limits.race_trait_max_count || 20"
            name-placeholder="黑暗视觉"
            text-placeholder="60 尺内微光视为明亮（≤80 字）"
            add-label="添加种族特性"
          />

          <ClassFeatureList
            v-else-if="kindOf(segment.key) === 'classTraits'"
            :state="state"
            :limits="limits"
          />

          <WeaponList
            v-else-if="kindOf(segment.key) === 'weapons'"
            :state="state"
            :enums="enums"
            :limits="limits"
          />

          <ItemList
            v-else-if="kindOf(segment.key) === 'items'"
            :state="state"
            :limits="limits"
          />

          <div v-else-if="kindOf(segment.key) === 'coins'" class="cb-grid cb-grid--5">
            <label v-for="coin in enums.coin_keys" :key="coin" class="cb-grid__cell">
              <span class="cb-grid__label">{{ coin }}</span>
              <input
                v-model="state[K.COINS][coin]"
                class="cb-input"
                inputmode="numeric"
                placeholder="0"
              />
            </label>
          </div>

          <FeatureList
            v-else-if="kindOf(segment.key) === 'features'"
            :state="state"
            :enums="enums"
            :limits="limits"
          />

          <MagicItemList
            v-else-if="kindOf(segment.key) === 'magicItems'"
            :state="state"
            :limits="limits"
          />

          <SpellList
            v-else-if="kindOf(segment.key) === 'spells'"
            :state="state"
            :enums="enums"
            :limits="limits"
            :abilities="abilities"
            :derived="spellStats"
          />

          <SlotList
            v-else-if="kindOf(segment.key) === 'slots'"
            :state="state"
          />

          <template v-else-if="kindOf(segment.key) === 'notes'">
            <div
              v-for="(note, index) in state[K.COMBAT_NOTES]"
              :key="index"
              class="cb-inline-row"
            >
              <input
                v-model="state[K.COMBAT_NOTES][index]"
                class="cb-input"
                placeholder="法师护甲(8小时)"
              />
              <button
                type="button"
                class="cb-icon"
                title="删除这一条"
                aria-label="删除这一条"
                @click="state[K.COMBAT_NOTES].splice(index, 1)"
              >×</button>
            </div>
            <div>
              <button
                type="button"
                class="cb-btn cb-btn--ghost cb-btn--small"
                @click="state[K.COMBAT_NOTES].push('')"
              >+ 添加记录</button>
            </div>
          </template>

          <template v-else-if="kindOf(segment.key) === 'background'">
            <div class="cb-grid cb-grid--2">
              <label v-for="key in backgroundFields" :key="key" class="cb-grid__cell">
                <span class="cb-grid__label">{{ key }}</span>
                <input
                  v-model="state[K.BACKGROUND][key]"
                  class="cb-input"
                  :placeholder="backgroundPlaceholder(key)"
                />
              </label>
            </div>
            <p class="cb-hint">
              背景字段固定，空值不会写入卡文本。5r 不显示理想 / 羁绊 / 缺点；切到 5e 可填写。
            </p>
          </template>
        </BuilderField>
      </div>
    </details>

    <section ref="exportPanel" class="cb-export">
      <h3 class="cb-export__title">导出命令</h3>
      <p class="cb-export__status" :class="statusClass">{{ statusText }}</p>

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

      <div class="cb-export__block">
        <h4>首次建卡：复制整卡</h4>
        <p class="cb-hint">
          新卡要先整卡记录一次。整卡太长发不出去时，先复制「精简整卡」建卡，再逐条发送下面的分段命令补全。
        </p>
        <div class="cb-inline cb-inline--top">
          <CopyButton :text="wholeCommand" label="复制整卡命令" :disabled="!canCopy" primary />
          <CopyButton :text="minimalCommand" label="复制精简整卡" :disabled="!canCopy" />
          <span class="cb-muted">整卡 {{ validation.length }} 字</span>
        </div>
        <pre class="cb-preview">{{ validation.text || '（还没有内容）' }}</pre>
      </div>

      <div class="cb-export__block">
        <h4>之后改单段：逐条复制发送</h4>
        <p class="cb-hint">每条命令单独发一条消息；只改这一段，其余段保持原样。</p>
        <div v-if="segmentCommands.length" class="cb-cmd-list">
          <div v-for="item in segmentCommands" :key="item.key" class="cb-cmd">
            <span class="cb-cmd__label">{{ item.label }}</span>
            <span class="cb-cmd__key">{{ item.key }}</span>
            <span class="cb-cmd__len">{{ item.length }} 字</span>
            <CopyButton :text="item.command" label="复制" :disabled="!canCopy" />
          </div>
        </div>
        <p v-else class="cb-muted">还没有可导出的段。</p>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'

import spec from '../card-builder/card-spec.json'
import {
  CARD_COMMAND,
  K,
  createCardBuilder,
} from '../card-builder/core.mjs'
import AbilityGroupEditor from './card-builder/AbilityGroupEditor.vue'
import BuilderField from './card-builder/BuilderField.vue'
import ClassFeatureList from './card-builder/ClassFeatureList.vue'
import CopyButton from './card-builder/CopyButton.vue'
import FeatureList from './card-builder/FeatureList.vue'
import ItemList from './card-builder/ItemList.vue'
import MagicItemList from './card-builder/MagicItemList.vue'
import NamedList from './card-builder/NamedList.vue'
import ProficiencyEditor from './card-builder/ProficiencyEditor.vue'
import RepeaterRows from './card-builder/RepeaterRows.vue'
import SlotList from './card-builder/SlotList.vue'
import SpellList from './card-builder/SpellList.vue'
import WeaponList from './card-builder/WeaponList.vue'

const builder = createCardBuilder(spec)
const enums = spec.enums
const limits = spec.limits
const abilities = enums.abilities
const skills = enums.skills
const combatKeys = ['AC', '先攻', '速度', '被动察觉']
const rulesVersion = ref('5r')

const state = reactive(builder.createState())
const openGroups = reactive(
  Object.fromEntries(builder.groups.map((group, index) => [group.id, index < 4])),
)

const queryOptions = computed(() => ({ rulesVersion: rulesVersion.value }))
const validation = computed(() => builder.validateState(state, queryOptions.value))
const segmentCommands = computed(() => builder.buildSegmentCommands(state, queryOptions.value))
const wholeCommand = computed(() => `${CARD_COMMAND}\n${validation.value.text}`)
const minimalCommand = computed(
  () => `${CARD_COMMAND}\n${builder.buildMinimalCard(state, queryOptions.value)}`,
)
const canCopy = computed(
  () => validation.value.errors.length === 0 && validation.value.text.length > 0,
)
const storyLength = computed(() =>
  Array.from((state[K.STORY] || '').replace(/\n/g, '')).length,
)
const abilityModifiers = computed(() => builder.deriveAbilityModifiers(state))
const checkValues = computed(() => builder.deriveCheckValues(state))
const proficiencyBonus = computed(() => builder.deriveProficiencyBonus(state))
const xpNextValue = computed(() => builder.deriveXpNext(state))
const initiativeValue = computed(() => builder.deriveInitiative(state))
const spellStats = computed(() => builder.deriveSpellStats(state))
const backgroundFields = computed(() => builder.backgroundKeysFor(rulesVersion.value))
const subclassVisible = computed(() =>
  builder.isSubclassAvailable(state, rulesVersion.value),
)
const subclassRuleText = computed(() => {
  if (!state[K.CLASS]) return '填写职业与等级后会按规则显示'
  const level = builder.subclassLevelFor(state[K.CLASS], rulesVersion.value)
  return `${state[K.CLASS]}在 ${level} 级获得子职`
})

watch(
  [() => state[K.LEVEL], () => state[K.CLASS], rulesVersion],
  () => {
    if (!subclassVisible.value && state[K.SUBCLASS]) {
      state[K.SUBCLASS] = ''
      showNotice('等级或职业变化后不再满足子职条件，已清空子职', 'warn')
    }
  },
)

const errorsByKey = computed(() => {
  const map = {}
  for (const error of validation.value.errors) {
    if (!error.key) continue
    if (!map[error.key]) map[error.key] = []
    map[error.key].push(error)
  }
  return map
})

const groups = computed(() =>
  builder.groups.map((group) => ({
    ...group,
    segments: builder.segments.filter((segment) => segment.group === group.id),
  })),
)

const filledKeys = computed(() => {
  const keys = new Set()
  for (const segment of builder.segments) {
    try {
      if (builder.contentFor(state, segment.key, queryOptions.value)) keys.add(segment.key)
    } catch {
      keys.add(segment.key)
    }
  }
  return keys
})

const statusClass = computed(() => {
  if (validation.value.errors.length > 0) return 'cb-status--error'
  if (validation.value.warnings.length > 0) return 'cb-status--warn'
  return 'cb-status--ok'
})

const statusText = computed(() => {
  const { errors, warnings } = validation.value
  if (errors.length > 0) return `${errors.length} 处待修正`
  if (warnings.length > 0) return `可以导出（${warnings.length} 条提醒）`
  return '可以导出'
})

const importOpen = ref(false)
const importText = ref('')
const importErrors = ref([])
const importWarnings = ref([])
const notice = ref('')
const noticeKind = ref('ok')
const exportPanel = ref(null)
let noticeTimer = null

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

function kindOf(key) {
  return builder.kinds[key]
}

function placeholder(segment) {
  const text = segment.example || ''
  return Array.from(text).length > 48 ? `${Array.from(text).slice(0, 46).join('')}…` : text
}

function combatPlaceholder(key) {
  return { AC: '16', 先攻: '+2', 速度: '30', 被动察觉: '13' }[key] || ''
}

function backgroundPlaceholder(key) {
  return {
    背景: '智者',
    阵营: '中立善良',
    信仰: '密斯特拉',
    体型: '中型',
    年龄: '132',
    外貌: '银发绿眼，深蓝法袍',
    个性: '喜欢追问原理',
    理想: '知识应当被分享',
    羁绊: '导师的笔记',
    缺点: '说话太直',
  }[key] || ''
}

function groupCount(group) {
  const total = group.segments.length
  const filled = group.segments.filter((segment) => filledKeys.value.has(segment.key)).length
  return `${filled}/${total} 已填`
}

function onToggle(groupId, event) {
  openGroups[groupId] = event.target.open
}

function applyState(nextState) {
  Object.assign(state, nextState)
}

function loadExample() {
  rulesVersion.value = '5r'
  const parsed = builder.parseCardText(builder.buildExampleCard())
  if (parsed.errors.length > 0) {
    showNotice('示例卡载入失败，请反馈这个问题', 'error')
    return
  }
  applyState(parsed.state)
  showNotice('已载入示例卡（5 级高等精灵法师），可以直接改；也可以从「导入卡文本」粘自己的卡。')
}

function doImport() {
  const result = builder.parseCardText(importText.value)
  importErrors.value = result.errors
  importWarnings.value = result.warnings
  if (result.errors.length > 0) {
    showNotice(`导入失败：${result.errors.length} 处需要修正`, 'error')
    return
  }
  applyState(result.state)
  rulesVersion.value = result.rulesVersion || '5r'
  importOpen.value = false
  showNotice(`已导入 ${result.found} 个段`)
}

function clearAll() {
  if (typeof window !== 'undefined' && !window.confirm('确定清空当前表单？已填写的内容不会保留。')) {
    return
  }
  applyState(builder.createState())
  importErrors.value = []
  importWarnings.value = []
  showNotice('已清空')
}

async function reveal(key) {
  const segment = builder.segments.find((item) => item.key === key)
  if (segment) openGroups[segment.group] = true
  await nextTick()
  if (!key) {
    exportPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    return
  }
  const target = document.querySelector(`[data-seg-key="${key}"]`)
  if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function scrollToExport() {
  exportPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function extFactory() {
  return { key: '', adv: '', bonus: '' }
}
</script>
