<script setup>
import { computed, shallowRef, watch } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import { statusLabel } from '../store'
import { gridTheme } from './gridSetup'
import {
  ActionsCell,
  AuthorCell,
  ChangesCell,
  KindCell,
  StateCell,
  TaskStatusCell,
  TasksCell,
  TitleCell
} from './repositoryItemsCells'
import ValuesFilter from './ValuesFilter.vue'

// The repository detail view's issues and PRs as a data grid (AG Grid). Rows
// arrive already enriched by the view; the cell renderers only display them, and
// the two row actions are emitted back to the view. The modules and theme come
// from gridSetup.js, shared with the other list grids.
const props = defineProps({
  // The enriched rows to display (see the view's tableRows).
  rows: { type: Array, default: () => [] },
  // The router-link component, resolved by the view, so the grid's cells can
  // keep internal navigation inside the SPA.
  routerLink: { type: [Object, Function], required: true }
})
const emit = defineEmits(['new-task', 'record-change'])

const theme = gridTheme

// AG Grid resolves these by name in the column definitions below. The value
// filter is a column filter, the rest are cell renderers.
const components = {
  valuesFilter: ValuesFilter,
  kind: KindCell,
  state: StateCell,
  title: TitleCell,
  author: AuthorCell,
  taskStatus: TaskStatusCell,
  tasks: TasksCell,
  changes: ChangesCell,
  actions: ActionsCell
}

// What every cell renderer gets besides its row: the router-link, and the two
// row actions routed back to the view.
const context = computed(() => ({
  RouterLink: props.routerLink,
  onNewTask: (row) => emit('new-task', row),
  onRecordChange: (row) => emit('record-change', row)
}))

const defaultColDef = {
  sortable: true,
  resizable: true,
  minWidth: 90,
  filter: true
  // No floating filter: each column's filter opens from the filter button in
  // its header, so the field only appears when the user asks for it.
}

// A multi-select value filter for a column, matching rows that carry any of the
// selected values. `getValues` lists the values a row holds for the column;
// `label` names a value for the checkbox list. Both are plain functions defined
// once, so the column definitions stay stable.
function valuesFilter(getValues, label) {
  return {
    filter: {
      component: 'valuesFilter',
      doesFilterPass: ({ model, data }) => !model || getValues(data).some((value) => model.values.includes(value))
    },
    filterParams: { getValues, label }
  }
}

const columnDefs = [
  {
    headerName: 'Kind',
    field: 'kind',
    width: 90,
    cellRenderer: 'kind',
    ...valuesFilter(
      (data) => [data.kind],
      (value) => (value === 'pr' ? 'PR' : 'issue')
    )
  },
  {
    headerName: '#',
    colId: 'number',
    valueGetter: (p) => Number(p.data.number) || null,
    width: 90,
    filter: 'agNumberColumnFilter'
  },
  { headerName: 'Title', field: 'title', flex: 1, minWidth: 260, cellRenderer: 'title' },
  {
    headerName: 'State',
    valueGetter: (p) => p.data.stateLabel,
    width: 110,
    cellRenderer: 'state',
    ...valuesFilter((data) => [data.stateLabel])
  },
  {
    headerName: 'Author',
    valueGetter: (p) => p.data.authorLabel,
    width: 150,
    cellRenderer: 'author',
    ...valuesFilter((data) => [data.authorLabel])
  },
  {
    headerName: 'Tasks',
    width: 220,
    sortable: false,
    // The column shows chips, so it has no plain value to filter on; the task
    // titles are the value a text filter matches.
    valueGetter: (p) => p.data.tasks.map((task) => task.title).join(' '),
    cellRenderer: 'tasks'
  },
  {
    headerName: 'Task status',
    colId: 'taskStatus',
    width: 160,
    // Sorts on the joined labels; the value filter matches any of the row's
    // task statuses.
    valueGetter: (p) => p.data.statuses.map((entry) => entry.label).join(' '),
    cellRenderer: 'taskStatus',
    ...valuesFilter((data) => data.statuses.map((entry) => entry.status), statusLabel)
  },
  { headerName: 'Changes', width: 200, sortable: false, filter: false, cellRenderer: 'changes' },
  { headerName: 'Actions', width: 220, sortable: false, filter: false, cellRenderer: 'actions' }
]

function getRowId(params) {
  return params.data.key
}

// The grid does not pick up a replaced rowData prop on its own here, so apply
// it through the API whenever the filtered rows change.
const gridApi = shallowRef(null)

function onGridReady(event) {
  gridApi.value = event.api
}

watch(
  () => props.rows,
  (rows) => gridApi.value?.setGridOption('rowData', rows)
)
</script>

<template>
  <ag-grid-vue
    class="repo-grid"
    :theme="theme"
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
  />
</template>
