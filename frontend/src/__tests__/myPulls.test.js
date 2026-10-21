import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  list: vi.fn()
}))

vi.mock('../api', () => ({
  api: { myPulls: { list: mocks.list } }
}))

import MyPullsView from '../views/MyPullsView.vue'
import {
  attentionRank,
  ciLabel,
  ciTone,
  matchesPullSearch,
  needsAttention,
  pullCounts,
  reviewLabel,
  reviewTone,
  sortPulls
} from '../myPulls'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }

function pull(overrides = {}) {
  return {
    repository: 'TomzxCode/agentic',
    number: 42,
    title: 'Add the My PRs page',
    url: 'https://github.com/TomzxCode/agentic/pull/42',
    draft: false,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-02T00:00:00Z',
    review_decision: 'REVIEW_REQUIRED',
    approved: false,
    approvers: [],
    ci: 'success',
    open_threads: 0,
    threads_total: 1,
    ...overrides
  }
}

function report(pulls, overrides = {}) {
  return { login: 'tomzx', generated_at: '2026-10-02T00:00:00Z', counts: {}, error: null, pulls, ...overrides }
}

beforeEach(() => {
  vi.clearAllMocks()
  store.people = []
  store.repositories = []
  store.toast = null
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  vi.spyOn(store, 'loadRepositories').mockResolvedValue()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('my pulls helpers', () => {
  it('labels the check rollup and the review decision', () => {
    expect(ciLabel(pull())).toBe('Passing')
    expect(ciLabel(pull({ ci: 'none' }))).toBe('No checks')
    expect(ciTone(pull({ ci: 'failure' }))).toBe('danger')
    expect(reviewLabel(pull())).toBe('Review required')
    expect(reviewLabel(pull({ review_decision: 'CHANGES_REQUESTED' }))).toBe('Changes requested')
    expect(reviewLabel(pull({ review_decision: '' }))).toBe('No review')
    expect(reviewTone(pull({ review_decision: 'APPROVED' }))).toBe('ok')
  })

  it('ranks what needs the author above what is waiting on someone else', () => {
    expect(attentionRank(pull({ ci: 'failure' }))).toBe(0)
    expect(attentionRank(pull({ review_decision: 'CHANGES_REQUESTED' }))).toBe(1)
    expect(attentionRank(pull({ open_threads: 2 }))).toBe(2)
    expect(attentionRank(pull({ ci: 'pending' }))).toBe(3)
    expect(attentionRank(pull())).toBe(4)
    expect(attentionRank(pull({ review_decision: 'APPROVED', approved: true, ci: 'success' }))).toBe(5)
    expect(attentionRank(pull({ review_decision: '', ci: 'none' }))).toBe(6)
  })

  it('calls only failing checks, requested changes, and open threads attention', () => {
    expect(needsAttention(pull({ ci: 'failure' }))).toBe(true)
    expect(needsAttention(pull({ review_decision: 'CHANGES_REQUESTED' }))).toBe(true)
    expect(needsAttention(pull({ open_threads: 1 }))).toBe(true)
    expect(needsAttention(pull({ ci: 'pending' }))).toBe(false)
    expect(needsAttention(pull())).toBe(false)
  })

  it('sorts attention first, then newest update', () => {
    const rows = [
      pull({ number: 1, review_decision: 'APPROVED', approved: true, updated_at: '2026-10-04T00:00:00Z' }),
      pull({ number: 2, ci: 'failure', updated_at: '2026-10-01T00:00:00Z' }),
      pull({ number: 3, open_threads: 1, updated_at: '2026-10-03T00:00:00Z' }),
      pull({ number: 4, ci: 'failure', updated_at: '2026-10-02T00:00:00Z' })
    ]
    expect(sortPulls(rows).map((entry) => entry.number)).toEqual([4, 2, 3, 1])
  })

  it('searches the repository, number, title, and approvers', () => {
    expect(matchesPullSearch(pull(), '')).toBe(true)
    expect(matchesPullSearch(pull(), 'agentic')).toBe(true)
    expect(matchesPullSearch(pull(), '#42')).toBe(true)
    expect(matchesPullSearch(pull(), 'my prs')).toBe(true)
    expect(matchesPullSearch(pull({ approvers: ['alice'] }), 'alice')).toBe(true)
    expect(matchesPullSearch(pull(), 'nomatch')).toBe(false)
  })

  it('counts the whole list', () => {
    const counts = pullCounts([
      pull({ ci: 'failure', open_threads: 2 }),
      pull({ review_decision: 'APPROVED', approved: true }),
      pull({ review_decision: 'CHANGES_REQUESTED' })
    ])
    expect(counts).toEqual({ total: 3, attention: 2, approved: 1, openThreads: 2 })
  })
})

describe('MyPullsView', () => {
  it('renders each pull request with its state', async () => {
    mocks.list.mockResolvedValue(
      report([
        pull({ review_decision: 'APPROVED', approved: true }),
        pull({
          repository: 'TomzxCode/other',
          number: 7,
          title: 'Rework the parser',
          review_decision: 'CHANGES_REQUESTED',
          ci: 'failure',
          approvers: ['alice', 'bob'],
          open_threads: 2,
          threads_total: 3
        })
      ])
    )
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    expect(wrapper.text()).toContain('2 open')
    expect(wrapper.text()).toContain('1 need attention')
    expect(wrapper.text()).toContain('1 approved')
    expect(wrapper.text()).toContain('2 open threads')
    expect(wrapper.text()).toContain('#42')
    expect(wrapper.text()).toContain('#7')
    expect(wrapper.text()).toContain('Failing')
    expect(wrapper.text()).toContain('Changes requested')
    expect(wrapper.text()).toContain('alice')
    expect(wrapper.text()).toContain('bob')
    // The failing PR needs attention, so it sorts above the other one.
    const numbers = wrapper.findAll('.my-pulls-link').map((link) => link.text())
    expect(numbers).toEqual(['#7', '#42'])
  })

  it('says what to fix when no login is configured', async () => {
    mocks.list.mockResolvedValue(
      report([], { login: '', error: 'No GitHub login is configured; set it in Settings > Identity.' })
    )
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    expect(wrapper.text()).toContain('No GitHub login is configured')
  })

  it('shows an empty state when there are no open pull requests', async () => {
    mocks.list.mockResolvedValue(report([]))
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    expect(wrapper.text()).toContain('You have no open pull requests')
  })

  it('refreshes with the refresh flag and filters by search', async () => {
    mocks.list.mockResolvedValue(report([pull(), pull({ number: 7, title: 'Other work' })], { login: 'tomzx' }))
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    await wrapper.find('.my-pulls-search').setValue('other')
    expect(wrapper.findAll('.my-pulls-link').map((link) => link.text())).toEqual(['#7'])

    await wrapper.find('.my-pulls-search').setValue('nothing matches')
    expect(wrapper.text()).toContain('No pull requests match')

    await wrapper.find('button.btn.sm.ghost').trigger('click')
    await flushPromises()
    expect(mocks.list).toHaveBeenLastCalledWith({ refresh: true })
  })
})
