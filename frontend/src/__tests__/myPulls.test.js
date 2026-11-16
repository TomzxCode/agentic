import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  checks: vi.fn()
}))

vi.mock('../api', () => ({
  api: { myPulls: { list: mocks.list, checks: mocks.checks } }
}))

import MyPullsView from '../views/MyPullsView.vue'
import {
  assignedReviewers,
  attentionRank,
  attentionState,
  checkCounts,
  checkLabel,
  checkTone,
  checksPassing,
  checksSummary,
  ciLabel,
  ciTone,
  CI_FILTERS,
  descriptionLabel,
  descriptionState,
  descriptionTitle,
  groupPulls,
  hasIndividualReviewer,
  hasMergeConflicts,
  isReadyToMerge,
  linkedIssueLabel,
  linkedIssueTitle,
  matchesCiFilter,
  matchesPullSearch,
  matchesReviewFilter,
  matchesThreadFilter,
  needsAttention,
  PULL_GROUPINGS,
  pullCounts,
  pullFilterCounts,
  pullStacks,
  blockerLabel,
  blockerTone,
  pullStatus,
  pullStatusLabel,
  readyToMergeReason,
  readyToMergeTitle,
  reviewLabel,
  reviewerPrefix,
  REVIEW_FILTERS,
  reviewTone,
  sortChecks,
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
    tasks: [],
    ...overrides
  }
}

function report(pulls, overrides = {}) {
  return { login: 'tomzx', generated_at: '2026-10-02T00:00:00Z', counts: {}, error: null, pulls, ...overrides }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.checks.mockReset()
  localStorage.clear()
  store.people = []
  store.repositories = []
  store.settings = {}
  store.toast = null
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  vi.spyOn(store, 'loadRepositories').mockResolvedValue()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('pull state helpers', () => {
  it('reads the four states a pull request can be in', () => {
    expect(pullStatus(pull({ state: 'OPEN' }))).toBe('open')
    expect(pullStatus(pull({ state: 'OPEN', draft: true }))).toBe('draft')
    expect(pullStatus(pull({ state: 'MERGED' }))).toBe('merged')
    expect(pullStatus(pull({ state: 'CLOSED' }))).toBe('closed')
    expect(pullStatusLabel(pull({ state: 'MERGED' }))).toBe('Merged')
  })

  it('tells a person assigned to review from a team-only request', () => {
    expect(hasIndividualReviewer(pull({ requested_users: ['alice'], requested_teams: [] }))).toBe(true)
    expect(hasIndividualReviewer(pull({ requested_users: [], approvers: ['bob'] }))).toBe(true)
    expect(hasIndividualReviewer(pull({ requested_users: [], approvers: [], requested_teams: ['platform'] }))).toBe(
      false
    )
    expect(assignedReviewers(pull({ requested_users: ['alice'], approvers: ['bob'] }))).toEqual(['alice'])
    expect(assignedReviewers(pull({ requested_users: [], approvers: ['bob'] }))).toEqual(['bob'])
    // A merged pull request names only its approvers, never a pending request.
    expect(assignedReviewers(pull({ state: 'MERGED', requested_users: ['carol'], approvers: ['bob'] }))).toEqual([
      'bob'
    ])
    expect(assignedReviewers(pull({ state: 'MERGED', requested_users: ['carol'], approvers: [] }))).toEqual([])
    expect(reviewerPrefix(pull({ requested_users: ['carol'] }))).toBe('waiting on ')
    expect(reviewerPrefix(pull({ state: 'MERGED', requested_users: ['carol'], approvers: ['bob'] }))).toBe(
      'approved by '
    )
  })

  it('reads merge conflicts and readiness', () => {
    expect(hasMergeConflicts(pull({ mergeable: false }))).toBe(true)
    expect(hasMergeConflicts(pull({ merge_state: 'DIRTY' }))).toBe(true)
    expect(hasMergeConflicts(pull({ mergeable: true }))).toBe(false)
    expect(hasMergeConflicts(pull({ mergeable: null, merge_state: '' }))).toBe(null)
    expect(isReadyToMerge(pull({ ready_to_merge: true }))).toBe(true)
    expect(isReadyToMerge(pull({ ready_to_merge: false }))).toBe(false)
    expect(readyToMergeTitle(pull({ ready_to_merge: false, state: 'MERGED' }))).toContain('Already merged')
    expect(readyToMergeTitle(pull({ ready_to_merge: false, merge_state: 'DIRTY' }))).toContain('conflicts')
    expect(readyToMergeTitle(pull({ ready_to_merge: true }))).toContain('ready to merge')
  })

  it('names the first reason a pull request is not ready', () => {
    expect(readyToMergeReason(pull({ ready_to_merge: false, state: 'OPEN', draft: true }))).toBe('draft')
    expect(readyToMergeReason(pull({ ready_to_merge: false, state: 'MERGED' }))).toBe('merged')
    expect(readyToMergeReason(pull({ ready_to_merge: false, merge_state: 'DIRTY' }))).toBe('conflicts')
    // GitHub's BLOCKED names no cause, so the row's own signals decide.
    expect(readyToMergeReason(pull({ ready_to_merge: false, merge_state: 'BLOCKED' }))).toBe('needs review')
    expect(
      readyToMergeReason(pull({ ready_to_merge: false, merge_state: 'BLOCKED', approved: true, ci: 'pending' }))
    ).toBe('checks pending')
    expect(
      readyToMergeReason(pull({ ready_to_merge: false, merge_state: 'BLOCKED', approved: true, approvers: ['bob'] }))
    ).toBe('branch rules')
    expect(readyToMergeReason(pull({ ready_to_merge: false, merge_state: 'UNSTABLE' }))).toBe('checks failing')
    // With no merge state read, the row's own signals decide, and what the
    // author can act on now comes before a review the PR is waiting on.
    expect(readyToMergeReason(pull({ ready_to_merge: false, merge_state: '', approved: false }))).toBe('needs review')
    expect(readyToMergeReason(pull({ ready_to_merge: false, merge_state: '', approved: false, ci: 'failure' }))).toBe(
      'checks failing'
    )
    expect(readyToMergeReason(pull({ ready_to_merge: false, merge_state: '', approved: true, ci: 'failure' }))).toBe(
      'checks failing'
    )
    expect(readyToMergeReason(pull({ ready_to_merge: false, merge_state: '', approved: false, open_threads: 2 }))).toBe(
      'comments open'
    )
    expect(readyToMergeReason(pull({ ready_to_merge: true }))).toBe('')
    // The Blocker cell reads "none" when nothing blocks, and a merged pull
    // request is done rather than blocked.
    expect(blockerLabel(pull({ state: 'MERGED', ready_to_merge: false }))).toBe('none')
    expect(blockerTone(pull({ state: 'MERGED', ready_to_merge: false }))).toBe('ok')
    expect(blockerLabel(pull({ state: 'CLOSED', ready_to_merge: false }))).toBe('closed')
    expect(blockerLabel(pull({ ready_to_merge: true }))).toBe('none')
    expect(blockerLabel(pull({ ready_to_merge: false, merge_state: 'DIRTY' }))).toBe('conflicts')
    expect(blockerTone(pull({ ready_to_merge: false, merge_state: 'DIRTY' }))).toBe('warn')
  })

  it('reads the linked-issue and description checks', () => {
    expect(linkedIssueLabel(pull({ linked_issues: [7] }))).toBe('#7')
    expect(linkedIssueLabel(pull({ linked_issues: [7, 9] }))).toBe('2 issues')
    expect(linkedIssueLabel(pull({ linked_issues: [] }))).toBe('none')
    expect(linkedIssueLabel(pull({ linked_issues: null }))).toBe('—')
    expect(linkedIssueTitle(pull({ linked_issues: [7, 9] }))).toContain('#7, #9')

    expect(descriptionState(pull({ has_description: true, description_updated: true }))).toBe('current')
    expect(descriptionLabel(pull({ has_description: true, description_updated: true }))).toBe('up to date')
    expect(descriptionLabel(pull({ has_description: true, description_updated: false }))).toBe('stale')
    expect(descriptionLabel(pull({ has_description: false, description_updated: false }))).toBe('missing')
    expect(descriptionLabel(pull({ has_description: null, description_updated: null }))).toBe('—')
    expect(descriptionTitle(pull({ has_description: true, description_updated: false }))).toContain('not updated')
  })

  it('counts no checks as not blocking a merge', () => {
    expect(checksPassing(pull({ ci: 'success' }))).toBe(true)
    expect(checksPassing(pull({ ci: 'none' }))).toBe(true)
    expect(checksPassing(pull({ ci: 'pending' }))).toBe(false)
    expect(checksPassing(pull({ ci: 'failure' }))).toBe(false)
  })
})

describe('my pulls helpers', () => {
  it('labels the check rollup and the review decision', () => {
    expect(ciLabel(pull())).toBe('Passing')
    expect(ciLabel(pull({ ci: 'none' }))).toBe('No checks')
    expect(ciTone(pull({ ci: 'failure' }))).toBe('danger')
    expect(reviewLabel(pull())).toBe('Required')
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

  it('names the state behind every rank', () => {
    // The first of the three author-facing states wins when a pull request has more than one.
    expect(attentionState(pull({ ci: 'failure', review_decision: 'CHANGES_REQUESTED', open_threads: 2 }))).toEqual({
      rank: 0,
      label: 'Failing checks'
    })
    expect(attentionState(pull({ review_decision: 'CHANGES_REQUESTED' }))).toEqual({
      rank: 1,
      label: 'Changes requested'
    })
    expect(attentionState(pull({ open_threads: 2 }))).toEqual({ rank: 2, label: '2 review threads open' })
    expect(attentionState(pull({ open_threads: 1 }))).toMatchObject({ rank: 2, label: '1 review thread open' })
    expect(attentionState(pull({ ci: 'pending' }))).toEqual({ rank: 3, label: 'Checks running' })
    expect(attentionState(pull())).toEqual({ rank: 4, label: 'Review required' })
    expect(attentionState(pull({ review_decision: 'APPROVED', approved: true }))).toEqual({
      rank: 5,
      label: 'Approved'
    })
    expect(attentionState(pull({ ci: 'none', review_decision: '' }))).toEqual({ rank: 6, label: 'No action needed' })
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

  it('labels one check and lists failing checks first', () => {
    const checks = [
      { name: 'lint', state: 'success' },
      { name: 'build', state: 'failure' },
      { name: 'integration', state: 'pending' },
      { name: 'docs', state: 'success' }
    ]

    expect(sortChecks(checks).map((check) => check.name)).toEqual(['build', 'integration', 'lint', 'docs'])
    expect(checkLabel({ state: 'failure' })).toBe('Failed')
    expect(checkLabel({ state: 'pending' })).toBe('Running')
    expect(checkLabel({ state: 'success' })).toBe('Passed')
    expect(checkLabel({ state: 'unknown' })).toBe('Unknown')
    expect(checkTone({ state: 'failure' })).toBe('danger')
    expect(checkTone({ state: 'pending' })).toBe('warn')
    expect(checkTone({ state: 'success' })).toBe('ok')

    expect(checkCounts(checks)).toEqual({ failure: 1, pending: 1, success: 2, total: 4 })
    expect(checksSummary(checks)).toBe('1 failing · 1 running · 2 passed')
    expect(checksSummary([{ name: 'build', state: 'failure' }])).toBe('1 failing')
    expect(checksSummary([])).toBe('')
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
    expect(review.map((group) => group.label)).toEqual(['Changes requested', 'Required', 'Approved', 'No review'])
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

describe('pull stacks', () => {
  it('keeps a list with no stack in the order given', () => {
    const first = pull({ number: 1, head_branch: 'one', base_branch: 'main' })
    const second = pull({ number: 2, head_branch: 'two', base_branch: 'main' })
    const rows = pullStacks([first, second])
    expect(rows.map((row) => row.item)).toEqual([first, second])
    expect(rows.every((row) => !row.stacked)).toBe(true)
    expect(rows.every((row) => !row.connectedAbove && !row.connectedBelow)).toBe(true)
  })

  it('orders a stack tip first and joins each row to the one it sits on', () => {
    const bottom = pull({ number: 1, head_branch: 'one', base_branch: 'main' })
    const middle = pull({ number: 2, head_branch: 'two', base_branch: 'one' })
    const tip = pull({ number: 3, head_branch: 'three', base_branch: 'two' })
    const rows = pullStacks([bottom, middle, tip])
    expect(rows.map((row) => row.item)).toEqual([tip, middle, bottom])
    expect(rows.map((row) => row.root)).toEqual([false, false, true])
    expect(rows.map((row) => row.connectedAbove)).toEqual([false, true, true])
    expect(rows.map((row) => row.connectedBelow)).toEqual([true, true, false])
    expect(rows.every((row) => row.stacked)).toBe(true)
    // Every row still carries the refs the column names.
    expect(rows[0].branch).toBe('three')
    expect(rows[2].base).toBe('main')
  })

  it('keeps the list order between stacks and never stacks across repositories', () => {
    const solo = pull({ number: 1, head_branch: 'solo', base_branch: 'main' })
    const bottom = pull({ number: 2, head_branch: 'one', base_branch: 'main' })
    const tip = pull({ number: 3, head_branch: 'two', base_branch: 'one' })
    const elsewhere = pull({
      repository: 'TomzxCode/other',
      number: 4,
      head_branch: 'two',
      base_branch: 'one'
    })
    const rows = pullStacks([bottom, solo, tip, elsewhere])
    expect(rows.map((row) => row.item.number)).toEqual([3, 2, 1, 4])
    // The other repository's branch is not the one the stack names.
    expect(rows[3].stacked).toBe(false)
  })

  it('treats a base branch no listed pull request publishes as the trunk', () => {
    const rows = pullStacks([pull({ number: 5, head_branch: 'lonely', base_branch: 'release/1.0' })])
    expect(rows[0].stacked).toBe(false)
    expect(rows[0].root).toBe(false)
    expect(rows[0].base).toBe('release/1.0')
  })

  it('does not loop on a cycle', () => {
    const a = pull({ number: 1, head_branch: 'a', base_branch: 'b' })
    const b = pull({ number: 2, head_branch: 'b', base_branch: 'a' })
    const rows = pullStacks([a, b])
    expect(rows).toHaveLength(2)
    expect(rows.every((row) => !row.stacked)).toBe(true)
  })
})

describe('MyPullsView', () => {
  it('renders each pull request with its state', async () => {
    mocks.list.mockResolvedValue(
      report([
        pull({
          review_decision: 'APPROVED',
          approved: true,
          state: 'OPEN',
          requested_users: ['carol'],
          mergeable: true,
          merge_state: 'CLEAN',
          ready_to_merge: true,
          linked_issues: [7],
          has_description: true,
          description_updated: true
        }),
        pull({
          repository: 'TomzxCode/other',
          number: 7,
          title: 'Rework the parser',
          review_decision: 'CHANGES_REQUESTED',
          ci: 'failure',
          approvers: ['alice', 'bob'],
          open_threads: 2,
          threads_total: 3,
          state: 'OPEN',
          mergeable: false,
          merge_state: 'DIRTY',
          linked_issues: [],
          has_description: true,
          description_updated: false
        })
      ])
    )
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    expect(wrapper.findAll('.my-pulls-table th').map((cell) => cell.text())).toEqual([
      'PR',
      'Blocker',
      'Status',
      'Review',
      'Reviewers',
      'Checks',
      'Comments',
      'Conflicts',
      'Issue',
      'Description',
      'Updated'
    ])
    // The mobile cards hide the header, so every state cell carries its own
    // column name.
    const firstRow = wrapper.findAll('.my-pulls-table tbody tr')[0]
    expect(firstRow.findAll('td[data-label]').map((cell) => cell.attributes('data-label'))).toEqual([
      'Blocker',
      'Status',
      'Review',
      'Reviewers',
      'Checks',
      'Comments',
      'Conflicts',
      'Issue',
      'Description',
      'Updated'
    ])
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
    // The reviewers cell names the person the review is waiting on, and the
    // conflicts, issue, description, and ready cells state the PR's checks.
    expect(wrapper.text()).toContain('carol')
    expect(wrapper.text()).toContain('conflicts')
    expect(wrapper.text()).toContain('up to date')
    expect(wrapper.text()).toContain('stale')
    const readyCell = (number) =>
      wrapper
        .findAll('.my-pulls-table tbody tr')
        .find((row) => row.find('.my-pulls-number').text() === number)
        .find('td[data-label="Blocker"]')
        .text()
    expect(readyCell('#42')).toBe('none')
    expect(readyCell('#7')).toBe('conflicts')
    const linked = wrapper.findAll('.my-pulls-table tbody tr').find((row) => row.text().includes('#42'))
    expect(linked.text()).toContain('#7')
    // The failing PR needs attention, so it sorts above the other one.
    const numbers = wrapper.findAll('.my-pulls-number').map((link) => link.text())
    expect(numbers).toEqual(['#7', '#42'])
  })

  it('marks every rank with its own colour and names it on hover', async () => {
    mocks.list.mockResolvedValue(
      report([
        pull({ number: 1, ci: 'failure', review_decision: 'REVIEW_REQUIRED', open_threads: 0 }),
        pull({ number: 2, ci: 'success', review_decision: 'CHANGES_REQUESTED', open_threads: 0 }),
        pull({ number: 3, ci: 'success', review_decision: 'REVIEW_REQUIRED', open_threads: 2, threads_total: 3 }),
        pull({ number: 4, ci: 'pending', review_decision: 'REVIEW_REQUIRED', open_threads: 0 }),
        pull({ number: 5, ci: 'success', review_decision: 'REVIEW_REQUIRED', open_threads: 0 }),
        pull({ number: 6, ci: 'success', review_decision: 'APPROVED', approved: true, open_threads: 0 }),
        pull({ number: 7, ci: 'none', review_decision: '', approved: false, open_threads: 0 })
      ])
    )
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    // Seven ranks, seven edges, each naming the state behind it.
    const rows = wrapper.findAll('.my-pulls-table tbody tr')
    expect(rows).toHaveLength(7)
    expect(rows.map((row) => row.classes().find((name) => name.startsWith('attention-rank-')))).toEqual([
      'attention-rank-0',
      'attention-rank-1',
      'attention-rank-2',
      'attention-rank-3',
      'attention-rank-4',
      'attention-rank-5',
      'attention-rank-6'
    ])
    const edges = wrapper.findAll('.my-pulls-attention')
    expect(edges).toHaveLength(7)
    expect(edges.map((edge) => edge.attributes('title'))).toEqual([
      'Failing checks',
      'Changes requested',
      '2 review threads open',
      'Checks running',
      'Review required',
      'Approved',
      'No action needed'
    ])
    expect(edges[0].attributes('aria-label')).toBe('Failing checks')
  })

  it('links each pull request to ghx, GitHub, and the app, in that order', async () => {
    store.settings = { ghx_url: 'http://ghx:8080/' }
    mocks.list.mockResolvedValue(report([pull()]))
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    // The title opens the app's PR view, not GitHub; the two external copies
    // come before it.
    const appLink = wrapper.get('.my-pulls-title')
    expect(appLink.text()).toBe('Add the My PRs page')
    expect(appLink.attributes('href')).toBe('/pr/TomzxCode/agentic/42')
    // The number names the pull request, but no longer opens anything.
    expect(wrapper.get('.my-pulls-number').text()).toBe('#42')
    expect(wrapper.get('.my-pulls-number').element.closest('a')).toBeNull()

    const ghx = wrapper.get('a[title="Open in ghx"]')
    expect(ghx.text()).toBe('ghx')
    expect(ghx.attributes('href')).toBe('http://ghx:8080/#/TomzxCode/agentic/pulls/42')

    const github = wrapper.get('a[title="Open on GitHub"]')
    expect(github.text()).toBe('gh')
    expect(github.attributes('href')).toBe('https://github.com/TomzxCode/agentic/pull/42')

    expect(
      wrapper
        .get('.my-pulls-pr-cell')
        .findAll('a')
        .map((link) => link.attributes('href'))
    ).toEqual([
      'http://ghx:8080/#/TomzxCode/agentic/pulls/42',
      'https://github.com/TomzxCode/agentic/pull/42',
      '/pr/TomzxCode/agentic/42'
    ])
    expect(wrapper.find('.my-pulls-task').exists()).toBe(false)
  })

  it('links the task each pull request is associated with', async () => {
    mocks.list.mockResolvedValue(
      report([
        pull({ tasks: [{ id: 't1', title: 'Ship the My PRs page', status: 'in_progress' }] }),
        pull({ number: 7, tasks: [] })
      ])
    )
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    // Only the linked row carries a task link, and it names the task.
    const tasks = wrapper.findAll('.my-pulls-task')
    expect(tasks).toHaveLength(1)
    expect(tasks[0].attributes('href')).toBe('/task/t1')
    expect(tasks[0].text()).toContain('Ship the My PRs page')
    expect(tasks[0].attributes('title')).toBe('Open task: Ship the My PRs page')
  })

  it('shows no ghx link when no ghx server is configured', async () => {
    mocks.list.mockResolvedValue(report([pull()]))
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    expect(wrapper.find('a[title="Open in ghx"]').exists()).toBe(false)
    expect(wrapper.get('a[title="Open on GitHub"]').text()).toBe('gh')
  })

  it('says what to fix when no login is configured', async () => {
    mocks.list.mockResolvedValue(
      report([], { login: '', error: 'No GitHub login is configured; set it in Settings > GitHub.' })
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
    expect(wrapper.findAll('.my-pulls-number').map((link) => link.text())).toEqual(['#7', '#42'])
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

    const numbers = () => wrapper.findAll('.my-pulls-number').map((link) => link.text())
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

  it('filters by repository picked from the searchable dropdown', async () => {
    mocks.list.mockResolvedValue(
      report([
        pull({ number: 42, repository: 'TomzxCode/agentic' }),
        pull({ number: 7, repository: 'acme/api' }),
        pull({ number: 9, repository: 'acme/api' })
      ])
    )
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    const numbers = () => wrapper.findAll('.my-pulls-number').map((link) => link.text())
    expect(numbers()).toEqual(['#42', '#7', '#9'])

    // Each option carries how many pull requests it would show.
    await wrapper.get('.my-pulls-repository-select .ss-trigger').trigger('click')
    const options = wrapper.findAll('.ss-option')
    expect(options.map((option) => option.text())).toEqual(['acme/api (2)', 'TomzxCode/agentic (1)'])

    await options[0].trigger('click')
    await flushPromises()
    expect(wrapper.get('.my-pulls-repository-select .ss-label').text()).toBe('acme/api (2)')
    expect(numbers()).toEqual(['#7', '#9'])

    // A second choice narrows to both, and the empty state clears them all.
    const remaining = wrapper.findAll('.ss-option').find((option) => option.text().includes('TomzxCode/agentic'))
    await remaining.trigger('click')
    await flushPromises()
    expect(numbers()).toEqual(['#42', '#7', '#9'])

    await wrapper.find('.my-pulls-search').setValue('nothing matches')
    expect(wrapper.text()).toContain('with the selected filters')
    await wrapper.find('.empty button').trigger('click')
    expect(numbers()).toEqual(['#42', '#7', '#9'])
    expect(wrapper.get('.my-pulls-repository-select .ss-label').text()).toBe('All repositories')
  })

  it('refreshes with the refresh flag and filters by search', async () => {
    mocks.list.mockResolvedValue(report([pull(), pull({ number: 7, title: 'Other work' })], { login: 'tomzx' }))
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    await wrapper.find('.my-pulls-search').setValue('other')
    expect(wrapper.findAll('.my-pulls-number').map((link) => link.text())).toEqual(['#7'])

    await wrapper.find('.my-pulls-search').setValue('nothing matches')
    expect(wrapper.text()).toContain('No pull requests match')

    await wrapper.find('button.btn.sm.ghost').trigger('click')
    await flushPromises()
    expect(mocks.list).toHaveBeenLastCalledWith({ refresh: true })
  })

  it('lists the individual checks when the CI badge opens, failing first', async () => {
    mocks.list.mockResolvedValue(report([pull({ ci: 'failure' })]))
    mocks.checks.mockResolvedValue({
      repository: 'TomzxCode/agentic',
      number: 42,
      rollup: 'failure',
      total: 5,
      error: null,
      checks: [
        { name: 'lint', state: 'success', description: 'passed', url: 'https://ci/lint' },
        { name: 'build', state: 'failure', description: 'failed', url: 'https://ci/build' },
        { name: 'integration', state: 'pending', description: 'running', url: '' }
      ]
    })
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    expect(wrapper.find('.my-pulls-checks').exists()).toBe(false)
    await wrapper.get('.my-pulls-ci-button').trigger('click')
    await flushPromises()

    expect(mocks.checks).toHaveBeenCalledWith({ repository: 'TomzxCode/agentic', number: 42, refresh: false })
    const rows = wrapper.findAll('.my-pulls-check')
    expect(rows.map((row) => row.find('.my-pulls-check-name').text())).toEqual(['build', 'integration', 'lint'])
    expect(rows.map((row) => row.find('.my-pulls-check-state').text())).toEqual(['Failed', 'Running', 'Passed'])
    expect(wrapper.get('.my-pulls-checks-summary').text()).toBe('1 failing · 1 running · 1 passed')
    expect(wrapper.get('.my-pulls-checks-all').attributes('href')).toBe(
      'https://github.com/TomzxCode/agentic/pull/42/checks'
    )
    expect(wrapper.get('.my-pulls-checks-more').text()).toBe('Showing 3 of 5 checks.')

    // Closing and reopening answers from the visit's copy.
    await wrapper.get('.my-pulls-ci-button').trigger('click')
    expect(wrapper.find('.my-pulls-checks').exists()).toBe(false)
    await wrapper.get('.my-pulls-ci-button').trigger('click')
    await flushPromises()
    expect(mocks.checks).toHaveBeenCalledTimes(1)
  })

  it('reports a failed check read, retries it, and closes on Escape or an outside click', async () => {
    mocks.list.mockResolvedValue(report([pull({ ci: 'failure' })]))
    mocks.checks
      .mockResolvedValueOnce({
        repository: 'TomzxCode/agentic',
        number: 42,
        rollup: 'failure',
        total: 0,
        error: 'Could not read this pull request’s checks from GitHub',
        checks: []
      })
      .mockResolvedValueOnce({
        repository: 'TomzxCode/agentic',
        number: 42,
        rollup: 'failure',
        total: 1,
        error: null,
        checks: [{ name: 'build', state: 'failure', description: 'failed', url: '' }]
      })
    const wrapper = mount(MyPullsView, { global: { stubs: { RouterLink: RouterLinkStub } } })
    await flushPromises()

    await wrapper.get('.my-pulls-ci-button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Could not read this pull request')
    expect(wrapper.get('.my-pulls-ci-button').attributes('aria-expanded')).toBe('true')

    await wrapper.get('.my-pulls-checks .btn').trigger('click')
    await flushPromises()
    expect(wrapper.get('.my-pulls-check-name').text()).toBe('build')
    expect(mocks.checks).toHaveBeenCalledTimes(2)
    expect(mocks.checks).toHaveBeenLastCalledWith({ repository: 'TomzxCode/agentic', number: 42, refresh: true })

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('.my-pulls-checks').exists()).toBe(false)
    expect(wrapper.get('.my-pulls-ci-button').attributes('aria-expanded')).toBe('false')

    // Reopening answers from the loaded copy, and a click elsewhere closes it.
    await wrapper.get('.my-pulls-ci-button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.my-pulls-checks').exists()).toBe(true)
    document.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(wrapper.find('.my-pulls-checks').exists()).toBe(false)
    expect(mocks.checks).toHaveBeenCalledTimes(2)
  })
})
