import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  queue: vi.fn(),
  report: vi.fn(),
  createTask: vi.fn(),
  approve: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    reviews: { queue: mocks.queue, report: mocks.report, approve: mocks.approve },
    tasks: { create: mocks.createTask }
  }
}))

import ReviewsView from '../views/ReviewsView.vue'
import { store, formatDateTime } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

// The state word and count a tri-state kind filter shows.
function filterState(wrapper, kind) {
  return wrapper.get(`.review-${kind}-filter .state`).text()
}
function filterCount(wrapper, kind) {
  return wrapper.get(`.review-${kind}-filter .count`).text()
}

// Open the author dropdown (a SearchSelect) and toggle one author's option.
async function openAuthors(wrapper) {
  await wrapper.get('.review-author-select .ss-trigger').trigger('click')
}
async function toggleAuthor(wrapper, name) {
  const option = wrapper.findAll('.ss-option').find((entry) => entry.text().includes(name))
  await option.trigger('click')
  await flushPromises()
}

// Open the repository dropdown (a SearchSelect) and toggle one repository's
// option.
async function openRepositories(wrapper) {
  await wrapper.get('.review-repository-select .ss-trigger').trigger('click')
}
async function toggleRepository(wrapper, name) {
  const option = wrapper.findAll('.ss-option').find((entry) => entry.text().includes(name))
  await option.trigger('click')
  await flushPromises()
}

function step(overrides = {}) {
  return {
    step: 'review-pr',
    commit: 'abc1234',
    verdict: 'pass',
    risk: '',
    confidence: '',
    stale: false,
    report: 'review-pr.abc1234.md',
    modified_at: '2026-01-12T06:00:00Z',
    ...overrides
  }
}

function pr(overrides = {}) {
  const number = overrides.number ?? 42
  return {
    owner: 'TomzxCode',
    name: 'agentic',
    repository: 'TomzxCode/agentic',
    number,
    title: 'Do the thing',
    url: `https://github.com/TomzxCode/agentic/pull/${number}`,
    author: 'alice',
    state: 'OPEN',
    draft: false,
    head_branch: 'feature',
    base_branch: 'main',
    labels: [],
    created_at: '2026-01-12T06:14:00Z',
    last_comment_at: '2026-01-12T07:00:00Z',
    last_comment_by: 'bob',
    head_commit: 'abc1234',
    reviewed_at: '2026-01-12T06:20:00Z',
    steps: {
      'review-pr': step(),
      'validate-pr': step({ step: 'validate-pr', report: 'validate-pr.abc1234.md', stale: true })
    },
    in_progress: {},
    stale_steps: ['validate-pr'],
    reviewed_steps: 2,
    readiness: 'yellow',
    status: 'needs-review',
    item_id: null,
    task_ids: [],
    ...overrides
  }
}

// A row in another repository, with its own URL and coordinates.
function prIn(repository, overrides = {}) {
  const [owner, name] = repository.split('/')
  const number = overrides.number ?? 42
  return pr({
    owner,
    name,
    repository,
    number,
    url: `https://github.com/${repository}/pull/${number}`,
    ...overrides
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  store.toast = null
  store.people = []
  store.repositories = []
  store.tasks = []
  store.settings = {}
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  vi.spyOn(store, 'loadRepositories').mockResolvedValue()
  vi.spyOn(store, 'loadTasks').mockResolvedValue()
  vi.spyOn(store, 'loadItems').mockResolvedValue()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ReviewsView', () => {
  it('shows an empty state when the store has no reports', async () => {
    mocks.queue.mockResolvedValue({ root: '/home/u/.sdlc', counts: { total: 0 }, prs: [] })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('No pull requests have review reports')
    expect(wrapper.text()).toContain('/home/u/.sdlc')
  })

  it('lists a PR grouped by repository with its review-step state', async () => {
    mocks.queue.mockResolvedValue({
      root: '/home/u/.sdlc',
      counts: { total: 1, ready: 0, blocked: 0, needs_review: 1 },
      prs: [pr()]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('TomzxCode/agentic')
    expect(wrapper.text()).toContain('#42')
    expect(wrapper.text()).toContain('alice')
    // The readiness light is the row's tooltip; the status column is gone.
    expect(wrapper.get('.review-readiness').attributes('title')).toContain('Still needs attention')
    expect(wrapper.text()).not.toContain('Needs review')
    // Nobody in the directory carries alice or bob, so both read grey and link
    // to the prefilled creation page rather than a person page.
    expect(wrapper.get('table a[href="/person/new?name=alice&alias=alice"]').classes()).toContain('faint')
    // The last review event reads as an absolute local date and time.
    expect(wrapper.get('.review-reviewed-at').text()).toBe(formatDateTime('2026-01-12T06:20:00Z'))
    // The validate step is stale, so its reviewed commit is shown in red.
    expect(wrapper.get('.review-stale').text()).toBe('abc1234')
  })

  it('links each pull request to ghx, GitHub, and the app, in that order', async () => {
    store.settings = { ghx_url: 'http://ghx:8080/' }
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr()] })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    // The title is the app link, not the number; the two external copies come
    // before it.
    const appLink = wrapper.get('.review-pr-link')
    expect(appLink.text()).toBe('Do the thing')
    expect(appLink.attributes('href')).toBe('/pr/TomzxCode/agentic/42')
    // The number still names the PR, but no longer opens anything.
    expect(wrapper.get('.review-number').text()).toBe('#42')
    expect(wrapper.get('.review-number').element.closest('a')).toBeNull()

    const ghx = wrapper.get('a[title="Open in ghx"]')
    expect(ghx.text()).toBe('ghx')
    expect(ghx.attributes('href')).toBe('http://ghx:8080/#/TomzxCode/agentic/pulls/42')

    const github = wrapper.get('a[title="Open on GitHub"]')
    expect(github.text()).toBe('gh')
    expect(github.attributes('href')).toBe('https://github.com/TomzxCode/agentic/pull/42')

    expect(
      wrapper
        .get('.review-pr-cell')
        .findAll('a')
        .map((link) => link.attributes('href'))
    ).toEqual([
      'http://ghx:8080/#/TomzxCode/agentic/pulls/42',
      'https://github.com/TomzxCode/agentic/pull/42',
      '/pr/TomzxCode/agentic/42'
    ])
  })

  it('drops the ghx link when no ghx server is configured', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr()] })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.find('a[title="Open in ghx"]').exists()).toBe(false)
    // The GitHub copy and the app link stay, so the row still has both.
    expect(wrapper.get('a[title="Open on GitHub"]').attributes('href')).toBe(
      'https://github.com/TomzxCode/agentic/pull/42'
    )
    expect(wrapper.get('.review-pr-link').attributes('href')).toBe('/pr/TomzxCode/agentic/42')
  })

  it('shows a spinner for a review step that is running', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [
        pr({
          in_progress: { 'validate-pr': { sha: 'abc1234', started_at: '2026-01-12T08:00:00Z' } }
        })
      ]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    const running = wrapper.get('.review-step-running')
    expect(running.find('.spinner').exists()).toBe(true)
    expect(running.attributes('title')).toBe(`Validate: running since ${formatDateTime('2026-01-12T08:00:00Z')}`)
    // The running step shows the spinner in place of its stale report.
    expect(wrapper.findAll('.review-col-step .review-step')).toHaveLength(1)
  })

  it('shows a spinner for a running step that has no report yet', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [pr({ steps: {}, in_progress: { 'review-pr': { sha: 'abc1234', started_at: null } } })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    const running = wrapper.get('.review-step-running')
    expect(running.find('.spinner').exists()).toBe(true)
    expect(running.attributes('title')).toBe('Review: running')
  })

  it('links the author and the last commenter to their person page', async () => {
    store.people = [
      { id: 'p1', name: 'Alice', aliases: ['alice'] },
      { id: 'p2', name: 'Bob', aliases: ['bob'] }
    ]
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr()] })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    const author = wrapper.get('table a[href="/person/p1"]')
    expect(author.text()).toBe('alice')
    const commenter = wrapper.get('table a[href="/person/p2"]')
    expect(commenter.text()).toBe('bob')
  })

  it('links a repository heading to its app page when the repository is registered', async () => {
    store.repositories = [{ id: 'r1', name: 'agentic', remote_url: 'git@github.com:TomzxCode/agentic.git' }]
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr()] })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.get('.group-head a').attributes('href')).toBe('/repositories/tomzxcode/agentic')
  })

  it('leaves a repository heading as plain text when the app does not track it', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr()] })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('TomzxCode/agentic')
    expect(wrapper.find('.group-head a').exists()).toBe(false)
  })

  it('marks a pull request the review scan found, before any report exists', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [
        pr({
          title: 'Awaiting review',
          steps: {},
          stale_steps: [],
          reviewed_steps: 0,
          head_commit: '',
          reviewed_at: null,
          request_source: 'requested'
        })
      ]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.get('.review-source').text()).toBe('📨')
    expect(wrapper.get('.review-source').attributes('title')).toBe('A review is requested from you')
    expect(wrapper.get('.review-source').attributes('aria-label')).toBe('A review is requested from you')
    // Nothing has run for it, so every step column reads as empty.
    expect(wrapper.findAll('.review-step').length).toBe(0)
  })

  it('says when the review request is a team request', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [
        pr({ number: 42, steps: {}, request_source: 'requested', review_scope: 'team' }),
        pr({ number: 9, steps: {}, request_source: 'requested', review_scope: 'both' })
      ]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    const titles = wrapper.findAll('.review-source').map((mark) => mark.attributes('title'))
    expect(titles).toEqual(['A review is requested from your team', 'A review is requested from you and your team'])
  })

  it('marks an already-reviewed pull request with the review emoji', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [pr({ request_source: 'reviewed' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.get('.review-source').text()).toBe('👀')
    expect(wrapper.get('.review-source').attributes('title')).toBe(
      'You reviewed this pull request and it is still open'
    )
  })

  it('highlights a pull request past the review SLO', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [
        pr({ number: 42, request_source: 'requested', slo_wait_seconds: 183600, slo_seconds: 86400 }),
        pr({ number: 9, request_source: 'requested' })
      ]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    // No badge: the row is tinted and its colored edge explains why on hover.
    expect(wrapper.find('.review-past-slo').exists()).toBe(false)
    const edges = wrapper.findAll('.review-slo-edge')
    expect(edges).toHaveLength(1)
    expect(edges[0].text()).toBe('')
    expect(edges[0].attributes('title')).toBe('Past the review SLO: awaited your review for 2d 3h; the SLO is 1d.')
    expect(edges[0].attributes('aria-label')).toBe(edges[0].attributes('title'))
    // The whole row carries the highlight, and only the flagged row does.
    const rows = wrapper.findAll('tbody tr')
    expect(rows[0].classes()).toContain('review-past-slo-row')
    expect(rows[1].classes()).not.toContain('review-past-slo-row')
    // The header counts the flagged rows alongside the other totals.
    expect(wrapper.text()).toContain('2 PRs · 0 ready · 0 blocked · 1 past SLO')
  })

  it('marks a pull request GitHub has already approved', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42, review_decision: 'APPROVED' }), pr({ number: 9, review_decision: 'REVIEW_REQUIRED' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    // Approved rows are left out by default; cycle to "all" to read the mark.
    await wrapper.get('.review-approved-filter').trigger('click')
    await wrapper.get('.review-approved-filter').trigger('click')
    await flushPromises()

    const approved = wrapper.findAll('.review-approved')
    expect(approved).toHaveLength(1)
    expect(approved[0].text()).toBe('✅')
    expect(approved[0].attributes('aria-label')).toBe('Approved on GitHub')
    // The mark rides on the approved PR only, so the other row carries none.
    const rows = wrapper.findAll('tbody tr')
    expect(rows[0].find('.review-approved').exists()).toBe(true)
    expect(rows[1].find('.review-approved').exists()).toBe(false)
  })

  it('opens a report when a step cell is clicked', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr()] })
    mocks.report.mockResolvedValue({
      name: 'review-pr.abc1234.md',
      content: '<!-- {"step":"review-pr"} -->\n# Review\n\nLooks good.',
      truncated: false
    })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()
    const reviewCell = wrapper.findAll('.review-step').find((cell) => cell.attributes('title').startsWith('Review'))
    await reviewCell.trigger('click')
    await flushPromises()

    expect(mocks.report).toHaveBeenCalledWith('TomzxCode/agentic', 42, 'review-pr.abc1234.md')
    expect(wrapper.get('.review-content').text()).toContain('Looks good')
    // The marker comment is stripped from the rendered report.
    expect(wrapper.html()).not.toContain('step&quot;:&quot;review-pr')
  })

  it('colours a step cell by its verdict and keeps the cell free of text', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [
        pr({
          steps: {
            'review-pr': step({ verdict: 'pass' }),
            'validate-pr': step({ step: 'validate-pr', verdict: 'fail', report: 'validate-pr.abc1234.md' }),
            'verify-pr': step({ step: 'verify-pr', verdict: 'decide', report: 'verify-pr.abc1234.md' }),
            'analyze-test-coverage': step({
              step: 'analyze-test-coverage',
              verdict: 'informational',
              report: 'analyze-test-coverage.abc1234.md'
            })
          }
        })
      ]
    })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    const cell = (label) =>
      wrapper
        .findAll('.review-col-step .review-step')
        .find((entry) => entry.attributes('title').startsWith(label))
        .element.closest('td')

    expect(cell('Review').classList).toContain('review-cell-ok')
    expect(cell('Review').textContent.trim()).toBe('')
    expect(cell('Validate').classList).toContain('review-cell-danger')
    expect(cell('Validate').textContent.trim()).toBe('')
    expect(cell('Verify').classList).toContain('review-cell-warn')
    expect(cell('Verify').textContent.trim()).toBe('')
    expect(cell('Coverage').classList).toContain('review-cell-info')
    expect(cell('Coverage').textContent.trim()).toBe('')
    // No verdict marks or words are left in the step columns.
    expect(wrapper.find('.review-col-step .review-verdict').exists()).toBe(false)
  })

  it('shows the adversarial review and folds the surface reviews into one column', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [
        pr({
          steps: {
            'review-pr': step(),
            'adversarial-pr-review': step({
              step: 'adversarial-pr-review',
              verdict: 'breaks',
              reproduced_count: 2,
              report: 'adversarial-pr-review.abc1234.md'
            }),
            'review-api-changes': step({
              step: 'review-api-changes',
              verdict: 'fail',
              report: 'review-api-changes.abc1234.md'
            }),
            'review-db-changes': step({
              step: 'review-db-changes',
              verdict: 'pass',
              report: 'review-db-changes.abc1234.md'
            })
          }
        })
      ]
    })
    mocks.report.mockResolvedValue({ name: 'report.md', content: '# Report', truncated: false })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    const headers = wrapper.findAll('.review-table th').map((head) => head.text())
    expect(headers).toContain('Adversarial')
    expect(headers).toContain('Surfaces')

    const adversarial = wrapper
      .findAll('.review-col-step .review-step')
      .find((cell) => cell.attributes('title').startsWith('Adversarial'))
    expect(adversarial.text()).toBe('')
    expect(adversarial.element.closest('td').classList).toContain('review-cell-danger')
    expect(adversarial.attributes('title')).toContain('2 reproduced')

    // One token per surface that has a report, in CLI, SDK, API, DB order.
    // Each token carries its own verdict as a tint, since one cell can hold
    // several surfaces with different results.
    const surfaces = wrapper.findAll('.review-surface')
    expect(surfaces.map((entry) => entry.get('.review-surface-label').text())).toEqual(['API', 'DB'])
    expect(surfaces[0].find('.review-verdict').exists()).toBe(false)
    expect(surfaces[0].classes()).toContain('review-cell-danger')
    expect(surfaces[1].classes()).toContain('review-cell-ok')

    await surfaces[0].get('button').trigger('click')
    await flushPromises()
    expect(mocks.report).toHaveBeenCalledWith('TomzxCode/agentic', 42, 'review-api-changes.abc1234.md')
  })

  it('shows a running surface review in the surfaces column', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [
        pr({
          steps: { 'review-pr': step() },
          in_progress: { 'review-cli-changes': { sha: 'abc1234', started_at: '2026-01-12T08:00:00Z' } }
        })
      ]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    const surfaces = wrapper.get('.review-surface')
    expect(surfaces.find('.review-step-running').exists()).toBe(true)
    expect(surfaces.get('.review-step-running').attributes('title')).toContain('CLI: running since')
  })

  it('emojis a link to a PR task before the readiness light', async () => {
    store.tasks = [{ id: 't1', title: 'Land the PR', status: 'in_progress' }]
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ task_ids: ['t1'] })] })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    const link = wrapper.get('a[href="/task/t1?view=pr"]')
    expect(link.text()).toBe('📝')
    expect(link.attributes('aria-label')).toBe('Task: Land the PR (opens in PR view)')
    expect(wrapper.find('.review-task-new').exists()).toBe(false)
    // The task link comes first in the PR cell, before the readiness light.
    expect(wrapper.get('.review-pr-cell-inner').element.firstElementChild.getAttribute('href')).toBe('/task/t1?view=pr')
  })

  it('offers a "+" before the readiness light that imports the PR into a task when none is linked', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr()] })
    mocks.createTask.mockResolvedValue({ id: 't2', title: 'Imported task', status: 'open' })
    vi.spyOn(store, 'loadTasks').mockImplementation(async () => {
      store.tasks = [{ id: 't2', title: 'Imported task', status: 'open' }]
    })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    const add = wrapper.get('.review-task-new')
    expect(add.attributes('title')).toBe('Create a task from PR #42')
    expect(wrapper.get('.review-pr-cell-inner').element.firstElementChild).toBe(add.element)
    await add.trigger('click')
    await flushPromises()

    expect(mocks.createTask).toHaveBeenCalledWith({ github_url: 'https://github.com/TomzxCode/agentic/pull/42' })
    expect(wrapper.get('a[href="/task/t2?view=pr"]').text()).toBe('📝')
    expect(wrapper.find('.review-task-new').exists()).toBe(false)
  })

  it('approves an open pull request from the queue after a confirmation', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ readiness: 'green' })] })
    mocks.approve.mockResolvedValue({ number: 42, repository: 'TomzxCode/agentic', approved: true })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    const button = wrapper.get('.review-approve')
    expect(button.attributes('title')).toBe('Approve PR #42 on GitHub')
    await button.trigger('click')

    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('TomzxCode/agentic#42')
    await dialog.get('textarea').setValue('Ship it')
    await dialog
      .findAll('button')
      .find((entry) => entry.text() === 'Approve')
      .trigger('click')
    await flushPromises()

    expect(mocks.approve).toHaveBeenCalledWith('TomzxCode/agentic', 42, 'Ship it')
    expect(store.toast).toMatchObject({ message: 'Approved TomzxCode/agentic#42', isError: false })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('.review-approve').exists()).toBe(false)
    expect(wrapper.get('.review-approved-by-me').attributes('title')).toBe('You approved this pull request')
    // GitHub's own review decision is left alone: another required review can
    // still be missing, so the row does not claim the PR is approved.
    expect(wrapper.find('.review-approved').exists()).toBe(false)
  })

  it('leaves the pull request unapproved when the dialog is cancelled', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr()] })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await wrapper.get('.review-approve').trigger('click')
    await wrapper
      .get('[role="dialog"]')
      .findAll('button')
      .find((entry) => entry.text() === 'Cancel')
      .trigger('click')
    await flushPromises()

    expect(mocks.approve).not.toHaveBeenCalled()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.find('.review-approve').exists()).toBe(true)
  })

  it('offers approval when the pull request state could not be read', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ state: '' })] })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    // The queue treats a row whose state could not be read as open.
    expect(wrapper.find('.review-approve').exists()).toBe(true)
  })

  it('does not offer approval for a draft, a closed, or an already-approved pull request', async () => {
    // The approved filter hides approved rows by default, so show them.
    localStorage.setItem('agentic.reviewQueueFilters', JSON.stringify({ approvedFilter: 'all' }))
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 3 },
      prs: [
        pr({ number: 1, draft: true }),
        pr({ number: 2, state: 'MERGED' }),
        pr({ number: 3, review_decision: 'APPROVED' })
      ]
    })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/3"]').exists()).toBe(true)
    expect(wrapper.find('.review-approve').exists()).toBe(false)
  })

  it('keeps the dialog open and reports the error when GitHub rejects the approval', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr()] })
    mocks.approve.mockRejectedValue(new Error('Can not approve your own pull request'))

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await wrapper.get('.review-approve').trigger('click')
    await wrapper
      .get('[role="dialog"]')
      .findAll('button')
      .find((entry) => entry.text() === 'Approve')
      .trigger('click')
    await flushPromises()

    expect(store.toast).toMatchObject({
      message: 'Can not approve your own pull request',
      isError: true
    })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.find('.review-approved-by-me').exists()).toBe(false)
  })

  it('shows only open pull requests by default, with a count per status', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 3 },
      prs: [pr({ number: 42, state: 'OPEN' }), pr({ number: 9, state: 'MERGED' }), pr({ number: 7, state: 'CLOSED' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(false)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/7"]').exists()).toBe(false)

    const chips = wrapper.findAll('.review-state-filter')
    expect(chips.map((chip) => chip.text())).toEqual(['Open 1', 'Merged 1', 'Closed 1', 'All 3'])
    // Open is the active filter, so its chip reads as pressed.
    expect(chips[0].attributes('aria-pressed')).toBe('true')
    // The header totals cover what the filter shows, not the whole queue.
    expect(wrapper.text()).toContain('1 PR · 0 ready · 0 blocked')
  })

  it('switches the status when another chip is clicked', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42, state: 'OPEN' }), pr({ number: 9, state: 'MERGED' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await wrapper.findAll('.review-state-filter')[1].trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
  })

  it('treats a row with no status as open', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ state: '' })] })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
  })

  it('splits the queue by who the review request is for', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 3 },
      prs: [
        pr({ number: 42, review_scope: 'me' }),
        pr({ number: 9, review_scope: 'team' }),
        pr({ number: 7, review_scope: 'both' })
      ]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    const chips = wrapper.findAll('.review-scope-filter')
    expect(chips.map((chip) => chip.text())).toEqual(['Team + me 3', 'Team 2', 'Me 2'])
    expect(chips.map((chip) => chip.attributes('aria-pressed'))).toEqual(['true', 'false', 'false'])
    expect(chips[0].attributes('title')).toBe('Reviews requested from your teams and from you')
    expect(chips[1].attributes('title')).toBe('Only reviews requested from your teams')
    expect(chips[2].attributes('title')).toBe('Only reviews requested from you, or ones you already reviewed')

    // The whole queue is shown by default.
    for (const number of [42, 9, 7]) {
      expect(wrapper.find(`a[href="https://github.com/TomzxCode/agentic/pull/${number}"]`).exists()).toBe(true)
    }

    // Team keeps the team-only request and the one both a team and the user owe.
    await wrapper.findAll('.review-scope-filter')[1].trigger('click')
    await flushPromises()
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/7"]').exists()).toBe(true)

    // Me keeps the personal request and the shared one.
    await wrapper.findAll('.review-scope-filter')[2].trigger('click')
    await flushPromises()
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(false)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/7"]').exists()).toBe(true)

    // Team + me brings everything back.
    await wrapper.findAll('.review-scope-filter')[0].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('3 PRs')
  })

  it('names a scope with no matching rows and offers to show everything', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [pr({ number: 42, review_scope: 'me' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await wrapper.findAll('.review-scope-filter')[1].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('No team review requests match.')

    const showAll = wrapper.findAll('button').find((button) => button.text() === 'Show team and mine')
    await showAll.trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.findAll('.review-scope-filter')[0].attributes('aria-pressed')).toBe('true')
  })

  it('remembers the scope choice when the queue is reopened', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42, review_scope: 'me' }), pr({ number: 9, review_scope: 'team' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await wrapper.findAll('.review-scope-filter')[1].trigger('click')
    await flushPromises()
    wrapper.unmount()

    const reopened = mount(ReviewsView, stub)
    await flushPromises()

    expect(reopened.findAll('.review-scope-filter')[1].attributes('aria-pressed')).toBe('true')
    expect(reopened.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(reopened.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
  })

  it('hides drafts by default, then shows only drafts, then everything', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42 }), pr({ number: 9, draft: true })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    // Hidden by default: the draft row is out, the other row stays.
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(false)
    expect(filterState(wrapper, 'draft')).toBe('hidden')
    expect(filterCount(wrapper, 'draft')).toBe('1')
    expect(wrapper.get('.review-draft-filter').attributes('title')).toBe('Drafts are hidden; click to show only drafts')
    // Drafts are left out of the header totals too.
    expect(wrapper.text()).toContain('1 PR ·')

    // One click keeps only drafts.
    await wrapper.get('.review-draft-filter').trigger('click')
    await flushPromises()
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(filterState(wrapper, 'draft')).toBe('only')

    // A second click keeps everything.
    await wrapper.get('.review-draft-filter').trigger('click')
    await flushPromises()
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(filterState(wrapper, 'draft')).toBe('all')
    expect(wrapper.text()).toContain('2 PRs ·')

    // A third click hides them again.
    await wrapper.get('.review-draft-filter').trigger('click')
    await flushPromises()
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(false)
    expect(filterState(wrapper, 'draft')).toBe('hidden')
    expect(filterCount(wrapper, 'draft')).toBe('1')
  })

  it('names the hidden drafts in the empty state and includes them on request', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ number: 9, draft: true })] })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('1 draft pull request is hidden.')
    const include = wrapper.findAll('button').find((button) => button.text() === 'Include drafts')
    await include.trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(filterState(wrapper, 'draft')).toBe('all')
  })

  it('says when only drafts are shown and offers to show everything', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ number: 42 })] })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    // Only drafts is a state where nothing here matches.
    await wrapper.get('.review-draft-filter').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('No drafts match.')

    const showAll = wrapper.findAll('button').find((button) => button.text() === 'Show every pull request')
    await showAll.trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(filterState(wrapper, 'draft')).toBe('all')
    expect(filterCount(wrapper, 'draft')).toBe('0')
  })

  it('filters the rows by the search text', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42, title: 'Add filters' }), pr({ number: 9, title: 'Fix the parser', author: 'carol' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await wrapper.get('.review-search').setValue('parser')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('1 PR ·')
  })

  it('filters the rows by author picked from the searchable dropdown', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42, author: 'alice' }), pr({ number: 9, author: 'carol' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await openAuthors(wrapper)
    expect(wrapper.findAll('.ss-option').map((option) => option.text())).toEqual(['alice (1)', 'carol (1)'])

    await toggleAuthor(wrapper, 'carol')

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
    // The trigger summarizes the chosen author.
    expect(wrapper.get('.review-author-select .ss-label').text()).toBe('carol (1)')
  })

  it('type-filters the author options and takes several authors', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 3 },
      prs: [pr({ number: 42, author: 'alice' }), pr({ number: 9, author: 'bob' }), pr({ number: 7, author: 'carol' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await openAuthors(wrapper)
    await wrapper.get('.ss-search').setValue('car')
    expect(wrapper.findAll('.ss-option').map((option) => option.text())).toEqual(['carol (1)'])
    await toggleAuthor(wrapper, 'carol')

    await wrapper.get('.ss-search').setValue('ali')
    await toggleAuthor(wrapper, 'alice')

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/7"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(false)
    expect(wrapper.get('.review-author-select .ss-label').text()).toBe('alice (1), carol (1)')
  })

  it('filters the rows by repository picked from the searchable dropdown', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [prIn('TomzxCode/agentic', { number: 42 }), prIn('acme/api', { number: 9 })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await openRepositories(wrapper)
    expect(wrapper.findAll('.ss-option').map((option) => option.text())).toEqual([
      'acme/api (1)',
      'TomzxCode/agentic (1)'
    ])

    await toggleRepository(wrapper, 'acme/api')

    expect(wrapper.find('a[href="https://github.com/acme/api/pull/9"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
    expect(wrapper.findAll('.group-head').map((head) => head.text())).toEqual(['acme/api1'])
    // The trigger summarizes the chosen repository.
    expect(wrapper.get('.review-repository-select .ss-label').text()).toBe('acme/api (1)')
  })

  it('takes several repositories and clears them from the empty state', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 3 },
      prs: [prIn('TomzxCode/agentic', { number: 42 }), prIn('acme/api', { number: 9 }), prIn('acme/web', { number: 7 })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await openRepositories(wrapper)
    await toggleRepository(wrapper, 'acme/api')
    await toggleRepository(wrapper, 'acme/web')

    expect(wrapper.find('a[href="https://github.com/acme/api/pull/9"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/acme/web/pull/7"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
    expect(wrapper.get('.review-repository-select .ss-label').text()).toBe('acme/api (1), acme/web (1)')

    // Choosing a repository with no matching rows under the status filter names
    // it and offers to clear the selection.
    await wrapper.findAll('.review-state-filter')[1].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('No pull requests in acme/api, acme/web.')

    const clear = wrapper.findAll('button').find((button) => button.text() === 'Clear repositories')
    await clear.trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
    // Merged still applies, so the open agentic row stays hidden and the clear
    // button is gone now that no repository is chosen.
    expect(wrapper.findAll('button').some((button) => button.text() === 'Clear repositories')).toBe(false)
  })

  it('selects every repository and clears the selection from the dropdown', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [prIn('TomzxCode/agentic', { number: 42 }), prIn('acme/api', { number: 9 })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await openRepositories(wrapper)
    await toggleRepository(wrapper, 'acme/api')
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)

    await wrapper.findAll('.ss-bulk-action')[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/acme/api/pull/9"]').exists()).toBe(true)
    expect(wrapper.get('.review-repository-select .ss-label').text()).toBe('acme/api (1), TomzxCode/agentic (1)')

    await wrapper.findAll('.ss-bulk-action')[1].trigger('click')
    await flushPromises()
    expect(wrapper.get('.review-repository-select .ss-label').text()).toBe('All repositories')
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
  })

  it('selects every author and clears the selection from the dropdown', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42, author: 'alice' }), pr({ number: 9, author: 'carol' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await openAuthors(wrapper)
    await toggleAuthor(wrapper, 'carol')
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)

    await wrapper.findAll('.ss-bulk-action')[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.get('.review-author-select .ss-label').text()).toBe('alice (1), carol (1)')

    await wrapper.findAll('.ss-bulk-action')[1].trigger('click')
    await flushPromises()
    expect(wrapper.get('.review-author-select .ss-label').text()).toBe('All authors')
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
  })

  it('names the chosen authors in the empty state and clears them', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42, author: 'alice', state: 'OPEN' }), pr({ number: 9, author: 'carol', state: 'MERGED' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await openAuthors(wrapper)
    await toggleAuthor(wrapper, 'carol')

    expect(wrapper.text()).toContain('No pull requests by carol.')
    const clear = wrapper.findAll('button').find((button) => button.text() === 'Clear author')
    await clear.trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
  })

  it('offers to show all when no pull request matches the default status', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ number: 9, state: 'MERGED' })] })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('No open pull requests.')
    const showAll = wrapper.findAll('button').find((button) => button.text() === 'Show all')
    await showAll.trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
  })

  it('remembers every filter when the queue is reopened', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 3 },
      prs: [
        prIn('TomzxCode/agentic', { number: 42, author: 'alice', title: 'Add filters', state: 'MERGED' }),
        prIn('acme/api', { number: 9, author: 'carol', title: 'Fix the parser', state: 'MERGED' }),
        prIn('acme/api', { number: 7, author: 'carol', title: 'Other work', state: 'OPEN' })
      ]
    })

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await openRepositories(wrapper)
    await toggleRepository(wrapper, 'acme/api')
    await openAuthors(wrapper)
    await toggleAuthor(wrapper, 'carol')
    await wrapper.findAll('.review-state-filter')[1].trigger('click')
    await wrapper.get('.review-search').setValue('parser')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/acme/api/pull/9"]').exists()).toBe(true)
    wrapper.unmount()

    // Coming back to the page restores the same filters, so the same row shows.
    const reopened = mount(ReviewsView, stub)
    await flushPromises()

    expect(reopened.get('.review-repository-select .ss-label').text()).toBe('acme/api (2)')
    expect(reopened.get('.review-author-select .ss-label').text()).toBe('carol (2)')
    expect(reopened.findAll('.review-state-filter')[1].attributes('aria-pressed')).toBe('true')
    expect(reopened.get('.review-search').element.value).toBe('parser')
    expect(reopened.find('a[href="https://github.com/acme/api/pull/9"]').exists()).toBe(true)
    expect(reopened.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
    expect(reopened.find('a[href="https://github.com/acme/api/pull/7"]').exists()).toBe(false)
  })

  it('remembers the drafts choice when the queue is reopened', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ number: 9, draft: true })] })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await wrapper.get('.review-draft-filter').trigger('click')
    await flushPromises()
    wrapper.unmount()

    const reopened = mount(ReviewsView, stub)
    await flushPromises()

    expect(filterState(reopened, 'draft')).toBe('only')
    expect(reopened.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
  })

  it('hides approved pull requests by default, then shows only approved, then everything', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42 }), pr({ number: 9, review_decision: 'APPROVED' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(false)
    const toggle = wrapper.get('.review-approved-filter')
    expect(filterState(wrapper, 'approved')).toBe('hidden')
    expect(filterCount(wrapper, 'approved')).toBe('1')
    expect(toggle.attributes('title')).toBe(
      'Approved pull requests are hidden; click to show only approved pull requests'
    )
    // The hidden row is left out of the header totals too.
    expect(wrapper.text()).toContain('1 PR ·')

    // One click keeps only the approved pull request.
    await toggle.trigger('click')
    await flushPromises()
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(filterState(wrapper, 'approved')).toBe('only')

    // A second click keeps everything, and the approved row carries its mark.
    await wrapper.get('.review-approved-filter').trigger('click')
    await flushPromises()
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(filterState(wrapper, 'approved')).toBe('all')
    expect(wrapper.text()).toContain('2 PRs ·')
    expect(wrapper.findAll('.review-approved')).toHaveLength(1)
  })

  it('names the hidden approved pull requests in the empty state and includes them on request', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [pr({ number: 9, review_decision: 'APPROVED' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('1 approved pull request is hidden.')
    const include = wrapper.findAll('button').find((button) => button.text() === 'Include approved')
    await include.trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(filterState(wrapper, 'approved')).toBe('all')
  })

  it('remembers the approved choice when the queue is reopened', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [pr({ number: 9, review_decision: 'APPROVED' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await wrapper.get('.review-approved-filter').trigger('click')
    await flushPromises()
    wrapper.unmount()

    const reopened = mount(ReviewsView, stub)
    await flushPromises()

    expect(filterState(reopened, 'approved')).toBe('only')
    expect(reopened.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
  })

  it('keeps reviewed pull requests by default and cycles them hidden, only, all', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42 }), pr({ number: 9, request_source: 'reviewed' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    // Reviewed rows are kept by default, unlike drafts and approved ones.
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(filterState(wrapper, 'reviewed')).toBe('all')
    expect(filterCount(wrapper, 'reviewed')).toBe('1')
    expect(wrapper.get('.review-reviewed-filter').attributes('title')).toBe(
      'Everything is shown; click to hide reviewed pull requests'
    )

    // One click hides the ones already reviewed.
    await wrapper.get('.review-reviewed-filter').trigger('click')
    await flushPromises()
    expect(filterState(wrapper, 'reviewed')).toBe('hidden')
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(false)

    // Another click keeps only those.
    await wrapper.get('.review-reviewed-filter').trigger('click')
    await flushPromises()
    expect(filterState(wrapper, 'reviewed')).toBe('only')
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(false)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)

    // The last click brings everything back.
    await wrapper.get('.review-reviewed-filter').trigger('click')
    await flushPromises()
    expect(filterState(wrapper, 'reviewed')).toBe('all')
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
  })

  it('offers to include the reviewed pull requests it hides', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [pr({ number: 9, request_source: 'reviewed' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    await wrapper.get('.review-reviewed-filter').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('1 reviewed pull request is hidden.')

    const include = wrapper.findAll('button').find((button) => button.text() === 'Include reviewed')
    await include.trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
    expect(filterState(wrapper, 'reviewed')).toBe('all')
  })

  it('says when only reviewed pull requests are shown and offers to show everything', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ number: 42 })] })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    // Cycle from all to hidden to only.
    await wrapper.get('.review-reviewed-filter').trigger('click')
    await wrapper.get('.review-reviewed-filter').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('No pull requests you reviewed match.')

    const showAll = wrapper.findAll('button').find((button) => button.text() === 'Show every pull request')
    await showAll.trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(filterState(wrapper, 'reviewed')).toBe('all')
  })

  it('remembers the reviewed choice when the queue is reopened', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [pr({ number: 9, request_source: 'reviewed' })]
    })
    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    // From "all", one click hides them and a second keeps only them.
    await wrapper.get('.review-reviewed-filter').trigger('click')
    await wrapper.get('.review-reviewed-filter').trigger('click')
    await flushPromises()
    wrapper.unmount()

    const reopened = mount(ReviewsView, stub)
    await flushPromises()

    expect(filterState(reopened, 'reviewed')).toBe('only')
    expect(reopened.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
  })

  it('falls back to the default filters when the stored filters are unusable', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42 }), pr({ number: 9, draft: true })]
    })
    localStorage.setItem(
      'agentic.reviewQueueFilters',
      JSON.stringify({
        state: 'bogus',
        repositories: 'acme/api',
        authors: 3,
        includeDrafts: 'yes',
        includeApproved: 'yes',
        search: { q: 'x' }
      })
    )

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.findAll('.review-state-filter')[0].attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('.review-repository-select .ss-label').text()).toBe('All repositories')
    expect(wrapper.get('.review-author-select .ss-label').text()).toBe('All authors')
    expect(filterState(wrapper, 'draft')).toBe('hidden')
    expect(filterCount(wrapper, 'draft')).toBe('1')
    expect(filterState(wrapper, 'approved')).toBe('hidden')
    expect(filterCount(wrapper, 'approved')).toBe('0')
    expect(filterState(wrapper, 'reviewed')).toBe('all')
    expect(wrapper.get('.review-search').element.value).toBe('')
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(false)
  })

  it('migrates a stored boolean draft or approved choice to the three-state filter', async () => {
    mocks.queue.mockResolvedValue({
      root: null,
      counts: { total: 2 },
      prs: [pr({ number: 42 }), pr({ number: 9, draft: true })]
    })
    // The old toggles stored booleans; true meant "show them alongside the
    // rest", which is now the "all" state.
    localStorage.setItem('agentic.reviewQueueFilters', JSON.stringify({ includeDrafts: true, includeApproved: true }))

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(filterState(wrapper, 'draft')).toBe('all')
    expect(filterState(wrapper, 'approved')).toBe('all')
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/9"]').exists()).toBe(true)
  })

  it('falls back to the default filters when the stored filters cannot be parsed', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ number: 42 })] })
    localStorage.setItem('agentic.reviewQueueFilters', '{not json')

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.findAll('.review-state-filter')[0].attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('.review-search').element.value).toBe('')
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
  })
})
