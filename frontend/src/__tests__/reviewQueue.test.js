import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  queue: vi.fn(),
  report: vi.fn(),
  createTask: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    reviews: { queue: mocks.queue, report: mocks.report },
    tasks: { create: mocks.createTask }
  }
}))

import ReviewsView from '../views/ReviewsView.vue'
import { store, formatDateTime } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const stub = {
  global: { stubs: { RouterLink: RouterLinkStub, ShareFindingsModal: { template: '<div class="share-stub" />' } } }
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
    expect(wrapper.get('.review-pr-cell a').attributes('title')).toContain('Still needs attention')
    expect(wrapper.text()).not.toContain('Needs review')
    // Nobody in the directory carries alice or bob, so both read grey and link
    // to the prefilled creation page rather than a person page.
    expect(wrapper.get('table a[href="/person/new?name=alice&alias=alice"]').classes()).toContain('faint')
    // The last review event reads as an absolute local date and time.
    expect(wrapper.get('.review-reviewed-at').text()).toBe(formatDateTime('2026-01-12T06:20:00Z'))
    // The validate step is stale, so its reviewed commit is shown in red.
    expect(wrapper.get('.review-stale').text()).toBe('abc1234')
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

    expect(wrapper.get('.group-head a').attributes('href')).toBe('/repositories/r1')
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

    expect(wrapper.get('.review-source').text()).toBe('requested')
    expect(wrapper.get('.review-source').attributes('title')).toBe('A review is requested from you')
    // Nothing has run for it, so every step column reads as empty.
    expect(wrapper.findAll('.review-step').length).toBe(0)
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
    expect(wrapper.get('.review-pr-cell').element.firstElementChild.getAttribute('href')).toBe('/task/t1?view=pr')
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
    expect(wrapper.get('.review-pr-cell').element.firstElementChild).toBe(add.element)
    await add.trigger('click')
    await flushPromises()

    expect(mocks.createTask).toHaveBeenCalledWith({ github_url: 'https://github.com/TomzxCode/agentic/pull/42' })
    expect(wrapper.get('a[href="/task/t2?view=pr"]').text()).toBe('📝')
    expect(wrapper.find('.review-task-new').exists()).toBe(false)
  })

  it('offers a share action that opens the findings modal for the PR', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ task_ids: ['t1'] })] })
    store.tasks = [{ id: 't1', title: 'Land the PR', status: 'in_progress' }]

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.find('.share-stub').exists()).toBe(false)
    await wrapper.get('.review-share').trigger('click')
    await flushPromises()
    expect(wrapper.find('.share-stub').exists()).toBe(true)
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

  it('falls back to the default filters when the stored filters are unusable', async () => {
    mocks.queue.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr({ number: 42 })] })
    localStorage.setItem(
      'agentic.reviewQueueFilters',
      JSON.stringify({ state: 'bogus', repositories: 'acme/api', authors: 3, search: { q: 'x' } })
    )

    const wrapper = mount(ReviewsView, stub)
    await flushPromises()

    expect(wrapper.findAll('.review-state-filter')[0].attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('.review-repository-select .ss-label').text()).toBe('All repositories')
    expect(wrapper.get('.review-author-select .ss-label').text()).toBe('All authors')
    expect(wrapper.get('.review-search').element.value).toBe('')
    expect(wrapper.find('a[href="https://github.com/TomzxCode/agentic/pull/42"]').exists()).toBe(true)
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
