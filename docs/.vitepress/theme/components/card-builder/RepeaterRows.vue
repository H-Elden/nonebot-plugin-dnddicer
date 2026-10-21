<template>
  <div class="cb-repeater" :class="{ 'cb-repeater--compact': compact }">
    <div v-for="(item, index) in items" :key="index" class="cb-repeater__row">
      <div class="cb-repeater__body">
        <slot :item="item" :index="index" />
      </div>
      <div class="cb-repeater__actions">
        <button
          type="button"
          class="cb-icon"
          title="上移"
          aria-label="上移"
          :disabled="index === 0"
          @click="move(index, -1)"
        >↑</button>
        <button
          type="button"
          class="cb-icon"
          title="下移"
          aria-label="下移"
          :disabled="index === items.length - 1"
          @click="move(index, 1)"
        >↓</button>
        <button
          type="button"
          class="cb-icon"
          title="删除这一行"
          aria-label="删除这一行"
          @click="remove(index)"
        >×</button>
      </div>
    </div>
    <div>
      <button
        v-if="items.length < max"
        type="button"
        class="cb-btn cb-btn--ghost cb-btn--small"
        @click="add"
      >+ {{ addLabel }}</button>
      <span v-if="items.length >= max" class="cb-hint">已达上限 {{ max }} 项</span>
    </div>
  </div>
</template>

<script setup>
// 通用行编辑器：增删与上下移动。行对象的形状由 factory 决定，字段由插槽渲染。
// compact 用于「键值对」这类单行就能放下的列表（背景），减少纵向占用。
const props = defineProps({
  items: { type: Array, required: true },
  max: { type: Number, default: 20 },
  addLabel: { type: String, default: '添加一行' },
  factory: { type: Function, required: true },
  compact: { type: Boolean, default: false },
})

function add() {
  if (props.items.length >= props.max) return
  props.items.push(props.factory())
}

function remove(index) {
  props.items.splice(index, 1)
  // 留一行空行，避免用户删光后找不到添加入口
  if (props.items.length === 0) props.items.push(props.factory())
}

function move(index, offset) {
  const target = index + offset
  if (target < 0 || target >= props.items.length) return
  const [row] = props.items.splice(index, 1)
  props.items.splice(target, 0, row)
}
</script>
