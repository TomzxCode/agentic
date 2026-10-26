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

  it('lists the before and after links', async () => {
    mocks.depsGet.mockResolvedValue({
      task_id: 't1',
      before: [{ id: 'a', title: 'Prerequisite' }],
      after: [{ id: 'b', title: 'Follow-up' }]
    })
    mocks.tasksList.mockResolvedValue([task])

    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('Prerequisite')
    expect(wrapper.text()).toContain('Follow-up')
    expect(wrapper.findAll('.dep-label').map((label) => label.text())).toEqual(['before', 'after', 'related'])
  })

  it('lists a related link on both sides', async () => {
    mocks.depsGet.mockResolvedValue({
      task_id: 't1',
      before: [],
      after: [],
      related: [{ id: 'b', title: 'Sibling' }]
    })
    mocks.tasksList.mockResolvedValue([task])

    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('Sibling')
  })

  it('removes a link and reloads', async () => {
    mocks.depsGet.mockResolvedValue({ task_id: 't1', before: [{ id: 'a', title: 'Prerequisite' }], after: [] })
    mocks.tasksList.mockResolvedValue([task])
    mocks.depsRemove.mockResolvedValue(null)

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.get('.chip-x').trigger('click')
    await flushPromises()

    expect(mocks.depsRemove).toHaveBeenCalledWith('t1', 'a')
    expect(wrapper.emitted('changed')).toBeTruthy()
  })

  it('links a task that must come before this one', async () => {
    mocks.depsGet.mockResolvedValue({ task_id: 't1', before: [], after: [] })
    mocks.tasksList.mockResolvedValue([task, { id: 'c', title: 'Other' }])
    mocks.depsAdd.mockResolvedValue({ task_id: 't1', before: [{ id: 'c', title: 'Other' }], after: [] })

    const wrapper = mountPanel()
    await flushPromises()
    await wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'c')
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
    await wrapper.findAllComponents(SearchSelect)[2].vm.$emit('update:modelValue', 'c')
    await flushPromises()

    expect(mocks.depsAdd).toHaveBeenCalledWith('t1', { related_id: 'c', relation: 'related' })
    expect(wrapper.emitted('changed')).toBeTruthy()
  })
})
