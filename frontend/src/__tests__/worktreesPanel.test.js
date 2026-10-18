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

import WorktreesPanel from '../components/WorktreesPanel.vue'
import SearchSelect from '../components/SearchSelect.vue'
import { store } from '../store'

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('WorktreesPanel', () => {
  const task = (over = {}) => ({
    id: 't1',
    repository_ids: ['r1'],
    worktrees: [
      {
        id: 'w1',
        status: 'active',
        branch: 'feature',
        path: '/w',
        repository_id: 'r1',
        created_at: new Date().toISOString()
      }
    ],
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

  it('picks the repository for a new worktree even after one exists', async () => {
    mocks.worktreeCreate.mockResolvedValue({})
    const wrapper = mount(WorktreesPanel, {
      props: {
        task: task({ repository_ids: ['r1', 'r2'] }),
        repositories: [
          { id: 'r1', name: 'alpha' },
          { id: 'r2', name: 'beta' }
        ]
      }
    })
    expect(wrapper.findComponent(SearchSelect).exists()).toBe(true)
    wrapper.findComponent(SearchSelect).vm.$emit('update:modelValue', 'r2')
    await flushPromises()
    await wrapper.get('.btn.primary').trigger('click')
    await flushPromises()
    expect(mocks.worktreeCreate).toHaveBeenCalledWith('t1', { repository_id: 'r2' })
  })

  it('labels each worktree with its repository', () => {
    const wrapper = mount(WorktreesPanel, {
      props: {
        task: task(),
        repositories: [{ id: 'r1', name: 'alpha' }]
      }
    })
    expect(wrapper.get('.chip').text()).toBe('alpha')
  })

  it('disables creation without any repository', () => {
    const wrapper = mount(WorktreesPanel, {
      props: { task: task({ worktrees: [], repository_ids: [] }), repositories: [] },
      global: { stubs: { SearchSelect: true } }
    })
    expect(wrapper.get('.btn.primary').attributes('disabled')).toBeDefined()
  })
})
