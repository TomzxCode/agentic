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

import ItemsView from '../views/ItemsView.vue'
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

describe('ItemsView', () => {
  beforeEach(() => {
    vi.spyOn(store, 'loadTasks').mockResolvedValue()
    store.tasks = [{ id: 't1', title: 'Task One', status: 'in_progress' }]
  })

  it('lists items, filters by source and search, and links tasks', async () => {
    mocks.itemsList.mockResolvedValue([
      {
        id: 'i1',
        source: 'github',
        kind: 'issue',
        title: 'Issue one',
        url: 'https://gh/1',
        content: 'body',
        task_ids: ['t1'],
        created_at: new Date().toISOString(),
        fetched_at: null
      },
      {
        id: 'i2',
        source: 'note',
        kind: '',
        title: 'A note',
        url: null,
        content: 'hello',
        task_ids: [],
        created_at: new Date().toISOString(),
        fetched_at: null
      }
    ])
    const wrapper = mount(ItemsView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('Issue one')
    expect(wrapper.text()).toContain('A note')
    // An item's title opens its own view.
    expect(wrapper.get('a.title[href="/items/i1"]').text()).toBe('Issue one')
    // The linked task chip shows the task's status as an icon.
    expect(wrapper.find('.task-status.st-in_progress').exists()).toBe(true)

    await wrapper
      .findAll('button')
      .find((b) => b.text().startsWith('Note'))
      .trigger('click')
    expect(wrapper.text()).not.toContain('Issue one')

    await wrapper
      .findAll('button')
      .find((b) => b.text().startsWith('All'))
      .trigger('click')
    await wrapper.get('input.input').setValue('issue')
    expect(wrapper.text()).toContain('Issue one')
    expect(wrapper.text()).not.toContain('A note')

    await wrapper.get('input.input').setValue('')
    expect(wrapper.get('a[href="/task/t1"]').text()).toContain('Task One')
  })

  it('refreshes and removes an item', async () => {
    mocks.itemsList.mockResolvedValue([
      {
        id: 'i1',
        source: 'github',
        kind: 'issue',
        title: 'Issue one',
        url: null,
        content: '',
        task_ids: [],
        created_at: new Date().toISOString(),
        fetched_at: null
      }
    ])
    mocks.itemsRefresh.mockResolvedValue({ id: 'i1', title: 'Refreshed' })
    mocks.itemsRemove.mockResolvedValue(null)
    vi.stubGlobal('confirm', () => true)

    const wrapper = mount(ItemsView, stub)
    await flushPromises()
    await wrapper.get('button[title="Refresh"]').trigger('click')
    await flushPromises()
    expect(mocks.itemsRefresh).toHaveBeenCalledWith('i1')
    expect(wrapper.text()).toContain('Refreshed')

    await wrapper.get('button[title="Delete"]').trigger('click')
    await flushPromises()
    expect(mocks.itemsRemove).toHaveBeenCalledWith('i1')
    expect(wrapper.text()).toContain('No resources')
  })

  it('offers a note no refresh and no person linker', async () => {
    mocks.itemsList.mockResolvedValue([
      {
        id: 'i2',
        source: 'note',
        kind: '',
        title: 'A note',
        url: null,
        content: 'hello',
        task_ids: [],
        created_at: new Date().toISOString(),
        fetched_at: null
      }
    ])
    const wrapper = mount(ItemsView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('A note')
    // A note has no source to re-fetch and no author, so the list offers
    // neither a refresh nor a person linker for it.
    expect(wrapper.find('button[title="Refresh"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Link a person')
  })

  it('notifies when loading fails', async () => {
    mocks.itemsList.mockRejectedValueOnce(new Error('offline'))
    mount(ItemsView, stub)
    await flushPromises()
    expect(store.toast).toEqual({ message: 'offline', isError: true })
  })

  it('shows the fetched status of a pull request item', async () => {
    mocks.itemsList.mockResolvedValue([
      {
        id: 'i1',
        source: 'github',
        kind: 'pull_request',
        title: 'Fix the thing',
        url: 'https://gh/pull/3',
        content: '',
        metadata_json: { state: 'MERGED' },
        task_ids: [],
        created_at: new Date().toISOString(),
        fetched_at: null
      }
    ])
    const wrapper = mount(ItemsView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('pull request')
    expect(wrapper.get('.badge.st-merged').text()).toBe('Merged')
  })

  it('links an unlinked item to a task', async () => {
    mocks.itemsList.mockResolvedValue([
      {
        id: 'i1',
        source: 'note',
        kind: '',
        title: 'A note',
        url: null,
        content: 'hello',
        task_ids: [],
        created_at: new Date().toISOString(),
        fetched_at: null
      }
    ])
    mocks.tasksAssociate.mockResolvedValue({})
    const wrapper = mount(ItemsView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('not linked to a task')

    await wrapper.get('.ss-trigger').trigger('click')
    // The picker shows each task's status icon.
    expect(wrapper.find('.ss-option .task-status').exists()).toBe(true)
    await wrapper.get('.ss-option').trigger('click')
    await flushPromises()

    expect(mocks.tasksAssociate).toHaveBeenCalledWith('t1', { item_id: 'i1' })
    expect(wrapper.text()).toContain('Task One')
    expect(store.toast).toEqual({ message: 'Linked to task', isError: false })
  })
})
