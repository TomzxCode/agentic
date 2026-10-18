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

import TasksView from '../views/TasksView.vue'
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

describe('TasksView', () => {
  beforeEach(() => {
    vi.spyOn(store, 'loadTasks').mockResolvedValue()
  })

  it('counts statuses and lists in-flight tasks by default', async () => {
    store.tasks = [
      {
        id: 't1',
        status: 'open',
        priority: 2,
        title: 'One',
        summary: 's',
        next_steps: [{ text: 'n', done: false }],
        updated_at: null
      },
      { id: 't2', status: 'in_progress', priority: 3, title: 'Two', next_steps: [], updated_at: null },
      { id: 't3', status: 'done', priority: 1, title: 'Three', next_steps: [], updated_at: null }
    ]
    const wrapper = mount(TasksView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('Open 1')
    expect(wrapper.text()).toContain('In progress 1')
    expect(wrapper.text()).toContain('Done 1')
    expect(store.loadTasks).toHaveBeenCalled()

    const rows = wrapper.findAll('.item').map((item) => item.text())
    expect(rows.some((text) => text.includes('One'))).toBe(true)
    expect(rows.some((text) => text.includes('Three'))).toBe(false)
  })

  it('filters the list by status from the badges at the top', async () => {
    store.tasks = [
      { id: 't1', status: 'open', priority: 2, title: 'One', next_steps: [], updated_at: null },
      { id: 't2', status: 'blocked', priority: 1, title: 'Two', next_steps: [], updated_at: null },
      { id: 't3', status: 'done', priority: 3, title: 'Three', next_steps: [], updated_at: null }
    ]
    const wrapper = mount(TasksView, stub)
    await flushPromises()

    const badges = wrapper.findAll('.status-badge')
    expect(badges.map((b) => b.text())).toEqual(['Open 1', 'In progress 0', 'Blocked 1', 'Done 1', 'Archived 0'])

    // Clicking "Blocked" narrows the list to blocked tasks and reads as active.
    await badges[2].trigger('click')
    expect(store.statusFilter).toBe('blocked')
    let rows = wrapper.findAll('.select-item').map((item) => item.text())
    expect(rows.some((text) => text.includes('Two'))).toBe(true)
    expect(rows.some((text) => text.includes('One'))).toBe(false)
    expect(wrapper.get('.status-badge.active').text()).toContain('Blocked')

    // Clicking the active badge again returns to the in-flight list.
    await wrapper.get('.status-badge.active').trigger('click')
    expect(store.statusFilter).toBe('')
    rows = wrapper.findAll('.select-item').map((item) => item.text())
    expect(rows.some((text) => text.includes('One'))).toBe(true)
    expect(rows.some((text) => text.includes('Three'))).toBe(false)

    // "Done" is normally hidden, so its badge is the only way to see those tasks.
    await wrapper.findAll('.status-badge')[3].trigger('click')
    expect(store.statusFilter).toBe('done')
    rows = wrapper.findAll('.select-item').map((item) => item.text())
    expect(rows).toHaveLength(1)
    expect(rows[0]).toContain('Three')
  })

  it('shows a status-specific empty state and clears it', async () => {
    store.statusFilter = 'blocked'
    store.tasks = [{ id: 't1', status: 'open', title: 'One', next_steps: [], updated_at: null }]
    const wrapper = mount(TasksView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('No blocked tasks')
    await wrapper.get('.panel .btn.ghost').trigger('click')
    expect(store.statusFilter).toBe('')
  })

  it('shows how long ago each task was created alongside its last update', async () => {
    const ago = (ms) => new Date(Date.now() - ms).toISOString()
    store.tasks = [
      {
        id: 't1',
        status: 'open',
        title: 'Old but active',
        next_steps: [],
        created_at: ago(3 * 86400_000),
        updated_at: ago(5 * 60_000)
      },
      {
        id: 't2',
        status: 'open',
        title: 'Fresh',
        next_steps: [],
        created_at: ago(5 * 60_000),
        updated_at: ago(5 * 60_000)
      }
    ]
    const wrapper = mount(TasksView, stub)
    await flushPromises()

    const rows = wrapper.findAll('.select-item').map((item) => item.text())
    expect(rows[0]).toContain('created 3d ago · updated 5m ago')
    // Not touched since it was created: the two collapse into one.
    expect(rows[1]).toContain('created 5m ago')
    expect(rows[1]).not.toContain('updated')
  })

  it('shows the getting-started panel when nothing is in flight', async () => {
    store.tasks = []
    const wrapper = mount(TasksView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('Get started')
  })

  it('filters by tag, counts the filtered set, and shows tag pills', async () => {
    store.tags = [
      { name: 'bug', count: 1 },
      { name: 'ui', count: 1 }
    ]
    store.tagFilter = 'bug'
    store.tasks = [
      { id: 't1', status: 'open', priority: 2, title: 'Bug task', next_steps: [], updated_at: null, tags: ['bug'] },
      { id: 't2', status: 'open', priority: 2, title: 'UI task', next_steps: [], updated_at: null, tags: ['ui'] }
    ]
    const wrapper = mount(TasksView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('Bug task')
    expect(wrapper.text()).not.toContain('UI task')
    expect(wrapper.text()).toContain('Open 1')
    expect(wrapper.findAll('.tag-filter').length).toBe(3) // All + two tags
    expect(wrapper.find('.tag-filter.active').text()).toContain('bug')
  })

  it('toggles the tag filter from a row pill and clears it', async () => {
    store.tags = [{ name: 'ui', count: 1 }]
    store.tasks = [
      { id: 't1', status: 'open', priority: 2, title: 'UI task', next_steps: [], updated_at: null, tags: ['ui'] }
    ]
    const wrapper = mount(TasksView, stub)
    await flushPromises()

    await wrapper.get('.item button.tag-chip').trigger('click')
    expect(store.tagFilter).toBe('ui')
    await wrapper.get('.tag-filter').trigger('click') // "All"
    expect(store.tagFilter).toBe('')
  })

  it('filters in-flight tasks by linked person and clears it', async () => {
    mocks.peopleList.mockResolvedValue([
      { id: 'p1', name: 'Ada' },
      { id: 'p2', name: 'Grace' },
      { id: 'p3', name: 'Unlinked' }
    ])
    store.tasks = [
      { id: 't1', status: 'open', title: 'Ada task', next_steps: [], updated_at: null, person_ids: ['p1'] },
      { id: 't2', status: 'open', title: 'Grace task', next_steps: [], updated_at: null, person_ids: ['p2'] },
      { id: 't3', status: 'done', title: 'Closed', next_steps: [], updated_at: null, person_ids: ['p1'] }
    ]
    const wrapper = mount(TasksView, stub)
    await flushPromises()

    // Only people linked to an in-flight task get a button, with their count.
    const personRow = wrapper.get('[aria-label="Filter by person"]')
    const names = personRow.findAll('.tag-filter').map((b) => b.text())
    expect(names).toHaveLength(3) // Anyone + two people
    expect(names[1]).toContain('Ada')
    expect(names[2]).toContain('Grace')
    expect(personRow.text()).not.toContain('Unlinked')
    expect(personRow.findAll('.count').map((c) => c.text())).toEqual(['1', '1'])

    await personRow
      .findAll('.tag-filter')
      .find((b) => b.text().includes('Ada'))
      .trigger('click')
    expect(store.personFilter).toBe('p1')
    const rows = wrapper.findAll('.select-item').map((item) => item.text())
    expect(rows.some((text) => text.includes('Ada task'))).toBe(true)
    expect(rows.some((text) => text.includes('Grace task'))).toBe(false)
    expect(wrapper.text()).toContain('Open 1')

    await wrapper.get('[aria-label="Filter by person"] .tag-filter').trigger('click') // "Anyone"
    expect(store.personFilter).toBe('')
  })

  it('shows each linked person after the task title and filters on click', async () => {
    mocks.peopleList.mockResolvedValue([
      { id: 'p1', name: 'Ada' },
      { id: 'p2', name: 'Grace' }
    ])
    store.tasks = [
      { id: 't1', status: 'open', title: 'Shared task', next_steps: [], updated_at: null, person_ids: ['p1', 'p2'] }
    ]
    const wrapper = mount(TasksView, stub)
    await flushPromises()

    const row = wrapper.get('.select-item')
    const title = row.get('.title')
    // Each linked person renders as a chip, in link order, after the title.
    expect(row.findAll('.person-chip').map((c) => c.text())).toEqual(['Ada', 'Grace'])
    expect(title.element.compareDocumentPosition(row.get('.person-chip').element)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING
    )

    await row.get('.person-chip').trigger('click')
    expect(store.personFilter).toBe('p1')
    expect(row.get('.person-chip').classes()).toContain('active')
  })

  it('shows a person-specific empty state when no task matches the filter', async () => {
    mocks.peopleList.mockResolvedValue([{ id: 'p1', name: 'Ada' }])
    store.personFilter = 'p1'
    store.tasks = [{ id: 't1', status: 'open', title: 'Other', next_steps: [], updated_at: null, person_ids: [] }]
    const wrapper = mount(TasksView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('Nothing linked to "Ada"')
    await wrapper.get('.panel .btn.ghost').trigger('click')
    expect(store.personFilter).toBe('')
  })

  it('bulk edits the status and tags of selected in-flight tasks', async () => {
    store.tags = [{ name: 'bug', count: 1 }]
    store.tasks = [
      { id: 't1', status: 'open', priority: 2, title: 'One', next_steps: [], updated_at: null, tags: [] },
      { id: 't2', status: 'blocked', priority: 1, title: 'Two', next_steps: [], updated_at: null, tags: [] },
      { id: 't3', status: 'done', priority: 3, title: 'Three', next_steps: [], updated_at: null, tags: [] }
    ]
    mocks.tasksBulkUpdate.mockResolvedValue({ updated: [{ id: 't1' }, { id: 't2' }], missing: [] })

    const wrapper = mount(TasksView, stub)
    await flushPromises()

    // The selectable list is the default view; only in-flight tasks show.
    const selectable = wrapper.findAll('.select-item')
    expect(selectable).toHaveLength(2)
    expect(wrapper.text()).not.toContain('Three')

    // The bulk bar stays hidden until at least one task is selected.
    expect(wrapper.find('.bulk-bar').exists()).toBe(false)

    await wrapper.findAll('.select-item .row-check')[0].setValue(true)
    expect(wrapper.find('.bulk-bar').exists()).toBe(true)
    await wrapper.find('input[aria-label="Select every shown task"]').setValue(true)
    expect(wrapper.text()).toContain('2 selected')

    await wrapper.get('select.bulk-status').setValue('done')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Apply')
      .trigger('click')
    await flushPromises()

    expect(mocks.tasksBulkUpdate).toHaveBeenCalledWith({ ids: ['t1', 't2'], status: 'done' })
    expect(store.loadTasks).toHaveBeenCalled()
    expect(store.toast).toEqual({ message: 'Updated 2 tasks', isError: false })
  })

  it('changes a task status inline from its row, like the sidebar', async () => {
    store.tasks = [{ id: 't1', status: 'open', priority: 2, title: 'One', next_steps: [], updated_at: null }]
    mocks.tasksUpdate.mockResolvedValue({ id: 't1', status: 'blocked' })

    const wrapper = mount(TasksView, stub)
    await flushPromises()

    // The row shows an icon-only status picker, not a read-only icon.
    const select = wrapper.get('.select-item .task-status-select')
    await select.get('.ss-trigger').trigger('click')
    await wrapper
      .findAll('.ss-option')
      .find((o) => o.text().includes('Blocked'))
      .trigger('click')
    await flushPromises()

    expect(mocks.tasksUpdate).toHaveBeenCalledWith('t1', { status: 'blocked' })
    expect(store.tasks[0].status).toBe('blocked')
  })

  it('reverts a row status when the update fails', async () => {
    store.tasks = [{ id: 't1', status: 'open', priority: 2, title: 'One', next_steps: [], updated_at: null }]
    mocks.tasksUpdate.mockRejectedValue(new Error('offline'))

    const wrapper = mount(TasksView, stub)
    await flushPromises()

    const select = wrapper.get('.select-item .task-status-select')
    await select.get('.ss-trigger').trigger('click')
    await wrapper
      .findAll('.ss-option')
      .find((o) => o.text().includes('Blocked'))
      .trigger('click')
    await flushPromises()

    expect(store.tasks[0].status).toBe('open')
    expect(store.toast).toEqual({ message: 'offline', isError: true })
  })

  it('shows each task priority as an icon in its row', async () => {
    store.tasks = [
      { id: 't1', status: 'open', priority: 3, title: 'Urgent one', next_steps: [], updated_at: null },
      { id: 't2', status: 'open', priority: 0, title: 'Low one', next_steps: [], updated_at: null }
    ]

    const wrapper = mount(TasksView, stub)
    await flushPromises()

    const icons = wrapper.findAll('.select-item .task-priority')
    expect(icons).toHaveLength(2)
    expect(icons[0].classes()).toContain('prio-urgent')
    expect(icons[1].classes()).toContain('prio-low')
    expect(icons[0].attributes('title')).toBe('Priority: urgent')
  })

  it('changes a task priority inline from the circle in its row', async () => {
    store.tasks = [{ id: 't1', status: 'open', priority: 3, title: 'One', next_steps: [], updated_at: null }]
    mocks.tasksUpdate.mockResolvedValue({ id: 't1', priority: 0 })

    const wrapper = mount(TasksView, stub)
    await flushPromises()

    const select = wrapper.get('.select-item .task-priority-select')
    await select.get('.ss-trigger').trigger('click')
    await wrapper
      .findAll('.ss-option')
      .find((o) => o.text().includes('Low'))
      .trigger('click')
    await flushPromises()

    expect(mocks.tasksUpdate).toHaveBeenCalledWith('t1', { priority: 0 })
    expect(store.tasks[0].priority).toBe(0)
  })

  it('reverts a row priority when the update fails', async () => {
    store.tasks = [{ id: 't1', status: 'open', priority: 3, title: 'One', next_steps: [], updated_at: null }]
    mocks.tasksUpdate.mockRejectedValue(new Error('offline'))

    const wrapper = mount(TasksView, stub)
    await flushPromises()

    const select = wrapper.get('.select-item .task-priority-select')
    await select.get('.ss-trigger').trigger('click')
    await wrapper
      .findAll('.ss-option')
      .find((o) => o.text().includes('Low'))
      .trigger('click')
    await flushPromises()

    expect(store.tasks[0].priority).toBe(3)
    expect(store.toast).toEqual({ message: 'offline', isError: true })
  })

  it('shows an upcoming deadlines section for near, in-flight deadlines only', async () => {
    const soon = new Date(Date.now() + 3_600_000).toISOString()
    const far = new Date(Date.now() + 20 * 86_400_000).toISOString()
    store.tasks = [
      { id: 't1', status: 'open', priority: 2, title: 'DueSoon', deadline: soon, next_steps: [], updated_at: null },
      { id: 't2', status: 'open', priority: 2, title: 'DueLater', deadline: far, next_steps: [], updated_at: null },
      { id: 't3', status: 'done', priority: 2, title: 'Closed', deadline: soon, next_steps: [], updated_at: null }
    ]

    const wrapper = mount(TasksView, stub)
    await flushPromises()

    const section = wrapper.get('.deadline-panel')
    expect(section.text()).toContain('Upcoming deadlines')
    expect(section.text()).toContain('DueSoon')
    expect(section.text()).not.toContain('DueLater')
    expect(section.text()).not.toContain('Closed')

    // The window control narrows and widens the section.
    await section.get('select').setValue(30)
    await flushPromises()
    expect(wrapper.get('.deadline-panel').text()).toContain('DueLater')
  })
})
