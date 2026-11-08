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
  // Open the bottom drawer on a phone even for a single pick, for pickers that
  // read better full-width there (status, priority, waiting on).
  drawer: { type: Boolean, default: false },
  // Above the option list's choices, offer "Select all" and "Deselect all" so a
  // long multi-select can be taken or cleared in one click. Only used in
  // multiple mode.
  bulkActions: { type: Boolean, default: false },
  // Summarize the chosen values in the trigger. Turn it off where another part
  // of the page already lists them, so the trigger keeps its placeholder.
  summary: { type: Boolean, default: true },
  // Offer the search text as a new value when it matches no option (free-text
  // lists like tags): first when nothing matches, after the close matches else.
  creatable: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

const open = ref(false)
const query = ref('')
const highlighted = ref(0)
// Set when the panel would run off the bottom of the viewport (a picker in the
// floating bulk bar), so it opens above the trigger instead.
const opensUp = ref(false)
const root = ref(null)
const input = ref(null)
// On a phone, a repeated-pick select (multi-select, or one that stays open for
// the next pick) opens as a bottom drawer, as does any picker that asks for it.
// The anchored popup is cramped there and ends up under the on-screen keyboard
// once its filter has the focus.
const isMobile = ref(false)
const asDrawer = computed(() => isMobile.value && (props.drawer || props.multiple || props.keepOpen))
// The drawer's heading: the caller's title, or its placeholder when the title
// is only the generic trigger tooltip.
const drawerTitle = computed(() => (props.title === 'Click to choose' ? props.placeholder : props.title))

function detectMobile() {
  isMobile.value = typeof window !== 'undefined' && window.innerWidth <= 760
}

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
const hasValue = computed(
  () => props.summary && (props.multiple ? selectedOptions.value.length > 0 : Boolean(selected.value))
)
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
  const matches = q ? normalized.value.filter((option) => option.label.toLowerCase().includes(q)) : normalized.value
  // In multiple mode the chosen options live in their own section, so the list
  // below only offers what is not chosen yet.
  const open = props.multiple ? matches.filter((option) => !selectedValues.value.has(option.value)) : matches
  const text = query.value.trim()
  if (!props.creatable || !text) return open
  // An exact match is the existing option, not a new value spelled the same way.
  if (normalized.value.some((option) => option.label.toLowerCase() === text.toLowerCase())) return open
  // A close match stays first so Enter takes it; the new value follows it, and
  // is the only entry when nothing matches at all.
  const create = { value: text, label: `Create "${text}"`, create: true }
  return [...open, create]
})

// The bulk actions' values: every real option currently listed, ignoring the
// empty-value sentinel. "Select all" therefore follows the search box, so a
// query can take one group of options at once.
const selectableValues = computed(() => filtered.value.map((option) => option.value).filter((value) => value !== ''))
const allSelected = computed(
  () =>
    props.multiple &&
    (selectableValues.value.length === 0 || selectableValues.value.every((value) => selectedValues.value.has(value)))
)

// Focus the filter box for the next pick, except in the drawer: on a phone that
// would raise the keyboard and cover the options being chosen.
function focusSearch() {
  nextTick(() => {
    if (!asDrawer.value) input.value?.focus()
  })
}

// Choose every listed option in one click, keeping the panel open for the next
// action.
function selectAll() {
  const next = new Set(selectedValues.value)
  for (const value of selectableValues.value) next.add(value)
  emit('update:modelValue', [...next])
  focusSearch()
}

// Clear the whole selection, whatever the search box currently lists.
function deselectAll() {
  emit('update:modelValue', [])
  focusSearch()
}

function toggle() {
  if (props.disabled) return
  open.value ? close() : show()
}

function show() {
  detectMobile()
  open.value = true
  query.value = ''
  const rect = root.value?.getBoundingClientRect()
  // The panel's search box plus its tallest option list is about 300px.
  opensUp.value = rect ? window.innerHeight - rect.bottom < 300 : false
  highlighted.value = Math.max(
    0,
    filtered.value.findIndex((option) => option.value === current.value)
  )
  document.addEventListener('mousedown', onOutside)
  window.addEventListener('resize', detectMobile)
  focusSearch()
}

function close() {
  open.value = false
  document.removeEventListener('mousedown', onOutside)
  window.removeEventListener('resize', detectMobile)
}

function onOutside(event) {
  if (root.value && !root.value.contains(event.target)) close()
}

// Remove a chosen value from the selected section above the option list.
function unselect(value) {
  const next = new Set(selectedValues.value)
  next.delete(String(value))
  emit('update:modelValue', [...next])
  focusSearch()
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
    focusSearch()
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
  focusSearch()
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
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onOutside)
  window.removeEventListener('resize', detectMobile)
})

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

    <div v-if="open && asDrawer" class="ss-backdrop" @click="close"></div>

    <div
      v-if="open"
      class="ss-panel"
      :class="{ up: opensUp, drawer: asDrawer }"
      :role="asDrawer ? 'dialog' : undefined"
      :aria-modal="asDrawer ? 'true' : undefined"
      :aria-label="asDrawer ? drawerTitle : undefined"
    >
      <div v-if="asDrawer" class="ss-drawer-head">
        <span class="ss-drawer-title">{{ drawerTitle }}</span>
        <button type="button" class="ss-drawer-close" aria-label="Close" @click="close">✕</button>
      </div>
      <input ref="input" v-model="query" class="ss-search" placeholder="Filter…" @keydown="onKeydown" />
      <div v-if="multiple && bulkActions" class="ss-bulk">
        <button type="button" class="ss-bulk-action" :disabled="allSelected" @click="selectAll">Select all</button>
        <button type="button" class="ss-bulk-action" :disabled="!selectedOptions.length" @click="deselectAll">
          Deselect all
        </button>
      </div>
      <div class="ss-body">
        <div v-if="multiple && selectedOptions.length" class="ss-selected">
          <div class="ss-selected-head">Selected</div>
          <div class="ss-selected-list">
            <button
              v-for="option in selectedOptions"
              :key="option.value"
              type="button"
              class="ss-selected-item"
              :aria-label="`Unselect ${option.label}`"
              @click="unselect(option.value)"
            >
              <component :is="option.icon" v-if="option.icon" v-bind="option.iconProps" />
              <span class="ss-option-label">{{ option.label }}</span>
              <span class="ss-selected-check" aria-hidden="true">✓</span>
            </button>
          </div>
        </div>
        <div class="ss-options">
          <div v-if="!filtered.length" class="ss-empty faint">
            {{ multiple && !query.trim() && normalized.length ? 'All selected' : 'No matches' }}
          </div>
          <button
            v-for="(option, index) in filtered"
            :key="option.value"
            type="button"
            class="ss-option"
            :class="{ active: index === highlighted, selected: isSelected(option), create: option.create }"
            @mouseenter="highlighted = index"
            @click="choose(option)"
          >
            <component :is="option.icon" v-if="option.icon" v-bind="option.iconProps" />
            <span class="ss-option-label">{{ option.label }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
