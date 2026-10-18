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

import PersonView from '../views/PersonView.vue'
import SearchSelect from '../components/SearchSelect.vue'
import EditableText from '../components/EditableText.vue'
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
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  vi.spyOn(store, 'loadTasks').mockResolvedValue()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('PersonView', () => {
  beforeEach(() => {
    store.tasks = [{ id: 't1', title: 'Fix flaky test' }]
    mocks.itemsList.mockResolvedValue([
      { id: 'i1', title: 'Issue 1', source: 'github', metadata_json: { state: 'OPEN' } },
      { id: 'i2', title: 'A thread', source: 'slack' }
    ])
    mocks.peopleGet.mockResolvedValue({
      id: 'p1',
      name: 'Ada',
      aliases: ['ada', 'ada@example.com'],
      notes: '',
      created_at: '2026-01-02T03:04:00Z',
      task_ids: ['t1'],
      involved_task_ids: ['t1'],
      requester_task_ids: [],
      item_ids: ['i1', 'i2']
    })
  })

  it('shows when the person was created', async () => {
    const wrapper = mount(PersonView, { props: { id: 'p1' }, ...stub })
    await flushPromises()
    expect(wrapper.text()).toContain(`Created ${formatDateTime('2026-01-02T03:04:00Z')}`)
  })

  it('shows the aliases and relationships of a person', async () => {
    const wrapper = mount(PersonView, { props: { id: 'p1' }, ...stub })
    await flushPromises()
    expect(mocks.peopleGet).toHaveBeenCalledWith('p1')
    expect(wrapper.text()).toContain('Ada')
    expect(wrapper.text()).toContain('@ada')
    expect(wrapper.text()).toContain('ada@example.com')
    expect(wrapper.text()).toContain('Fix flaky test')
    // A task the person is one of the people on, not its requester.
    expect(wrapper.get('.role-label').text()).toBe('people')
    // Linked items are grouped by source, each group labelled with its type.
    expect(wrapper.text()).toContain('GitHub')
    expect(wrapper.text()).toContain('Slack')
    expect(wrapper.text()).toContain('Issue 1')
    expect(wrapper.text()).toContain('A thread')
    // A GitHub item shows its state; a Slack item shows a speech emoji.
    expect(wrapper.get('.badge.st-open').text()).toBe('Open')
    expect(wrapper.get('.item-emoji').text()).toBe('💬')
  })

  it('labels each task with how the person is attached to it', async () => {
    store.tasks = [
      { id: 't1', title: 'Involved' },
      { id: 't2', title: 'Requested' },
      { id: 't3', title: 'Both' }
    ]
    mocks.peopleGet.mockResolvedValue({
      id: 'p1',
      name: 'Ada',
      aliases: [],
      notes: '',
      task_ids: ['t1', 't2', 't3'],
      involved_task_ids: ['t1', 't3'],
      requester_task_ids: ['t2', 't3'],
      item_ids: []
    })
    const wrapper = mount(PersonView, { props: { id: 'p1' }, ...stub })
    await flushPromises()
    const labels = wrapper.findAll('.task-role').map((el) => el.get('.role-label').text())
    expect(labels).toEqual(['people', 'requested by', 'people · requested by'])
  })

  it('renames a person', async () => {
    mocks.peopleUpdate.mockResolvedValue({})
    const wrapper = mount(PersonView, { props: { id: 'p1' }, ...stub })
    await flushPromises()
    wrapper.findAllComponents(EditableText)[0].vm.$emit('save', 'Ada L')
    await flushPromises()
    expect(mocks.peopleUpdate).toHaveBeenCalledWith('p1', { name: 'Ada L' })
  })

  it('adds an alias', async () => {
    mocks.peopleUpdate.mockResolvedValue({})
    const wrapper = mount(PersonView, { props: { id: 'p1' }, ...stub })
    await flushPromises()
    await wrapper.get('input.input').setValue('ada-l')
    await wrapper.get('.panel .btn').trigger('click')
    await flushPromises()
    expect(mocks.peopleUpdate).toHaveBeenCalledWith('p1', {
      aliases: ['ada', 'ada@example.com', 'ada-l']
    })
  })

  it('removes an alias', async () => {
    mocks.peopleUpdate.mockResolvedValue({})
    const wrapper = mount(PersonView, { props: { id: 'p1' }, ...stub })
    await flushPromises()
    await wrapper.get('.chip .chip-x').trigger('click')
    await flushPromises()
    expect(mocks.peopleUpdate).toHaveBeenCalledWith('p1', { aliases: ['ada@example.com'] })
  })

  it('merges this person into another when confirmed', async () => {
    vi.stubGlobal('confirm', () => true)
    store.people = [
      { id: 'p1', name: 'Ada' },
      { id: 'p2', name: 'Grace' }
    ]
    mocks.peopleMerge.mockResolvedValue({})
    const wrapper = mount(PersonView, { props: { id: 'p1' }, ...stub })
    await flushPromises()
    wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'p2')
    await flushPromises()
    expect(mocks.peopleMerge).toHaveBeenCalledWith('p2', 'p1')
    expect(mocks.push).toHaveBeenCalledWith('/person/p2')
  })

  it('does not merge when the confirmation is declined', async () => {
    vi.stubGlobal('confirm', () => false)
    store.people = [
      { id: 'p1', name: 'Ada' },
      { id: 'p2', name: 'Grace' }
    ]
    const wrapper = mount(PersonView, { props: { id: 'p1' }, ...stub })
    await flushPromises()
    wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'p2')
    await flushPromises()
    expect(mocks.peopleMerge).not.toHaveBeenCalled()
  })

  it('deletes a person when confirmed and returns to the list', async () => {
    vi.stubGlobal('confirm', () => true)
    mocks.peopleRemove.mockResolvedValue(null)
    const wrapper = mount(PersonView, { props: { id: 'p1' }, ...stub })
    await flushPromises()
    await wrapper.get('button.btn.danger').trigger('click')
    await flushPromises()
    expect(mocks.peopleRemove).toHaveBeenCalledWith('p1')
    expect(mocks.push).toHaveBeenCalledWith('/people')
  })

  it('does not delete when the confirmation is declined', async () => {
    vi.stubGlobal('confirm', () => false)
    const wrapper = mount(PersonView, { props: { id: 'p1' }, ...stub })
    await flushPromises()
    await wrapper.get('button.btn.danger').trigger('click')
    expect(mocks.peopleRemove).not.toHaveBeenCalled()
  })
})
