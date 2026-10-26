import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  inboxGet: vi.fn(),
  tasksUpdate: vi.fn(),
  itemsRefresh: vi.fn(),
  changesCreate: vi.fn(),
  worktreesRemove: vi.fn(),
  myPullsPoke: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    inbox: { get: mocks.inboxGet },
    tasks: { update: mocks.tasksUpdate },
    items: { refresh: mocks.itemsRefresh },
    changes: { create: mocks.changesCreate },
    worktrees: { remove: mocks.worktreesRemove },
    myPulls: { poke: mocks.myPullsPoke }
  }
}))

import InboxView from '../views/InboxView.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const StatusIconStub = { props: ['status', 'label'], template: '<i class="status-icon"></i>' }
const stub = { global: { stubs: { RouterLink: RouterLinkStub, StatusIcon: StatusIconStub } } }

function closeSuggestion() {
  return {
    id: 'close_task_finished_items:t1:close',
    kind: 'close_task_finished_items',
    reason: 'PR o/r#5 is merged.',
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
  localStorage.clear()
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

  it('flags a pull request past the review SLO with a link', async () => {
    mocks.inboxGet.mockResolvedValue([
      {
        id: 'review_pr_past_slo:o/r:7',
        kind: 'review_pr_past_slo',
        reason: 'Has awaited your review for 2d 3h; the SLO is 1d.',
        task_id: null,
        task_title: '',
        task_status: '',
        repository: 'o/r',
        number: 7,
        title: 'Fix the thing',
        url: 'https://github.com/o/r/pull/7',
        actions: [
          {
            id: 'open:o/r:7',
            kind: 'open_url',
            label: 'Review PR',
            url: 'https://github.com/o/r/pull/7'
          }
        ]
      }
    ])

    const wrapper = mount(InboxView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('Reviews past SLO')
    expect(wrapper.text()).toContain('Fix the thing')
    expect(wrapper.text()).toContain('Has awaited your review for 2d 3h; the SLO is 1d.')
    // The title opens the app's own PR page; the action still goes to GitHub,
    // where the review happens.
    const links = wrapper.findAll('.inbox-item a')
    expect(links.map((link) => link.attributes('href'))).toEqual(['/pr/o/r/7', 'https://github.com/o/r/pull/7'])
    expect(links[1].text()).toBe('Review PR')
  })

  it('renders a suggestion and closes the task through its action', async () => {
    mocks.inboxGet.mockResolvedValueOnce([closeSuggestion()]).mockResolvedValue([])
    mocks.tasksUpdate.mockResolvedValue({})

    const wrapper = mount(InboxView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('Close finished tasks')
    expect(wrapper.text()).toContain('Do the thing')
    expect(wrapper.text()).toContain('PR o/r#5 is merged.')

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
        reason: 'PR o/r#5 is merged and has no change recorded.',
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

  it("lists an unreviewed pull request's reviewers with their own pokes", async () => {
    mocks.inboxGet
      .mockResolvedValueOnce([
        {
          id: 'poke_pr_no_reviews:o/r:21',
          kind: 'poke_pr_no_reviews',
          reason: 'No reviews after 2d 6h; the nudge threshold is 1h 30m.',
          task_id: null,
          task_title: '',
          task_status: '',
          repository: 'o/r',
          number: 21,
          title: 'Fix the thing',
          url: 'https://github.com/o/r/pull/21',
          reviewers: ['alice', 'bob'],
          actions: [
            {
              id: 'open:o/r:21',
              kind: 'open_pr',
              label: 'Open PR',
              repository: 'o/r',
              number: 21,
              title: 'Fix the thing'
            }
          ]
        }
      ])
      .mockResolvedValue([])
    mocks.myPullsPoke.mockResolvedValue({ poked: [{ login: 'alice', name: 'Alice' }], failed: [] })

    const wrapper = mount(InboxView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('Poke reviewers')
    expect(wrapper.text()).toContain('No reviews after 2d 6h; the nudge threshold is 1h 30m.')
    // The row's title and the open action both stay in the app (the reviewer
    // names link to their people pages too).
    const hrefs = wrapper.findAll('.inbox-item a').map((link) => link.attributes('href'))
    expect(hrefs.filter((href) => href === '/pr/o/r/21')).toHaveLength(2)
    // The reviewers are listed the way the PR page lists them: a row each,
    // requesting a review, with a poke button.
    const rows = wrapper.findAll('.review-person')
    expect(rows.map((row) => row.get('a').text())).toEqual(['@alice', '@bob'])
    expect(rows[0].text()).toContain('Awaiting review')
    expect(rows[0].text()).toContain('requested')
    expect(rows.map((row) => row.get('.review-poke').text())).toEqual(['👉', '👉'])
    await rows[0].get('.review-poke').trigger('click')
    await flushPromises()

    expect(mocks.myPullsPoke).toHaveBeenCalledWith({
      repository: 'o/r',
      number: 21,
      title: 'Fix the thing',
      url: 'https://github.com/o/r/pull/21',
      logins: ['alice']
    })
    expect(store.toast).toEqual({ message: 'Poked Alice on Slack', isError: false })
  })

  it('reports why a reviewer could not be poked', async () => {
    mocks.inboxGet
      .mockResolvedValueOnce([
        {
          id: 'poke_pr_no_reviews:o/r:21',
          kind: 'poke_pr_no_reviews',
          reason: 'No reviews after 2d 6h; the nudge threshold is 1h 30m.',
          task_id: null,
          task_title: '',
          task_status: '',
          repository: 'o/r',
          number: 21,
          title: 'Fix the thing',
          url: 'https://github.com/o/r/pull/21',
          reviewers: ['alice'],
          actions: [
            {
              id: 'open:o/r:21',
              kind: 'open_pr',
              label: 'Open PR',
              repository: 'o/r',
              number: 21,
              title: 'Fix the thing'
            }
          ]
        }
      ])
      .mockResolvedValue([])
    mocks.myPullsPoke.mockResolvedValue({
      poked: [],
      failed: [{ login: 'alice', reason: 'Alice has no Slack user id or handle among their aliases.' }]
    })

    const wrapper = mount(InboxView, stub)
    await flushPromises()
    await wrapper.get('.review-poke').trigger('click')
    await flushPromises()

    expect(store.toast).toEqual({
      message: 'Alice has no Slack user id or handle among their aliases.',
      isError: true
    })
  })

  it('offers to find a reviewer for an unreviewed pull request nobody was asked to review', async () => {
    mocks.inboxGet
      .mockResolvedValueOnce([
        {
          id: 'find_pr_reviewer:o/r:22',
          kind: 'find_pr_reviewer',
          reason: 'No reviews after 2d 6h; the nudge threshold is 1h 30m. No reviewer is requested.',
          task_id: null,
          task_title: '',
          task_status: '',
          repository: 'o/r',
          number: 22,
          title: 'Big change',
          url: 'https://github.com/o/r/pull/22',
          reviewers: [],
          actions: [
            {
              id: 'open:o/r:22',
              kind: 'open_pr',
              label: 'Open PR',
              repository: 'o/r',
              number: 22,
              title: 'Big change'
            }
          ]
        }
      ])
      .mockResolvedValue([])

    const wrapper = mount(InboxView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('Find a reviewer')
    expect(wrapper.text()).toContain('No reviewer is requested.')
    // Nobody to poke, so there is no reviewer row and no poke button.
    expect(wrapper.find('.review-person').exists()).toBe(false)
    expect(wrapper.find('.review-poke').exists()).toBe(false)
    expect(wrapper.findAll('.inbox-item a').map((link) => link.attributes('href'))).toEqual([
      '/pr/o/r/22',
      '/pr/o/r/22'
    ])
  })

  it('offers a tab per suggestion kind that narrows the list to that section', async () => {
    mocks.inboxGet.mockResolvedValue([
      {
        id: 'review_pr_past_slo:o/r:7',
        kind: 'review_pr_past_slo',
        reason: 'Has awaited your review for 2d 3h; the SLO is 1d.',
        task_id: null,
        task_title: '',
        task_status: '',
        repository: 'o/r',
        number: 7,
        title: 'Fix the thing',
        url: 'https://github.com/o/r/pull/7',
        actions: [{ id: 'open:o/r:7', kind: 'open_url', label: 'Review PR', url: 'https://github.com/o/r/pull/7' }]
      },
      closeSuggestion()
    ])

    const wrapper = mount(InboxView, stub)
    await flushPromises()

    // A tab per kind present, in the fixed order the sections are shown, plus All.
    const tabs = wrapper.findAll('.inbox-tabs [role="tab"]')
    expect(tabs.map((tab) => tab.text())).toEqual(['All 2', 'Reviews past SLO 1', 'Close finished tasks 1'])
    expect(tabs[0].attributes('aria-selected')).toBe('true')
    expect(wrapper.findAll('.inbox-item')).toHaveLength(2)

    await tabs[2].trigger('click')

    expect(tabs[2].attributes('aria-selected')).toBe('true')
    expect(tabs[0].attributes('aria-selected')).toBe('false')
    expect(wrapper.findAll('.inbox-item')).toHaveLength(1)
    expect(wrapper.findAll('.group-head').map((head) => head.text())).toEqual(['Close finished tasks 1'])

    await tabs[0].trigger('click')
    expect(wrapper.findAll('.inbox-item')).toHaveLength(2)
  })

  it('falls back to All when the selected kind has nothing left', async () => {
    mocks.inboxGet.mockResolvedValue([closeSuggestion()])

    const wrapper = mount(InboxView, stub)
    await flushPromises()
    await wrapper.findAll('.inbox-tabs [role="tab"]')[1].trigger('click')
    expect(wrapper.findAll('.inbox-tabs [role="tab"]')[1].attributes('aria-selected')).toBe('true')

    // The only suggestion of that kind is gone on the next read.
    mocks.inboxGet.mockResolvedValue([
      {
        id: 'review_pr_past_slo:o/r:7',
        kind: 'review_pr_past_slo',
        reason: 'Has awaited your review for 2d 3h; the SLO is 1d.',
        task_id: null,
        task_title: '',
        task_status: '',
        repository: 'o/r',
        number: 7,
        title: 'Fix the thing',
        url: 'https://github.com/o/r/pull/7',
        actions: []
      }
    ])
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Refresh')
      .trigger('click')
    await flushPromises()

    const tabs = wrapper.findAll('.inbox-tabs [role="tab"]')
    expect(tabs.map((tab) => tab.text())).toEqual(['All 1', 'Reviews past SLO 1'])
    expect(tabs[0].attributes('aria-selected')).toBe('true')
    expect(wrapper.text()).toContain('Fix the thing')
    // Only the view falls back; the picked kind is still remembered for when it
    // has suggestions again.
    expect(localStorage.getItem('agentic.inboxTab')).toBe('close_task_finished_items')
  })

  it('shows no tabs when the inbox is empty', async () => {
    mocks.inboxGet.mockResolvedValue([])
    const wrapper = mount(InboxView, stub)
    await flushPromises()
    expect(wrapper.find('.inbox-tabs').exists()).toBe(false)
  })

  it('remembers the picked tab for the next visit', async () => {
    mocks.inboxGet.mockResolvedValue([closeSuggestion()])
    const wrapper = mount(InboxView, stub)
    await flushPromises()

    await wrapper.findAll('.inbox-tabs [role="tab"]')[1].trigger('click')
    expect(localStorage.getItem('agentic.inboxTab')).toBe('close_task_finished_items')

    wrapper.unmount()
    const reopened = mount(InboxView, stub)
    await flushPromises()

    const tabs = reopened.findAll('.inbox-tabs [role="tab"]')
    expect(tabs[1].attributes('aria-selected')).toBe('true')
    expect(reopened.findAll('.inbox-item')).toHaveLength(1)
    expect(reopened.findAll('.group-head').map((head) => head.text())).toEqual(['Close finished tasks 1'])
  })

  it('ignores a stored tab that is not a known kind', async () => {
    localStorage.setItem('agentic.inboxTab', 'not_a_kind')
    mocks.inboxGet.mockResolvedValue([closeSuggestion()])

    const wrapper = mount(InboxView, stub)
    await flushPromises()

    expect(wrapper.findAll('.inbox-tabs [role="tab"]')[0].attributes('aria-selected')).toBe('true')
  })
})
