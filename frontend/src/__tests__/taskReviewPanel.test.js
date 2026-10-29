import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  taskReviews: vi.fn(),
  report: vi.fn(),
  findings: vi.fn(),
  createRun: vi.fn(),
  githubIssue: vi.fn(),
  pullReviewers: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    github: { issue: mocks.githubIssue, pullReviewers: mocks.pullReviewers },
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
  mocks.pullReviewers.mockResolvedValue({ reviewers: [], error: null })
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

  it('shows the pull request description and metadata on the description tab', async () => {
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    expect(mocks.githubIssue).toHaveBeenCalledWith('https://github.com/acme/api/pull/42')
    // The state badge and labels come from the GitHub read on every pane; the
    // body belongs to the description pane.
    expect(wrapper.get('.task-item-title .badge').text()).toBe('Open')
    expect(wrapper.get('.task-item-meta .badge').text()).toBe('enhancement')
    expect(wrapper.find('.task-item-body').exists()).toBe(false)
    // The panes are one switch at the top of the pull request, with the
    // description first and the reports only when there are any.
    expect(wrapper.findAll('.pr-panel-tabs button').map((button) => button.text())).toEqual([
      'Description',
      'Review',
      'Reports 1'
    ])

    await wrapper.get('.pr-panel-tabs button:nth-of-type(1)').trigger('click')
    await flushPromises()
    expect(wrapper.get('.task-item-body').html()).toContain('<strong>adds</strong>')
    expect(wrapper.find('.task-pr-steps').exists()).toBe(false)
  })

  it('reads the reviewers only on the description pane', async () => {
    mocks.pullReviewers.mockResolvedValue({
      reviewers: [{ login: 'carol', state: 'PENDING', submitted_at: null, requested: true }],
      error: null
    })
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    // The default pane is Review, so the reviewer read waits for Description.
    expect(mocks.pullReviewers).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('Reviewers')

    await wrapper.get('.pr-panel-tabs button:nth-of-type(1)').trigger('click')
    await flushPromises()
    expect(mocks.pullReviewers).toHaveBeenCalledWith('https://github.com/acme/api/pull/42')
    expect(wrapper.text()).toContain('Reviewers')
    expect(wrapper.get('.field').attributes('style') || '').not.toContain('display: none')

    // Leaving the pane hides them without reading GitHub again.
    await wrapper.get('.pr-panel-tabs button:nth-of-type(2)').trigger('click')
    await flushPromises()
    // v-show hides the loaded list rather than dropping it (jsdom's
    // isVisible() does not read the CSS), so the second visit reads nothing.
    expect(wrapper.get('.field').attributes('style')).toContain('display: none')
    expect(mocks.pullReviewers).toHaveBeenCalledTimes(1)
  })

  it('falls back to the stored pull request when GitHub cannot be read', async () => {
    mocks.githubIssue.mockRejectedValue(new Error('ghx failed'))
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    expect(wrapper.text()).toContain('Could not read the pull request from GitHub')
    expect(wrapper.text()).toContain('Stored PR title')
    await wrapper.get('.pr-panel-tabs button:nth-of-type(1)').trigger('click')
    await flushPromises()
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

  it('lists each step report as a tab in the reports pane', async () => {
    mocks.taskReviews.mockResolvedValue({
      root: null,
      counts: { total: 1 },
      prs: [
        pr({
          steps: {
            'validate-pr': step({ step: 'validate-pr', report: 'validate-pr.abc1234.md' }),
            'review-pr': step()
          }
        })
      ]
    })
    mocks.report.mockImplementation(async (_repository, _number, name) => ({
      name,
      content: `# ${name}\n\nLooks good.`,
      truncated: false
    }))
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    // The review pane is the default, so the steps read first.
    expect(wrapper.find('.task-pr-steps').exists()).toBe(true)
    await wrapper.get('.pr-panel-tabs button:nth-of-type(3)').trigger('click')
    await flushPromises()

    const tabs = wrapper.findAll('.pr-report-tabs button')
    expect(tabs.map((tab) => tab.text())).toEqual(['Validate', 'Review'])
    // The newest report opens at once, so the pane is never blank.
    expect(mocks.report).toHaveBeenCalledWith('acme/api', 42, 'validate-pr.abc1234.md')
    expect(wrapper.get('.review-content').text()).toContain('validate-pr.abc1234.md')

    await tabs[1].trigger('click')
    await flushPromises()
    expect(mocks.report).toHaveBeenCalledWith('acme/api', 42, 'review-pr.abc1234.md')
    expect(wrapper.get('.review-content').text()).toContain('review-pr.abc1234.md')
  })

  it('shows the adversarial step and the surface reports in the review pane', async () => {
    mocks.taskReviews.mockResolvedValue({
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
            })
          }
        })
      ]
    })
    mocks.report.mockResolvedValue({ name: 'report.md', content: '# Report', truncated: false })

    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    // The adversarial step is its own labeled cell.
    const labels = wrapper.findAll('.task-pr-step-label').map((label) => label.text())
    expect(labels).toContain('Adversarial')
    expect(labels).toContain('Surfaces')
    const adversarial = wrapper
      .findAll('.task-pr-step .review-step')
      .find((cell) => cell.attributes('title').startsWith('Adversarial'))
    expect(adversarial.text()).toContain('❌')
    expect(adversarial.attributes('title')).toContain('2 reproduced')

    // The surfaces share one cell, one token per report.
    expect(wrapper.findAll('.review-surface-badges .review-step').map((cell) => cell.text())).toEqual(['API❌'])

    await wrapper.get('.pr-panel-tabs button:nth-of-type(3)').trigger('click')
    await flushPromises()
    const tabs = wrapper.findAll('.pr-report-tabs button')
    expect(tabs.map((tab) => tab.text())).toEqual(['Adversarial', 'Review', 'API'])
  })

  it('switches from a report back to the review pane', async () => {
    mocks.report.mockResolvedValue({ name: 'review-pr.abc1234.md', content: '# Review', truncated: false })
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    await wrapper.get('.task-pr-steps .review-step').trigger('click')
    await flushPromises()
    expect(wrapper.find('.review-content').exists()).toBe(true)

    await wrapper.get('.pr-panel-tabs button:nth-of-type(2)').trigger('click')
    await flushPromises()
    expect(wrapper.find('.review-content').exists()).toBe(false)
    expect(wrapper.find('.task-pr-steps').exists()).toBe(true)
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
    expect(wrapper.get('.task-pr-steps').element.nextElementSibling).toBe(selector.element)
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
