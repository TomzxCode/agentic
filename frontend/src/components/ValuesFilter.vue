<script setup>
import { computed, ref } from 'vue'

// A multi-select value filter for a column whose values come from a fixed or
// discrete set: a checkbox list in the column's filter popup, modelled on AG
// Grid's Set Filter (which is Enterprise) and built on the Community custom
// filter support.
//
// The column supplies, through `filterParams`:
//   getValues  maps a row's data to the values it carries for this column
//   label      maps a value to its display label (optional)
// The selected values are reported back through `onModelChange` as
// `{ values: [...] }`, and the column's `doesFilterPass` matches on that model.
const props = defineProps({ params: { type: Object, required: true } })

const selected = ref(new Set(props.params.model?.values || []))
const query = ref('')
const all = ref(collectOptions())

// The distinct values across the grid's rows, so the list reflects the data.
function collectOptions() {
  const values = new Set()
  props.params.api?.forEachNode((node) => {
    for (const value of props.params.getValues?.(node.data) || []) if (value) values.add(value)
  })
  const label = props.params.label || ((value) => value)
  return [...values]
    .map((value) => ({ value, label: label(value) }))
    .sort((a, b) => a.label.toLowerCase().localeCompare(b.label.toLowerCase()))
}

const visible = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return all.value
  return all.value.filter((option) => option.label.toLowerCase().includes(q))
})

// A long list (many authors, say) gets a box to narrow the options.
const showSearch = computed(() => all.value.length > 8)

function toggle(value) {
  const next = new Set(selected.value)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  selected.value = next
  props.params.onModelChange(next.size ? { values: [...next] } : null)
}

// The grid calls these: `refresh` when the model changes from outside (grid
// state or the API), `onNewRowsLoaded` when the row data changes.
function refresh(params) {
  selected.value = new Set(params.model?.values || [])
}

function onNewRowsLoaded() {
  all.value = collectOptions()
}

defineExpose({ refresh, onNewRowsLoaded })
</script>

<template>
  <div class="value-filter">
    <input
      v-if="showSearch"
      v-model="query"
      class="input value-filter-search"
      type="text"
      placeholder="Search values…"
      aria-label="Search filter values"
    />
    <label v-for="option in visible" :key="option.value" class="value-filter-option">
      <input type="checkbox" :checked="selected.has(option.value)" @change="toggle(option.value)" />
      <span>{{ option.label }}</span>
    </label>
    <p v-if="!visible.length" class="faint">No values.</p>
  </div>
</template>
