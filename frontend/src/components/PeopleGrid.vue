<script setup>
import { computed, shallowRef, watch } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import { gridTheme } from './gridSetup'
import { NameCell } from './peopleCells'

// The people list as a data grid (AG Grid), the same treatment the repository
// views get: per-column sorting, text and number filters, and the name as a link.
const props = defineProps({
  // The enriched person rows to display (see the view's rows).
  rows: { type: Array, default: () => [] },
  // The router-link component, resolved by the view, so the name cell can link
  // to a person inside the SPA.
  routerLink: { type: [Object, Function], required: true }
})
const emit = defineEmits(['count'])

const components = { name: NameCell }

const context = computed(() => ({ RouterLink: props.routerLink }))

const columnDefs = [
  // The list opens alphabetical by name.
  { headerName: 'Name', field: 'name', flex: 1, minWidth: 200, cellRenderer: 'name', sort: 'asc' },
  {
    headerName: 'Aliases',
    colId: 'aliases',
    valueGetter: (p) => p.data.aliases_line,
    minWidth: 240,
    cellClass: 'faint'
  },
  {
    headerName: 'Tasks',
    colId: 'tasks',
    valueGetter: (p) => p.data.task_count,
    width: 100,
    filter: 'agNumberColumnFilter'
  },
  {
    headerName: 'Items',
    colId: 'items',
    valueGetter: (p) => p.data.item_count,
    width: 100,
    filter: 'agNumberColumnFilter'
  }
]

const defaultColDef = { sortable: true, resizable: true, minWidth: 90, filter: true }

function getRowId(params) {
  return params.data.id
}

// The grid does not pick up a replaced rowData prop on its own here, so apply
// it through the API whenever the rows change.
const gridApi = shallowRef(null)

function onGridReady(event) {
  gridApi.value = event.api
}

// How many rows the grid currently shows, so the view's header can report it.
function onModelUpdated(event) {
  emit('count', event.api.getDisplayedRowCount())
}

watch(
  () => props.rows,
  (rows) => gridApi.value?.setGridOption('rowData', rows)
)
</script>

<template>
  <ag-grid-vue
    class="repo-grid"
    :theme="gridTheme"
    :components="components"
    :context="context"
    :column-defs="columnDefs"
    :default-col-def="defaultColDef"
    :row-data="rows"
    :get-row-id="getRowId"
    :animate-rows="false"
    :enable-filter-handlers="true"
    dom-layout="normal"
    @grid-ready="onGridReady"
    @model-updated="onModelUpdated"
  />
</template>
