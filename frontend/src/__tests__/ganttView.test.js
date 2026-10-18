import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  itemsList: vi.fn(),
  itemsRefresh: vi.fn(),
  itemsRemove: vi.fn(),
  tasksAssociate: vi.fn(),
  tasksUpdate: vi.fn(),
  tasksBulkUpdate: vi.fn(),
  ganttGet: vi.fn(),
  peopleList: vi.fn(),
  push: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    items: { list: mocks.itemsList, refresh: mocks.itemsRefresh, remove: mocks.itemsRemove },
    tasks: { associate: mocks.tasksAssociate, update: mocks.tasksUpdate, bulkUpdate: mocks.tasksBulkUpdate },
    gantt: { get: mocks.ganttGet },
    people: { list: mocks.peopleList }
  }
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }) }))

import GanttView from '../views/GanttView.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }

const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  store.tagFilter = ''
  store.personFilter = ''
  store.statusFilter = ''
  store.tags = []
  store.people = []
  mocks.peopleList.mockResolvedValue([])
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('GanttView', () => {
  const rows = [
    {
      id: 't1',
      title: 'Task One',
      status: 'in_progress',
      priority: 2,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
      markers: [
        { id: 'm1', type: 'created', message: 'created', created_at: '2026-01-01T00:00:00Z' },
        { id: 'm2', type: 'updated', message: 'updated', created_at: '2026-01-02T00:00:00Z' }
      ]
    }
  ]

  it('renders rows, markers, and a legend', async () => {
    mocks.ganttGet.mockResolvedValue(rows)
    const wrapper = mount(GanttView, stub)
    await flushPromises()
    expect(mocks.ganttGet).toHaveBeenCalledWith({ includeDone: false })
    expect(wrapper.text()).toContain('Task One')
    expect(wrapper.findAll('.gantt-marker')).toHaveLength(2)
    expect(wrapper.findAll('.legend-item').length).toBeGreaterThanOrEqual(2)
  })

  it('reloads including done tasks', async () => {
    mocks.ganttGet.mockResolvedValue([])
    const wrapper = mount(GanttView, stub)
    await flushPromises()
    await wrapper.get('input[type=checkbox]').setValue(true)
    await flushPromises()
    expect(mocks.ganttGet).toHaveBeenLastCalledWith({ includeDone: true })
  })

  it('shows an error with a working retry', async () => {
    mocks.ganttGet.mockRejectedValueOnce(new Error('offline'))
    const wrapper = mount(GanttView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('offline')

    mocks.ganttGet.mockResolvedValue(rows)
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Retry')
      .trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Task One')
  })

  it('warns when the picked range is invalid', async () => {
    mocks.ganttGet.mockResolvedValue(rows)
    const wrapper = mount(GanttView, stub)
    await flushPromises()

    const [start, end] = wrapper.findAll('input[type="datetime-local"]')
    await start.setValue('2030-01-02T00:00:00')
    await end.setValue('2030-01-01T00:00:00')
    expect(wrapper.text()).toContain('End must be after start')
  })
})
