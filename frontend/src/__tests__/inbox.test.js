import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  inboxGet: vi.fn(),
  tasksUpdate: vi.fn(),
  itemsRefresh: vi.fn(),
  changesCreate: vi.fn(),
  worktreesRemove: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    inbox: { get: mocks.inboxGet },
    tasks: { update: mocks.tasksUpdate },
    items: { refresh: mocks.itemsRefresh },
    changes: { create: mocks.changesCreate },
    worktrees: { remove: mocks.worktreesRemove }
  }
}))

import InboxView from '../views/InboxView.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const StatusIconStub = { props: ['status', 'label'], template: '<i class="status-icon"></i>' }
const stub = { global: { stubs: { RouterLink: RouterLinkStub, StatusIcon: StatusIconStub } } }

function closeSuggestion() {
  return {
    id: 'close_task_merged_pr:t1:close',
    kind: 'close_task_merged_pr',
    reason: 'PR #5 is merged.',
    task_id: 't1',
    task_title: 'Do the thing',
    task_status: 'open',
    actions: [{ id: 'close', kind: 'set_task_status', label: 'Close task', task_id: 't1', status: 'done' }]
  }
}

function mergeItem(overrides = {}) {
  return {
    id: 'i1',
    source: 'github',
    kind: 'pull_request',
    title: 'Merged PR',
    url: 'https://github.com/o/r/pull/5',
    external_id: 'o/r#5',
    metadata_json: { state: 'MERGED', merged_at: '2026-01-01T00:00:00+00:00' },
    ...overrides
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  store.tasks = [{ id: 't1', title: 'Do the thing', status: 'open', tags: [] }]
  store.items = []
  store.inbox = []
  store.inboxCount = 0
  store.toast = null
  vi.spyOn(store, 'loadTasks').mockResolvedValue()
  vi.spyOn(store, 'loadItems').mockResolvedValue()
  vi.spyOn(store, 'loadInbox').mockImplementation(async () => {
    store.inbox = (await mocks.inboxGet()) || []
    store.inboxCount = store.inbox.length
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('InboxView', () => {
  it('shows inbox zero when there is nothing to do', async () => {
    mocks.inboxGet.mockResolvedValue([])
    const wrapper = mount(InboxView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('Inbox zero')
  })

  it('renders a suggestion and closes the task through its action', async () => {
    mocks.inboxGet.mockResolvedValueOnce([closeSuggestion()]).mockResolvedValue([])
    mocks.tasksUpdate.mockResolvedValue({})

    const wrapper = mount(InboxView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('Close finished tasks')
    expect(wrapper.text()).toContain('Do the thing')
    expect(wrapper.text()).toContain('PR #5 is merged.')

    await wrapper.get('.inbox-item button').trigger('click')
    await flushPromises()

    expect(mocks.tasksUpdate).toHaveBeenCalledWith('t1', { status: 'done' })
    // The suggestion is gone once the task is closed.
    expect(wrapper.text()).toContain('Inbox zero')
  })

  it('records a change for a merged PR using its stored merge time', async () => {
    store.items = [mergeItem()]
    mocks.inboxGet.mockResolvedValue([
      {
        id: 'record_change_merged_pr:t1:i1',
        kind: 'record_change_merged_pr',
        reason: 'PR #5 is merged and has no change recorded.',
        task_id: 't1',
        task_title: 'Do the thing',
        task_status: 'open',
        actions: [{ id: 'record:i1', kind: 'create_change', label: 'Record change', task_id: 't1', item_id: 'i1' }]
      }
    ])
    mocks.changesCreate.mockResolvedValue({})

    const wrapper = mount(InboxView, stub)
    await flushPromises()
    await wrapper.get('.inbox-item button').trigger('click')
    await flushPromises()

    expect(mocks.itemsRefresh).not.toHaveBeenCalled()
    expect(mocks.changesCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        task_id: 't1',
        status: 'accepted',
        external_ref: 'https://github.com/o/r/pull/5'
      })
    )
  })

  it('removes a leftover worktree of a closed task', async () => {
    mocks.inboxGet.mockResolvedValue([
      {
        id: 'remove_worktree_done_task:t1:w1',
        kind: 'remove_worktree_done_task',
        reason: 'Worktree agentic/foo is still checked out.',
        task_id: 't1',
        task_title: 'Do the thing',
        task_status: 'done',
        actions: [
          { id: 'prune:w1', kind: 'remove_worktree', label: 'Remove worktree', task_id: 't1', worktree_id: 'w1' }
        ]
      }
    ])
    mocks.worktreesRemove.mockResolvedValue(null)

    const wrapper = mount(InboxView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('Clean up worktrees')
    await wrapper.get('.inbox-item button').trigger('click')
    await flushPromises()

    expect(mocks.worktreesRemove).toHaveBeenCalledWith('t1', 'w1')
  })
})
