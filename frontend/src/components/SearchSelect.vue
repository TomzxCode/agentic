<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: [String, Number, Array], default: '' },
  options: { type: Array, required: true }, // [{ value, label, icon?, iconProps? }]
  placeholder: { type: String, default: 'Select…' },
  variant: { type: String, default: 'field' }, // field | inline | icon
  title: { type: String, default: 'Click to choose' },
  disabled: { type: Boolean, default: false },
  sort: { type: Boolean, default: true },
  // Keep the list open after choosing, so several options can be picked in a row.
  keepOpen: { type: Boolean, default: false },
  // Multi-select: `modelValue` is an array, choosing toggles a value, and the
  // list stays open so several can be picked in a row.
  multiple: { type: Boolean, default: false },
  // Above the option list's choices, offer "Select all" and "Deselect all" so a
  // long multi-select can be taken or cleared in one click. Only used in
  // multiple mode.
  bulkActions: { type: Boolean, default: false }
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

const current = computed(() => (props.multiple ? '' : String(props.modelValue ?? '')))
const selected = computed(() => normalized.value.find((option) => option.value === current.value))
// The chosen values as a set, only in multiple mode.
const selectedValues = computed(() =>
  props.multiple
    ? new Set((Array.isArray(props.modelValue) ? props.modelValue : []).map((value) => String(value ?? '')))
    : null
)
const selectedOptions = computed(() => normalized.value.filter((option) => selectedValues.value?.has(option.value)))
const hasValue = computed(() => (props.multiple ? selectedOptions.value.length > 0 : Boolean(selected.value)))
// The trigger's text: the chosen option, or, in multiple mode, their labels.
const label = computed(() =>
  props.multiple ? selectedOptions.value.map((option) => option.label).join(', ') : selected.value?.label || ''
)

// Whether an option reads as chosen, in both modes.
function isSelected(option) {
  return props.multiple ? selectedValues.value.has(option.value) : option.value === current.value
}

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? normalized.value.filter((option) => option.label.toLowerCase().includes(q)) : normalized.value
})

// The bulk actions' values: every real option currently listed, ignoring the
// empty-value sentinel. "Select all" therefore follows the search box, so a
// query can take one group of options at once.
const selectableValues = computed(() => filtered.value.map((option) => option.value).filter((value) => value !== ''))
const allSelected = computed(
  () =>
    props.multiple &&
    selectableValues.value.length > 0 &&
    selectableValues.value.every((value) => selectedValues.value.has(value))
)

// Choose every listed option in one click, keeping the panel open for the next
// action.
function selectAll() {
  const next = new Set(selectedValues.value)
  for (const value of selectableValues.value) next.add(value)
  emit('update:modelValue', [...next])
  nextTick(() => input.value?.focus())
}

// Clear the whole selection, whatever the search box currently lists.
function deselectAll() {
  emit('update:modelValue', [])
  nextTick(() => input.value?.focus())
}

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
  if (props.multiple) {
    const next = new Set(selectedValues.value)
    if (next.has(option.value)) next.delete(option.value)
    else next.add(option.value)
    emit('update:modelValue', [...next])
    // Stay open for the next pick: clear the filter and keep the keyboard focus.
    query.value = ''
    highlighted.value = Math.max(0, filtered.value.indexOf(option))
    nextTick(() => input.value?.focus())
    return
  }
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
        <span class="ss-label" :class="{ placeholder: !hasValue }">{{ hasValue ? label : placeholder }}</span>
      </template>
    </button>

    <div v-if="open" class="ss-panel">
      <input ref="input" v-model="query" class="ss-search" placeholder="Filter…" @keydown="onKeydown" />
      <div v-if="multiple && bulkActions" class="ss-bulk">
        <button type="button" class="ss-bulk-action" :disabled="allSelected" @click="selectAll">Select all</button>
        <button type="button" class="ss-bulk-action" :disabled="!selectedOptions.length" @click="deselectAll">
          Deselect all
        </button>
      </div>
      <div class="ss-options">
        <div v-if="!filtered.length" class="ss-empty faint">No matches</div>
        <button
          v-for="(option, index) in filtered"
          :key="option.value"
          type="button"
          class="ss-option"
          :class="{ active: index === highlighted, selected: isSelected(option) }"
          :aria-pressed="multiple ? isSelected(option) : undefined"
          @mouseenter="highlighted = index"
          @click="choose(option)"
        >
          <span v-if="multiple" class="ss-check" aria-hidden="true">{{ isSelected(option) ? '✓' : '' }}</span>
          <component :is="option.icon" v-if="option.icon" v-bind="option.iconProps" />
          <span class="ss-option-label">{{ option.label }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
