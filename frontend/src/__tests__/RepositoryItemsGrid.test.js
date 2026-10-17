import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { AgGridVue } from 'ag-grid-vue3'
import RepositoryItemsGrid from '../components/RepositoryItemsGrid.vue'

// A minimal router-link stand-in: the grid is handed the component to use, so a
// test passes this in instead of mounting a router.
const LinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }

// A settled grid: AG Grid renders rows and their cells asynchronously.
const settle = async () => {
  await flushPromises()
  await new Promise((resolve) => setTimeout(resolve, 30))
}

const baseRow = (overrides) => ({
  key: 'issue:1',
  kind: 'issue',
  number: '1',
  title: 'Open issue',
  url: 'https://github.com/acme/api/issues/1',
  stateLabel: 'Open',
  stateClass: 'st-open',
  authorLabel: '',
  personId: '',
  tasks: [],
  statuses: [],
  changes: [],
  canCreate: false,
  canRecord: false,
  busy: false,
  fetched: '',
  raw: { id: 'i1' },
  ...overrides
})

const mountGrid = async (rows) => {
  const wrapper = mount(RepositoryItemsGrid, {
    props: { rows, routerLink: LinkStub },
    attachTo: document.body
  })
  await settle()
  return wrapper
}

describe('RepositoryItemsGrid', () => {
  it('renders each row as a kind badge, state badge, title link, and number', async () => {
    const wrapper = await mountGrid([baseRow({})])

    expect(wrapper.get('.badge.st-open').text()).toBe('Open')
    expect(wrapper.findAll('.badge').map((b) => b.text())).toEqual(['issue', 'Open'])
    expect(wrapper.get('a[href="https://github.com/acme/api/issues/1"]').text()).toBe('Open issue')
  })

  it('links an author to the person carrying the login', async () => {
    const wrapper = await mountGrid([baseRow({ authorLabel: '@alice', personId: 'p1' })])
    expect(wrapper.get('a[href="/person/p1"]').text()).toBe('@alice')
  })

  it('shows the tasks a row is associated with as chips', async () => {
    const wrapper = await mountGrid([baseRow({ tasks: [{ id: 't1', title: 'Task One', status: 'open' }] })])
    expect(wrapper.get('a[href="/task/t1"]').text()).toContain('Task One')
  })

  it("shows the statuses of a row's tasks", async () => {
    const wrapper = await mountGrid([
      baseRow({
        tasks: [
          { id: 't1', title: 'Task One', status: 'open' },
          { id: 't2', title: 'Task Two', status: 'done' }
        ],
        statuses: [
          { status: 'open', label: 'Open' },
          { status: 'done', label: 'Done' }
        ]
      })
    ])
    const cell = wrapper.get('.ag-cell[col-id="taskStatus"]')
    expect(cell.text()).toContain('Open')
    expect(cell.text()).toContain('Done')
  })

  it('emits new-task when the create button is clicked', async () => {
    const raw = { url: 'https://github.com/acme/api/issues/1' }
    const wrapper = await mountGrid([baseRow({ canCreate: true, raw })])
    await wrapper.get('button[title="Create a task from this issue"]').trigger('click')
    expect(wrapper.emitted('new-task')?.[0]).toEqual([raw])
  })

  it('emits record-change when the record button is clicked', async () => {
    const raw = { id: 'i5' }
    const wrapper = await mountGrid([baseRow({ kind: 'pr', canRecord: true, raw })])
    await wrapper.get('button[title="Record a change for this PR"]').trigger('click')
    expect(wrapper.emitted('record-change')?.[0]).toEqual([raw])
  })

  it('sorts the rows when a column header is clicked', async () => {
    const wrapper = await mountGrid([
      baseRow({ key: 'issue:2', number: '2', title: 'two' }),
      baseRow({ key: 'issue:3', number: '3', title: 'three' })
    ])

    const header = wrapper.findAll('.ag-header-cell').find((h) => h.text().includes('#'))
    await header.get('.ag-header-cell-label').trigger('click')
    await settle()

    // Ascending by number puts #2 before #3.
    const numbers = wrapper.findAll('.ag-cell[col-id="number"]').map((c) => c.text())
    expect(numbers).toEqual(['2', '3'])
  })

  it('shows no filter field until the column filter button is used', async () => {
    const wrapper = await mountGrid([
      baseRow({ key: 'issue:1', number: '1', title: 'alpha' }),
      baseRow({ key: 'issue:2', number: '2', title: 'beta' })
    ])

    // No filter field is on screen; each header carries the button that opens
    // one.
    expect(wrapper.find('.ag-filter').exists()).toBe(false)
    expect(wrapper.find('.ag-floating-filter').exists()).toBe(false)
    expect(wrapper.find('.ag-header-cell[col-id="title"] .ag-header-cell-filter-button').exists()).toBe(true)

    // Applying a column filter narrows the rows.
    const api = wrapper.getComponent(AgGridVue).vm.api
    await api.setFilterModel({ title: { filterType: 'text', type: 'contains', filter: 'alpha' } })
    await settle()

    expect(wrapper.text()).toContain('alpha')
    expect(wrapper.text()).not.toContain('beta')
  })

  it('filters rows by a multi-select value filter', async () => {
    const wrapper = await mountGrid([
      baseRow({ key: 'issue:1', number: '1', kind: 'issue', title: 'an issue' }),
      baseRow({ key: 'pr:2', number: '2', kind: 'pr', title: 'a pull request' })
    ])
    const api = wrapper.getComponent(AgGridVue).vm.api

    await api.setFilterModel({ kind: { values: ['pr'] } })
    await settle()
    expect(wrapper.text()).toContain('a pull request')
    expect(wrapper.text()).not.toContain('an issue')

    // Selecting more than one value keeps the rows carrying any of them.
    await api.setFilterModel({ kind: { values: ['issue', 'pr'] } })
    await settle()
    expect(wrapper.text()).toContain('an issue')
    expect(wrapper.text()).toContain('a pull request')
  })

  it('filters rows by any of the selected task statuses', async () => {
    const wrapper = await mountGrid([
      baseRow({ key: 'issue:1', number: '1', title: 'done work', statuses: [{ status: 'done', label: 'Done' }] }),
      baseRow({ key: 'issue:2', number: '2', title: 'open work', statuses: [{ status: 'open', label: 'Open' }] }),
      baseRow({
        key: 'pr:3',
        number: '3',
        title: 'mixed work',
        statuses: [
          { status: 'open', label: 'Open' },
          { status: 'done', label: 'Done' }
        ]
      })
    ])
    const api = wrapper.getComponent(AgGridVue).vm.api

    await api.setFilterModel({ taskStatus: { values: ['done'] } })
    await settle()

    expect(wrapper.text()).toContain('done work')
    expect(wrapper.text()).toContain('mixed work')
    expect(wrapper.text()).not.toContain('open work')
  })
})
