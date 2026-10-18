import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { config, enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

// WorktreesPanel renders a <router-link>; stub it so mounting does not warn
// about an unresolved component.
config.global.stubs = { RouterLink: { props: ['to'], template: '<a><slot /></a>' } }

const mocks = vi.hoisted(() => ({
  taskUpdate: vi.fn(),
  associate: vi.fn(),
  unassociate: vi.fn(),
  itemRefresh: vi.fn(),
  itemUpdate: vi.fn(),
  worktreeCreate: vi.fn(),
  worktreeRemove: vi.fn(),
  refreshContext: vi.fn(),
  refreshSummary: vi.fn(),
  settingsGet: vi.fn(),
  changeCreate: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    tasks: { update: mocks.taskUpdate, associate: mocks.associate, unassociate: mocks.unassociate },
    items: { refresh: mocks.itemRefresh, update: mocks.itemUpdate },
    worktrees: { create: mocks.worktreeCreate, remove: mocks.worktreeRemove },
    runs: { refreshContext: mocks.refreshContext, refreshSummary: mocks.refreshSummary },
    settings: { get: mocks.settingsGet },
    changes: { create: mocks.changeCreate }
  }
}))

import ContextPanel from '../components/ContextPanel.vue'
import { store } from '../store'

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ContextPanel', () => {
  const task = (over = {}) => ({
    id: 't1',
    summary: 'The summary',
    next_steps: [{ text: 'Step A', done: false }],
    context_updated_at: null,
    ...over
  })

  it('renders the summary and edits the next steps as a Markdown field', async () => {
    mocks.taskUpdate.mockResolvedValue({})
    const wrapper = mount(ContextPanel, { props: { task: task() } })
    expect(wrapper.get('.summary').text()).toBe('The summary')
    expect(wrapper.find('.badge.warn').exists()).toBe(false)

    const box = wrapper.get('.next-steps input.task-list-item-checkbox')
    expect(box.element.disabled).toBe(false)
    expect(box.element.checked).toBe(false)
    expect(wrapper.get('.next-steps .md li').text()).toBe('Step A')

    await wrapper.get('.next-steps').trigger('click')
    const field = wrapper.get('textarea.inline-input')
    expect(field.element.value).toBe('- [ ] Step A')
    await field.setValue('- [ ] Step A\n- [x] Step B')
    await field.trigger('blur')
    await flushPromises()
    expect(mocks.taskUpdate).toHaveBeenCalledWith('t1', {
      next_steps: [
        { text: 'Step A', done: false },
        { text: 'Step B', done: true }
      ]
    })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('ticks a next step from its checkbox', async () => {
    mocks.taskUpdate.mockResolvedValue({})
    const wrapper = mount(ContextPanel, { props: { task: task() } })
    await wrapper.get('.next-steps input.task-list-item-checkbox').trigger('click')
    await flushPromises()
    expect(mocks.taskUpdate).toHaveBeenCalledWith('t1', { next_steps: [{ text: 'Step A', done: true }] })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('shows empty states', () => {
    const wrapper = mount(ContextPanel, { props: { task: task({ summary: '', next_steps: [] }) } })
    expect(wrapper.text()).toContain('No context yet')
    expect(wrapper.get('.next-steps').text()).toContain('No next steps yet')
  })

  it('flags a task with no next steps in the header badge', () => {
    const wrapper = mount(ContextPanel, { props: { task: task({ summary: 'Has a summary', next_steps: [] }) } })
    expect(wrapper.get('.badge.warn').text()).toBe('no next steps')
  })

  it('refreshes with the agent and emits changed', async () => {
    mocks.refreshContext.mockResolvedValue({})
    const wrapper = mount(ContextPanel, { props: { task: task() } })
    await wrapper.get('.panel-head button').trigger('click')
    await flushPromises()
    expect(mocks.refreshContext).toHaveBeenCalledWith('t1')
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(store.toast.message).toContain('Agent is reading')
  })

  it('notifies when the refresh fails', async () => {
    mocks.refreshContext.mockRejectedValueOnce(new Error('agent down'))
    const wrapper = mount(ContextPanel, { props: { task: task() } })
    await wrapper.get('.panel-head button').trigger('click')
    await flushPromises()
    expect(store.toast).toEqual({ message: 'agent down', isError: true })
  })

  it('offers to name and summarize a task with a Slack thread', async () => {
    mocks.refreshSummary.mockResolvedValue({})
    const withSlack = task({
      associations: [{ id: 'a1', note: '', created_at: 'x', item: { id: 'i1', source: 'slack', content: 'th' } }]
    })
    const wrapper = mount(ContextPanel, { props: { task: withSlack } })
    const buttons = wrapper.findAll('.panel-head button')
    expect(buttons.map((b) => b.text()).join(' ')).toContain('Name & summarize')

    await buttons[1].trigger('click')
    await flushPromises()
    expect(mocks.refreshSummary).toHaveBeenCalledWith('t1')
    expect(store.toast.message).toContain('naming the task')
  })

  it('hides the summarize action without a Slack thread', () => {
    const wrapper = mount(ContextPanel, { props: { task: task() } })
    expect(wrapper.text()).not.toContain('Name & summarize')
  })
})
