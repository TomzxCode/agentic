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
  linkTask: vi.fn(),
  unlinkTask: vi.fn(),
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
      linkTask: mocks.linkTask,
      unlinkTask: mocks.unlinkTask,
      linkItem: mocks.linkItem,
      unlinkItem: mocks.unlinkItem
    },
    items: { list: mocks.itemsList }
  }
}))

import PeoplePanel from '../components/PeoplePanel.vue'
import PeopleView from '../views/PeopleView.vue'
import SearchSelect from '../components/SearchSelect.vue'
import EditableText from '../components/EditableText.vue'
import { store } from '../store'

beforeEach(() => {
  vi.clearAllMocks()
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

describe('PeoplePanel', () => {
  const task = (over = {}) => ({
    id: 't1',
    people: [{ id: 'p1', name: 'Ada' }],
    ...over
  })

  it('renders the people and the empty state', () => {
    const wrapper = mount(PeoplePanel, { props: { task: task() } })
    expect(wrapper.text()).toContain('Ada')

    const empty = mount(PeoplePanel, { props: { task: task({ people: [] }) } })
    expect(empty.text()).toContain('Nobody associated yet')
  })

  it('links an existing person', async () => {
    store.people = [
      { id: 'p1', name: 'Ada' },
      { id: 'p2', name: 'Grace' }
    ]
    mocks.linkTask.mockResolvedValue({})
    const wrapper = mount(PeoplePanel, { props: { task: task() } })
    wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'p2')
    await flushPromises()
    expect(mocks.linkTask).toHaveBeenCalledWith('t1', { person_id: 'p2' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('creates and links a new person', async () => {
    mocks.linkTask.mockResolvedValue({})
    const wrapper = mount(PeoplePanel, { props: { task: task() } })
    await wrapper.get('input.input').setValue('Alan')
    await wrapper.get('.btn').trigger('click')
    await flushPromises()
    expect(mocks.linkTask).toHaveBeenCalledWith('t1', { name: 'Alan' })
    expect(wrapper.get('input.input').element.value).toBe('')
  })

  it('removes a person', async () => {
    mocks.unlinkTask.mockResolvedValue(null)
    const wrapper = mount(PeoplePanel, { props: { task: task() } })
    await wrapper.get('.chip-x').trigger('click')
    await flushPromises()
    expect(mocks.unlinkTask).toHaveBeenCalledWith('t1', 'p1')
  })

  it('notifies on failure', async () => {
    mocks.linkTask.mockRejectedValueOnce(new Error('bad'))
    const wrapper = mount(PeoplePanel, { props: { task: task({ people: [] }) } })
    await wrapper.get('input.input').setValue('Alan')
    await wrapper.get('.btn').trigger('click')
    await flushPromises()
    expect(store.toast).toEqual({ message: 'bad', isError: true })
  })
})

describe('PeopleView', () => {
  beforeEach(() => {
    store.tasks = [{ id: 't1', title: 'Fix flaky test' }]
    mocks.itemsList.mockResolvedValue([{ id: 'i1', title: 'Issue 1' }])
    mocks.peopleList.mockResolvedValue([{ id: 'p1', name: 'Ada' }])
    mocks.peopleGet.mockResolvedValue({
      id: 'p1',
      name: 'Ada',
      email: 'ada@example.com',
      handle: 'ada',
      notes: '',
      task_ids: ['t1'],
      item_ids: ['i1']
    })
  })

  it('lists each person with their links', async () => {
    const wrapper = mount(PeopleView)
    await flushPromises()
    expect(mocks.peopleGet).toHaveBeenCalledWith('p1')
    expect(wrapper.text()).toContain('Ada')
    expect(wrapper.text()).toContain('Fix flaky test')
    expect(wrapper.text()).toContain('Issue 1')
  })

  it('creates a person', async () => {
    mocks.peopleCreate.mockResolvedValue({ id: 'p2', name: 'Grace', task_count: 0, item_count: 0 })
    const wrapper = mount(PeopleView)
    await flushPromises()
    await wrapper.findAll('input.input')[1].setValue('Grace')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.peopleCreate).toHaveBeenCalledWith({ name: 'Grace' })
  })

  it('renames a person', async () => {
    mocks.peopleUpdate.mockResolvedValue({})
    const wrapper = mount(PeopleView)
    await flushPromises()
    wrapper.findComponent(EditableText).vm.$emit('save', 'Ada L')
    await flushPromises()
    expect(mocks.peopleUpdate).toHaveBeenCalledWith('p1', { name: 'Ada L' })
  })

  it('deletes a person when confirmed', async () => {
    vi.stubGlobal('confirm', () => true)
    mocks.peopleRemove.mockResolvedValue(null)
    const wrapper = mount(PeopleView)
    await flushPromises()
    await wrapper.get('button.btn.danger').trigger('click')
    await flushPromises()
    expect(mocks.peopleRemove).toHaveBeenCalledWith('p1')
  })

  it('does not delete when the confirmation is declined', async () => {
    vi.stubGlobal('confirm', () => false)
    const wrapper = mount(PeopleView)
    await flushPromises()
    await wrapper.get('button.btn.danger').trigger('click')
    expect(mocks.peopleRemove).not.toHaveBeenCalled()
  })
})
