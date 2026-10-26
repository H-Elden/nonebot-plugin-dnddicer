<template>
  <div class="cb-half-prof">
    <p v-if="!hasBonus" class="cb-hint">填写等级后显示取整结果。</p>

    <div class="cb-chip-grid">
      <span v-for="preset in presets" :key="preset.key" class="cb-half-prof__item">
        <ToggleChip
          :active="hasRule(preset.scope, preset.rounding)"
          :title="preset.tooltip"
          @toggle="toggleRule(preset.scope, preset.rounding)"
        >{{ preset.label }}</ToggleChip>
        <span
          v-if="hasRule(preset.scope, preset.rounding) && hasBonus"
          class="cb-half-prof__bonus"
        >半熟练加值：{{ formatBonus(preset.rounding) }}</span>
      </span>
    </div>

    <div class="cb-chip-grid">
      <span v-for="rule in extraRules" :key="ruleKey(rule)" class="cb-half-prof__item">
        <span class="cb-chip cb-chip--1 cb-chip--static">
          {{ rule.scope }} · {{ roundingLabel(rule.rounding) }}
          <button
            type="button"
            class="cb-chip__remove"
            title="移除"
            @click="removeRule(rule)"
          >×</button>
        </span>
        <span v-if="hasBonus" class="cb-half-prof__bonus">
          半熟练加值：{{ formatBonus(rule.rounding) }}
        </span>
      </span>
      <span v-if="rules.length === 0" class="cb-muted">未选择（不会加半熟练）</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import ToggleChip from './ToggleChip.vue'

// $半熟练$：按「范围 + 取整」记录规则，由骰娘按当前熟练加值现算。
// 预设只负责生成规则；卡文本存的是 全部/技能/力敏体 + 向下/向上。
const props = defineProps({
  rules: { type: Array, required: true },
  proficiencyBonus: { type: [Number, String], default: '' },
  rulesVersion: { type: String, default: '5r' },
})

const presets = computed(() =>
  props.rulesVersion === '5e'
    ? [
        {
          key: 'joat-5e',
          label: '万事通（全部 · 向下取整）',
          tooltip: '为六属性检定、技能检定与先攻检定加上半熟练加值（不含豁免）',
          scope: '全部',
          rounding: '向下',
        },
        {
          key: 'athlete-5e',
          label: '运动健将（力敏体 · 向上取整）',
          tooltip:
            '为力量、敏捷、体质相关的属性检定、技能检定与先攻检定加上半熟练加值（不含豁免）',
          scope: '力敏体',
          rounding: '向上',
        },
      ]
    : [
        {
          key: 'joat-5r',
          label: '万事通（技能 · 向下取整）',
          tooltip: '为 18 项技能检定加上半熟练加值（不含先攻与豁免）',
          scope: '技能',
          rounding: '向下',
        },
      ],
)

const extraRules = computed(() =>
  props.rules.filter(
    (rule) =>
      !presets.value.some(
        (preset) => preset.scope === rule.scope && preset.rounding === rule.rounding,
      ),
  ),
)

const profBonusValue = computed(() => {
  const value = Number(props.proficiencyBonus)
  return Number.isFinite(value) && value > 0 ? value : 0
})

const hasBonus = computed(() => profBonusValue.value > 0)

function bonusValue(rounding) {
  return rounding === '向上'
    ? Math.ceil(profBonusValue.value / 2)
    : Math.floor(profBonusValue.value / 2)
}

function formatBonus(rounding) {
  return `+${bonusValue(rounding)}`
}

function roundingLabel(rounding) {
  return rounding === '向下' || rounding === '向上' ? `${rounding}取整` : rounding
}

function ruleKey(rule) {
  return `${rule.scope}:${rule.rounding}`
}

function hasRule(scope, rounding) {
  return props.rules.some(
    (rule) => rule.scope === scope && rule.rounding === rounding,
  )
}

function toggleRule(scope, rounding) {
  const index = props.rules.findIndex(
    (rule) => rule.scope === scope && rule.rounding === rounding,
  )
  if (index >= 0) props.rules.splice(index, 1)
  else props.rules.push({ scope, rounding })
}

function removeRule(rule) {
  const index = props.rules.indexOf(rule)
  if (index >= 0) props.rules.splice(index, 1)
}
</script>
