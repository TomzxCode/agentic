<script setup>
import { computed, shallowRef, watch } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import { gridTheme } from './gridSetup'
import { BranchCell, LinksCell, NameCell, RemoveCell } from './repositoriesCells'
import ValuesFilter from './ValuesFilter.vue'

// The repositories list as a data grid (AG Grid), the same treatment the
// repository detail view's issues and PRs get: per-column sorting, text and
// number filters, and a multi-select value filter for the discrete columns.
const props = defineProps({
  // The enriched repository rows to display (see the view's rows).
  rows: { type: Array, default: () => [] },
  // The router-link component, resolved by the view, so the name cell can link
  // to a repository inside the SPA.
  routerLink: { type: [Object, Function], required: true }
})
const emit = defineEmits(['remove', 'count', 'ready'])

const components = {
  valuesFilter: ValuesFilter,
  name: NameCell,
  branch: BranchCell,
  links: LinksCell,
  actions: RemoveCell
}

const context = computed(() => ({
  RouterLink: props.routerLink,
  onRemove: (row) => emit('remove', row)
}))

// A multi-select value filter for a column, matching rows that carry any of the
// selected values. `getValues` lists the values a row holds for the column;
// both functions are defined once, so the column definitions stay stable.
function valuesFilter(getValues) {
  return {
    filter: {
      component: 'valuesFilter',
      doesFilterPass: ({ model, data }) => !model || getValues(data).some((value) => model.values.includes(value))
    },
    filterParams: { getValues }
  }
}

const defaultColDef = {
  sortable: true,
  resizable: true,
  minWidth: 90,
  filter: true
}

const columnDefs = [
  {
    headerName: 'Name',
    field: 'name',
    flex: 1,
    minWidth: 220,
    cellRenderer: 'name',
    // The list opens alphabetical by name, as it did before.
    sort: 'asc'
  },
  { headerName: 'Links', width: 120, sortable: false, filter: false, cellRenderer: 'links' },
  { headerName: 'Path', field: 'path', minWidth: 220, cellClass: 'faint mono' },
  {
    headerName: 'Branch',
    width: 120,
    cellRenderer: 'branch',
    ...valuesFilter((data) => [data.default_branch])
  },
  { headerName: 'Issues', valueGetter: (p) => p.data.issue_count, width: 100, filter: 'agNumberColumnFilter' },
  { headerName: 'PRs', valueGetter: (p) => p.data.pull_count, width: 90, filter: 'agNumberColumnFilter' },
  { headerName: 'States', valueGetter: (p) => p.data.states_line, minWidth: 180, cellClass: 'faint' },
  { headerName: 'Remote', valueGetter: (p) => p.data.remote_url, minWidth: 220, cellClass: 'faint' },
  {
    headerName: 'Added',
    valueGetter: (p) => p.data.added_at,
    valueFormatter: (p) => p.data.added,
    width: 130,
    filter: false
  },
  { headerName: 'Actions', width: 130, sortable: false, filter: false, lockVisible: true, cellRenderer: 'actions' }
]

function getRowId(params) {
  return params.data.id
}

// The grid does not pick up a replaced rowData prop on its own here, so apply
// it through the API whenever the rows change.
const gridApi = shallowRef(null)

function onGridReady(event) {
  gridApi.value = event.api
  // The hosting view's column chooser needs the api to read and hide columns.
  emit('ready', event.api)
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
