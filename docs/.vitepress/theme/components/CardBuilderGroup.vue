<template>
  <div class="cb-section" :data-group="groupId">
    <BuilderField
      v-for="segment in segments"
      :key="segment.key"
      :label="segment.label"
      :summary="segment.summary"
      :segment-key="segment.key"
      :required="segment.required"
      :errors="errorsByKey[segment.key]"
      :copy-command="segmentCommandsByKey[segment.key]?.command || ''"
      :copy-disabled="!segmentCommandsByKey[segment.key] || !!cardNameError"
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
        <p class="cb-inline-note">
          {{ storyLength }} / {{ limits.story_max_len || 1000 }} 字
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

      <div v-else-if="kindOf(segment.key) === 'combat'">
        <div class="cb-grid cb-grid--4">
          <label v-for="key in combatKeys" :key="key" class="cb-grid__cell">
            <span class="cb-grid__label">{{ key }}</span>
            <input
              v-model="state[K.COMBAT][key]"
              class="cb-input"
              :placeholder="combatPlaceholder(key)"
            />
          </label>
          <label class="cb-grid__cell">
            <span class="cb-grid__label">
              先攻
              <HintDot text="由敏捷调整值、先攻熟练与额外加值自动算出，这里只预览结果。" />
            </span>
            <input
              class="cb-input cb-input--readonly"
              :value="checkValues['先攻'] || initiativeValue || '—'"
              readonly
              placeholder="—"
            />
          </label>
          <label class="cb-grid__cell">
            <span class="cb-grid__label">
              被动察觉
              <HintDot text="10 + 察觉检定加值；有优势 +5、劣势 -5，这里只预览结果。" />
            </span>
            <input
              class="cb-input cb-input--readonly"
              :value="passivePerceptionValue || '—'"
              readonly
              placeholder="—"
            />
          </label>
        </div>
      </div>

      <div v-else-if="kindOf(segment.key) === 'progress'" class="cb-grid cb-grid--3">
        <label class="cb-grid__cell">
          <span class="cb-grid__label">经验（当前）</span>
          <input v-model="state[K.PROGRESS].xp" class="cb-input" inputmode="numeric" placeholder="6500" />
        </label>
        <label class="cb-grid__cell">
          <span class="cb-grid__label">
            下一级所需
            <HintDot text="按等级自动算出，只用于预览，不需要填写。" />
          </span>
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
                <option value="">无</option>
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
      </template>
    </BuilderField>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { K } from '../card-builder/core.mjs'
import {
  abilityModifiers,
  abilities,
  backgroundFields,
  builder,
  cardNameError,
  checkValues,
  enums,
  errorsByKey,
  initiativeValue,
  limits,
  passivePerceptionValue,
  proficiencyBonus,
  segmentCommandsByKey,
  skills,
  spellStats,
  state,
  storyLength,
  subclassVisible,
  subclassRuleText,
  xpNextValue,
} from '../card-builder/store.mjs'
import AbilityGroupEditor from './card-builder/AbilityGroupEditor.vue'
import BuilderField from './card-builder/BuilderField.vue'
import ClassFeatureList from './card-builder/ClassFeatureList.vue'
import FeatureList from './card-builder/FeatureList.vue'
import HintDot from './card-builder/HintDot.vue'
import ItemList from './card-builder/ItemList.vue'
import MagicItemList from './card-builder/MagicItemList.vue'
import NamedList from './card-builder/NamedList.vue'
import ProficiencyEditor from './card-builder/ProficiencyEditor.vue'
import RepeaterRows from './card-builder/RepeaterRows.vue'
import SlotList from './card-builder/SlotList.vue'
import SpellList from './card-builder/SpellList.vue'
import WeaponList from './card-builder/WeaponList.vue'

const props = defineProps({
  groupId: { type: String, required: true },
})

const segments = computed(() =>
  builder.formSegments.filter((segment) => segment.group === props.groupId),
)
const combatKeys = ['AC', '速度']

function kindOf(key) {
  return builder.kinds[key]
}

function placeholder(segment) {
  const text = segment.example || ''
  return Array.from(text).length > 48
    ? `${Array.from(text).slice(0, 46).join('')}…`
    : text
}

function combatPlaceholder(key) {
  return { AC: '16', 速度: '30' }[key] || ''
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

function extFactory() {
  return { key: '', adv: '', bonus: '' }
}
</script>
