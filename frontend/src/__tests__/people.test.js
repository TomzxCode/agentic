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
import PeopleView from '../views/PeopleView.vue'
import PersonView from '../views/PersonView.vue'
import SearchSelect from '../components/SearchSelect.vue'
import EditableText from '../components/EditableText.vue'
import { store } from '../store'

const RouterLinkStub = {
  props: ['to'],
  template: '<a :href="typeof to === \'string\' ? to : to.path"><slot /></a>'
}

const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

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

describe('PeopleView', () => {
  beforeEach(() => {
    store.people = [{ id: 'p1', name: 'Ada', aliases: ['ada', 'ada@example.com'], task_count: 1, item_count: 1 }]
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

  it('creates a person', async () => {
    mocks.peopleCreate.mockResolvedValue({ id: 'p2', name: 'Grace', task_count: 0, item_count: 0 })
    const wrapper = await mountPeople()
    await wrapper.get('input[placeholder="Add a person by name…"]').setValue('Grace')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.peopleCreate).toHaveBeenCalledWith({ name: 'Grace' })
  })
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
      task_ids: ['t1'],
      involved_task_ids: ['t1'],
      requester_task_ids: [],
      item_ids: ['i1', 'i2']
    })
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
