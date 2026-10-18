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
    reviewed_at: '2026-01-12T06:20:00Z',
    steps: {
      'review-pr': step(),
      'validate-pr': step({ step: 'validate-pr', report: 'validate-pr.abc1234.md', stale: true })
    },
    stale_steps: ['validate-pr'],
    reviewed_steps: 2,
    readiness: 'yellow',
    status: 'needs-review',
    item_id: null,
    task_ids: [],
    ...overrides
  }
}

beforeEach(() => {
  vi.clearAllMocks()
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
    expect(wrapper.find('table a[href^="/person/"]').exists()).toBe(false)
    // The last review event reads as an absolute local date and time.
    expect(wrapper.get('.review-reviewed-at').text()).toBe(formatDateTime('2026-01-12T06:20:00Z'))
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
})
