<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  options: { type: Array, required: true }, // [{ value, label, icon?, iconProps? }]
  placeholder: { type: String, default: 'Select…' },
  variant: { type: String, default: 'field' }, // field | inline | icon
  title: { type: String, default: 'Click to choose' },
  disabled: { type: Boolean, default: false },
  sort: { type: Boolean, default: true },
  // Keep the list open after choosing, so several options can be picked in a row.
  keepOpen: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const query = ref('')
const highlighted = ref(0)
const root = ref(null)
const input = ref(null)

const normalized = computed(() => {
  const options = props.options.map((option) => ({
    value: String(option.value ?? ''),
    label: option.label ?? String(option.value ?? ''),
    icon: option.icon || null,
    iconProps: option.iconProps || null
  }))
  if (!props.sort) return options
  // Alphabetical, but keep the empty-value sentinel (None/Auto/…) first.
  const sorted = [...options].sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }))
  return [...sorted.filter((o) => o.value === ''), ...sorted.filter((o) => o.value !== '')]
})

const current = computed(() => String(props.modelValue ?? ''))
const selected = computed(() => normalized.value.find((option) => option.value === current.value))
const hasValue = computed(() => Boolean(selected.value))

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? normalized.value.filter((option) => option.label.toLowerCase().includes(q)) : normalized.value
})

function toggle() {
  if (props.disabled) return
  open.value ? close() : show()
}

function show() {
  open.value = true
  query.value = ''
  highlighted.value = Math.max(
    0,
    filtered.value.findIndex((option) => option.value === current.value)
  )
  document.addEventListener('mousedown', onOutside)
  nextTick(() => input.value?.focus())
}

function close() {
  open.value = false
  document.removeEventListener('mousedown', onOutside)
}

function onOutside(event) {
  if (root.value && !root.value.contains(event.target)) close()
}

function choose(option) {
  emit('update:modelValue', option.value)
  if (!props.keepOpen) {
    close()
    return
  }
  // Stay open for the next pick: clear the filter and keep the keyboard focus.
  query.value = ''
  highlighted.value = 0
  nextTick(() => input.value?.focus())
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation() // don't also close an enclosing modal
    close()
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    highlighted.value = Math.min(highlighted.value + 1, filtered.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlighted.value = Math.max(highlighted.value - 1, 0)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const option = filtered.value[highlighted.value]
    if (option) choose(option)
  }
}

watch(filtered, () => (highlighted.value = 0))
onBeforeUnmount(() => document.removeEventListener('mousedown', onOutside))

// Let a parent (e.g. the command palette) open the dropdown directly.
defineExpose({ activate: show })
</script>

<template>
  <div ref="root" class="search-select" :class="[variant, { open, disabled }]">
    <button
      type="button"
      class="ss-trigger"
      :title="title"
      :disabled="disabled"
      @click="toggle"
      @keydown.down.prevent="toggle"
    >
      <component :is="selected.icon" v-if="selected?.icon" v-bind="selected.iconProps" />
      <template v-if="variant !== 'icon'">
        <span class="ss-label" :class="{ placeholder: !hasValue }">{{ selected ? selected.label : placeholder }}</span>
        <span class="ss-caret">▾</span>
      </template>
    </button>

    <div v-if="open" class="ss-panel">
      <input ref="input" v-model="query" class="ss-search" placeholder="Filter…" @keydown="onKeydown" />
      <div class="ss-options">
        <div v-if="!filtered.length" class="ss-empty faint">No matches</div>
        <button
          v-for="(option, index) in filtered"
          :key="option.value"
          type="button"
          class="ss-option"
          :class="{ active: index === highlighted, selected: option.value === current }"
          @mouseenter="highlighted = index"
          @click="choose(option)"
        >
          <component :is="option.icon" v-if="option.icon" v-bind="option.iconProps" />
          <span class="ss-option-label">{{ option.label }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
