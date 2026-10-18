<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

// A show/hide-columns control for a list grid, built on AG Grid's Community
// column API: the Columns tool panel and the header column menu that carry this
// in AG Grid are Enterprise, so this is the small equivalent.
//
// The hosting view passes the grid's `api` once the grid is ready. The choice is
// kept in localStorage per grid: which columns are useful is a per-device view
// preference, like the sidebar width, not server state.
const props = defineProps({
  // The grid's api, handed over when the grid reports itself ready.
  api: { type: Object, default: null },
  // Identifies the grid whose columns these are, so each grid keeps its own set.
  storageKey: { type: String, required: true },
  label: { type: String, default: 'Columns' }
})

const STORAGE_PREFIX = 'agentic.gridColumns.'

const open = ref(false)
const columns = ref([])
const hiddenCount = ref(0)
const root = ref(null)

// The stored choice: a colId-to-visible map. A column with no entry is visible.
function readSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_PREFIX + props.storageKey) || '{}') || {}
  } catch {
    return {}
  }
}

function writeSaved(state) {
  try {
    localStorage.setItem(STORAGE_PREFIX + props.storageKey, JSON.stringify(state))
  } catch {
    // Storage can be full or blocked in private modes; losing the preference
    // costs nothing here.
  }
}

// The columns the user may show or hide: every column except the ones the grid
// marks `lockVisible` (a row's actions, say), with each one's current state.
function readColumns() {
  const api = props.api
  if (!api) return []
  return (api.getColumns() || [])
    .filter((column) => !column.getColDef().lockVisible)
    .map((column) => ({
      colId: column.getColId(),
      label: column.getColDef().headerName || column.getColId(),
      visible: column.isVisible()
    }))
}

function countHidden() {
  hiddenCount.value = columns.value.filter((column) => !column.visible).length
}

// Apply the stored choice to the grid, then read back what is shown. Called once
// the grid's api arrives; `setColumnsVisible` only touches visibility, so the
// sort and filter state is left alone.
function sync() {
  const api = props.api
  if (!api) {
    columns.value = []
    hiddenCount.value = 0
    return
  }
  for (const [colId, visible] of Object.entries(readSaved())) {
    api.setColumnsVisible([colId], visible !== false)
  }
  columns.value = readColumns()
  countHidden()
}

watch(
  () => props.api,
  (api) => {
    if (api) sync()
  },
  { immediate: true }
)

function toggle(column) {
  const api = props.api
  if (!api) return
  const visible = !column.visible
  api.setColumnsVisible([column.colId], visible)
  column.visible = visible
  const saved = readSaved()
  saved[column.colId] = visible
  writeSaved(saved)
  countHidden()
}

function showAll() {
  const api = props.api
  if (!api) return
  for (const column of columns.value) {
    if (column.visible) continue
    api.setColumnsVisible([column.colId], true)
    column.visible = true
  }
  writeSaved({})
  countHidden()
}

function onDocumentClick(event) {
  if (open.value && root.value && !root.value.contains(event.target)) open.value = false
}

function onKeydown(event) {
  if (event.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div v-if="columns.length" ref="root" class="col-chooser">
    <button
      class="btn sm"
      type="button"
      aria-haspopup="true"
      :aria-expanded="open ? 'true' : 'false'"
      :title="label"
      @click="open = !open"
    >
      {{ label }}
      <span v-if="hiddenCount" class="faint">· {{ hiddenCount }} hidden</span>
    </button>
    <div v-if="open" class="col-chooser-menu" role="menu">
      <label v-for="column in columns" :key="column.colId" class="col-chooser-option">
        <input type="checkbox" :checked="column.visible" @change="toggle(column)" />
        <span>{{ column.label }}</span>
      </label>
      <button class="btn sm ghost col-chooser-reset" type="button" :disabled="!hiddenCount" @click="showAll">
        Show all
      </button>
    </div>
  </div>
</template>
