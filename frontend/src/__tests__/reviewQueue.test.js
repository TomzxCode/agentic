import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  queue: vi.fn(),
  report: vi.fn()
}))

vi.mock('../api', () => ({
  api: { reviews: { queue: mocks.queue, report: mocks.report } }
}))

import ReviewsView from '../views/ReviewsView.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

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
  return {
    owner: 'TomzxCode',
    name: 'agentic',
    repository: 'TomzxCode/agentic',
    number: 42,
    title: 'Do the thing',
    url: 'https://github.com/TomzxCode/agentic/pull/42',
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
    steps: {
      'review-pr': step(),
      'validate-pr': step({ step: 'validate-pr', report: 'validate-pr.abc1234.md', stale: true })
    },
    stale_steps: ['validate-pr'],
    reviewed_steps: 2,
    readiness: 'yellow',
    status: 'needs-review',
    item_id: null,
    ...overrides
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  store.people = []
  store.repositories = []
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  vi.spyOn(store, 'loadRepositories').mockResolvedValue()
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
    expect(wrapper.find('table a[href^="/person/"]').exists()).toBe(false)
    // The validate step is stale, so its reviewed commit is shown in red.
    expect(wrapper.get('.review-stale').text()).toBe('abc1234')
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
})
