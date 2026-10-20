import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  taskReviews: vi.fn(),
  report: vi.fn(),
  findings: vi.fn(),
  createRun: vi.fn(),
  githubIssue: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    github: { issue: mocks.githubIssue },
    reviews: { task: mocks.taskReviews, report: mocks.report, findings: mocks.findings },
    runs: { create: mocks.createRun }
  }
}))

import TaskReviewPanel from '../components/TaskReviewPanel.vue'
import { store } from '../store'

// The agent panel's adopt(), so a test can see the run the findings selector
// starts handed over to the panel.
const adopt = vi.fn()

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const AgentPanelStub = {
  setup(_, { expose }) {
    expose({ adopt })
    return () => h('div', { class: 'agent-stub' })
  }
}
const stub = {
  global: { stubs: { RouterLink: RouterLinkStub, AgentPanel: AgentPanelStub } }
}

function finding(overrides = {}) {
  return {
    step: 'review-pr',
    title: 'Fix the thing',
    description: 'It is broken.',
    severity: 'must',
    status: 'open',
    sha: 'abc1234',
    ...overrides
  }
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
    owner: 'acme',
    name: 'api',
    repository: 'acme/api',
    number: 42,
    title: 'Do the thing',
    url: 'https://github.com/acme/api/pull/42',
    author: 'alice',
    state: 'OPEN',
    draft: false,
    head_commit: 'abc1234',
    steps: { 'review-pr': step() },
    in_progress: {},
    stale_steps: [],
    reviewed_steps: 1,
    readiness: 'yellow',
    status: 'needs-review',
    task_ids: [],
    ...overrides
  }
}

const task = {
  id: 't1',
  title: 'Review the thing',
  associations: [
    {
      id: 'a1',
      item: {
        id: 'i1',
        source: 'github',
        kind: 'pull_request',
        url: 'https://github.com/acme/api/pull/42',
        title: 'Stored PR title',
        content: 'stored PR body',
        metadata_json: {}
      }
    }
  ]
}

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  store.people = []
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  mocks.taskReviews.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr()] })
  mocks.findings.mockResolvedValue([finding()])
  mocks.createRun.mockResolvedValue({ id: 'r1', status: 'queued' })
  mocks.githubIssue.mockResolvedValue({
    number: 42,
    title: 'Do the thing',
    url: 'https://github.com/acme/api/pull/42',
    state: 'OPEN',
    is_draft: false,
    created_at: '2026-01-10T00:00:00Z',
    author: 'alice',
    labels: ['enhancement'],
    body: 'It **adds** the thing.'
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('TaskReviewPanel', () => {
  it('shows the review queue row for each linked pull request', async () => {
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    expect(mocks.taskReviews).toHaveBeenCalledWith('t1', { refresh: false })
    expect(wrapper.text()).toContain('acme/api#42')
    expect(wrapper.text()).toContain('Do the thing')
    expect(wrapper.text()).toContain('alice')
    // The readiness light is the tooltip on the panel head.
    expect(wrapper.get('.task-pr-readiness').attributes('title')).toContain('Still needs attention')
    // The reviewed commit and the review step's verdict are shown.
    expect(wrapper.get('.task-pr-reviewed a').text()).toBe('abc1234')
    expect(wrapper.text()).toContain('Review')
  })

  it('shows a spinner for a review step that is running', async () => {
    mocks.taskReviews.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [
        pr({
          in_progress: { 'validate-pr': { sha: 'abc1234', started_at: '2026-01-12T08:00:00Z' } }
        })
      ]
    })
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    const running = wrapper.get('.review-step-running')
    expect(running.find('.spinner').exists()).toBe(true)
    expect(running.attributes('title')).toContain('Validate: running since')
  })

  it('shows the pull request description and metadata, as issue mode does', async () => {
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    expect(mocks.githubIssue).toHaveBeenCalledWith('https://github.com/acme/api/pull/42')
    // The state badge, labels, and body come from the GitHub read.
    expect(wrapper.get('.task-item-title .badge').text()).toBe('Open')
    expect(wrapper.get('.task-item-meta .badge').text()).toBe('enhancement')
    expect(wrapper.get('.task-item-body').html()).toContain('<strong>adds</strong>')
  })

  it('falls back to the stored pull request when GitHub cannot be read', async () => {
    mocks.githubIssue.mockRejectedValue(new Error('ghx failed'))
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    expect(wrapper.text()).toContain('Could not read the pull request from GitHub')
    expect(wrapper.text()).toContain('Stored PR title')
    expect(wrapper.text()).toContain('stored PR body')
  })

  it('says so when the store has no reports for the linked pull request', async () => {
    mocks.taskReviews.mockResolvedValue({ root: null, counts: { total: 0 }, prs: [] })
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    expect(wrapper.text()).toContain('acme/api#42')
    expect(wrapper.text()).toContain('No review reports')
  })

  it('opens a step report in the viewer', async () => {
    mocks.report.mockResolvedValue({
      name: 'review-pr.abc1234.md',
      content: '<!-- {"step":"review-pr"} -->\n# Review\n\nLooks good.',
      truncated: false
    })
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    await wrapper.get('.task-pr-steps .review-step').trigger('click')
    await flushPromises()

    expect(mocks.report).toHaveBeenCalledWith('acme/api', 42, 'review-pr.abc1234.md')
    expect(wrapper.get('.review-content').text()).toContain('Looks good')
    expect(wrapper.html()).not.toContain('step&quot;:&quot;review-pr')
  })

  it('shows a message when the task links no pull request', async () => {
    const wrapper = mount(TaskReviewPanel, { props: { task: { id: 't1', associations: [] } }, ...stub })
    await flushPromises()
    expect(wrapper.text()).toContain('not linked to a pull request')
  })

  it('shows the agent panel so the pull requests can be worked through an agent', async () => {
    const wrapper = mount(TaskReviewPanel, { props: { task, harnesses: [] }, ...stub })
    await flushPromises()
    // The Agent panel is the interface for acting on the pull requests, as in
    // issue mode.
    expect(wrapper.get('.agent-stub').exists()).toBe(true)
  })

  it('keeps the agent panel when the review queue cannot be read', async () => {
    mocks.taskReviews.mockRejectedValue(new Error('queue failed'))
    const wrapper = mount(TaskReviewPanel, { props: { task, harnesses: [] }, ...stub })
    await flushPromises()

    expect(wrapper.text()).toContain('Could not load the review queue')
    expect(wrapper.get('.agent-stub').exists()).toBe(true)
  })

  it('lists the PR findings inline below the review-step row', async () => {
    mocks.findings.mockResolvedValue([
      finding({ title: 'Fix the thing' }),
      finding({ title: 'Tidy the helper', severity: 'may' })
    ])
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    expect(mocks.findings).toHaveBeenCalledWith('acme/api', 42)
    const selector = wrapper.get('.findings-selector')
    expect(selector.text()).toContain('Fix the thing')
    expect(selector.text()).toContain('Tidy the helper')
    // The Behavior -> Review step row comes first; the findings follow it.
    expect(selector.element.previousElementSibling.classList.contains('task-pr-steps')).toBe(true)
  })

  it('sends the selected findings to an agent on the task', async () => {
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    await wrapper.get('.findings-selector .btn.primary').trigger('click')
    await flushPromises()

    expect(mocks.createRun).toHaveBeenCalledWith('t1', { prompt: expect.stringContaining('Fix the thing') })
    expect(store.toast).toEqual({ message: 'Sent the findings to an agent', isError: false })
  })

  it('hands the run it starts to the agent panel, so its history updates at once', async () => {
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    await wrapper.get('.findings-selector .btn.primary').trigger('click')
    await flushPromises()

    expect(adopt).toHaveBeenCalledWith({ id: 'r1', status: 'queued' })
  })
})
