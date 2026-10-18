import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  peopleList: vi.fn(),
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
    items: { list: mocks.itemsList }
  }
}))

import PeopleSelect from '../components/PeopleSelect.vue'
import SearchSelect from '../components/SearchSelect.vue'
import { store } from '../store'

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  store.toast = null
  store.tasks = []
  store.people = []
  mocks.peopleList.mockResolvedValue([])
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  vi.spyOn(store, 'loadTasks').mockResolvedValue()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('PeopleSelect', () => {
  const task = (over = {}) => ({
    id: 't1',
    people: [{ id: 'p1', name: 'Ada' }],
    ...over
  })

  it('renders the linked people and the empty state', () => {
    const wrapper = mount(PeopleSelect, { props: { task: task() } })
    expect(wrapper.text()).toContain('Ada')

    const empty = mount(PeopleSelect, { props: { task: task({ people: [] }) } })
    expect(empty.text()).toContain('no people')
  })

  it('links an existing person', async () => {
    store.people = [
      { id: 'p1', name: 'Ada' },
      { id: 'p2', name: 'Grace' }
    ]
    mocks.linkTask.mockResolvedValue({})
    const wrapper = mount(PeopleSelect, { props: { task: task() } })
    expect(wrapper.findComponent(SearchSelect).props('keepOpen')).toBe(true)
    wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'p2')
    await flushPromises()
    expect(mocks.linkTask).toHaveBeenCalledWith('t1', { person_id: 'p2' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('removes a person', async () => {
    mocks.unlinkTask.mockResolvedValue(null)
    const wrapper = mount(PeopleSelect, { props: { task: task() } })
    await wrapper.get('.chip-x').trigger('click')
    await flushPromises()
    expect(mocks.unlinkTask).toHaveBeenCalledWith('t1', 'p1')
  })

  it('notifies on failure', async () => {
    mocks.linkTask.mockRejectedValueOnce(new Error('bad'))
    store.people = [{ id: 'p2', name: 'Grace' }]
    const wrapper = mount(PeopleSelect, { props: { task: task({ people: [] }) } })
    wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'p2')
    await flushPromises()
    expect(store.toast).toEqual({ message: 'bad', isError: true })
  })

  it('suggests people named by linked items and links them on click', async () => {
    mocks.linkTask.mockResolvedValue({})
    const wrapper = mount(PeopleSelect, {
      props: {
        task: task({ people: [], suggested_people: [{ id: 'p2', name: 'Grace' }] })
      }
    })
    await wrapper.get('.chip-add').trigger('click')
    await flushPromises()
    expect(mocks.linkTask).toHaveBeenCalledWith('t1', { person_id: 'p2' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('hides a suggestion that is already linked', () => {
    const wrapper = mount(PeopleSelect, {
      props: {
        task: task({
          people: [{ id: 'p2', name: 'Grace' }],
          suggested_people: [{ id: 'p2', name: 'Grace' }]
        })
      }
    })
    expect(wrapper.find('.chip-add').exists()).toBe(false)
  })

  it('renders and links the requesters when kind is requesters', async () => {
    store.people = [
      { id: 'p1', name: 'Ada' },
      { id: 'p2', name: 'Grace' }
    ]
    mocks.linkRequester.mockResolvedValue({})
    const wrapper = mount(PeopleSelect, {
      props: { task: task({ requesters: [{ id: 'p1', name: 'Ada' }] }), kind: 'requesters' }
    })
    expect(wrapper.text()).toContain('Ada')
    wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'p2')
    await flushPromises()
    expect(mocks.linkRequester).toHaveBeenCalledWith('t1', { person_id: 'p2' })
    expect(mocks.linkTask).not.toHaveBeenCalled()
  })

  it('removes a requester', async () => {
    mocks.unlinkRequester.mockResolvedValue(null)
    const wrapper = mount(PeopleSelect, {
      props: { task: task({ requesters: [{ id: 'p1', name: 'Ada' }] }), kind: 'requesters' }
    })
    await wrapper.get('.chip-x').trigger('click')
    await flushPromises()
    expect(mocks.unlinkRequester).toHaveBeenCalledWith('t1', 'p1')
  })

  it('does not offer item suggestions for requesters', () => {
    const wrapper = mount(PeopleSelect, {
      props: {
        task: task({ requesters: [], suggested_people: [{ id: 'p2', name: 'Grace' }] }),
        kind: 'requesters'
      }
    })
    expect(wrapper.find('.chip-add').exists()).toBe(false)
  })
})
