import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  peopleList: vi.fn(),
  slackUsers: vi.fn(),
  peopleGet: vi.fn(),
  peopleCreate: vi.fn(),
  peopleUpdate: vi.fn(),
  peopleRemove: vi.fn(),
  peopleMerge: vi.fn(),
  linkTask: vi.fn(),
  unlinkTask: vi.fn(),
  linkRequester: vi.fn(),
  unlinkRequester: vi.fn(),
  linkItem: vi.fn(),
  unlinkItem: vi.fn(),
  itemsList: vi.fn()
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.push })
}))

vi.mock('../api', () => ({
  api: {
    people: {
      list: mocks.peopleList,
      get: mocks.peopleGet,
      create: mocks.peopleCreate,
      update: mocks.peopleUpdate,
      remove: mocks.peopleRemove,
      merge: mocks.peopleMerge,
      linkTask: mocks.linkTask,
      unlinkTask: mocks.unlinkTask,
      linkRequester: mocks.linkRequester,
      unlinkRequester: mocks.unlinkRequester,
      linkItem: mocks.linkItem,
      unlinkItem: mocks.unlinkItem
    },
    slack: { users: mocks.slackUsers },
    items: { list: mocks.itemsList }
  }
}))

import PeopleView from '../views/PeopleView.vue'
import { AgGridVue } from 'ag-grid-vue3'
import { formatDateTime, store } from '../store'

const RouterLinkStub = {
  props: ['to'],
  template: '<a :href="typeof to === \'string\' ? to : to.path"><slot /></a>'
}

const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  store.toast = null
  store.tasks = []
  store.people = []
  mocks.peopleList.mockResolvedValue([])
  mocks.slackUsers.mockResolvedValue({ names: {} })
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  vi.spyOn(store, 'loadTasks').mockResolvedValue()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('PeopleView', () => {
  beforeEach(() => {
    store.people = [
      {
        id: 'p1',
        name: 'Ada',
        aliases: ['ada', 'ada@example.com'],
        task_count: 1,
        item_count: 1,
        created_at: '2026-01-01T00:00:00Z'
      }
    ]
  })

  // AG Grid renders its rows and cells asynchronously.
  const settle = async () => {
    await flushPromises()
    await new Promise((resolve) => setTimeout(resolve, 20))
  }

  const mountPeople = async () => {
    const wrapper = mount(PeopleView, stub)
    await settle()
    return wrapper
  }

  it('lists people, each linking to their detail page', async () => {
    const wrapper = await mountPeople()
    expect(wrapper.text()).toContain('Ada')
    expect(wrapper.text()).toContain('@ada')
    expect(wrapper.text()).toContain('ada@example.com')
    // The counts are their own columns.
    expect(wrapper.get('.ag-cell[col-id="tasks"]').text()).toBe('1')
    expect(wrapper.get('.ag-cell[col-id="items"]').text()).toBe('1')
    expect(wrapper.get('a.title').attributes('href')).toBe('/person/p1')
  })

  it('filters the list as a name is typed, matching aliases too', async () => {
    store.people = [
      { id: 'p1', name: 'Ada', aliases: ['ada', 'ada@example.com'], task_count: 0, item_count: 0 },
      { id: 'p2', name: 'Grace', aliases: ['grace-hopper'], task_count: 0, item_count: 0 }
    ]
    const wrapper = await mountPeople()
    const input = wrapper.get('input[placeholder="Add a person by name…"]')

    await input.setValue('gra')
    await settle()
    expect(wrapper.text()).toContain('Grace')
    expect(wrapper.text()).not.toContain('Ada')
    expect(wrapper.text()).toContain('1 of 2')

    // Typing part of an alias finds the person too, so a handle that already
    // belongs to someone is visible before a duplicate is created.
    await input.setValue('ada@exam')
    await settle()
    expect(wrapper.text()).toContain('Ada')
    expect(wrapper.text()).not.toContain('Grace')

    await input.setValue('')
    await settle()
    expect(wrapper.text()).toContain('Grace')
    expect(wrapper.text()).toContain('2 of 2')
  })

  it('shows when each person was created', async () => {
    const wrapper = await mountPeople()
    expect(wrapper.get('.ag-cell[col-id="created"]').text()).toBe(formatDateTime('2026-01-01T00:00:00Z'))
  })

  it('shows a Slack user id alias as the name slackx resolves it to', async () => {
    store.people = [
      {
        id: 'p1',
        name: 'Ada',
        aliases: ['U0123ABCDEF'],
        task_count: 0,
        item_count: 0,
        created_at: '2026-01-01T00:00:00Z'
      }
    ]
    mocks.slackUsers.mockResolvedValue({ names: { U0123ABCDEF: 'Tom Rochette' } })
    const wrapper = await mountPeople()
    expect(wrapper.get('.ag-cell[col-id="aliases"]').text()).toBe('Tom Rochette (@U0123ABCDEF)')
    // Only the alias that looks like a Slack user id is sent to the lookup.
    expect(mocks.slackUsers).toHaveBeenCalledWith(['U0123ABCDEF'])
  })

  it('keeps the raw Slack user id when slackx cannot resolve it', async () => {
    store.people = [
      {
        id: 'p1',
        name: 'Ada',
        aliases: ['U0123ABCDEF'],
        task_count: 0,
        item_count: 0,
        created_at: '2026-01-01T00:00:00Z'
      }
    ]
    const wrapper = await mountPeople()
    expect(wrapper.get('.ag-cell[col-id="aliases"]').text()).toBe('@U0123ABCDEF')
  })

  it('hides a column through the chooser and remembers the choice', async () => {
    const wrapper = await mountPeople()
    const api = wrapper.getComponent(AgGridVue).vm.api
    expect(api.getColumn('created').isVisible()).toBe(true)

    await wrapper.get('.col-chooser > .btn').trigger('click')
    const option = wrapper.findAll('.col-chooser-option').find((entry) => entry.text() === 'Created')
    await option.get('input').setValue(false)
    await settle()

    expect(api.getColumn('created').isVisible()).toBe(false)
    expect(localStorage.getItem('agentic.gridColumns.people')).toContain('"created":false')
  })

  it('restores a saved column choice onto the grid', async () => {
    localStorage.setItem('agentic.gridColumns.people', JSON.stringify({ created: false }))
    const wrapper = await mountPeople()
    expect(wrapper.getComponent(AgGridVue).vm.api.getColumn('created').isVisible()).toBe(false)
  })

  it('creates a person', async () => {
    mocks.peopleCreate.mockResolvedValue({ id: 'p2', name: 'Grace', task_count: 0, item_count: 0 })
    const wrapper = await mountPeople()
    await wrapper.get('input[placeholder="Add a person by name…"]').setValue('Grace')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.peopleCreate).toHaveBeenCalledWith({ name: 'Grace' })
  })
})
