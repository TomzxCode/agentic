import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { config, enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

// WorktreesPanel renders a <router-link>; stub it so mounting does not warn
// about an unresolved component.
config.global.stubs = { RouterLink: { props: ['to'], template: '<a><slot /></a>' } }

const mocks = vi.hoisted(() => ({
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
    tasks: { associate: mocks.associate, unassociate: mocks.unassociate },
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
    context_updated_at: null,
    ...over
  })

  it('renders the summary', () => {
    const wrapper = mount(ContextPanel, { props: { task: task() } })
    expect(wrapper.get('.summary').text()).toBe('The summary')
  })

  it('shows the empty state when there is no summary', () => {
    const wrapper = mount(ContextPanel, { props: { task: task({ summary: '' }) } })
    expect(wrapper.text()).toContain('No context yet')
    expect(wrapper.text()).toContain('proposes checklist items')
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
