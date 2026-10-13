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
  worktreeCreate: vi.fn(),
  worktreeRemove: vi.fn(),
  refreshContext: vi.fn(),
  refreshSummary: vi.fn(),
  settingsGet: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    tasks: { update: mocks.taskUpdate, associate: mocks.associate, unassociate: mocks.unassociate },
    items: { refresh: mocks.itemRefresh },
    worktrees: { create: mocks.worktreeCreate, remove: mocks.worktreeRemove },
    runs: { refreshContext: mocks.refreshContext, refreshSummary: mocks.refreshSummary },
    settings: { get: mocks.settingsGet }
  }
}))

import ContextPanel from '../components/ContextPanel.vue'
import ItemsPanel from '../components/ItemsPanel.vue'
import RepositorySelect from '../components/RepositorySelect.vue'
import SearchSelect from '../components/SearchSelect.vue'
import WorktreesPanel from '../components/WorktreesPanel.vue'
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

  it('renders the summary and toggles a next step', async () => {
    mocks.taskUpdate.mockResolvedValue({})
    const wrapper = mount(ContextPanel, { props: { task: task() } })
    expect(wrapper.get('.summary').text()).toBe('The summary')
    expect(wrapper.find('.badge.warn').exists()).toBe(false)

    await wrapper.get('input[type=checkbox]').trigger('change')
    await flushPromises()
    expect(mocks.taskUpdate).toHaveBeenCalledWith('t1', { next_steps: [{ text: 'Step A', done: true }] })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('shows empty states', () => {
    const wrapper = mount(ContextPanel, { props: { task: task({ summary: '', next_steps: [] }) } })
    expect(wrapper.text()).toContain('No context yet')
    expect(wrapper.text()).toContain('No next steps defined')
  })

  it('flags a task with no next steps in the header badge', () => {
    const wrapper = mount(ContextPanel, { props: { task: task({ summary: 'Has a summary', next_steps: [] }) } })
    expect(wrapper.get('.badge.warn').text()).toBe('no next steps')
    expect(wrapper.get('.context-missing').text()).toContain('No next steps defined')
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

describe('ItemsPanel', () => {
  const task = (over = {}) => ({
    id: 't1',
    associations: [
      {
        id: 'a1',
        note: 'a note',
        created_at: new Date().toISOString(),
        item: { id: 'i1', source: 'github', title: 'Issue 1', url: 'https://x', content: 'body', fetched_at: null }
      }
    ],
    ...over
  })

  it('groups items by source and shows notes', () => {
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    expect(wrapper.text()).toContain('github')
    expect(wrapper.text()).toContain('Issue 1')
    expect(wrapper.text()).toContain('a note')
  })

  it('does nothing when the draft is empty', async () => {
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.associate).not.toHaveBeenCalled()
  })

  it('associates a new item and clears the draft', async () => {
    mocks.associate.mockResolvedValue({})
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    await wrapper.findAll('input')[0].setValue('https://github.com/o/r/issues/2')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.associate).toHaveBeenCalledWith(
      't1',
      expect.objectContaining({ item: expect.objectContaining({ url: 'https://github.com/o/r/issues/2' }) })
    )
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.findAll('input')[0].element.value).toBe('')
  })

  it('notifies when associating fails', async () => {
    mocks.associate.mockRejectedValueOnce(new Error('bad'))
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    await wrapper.findAll('input')[0].setValue('https://x')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(store.toast).toEqual({ message: 'bad', isError: true })
  })

  it('removes and refreshes an item', async () => {
    mocks.unassociate.mockResolvedValue({})
    mocks.itemRefresh.mockResolvedValue({})
    const wrapper = mount(ItemsPanel, { props: { task: task() } })

    await wrapper.get('button[title="Remove"]').trigger('click')
    await flushPromises()
    expect(mocks.unassociate).toHaveBeenCalledWith('t1', 'i1')

    await wrapper.get('button[title="Refresh"]').trigger('click')
    await flushPromises()
    expect(mocks.itemRefresh).toHaveBeenCalledWith('i1')
  })

  it('toggles the expanded state', async () => {
    const wrapper = mount(ItemsPanel, { props: { task: task() } })
    const expand = wrapper.get('button[title="Expand"]')
    expect(expand.text()).toBe('▸')
    await expand.trigger('click')
    expect(wrapper.get('button[title="Expand"]').text()).toBe('▾')
  })
})

describe('RepositorySelect', () => {
  const repositories = [
    { id: 'a', name: 'Alpha' },
    { id: 'b', name: 'Beta' }
  ]

  it('renders the selected chips and the empty label', () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: ['b'], repositories } })
    expect(wrapper.get('.chip').text()).toContain('Beta')

    const empty = mount(RepositorySelect, { props: { modelValue: [], repositories: [] } })
    expect(empty.text()).toBe('no repositories')
  })

  it('emits an added repository and removes one', async () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: ['a'], repositories } })
    wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'b')
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toEqual([[['a', 'b']]])

    await wrapper.get('.chip-x').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[['a', 'b']], [[]]])
  })

  it('exposes activate for the command palette', () => {
    const wrapper = mount(RepositorySelect, { props: { modelValue: [], repositories } })
    wrapper.vm.activate()
    expect(wrapper.findComponent(SearchSelect).exists()).toBe(true)
  })
})

describe('WorktreesPanel', () => {
  const task = (over = {}) => ({
    id: 't1',
    repository_ids: ['r1'],
    worktrees: [{ id: 'w1', status: 'active', branch: 'feature', path: '/w', created_at: new Date().toISOString() }],
    ...over
  })

  beforeEach(() => {
    store.settings = { editor_url_template: 'vscode://file/{path}' }
  })

  it('lists worktrees and opens the editor', async () => {
    const open = vi.fn()
    vi.stubGlobal('open', open)
    const wrapper = mount(WorktreesPanel, { props: { task: task() } })
    expect(wrapper.text()).toContain('feature')
    expect(wrapper.text()).toContain('/w')

    await wrapper.get('button[title="Open in editor"]').trigger('click')
    expect(open).toHaveBeenCalledWith('vscode://file//w', '_blank')
  })

  it('copies the worktree path', async () => {
    const writeText = vi.fn()
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = mount(WorktreesPanel, { props: { task: task() } })
    await wrapper.get('button[title="Copy path"]').trigger('click')
    expect(writeText).toHaveBeenCalledWith('/w')
    expect(store.toast.message).toBe('Path copied')
  })

  it('removes a worktree when confirmed', async () => {
    vi.stubGlobal('confirm', () => true)
    mocks.worktreeRemove.mockResolvedValue({})
    const wrapper = mount(WorktreesPanel, { props: { task: task() } })
    await wrapper.get('button.btn.danger').trigger('click')
    await flushPromises()
    expect(mocks.worktreeRemove).toHaveBeenCalledWith('t1', 'w1')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('does not remove when the confirmation is declined', async () => {
    vi.stubGlobal('confirm', () => false)
    const wrapper = mount(WorktreesPanel, { props: { task: task() } })
    await wrapper.get('button.btn.danger').trigger('click')
    expect(mocks.worktreeRemove).not.toHaveBeenCalled()
  })

  it('creates a worktree with the drafted branch', async () => {
    mocks.worktreeCreate.mockResolvedValue({})
    const wrapper = mount(WorktreesPanel, {
      props: { task: task({ worktrees: [] }) },
      global: { stubs: { SearchSelect: true } }
    })
    await wrapper.findAll('input')[0].setValue('my-branch')
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.worktreeCreate).toHaveBeenCalledWith('t1', { repository_id: 'r1', branch: 'my-branch' })
  })

  it('disables creation without any repository', () => {
    const wrapper = mount(WorktreesPanel, {
      props: { task: task({ worktrees: [], repository_ids: [] }), repositories: [] },
      global: { stubs: { SearchSelect: true } }
    })
    expect(wrapper.get('.btn.primary').attributes('disabled')).toBeDefined()
  })
})
