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
  CI_FILTERS,
  groupPulls,
  matchesCiFilter,
  matchesPullSearch,
  matchesReviewFilter,
  matchesThreadFilter,
  needsAttention,
  PULL_GROUPINGS,
  pullCounts,
  pullFilterCounts,
  reviewLabel,
  REVIEW_FILTERS,
  reviewTone,
  sortPulls,
  THREAD_FILTERS
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
  localStorage.clear()
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

describe('grouping', () => {
  it('offers the flat list plus the three facets', () => {
    expect(PULL_GROUPINGS.map((option) => option.value)).toEqual(['', 'repository', 'ci', 'review'])
  })

  it('returns the flat list as one unlabeled section when no grouping is chosen', () => {
    const rows = [pull({ number: 2 }), pull({ number: 1 })]
    const groups = groupPulls(rows, '')
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe(null)
    expect(groups[0].pulls.map((entry) => entry.number)).toEqual([2, 1])
  })

  it('groups by repository in name order, keeping each row once', () => {
    const groups = groupPulls(
      [
        pull({ repository: 'TomzxCode/other', number: 7 }),
        pull({ repository: 'TomzxCode/agentic', number: 42 }),
        pull({ repository: 'tomzxcode/other', number: 9 })
      ],
      'repository'
    )
    expect(groups.map((group) => group.label)).toEqual(['TomzxCode/agentic', 'TomzxCode/other'])
    // A casing difference does not split one repository in two.
    expect(groups[1].pulls.map((entry) => entry.number)).toEqual([7, 9])
    expect(groups.every((group) => group.badge === false)).toBe(true)
  })

  it('groups CI and review states with what needs the author first', () => {
    const ci = groupPulls(
      [pull({ ci: 'success' }), pull({ ci: 'none' }), pull({ ci: 'failure' }), pull({ ci: 'pending' })],
      'ci'
    )
    expect(ci.map((group) => [group.label, group.tone])).toEqual([
      ['Failing', 'danger'],
      ['Running', 'warn'],
      ['Passing', 'ok'],
      ['No checks', '']
    ])
    // State sections carry a badge; repository sections do not.
    expect(ci.every((group) => group.badge)).toBe(true)

    const review = groupPulls(
      [
        pull({ review_decision: 'APPROVED', approved: true }),
        pull({ review_decision: '' }),
        pull({ review_decision: 'REVIEW_REQUIRED' }),
        pull({ review_decision: 'CHANGES_REQUESTED' })
      ],
      'review'
    )
    expect(review.map((group) => group.label)).toEqual([
      'Changes requested',
      'Review required',
      'Approved',
      'No review'
    ])
  })

  it('drops the states the list has none of', () => {
    const groups = groupPulls([pull({ ci: 'success' })], 'ci')
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('Passing')
  })
})

describe('filtering', () => {
  it('offers every facet an Any option first', () => {
    expect(CI_FILTERS[0].value).toBe('')
    expect(REVIEW_FILTERS[0].value).toBe('')
    expect(THREAD_FILTERS[0].value).toBe('')
  })

  it('matches a pull request against one value per facet', () => {
    const row = pull({ ci: 'failure', review_decision: 'APPROVED', approved: true, open_threads: 2 })
    expect(matchesCiFilter(row, '')).toBe(true)
    expect(matchesCiFilter(row, 'failure')).toBe(true)
    expect(matchesCiFilter(row, 'success')).toBe(false)
    expect(matchesCiFilter(pull({ ci: 'none' }), 'none')).toBe(true)
    expect(matchesCiFilter(pull({ ci: undefined }), 'none')).toBe(true)

    expect(matchesReviewFilter(row, 'APPROVED')).toBe(true)
    expect(matchesReviewFilter(row, 'CHANGES_REQUESTED')).toBe(false)
    expect(matchesReviewFilter(pull({ review_decision: '' }), 'none')).toBe(true)

    expect(matchesThreadFilter(row, 'open')).toBe(true)
    expect(matchesThreadFilter(row, 'none')).toBe(false)
    expect(matchesThreadFilter(pull({ open_threads: 0 }), 'none')).toBe(true)
  })

  it('counts each option over the whole list', () => {
    const counts = pullFilterCounts([
      pull({ ci: 'failure', review_decision: 'APPROVED', open_threads: 1 }),
      pull({ ci: 'success', review_decision: 'APPROVED' }),
      pull({ ci: 'none', review_decision: '' })
    ])
    expect(counts.ci).toEqual({ failure: 1, success: 1, none: 1 })
    expect(counts.review).toEqual({ APPROVED: 2, none: 1 })
    expect(counts.threads).toEqual({ open: 1, none: 2 })
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

  it('splits the list into sections for the chosen grouping and remembers the choice', async () => {
    mocks.list.mockResolvedValue(
      report([pull({ number: 42, ci: 'success' }), pull({ number: 7, ci: 'failure', repository: 'TomzxCode/other' })])
    )
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    const select = wrapper.find('.my-pulls-group-select')
    expect(select.findAll('option').map((option) => option.text())).toEqual([
      'None',
      'Repository',
      'CI status',
      'Review status'
    ])

    // Flat by default: one table, no headings.
    expect(wrapper.findAll('.my-pulls-group')).toHaveLength(1)
    expect(wrapper.find('.my-pulls-group-head').exists()).toBe(false)

    await select.setValue('ci')
    const stateHeads = wrapper.findAll('.my-pulls-group-head')
    expect(stateHeads.map((head) => head.element.firstElementChild.textContent)).toEqual(['Failing', 'Passing'])
    expect(stateHeads.map((head) => head.find('.my-pulls-group-count').text())).toEqual(['1', '1'])
    expect(wrapper.findAll('.my-pulls-link').map((link) => link.text())).toEqual(['#7', '#42'])
    expect(localStorage.getItem('agentic.myPullsGroupBy')).toBe('ci')

    await select.setValue('repository')
    const repositoryHeads = wrapper.findAll('.my-pulls-group-head')
    expect(repositoryHeads.map((head) => head.element.firstElementChild.textContent)).toEqual([
      'TomzxCode/agentic',
      'TomzxCode/other'
    ])
    // The heading names the repository, so the rows no longer repeat it.
    expect(wrapper.findAll('.my-pulls-repository')).toHaveLength(0)
  })

  it('filters by CI, review, and threads, and clears them together', async () => {
    mocks.list.mockResolvedValue(
      report([
        pull({ number: 42, ci: 'success', review_decision: 'APPROVED', approved: true }),
        pull({ number: 7, ci: 'failure', review_decision: 'CHANGES_REQUESTED', open_threads: 2 })
      ])
    )
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    const numbers = () => wrapper.findAll('.my-pulls-link').map((link) => link.text())
    const rows = wrapper.findAll('.my-pulls-filter-row')
    expect(rows).toHaveLength(3)
    // Each chip states how many pull requests it would show, over the whole list.
    expect(rows[0].findAll('.my-pulls-chip').map((chip) => chip.text())).toEqual([
      'Any 2',
      'Failing 1',
      'Running 0',
      'Passing 1',
      'No checks 0'
    ])

    await rows[0].findAll('.my-pulls-chip')[1].trigger('click')
    expect(numbers()).toEqual(['#7'])

    // The search and the filters narrow together, and one button clears both.
    await wrapper.find('.my-pulls-search').setValue('nothing matches')
    expect(wrapper.text()).toContain('with the selected filters')
    await wrapper.find('.empty button').trigger('click')
    expect(numbers()).toEqual(['#7', '#42'])

    await rows[1].findAll('.my-pulls-chip')[3].trigger('click')
    expect(numbers()).toEqual(['#42'])
    await rows[1].findAll('.my-pulls-chip')[0].trigger('click')
    expect(numbers()).toEqual(['#7', '#42'])

    await rows[2].findAll('.my-pulls-chip')[1].trigger('click')
    expect(numbers()).toEqual(['#7'])
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
