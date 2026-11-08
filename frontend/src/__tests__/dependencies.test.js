import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  graphGet: vi.fn(),
  depsGet: vi.fn(),
  depsAdd: vi.fn(),
  depsRemove: vi.fn(),
  tasksList: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    graph: { get: mocks.graphGet },
    tasks: {
      list: mocks.tasksList,
      dependencies: mocks.depsGet,
      addDependency: mocks.depsAdd,
      removeDependency: mocks.depsRemove
    }
  }
}))

import DependencyGraphView from '../views/DependencyGraphView.vue'
import DependenciesSelect from '../components/DependenciesSelect.vue'
import SearchSelect from '../components/SearchSelect.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
})

describe('DependencyGraphView', () => {
  it('draws a node per task and an edge per link', async () => {
    mocks.graphGet.mockResolvedValue({
      nodes: [
        { id: 'a', title: 'First', status: 'open', priority: 2 },
        { id: 'b', title: 'Second', status: 'in_progress', priority: 2 }
      ],
      edges: [{ before_id: 'a', after_id: 'b' }]
    })
    const wrapper = mount(DependencyGraphView)
    await flushPromises()

    expect(mocks.graphGet).toHaveBeenCalledWith({ includeDone: false })
    expect(wrapper.findAll('.dep-node')).toHaveLength(2)
    expect(wrapper.findAll('.dep-edge')).toHaveLength(1)
    expect(wrapper.get('a[href="/task/a"]').text()).toContain('First')
  })

  it('shows an empty state when there are no tasks', async () => {
    mocks.graphGet.mockResolvedValue({ nodes: [], edges: [] })
    const wrapper = mount(DependencyGraphView)
    await flushPromises()
    expect(wrapper.text()).toContain('No tasks to show')
  })

  it('reloads including done tasks when the toggle changes', async () => {
    mocks.graphGet.mockResolvedValue({ nodes: [], edges: [] })
    const wrapper = mount(DependencyGraphView)
    await flushPromises()

    await wrapper.get('.gantt-toggle input').setValue(true)
    await flushPromises()
    expect(mocks.graphGet).toHaveBeenLastCalledWith({ includeDone: true })
  })
})

describe('DependenciesSelect', () => {
  const task = { id: 't1', title: 'Center task' }
  const mountPanel = () =>
    mount(DependenciesSelect, { props: { task }, global: { stubs: { RouterLink: RouterLinkStub } } })

  it('lists the before and after links with their current status', async () => {
    mocks.depsGet.mockResolvedValue({
      task_id: 't1',
      before: [{ id: 'a', title: 'Prerequisite', status: 'blocked' }],
      after: [{ id: 'b', title: 'Follow-up', status: 'done' }]
    })
    mocks.tasksList.mockResolvedValue([task])

    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('Prerequisite')
    expect(wrapper.text()).toContain('Follow-up')
    expect(wrapper.findAll('.dep-label').map((label) => label.text())).toEqual([
      'before',
      'after',
      'related',
      'parents',
      'children'
    ])
    expect(wrapper.get('.chip .task-status').classes()).toContain('st-blocked')
    expect(wrapper.get('.chip .task-status').attributes('aria-label')).toBe('Blocked')
    expect(wrapper.findAll('.chip .task-status')[1].classes()).toContain('st-done')
  })

  it('lists a related link on both sides with its current status', async () => {
    mocks.depsGet.mockResolvedValue({
      task_id: 't1',
      before: [],
      after: [],
      related: [{ id: 'b', title: 'Sibling', status: 'in_progress' }]
    })
    mocks.tasksList.mockResolvedValue([task])

    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('Sibling')
    expect(wrapper.get('.chip .task-status').classes()).toContain('st-in_progress')
  })

  it('removes a link and reloads', async () => {
    mocks.depsGet.mockResolvedValue({ task_id: 't1', before: [{ id: 'a', title: 'Prerequisite' }], after: [] })
    mocks.tasksList.mockResolvedValue([task])
    mocks.depsRemove.mockResolvedValue(null)

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('.chip-x').trigger('click')
    await flushPromises()

    expect(mocks.depsRemove).toHaveBeenCalledWith('t1', 'a', 'before')
    expect(wrapper.emitted('changed')).toBeTruthy()
  })

  it('links a task that must come before this one', async () => {
    mocks.depsGet.mockResolvedValue({ task_id: 't1', before: [], after: [] })
    mocks.tasksList.mockResolvedValue([task, { id: 'c', title: 'Other' }])
    mocks.depsAdd.mockResolvedValue({ task_id: 't1', before: [{ id: 'c', title: 'Other' }], after: [] })

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', ['c'])
    await flushPromises()

    expect(mocks.depsAdd).toHaveBeenCalledWith('t1', { related_id: 'c', relation: 'before' })
    expect(wrapper.emitted('changed')).toBeTruthy()
  })

  it('links a related task', async () => {
    mocks.depsGet.mockResolvedValue({ task_id: 't1', before: [], after: [], related: [] })
    mocks.tasksList.mockResolvedValue([task, { id: 'c', title: 'Other' }])
    mocks.depsAdd.mockResolvedValue({
      task_id: 't1',
      before: [],
      after: [],
      related: [{ id: 'c', title: 'Other' }]
    })

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.findAllComponents(SearchSelect)[2].vm.$emit('update:modelValue', ['c'])
    await flushPromises()

    expect(mocks.depsAdd).toHaveBeenCalledWith('t1', { related_id: 'c', relation: 'related' })
    expect(wrapper.emitted('changed')).toBeTruthy()
  })

  it('keeps a linked task listed in the picker so it can be unlinked there', async () => {
    mocks.depsGet.mockResolvedValue({ task_id: 't1', before: [{ id: 'a', title: 'Prerequisite' }], after: [] })
    mocks.tasksList.mockResolvedValue([task, { id: 'a', title: 'Prerequisite' }, { id: 'c', title: 'Other' }])
    mocks.depsRemove.mockResolvedValue(null)

    const wrapper = mountPanel()
    await flushPromises()

    const select = wrapper.findAllComponents(SearchSelect)[0]
    expect(select.props('modelValue')).toEqual(['a'])
    expect(select.props('summary')).toBe(false)
    expect(select.props('bulkActions')).toBe(true)
    expect(select.props('options').map((option) => option.value)).toContain('a')

    await select.vm.$emit('update:modelValue', [])
    await flushPromises()

    expect(mocks.depsRemove).toHaveBeenCalledWith('t1', 'a', 'before')
  })

  it('links and unlinks parents and children', async () => {
    mocks.depsGet.mockResolvedValue({
      task_id: 't1',
      before: [],
      after: [],
      related: [],
      parents: [{ id: 'p', title: 'Parent', status: 'open' }],
      children: [{ id: 'c', title: 'Child', status: 'done' }]
    })
    mocks.tasksList.mockResolvedValue([task, { id: 'other', title: 'Other' }])
    mocks.depsAdd.mockResolvedValue({
      task_id: 't1',
      parents: [{ id: 'p', title: 'Parent' }],
      children: [{ id: 'c', title: 'Child' }]
    })
    mocks.depsRemove.mockResolvedValue(null)

    const wrapper = mountPanel()
    await flushPromises()

    expect(wrapper.text()).toContain('Parent')
    expect(wrapper.text()).toContain('Child')

    // The parent group is the fourth picker, the child group the fifth.
    await wrapper.findAllComponents(SearchSelect)[3].vm.$emit('update:modelValue', ['p', 'other'])
    await flushPromises()
    expect(mocks.depsAdd).toHaveBeenCalledWith('t1', { related_id: 'other', relation: 'parent' })

    await wrapper.findAllComponents(SearchSelect)[4].vm.$emit('update:modelValue', ['c', 'other'])
    await flushPromises()
    expect(mocks.depsAdd).toHaveBeenCalledWith('t1', { related_id: 'other', relation: 'child' })

    // A child's unlink removes only the parent/child link.
    const childChip = wrapper.findAll('.chip').find((chip) => chip.text().includes('Child'))
    await childChip.get('.chip-x').trigger('click')
    await flushPromises()
    expect(mocks.depsRemove).toHaveBeenCalledWith('t1', 'c', 'child')
  })
})
