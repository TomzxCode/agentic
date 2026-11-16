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
  taskLinks: vi.fn(),
  pullReviewers: vi.fn(),
  commentPull: vi.fn(),
  approve: vi.fn(),
  feedbackList: vi.fn(),
  setFeedbackDecision: vi.fn(),
  routeQuery: {},
  routerPush: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    github: {
      issue: mocks.githubIssue,
      taskLinks: mocks.taskLinks,
      pullReviewers: mocks.pullReviewers,
      commentPull: mocks.commentPull
    },
    reviews: { task: mocks.taskReviews, report: mocks.report, findings: mocks.findings, approve: mocks.approve },
    runs: { create: mocks.createRun },
    feedback: { list: mocks.feedbackList, setDecision: mocks.setFeedbackDecision }
  }
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: mocks.routeQuery }),
  useRouter: () => ({ push: mocks.routerPush })
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

function feedbackItem(overrides = {}) {
  return {
    feedback_id: 'comment-1',
    kind: 'comment',
    repo: 'acme/api',
    pr: '42',
    author: 'carol',
    created_at: '2026-01-11T00:00:00Z',
    head_commit: 'abc1234',
    analyzed_at: '2026-01-11T01:00:00Z',
    recommendation: 'implement',
    confidence: 'high',
    session_link: '',
    decision: null,
    decided_at: null,
    executed_at: null,
    title: 'Tighten the check',
    path: '/home/u/.sdlc/acme/api/pull-requests/42/feedback/comment-1.md',
    sections: { Comment: '> please fix this', 'Suggested reply': 'Fixed.' },
    status: 'pending',
    run_state: 'none',
    state: 'open',
    pr_url: 'https://github.com/acme/api/pull/42',
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
  mocks.routeQuery = {}
  mocks.taskLinks.mockResolvedValue({ issues: [], pulls: [] })
  vi.spyOn(store, 'loadPeople').mockResolvedValue()
  mocks.taskReviews.mockResolvedValue({ root: null, counts: { total: 1 }, prs: [pr()] })
  mocks.findings.mockResolvedValue([finding()])
  mocks.pullReviewers.mockResolvedValue({ reviewers: [], error: null })
  mocks.feedbackList.mockResolvedValue({ root: '/home/u/.sdlc', items: [] })
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

  it('leaves a comment on the pull request from the header', async () => {
    mocks.commentPull.mockResolvedValue({ url: 'https://github.com/acme/api/pull/42', commented: true })
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Comment')
      .trigger('click')
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('acme/api#42')
    await dialog.get('textarea').setValue('Looks good to me')
    await dialog
      .findAll('button')
      .find((button) => button.text() === 'Comment')
      .trigger('click')
    await flushPromises()

    expect(mocks.commentPull).toHaveBeenCalledWith({
      url: 'https://github.com/acme/api/pull/42',
      body: 'Looks good to me'
    })
    expect(store.toast).toMatchObject({ message: 'Comment posted', isError: false })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  })

  it('approves the pull request from the header', async () => {
    mocks.approve.mockResolvedValue({ number: 42, repository: 'acme/api', approved: true })
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('Approve'))
      .trigger('click')
    const dialog = wrapper.get('[role="dialog"]')
    await dialog.get('textarea').setValue('Ship it')
    await dialog
      .findAll('button')
      .find((button) => button.text() === 'Approve')
      .trigger('click')
    await flushPromises()

    expect(mocks.approve).toHaveBeenCalledWith('acme/api', 42, 'Ship it')
    expect(store.toast).toMatchObject({ message: 'Approved acme/api#42', isError: false })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper.get('.task-pr-approved').text()).toBe('Approved')
  })

  it('offers approval only on an open, non-draft pull request GitHub has not approved', async () => {
    mocks.taskReviews.mockResolvedValue({
      root: null,
      counts: { total: 3 },
      prs: [pr({ draft: true })]
    })
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    expect(wrapper.findAll('button').some((button) => button.text().includes('Approve'))).toBe(false)

    wrapper.unmount()
    mocks.taskReviews.mockResolvedValue({
      root: null,
      counts: { total: 3 },
      prs: [pr({ review_decision: 'APPROVED' })]
    })
    const approved = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    expect(approved.findAll('button').some((button) => button.text().includes('Approve'))).toBe(false)
  })

  it('says so when the comment could not be posted', async () => {
    mocks.commentPull.mockRejectedValue(new Error('ghx is not installed'))
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Comment')
      .trigger('click')
    const dialog = wrapper.get('[role="dialog"]')
    await dialog.get('textarea').setValue('Looks good')
    await dialog
      .findAll('button')
      .find((button) => button.text() === 'Comment')
      .trigger('click')
    await flushPromises()

    expect(store.toast).toMatchObject({ message: 'ghx is not installed', isError: true })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
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
    // The author line sits on the head row, above the panes.
    const html = wrapper.html()
    expect(html.indexOf('task-item-meta')).toBeLessThan(html.indexOf('pr-panel-tabs'))
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

  it("shows the pull request's analyzed reviewer feedback as a tab", async () => {
    mocks.feedbackList.mockResolvedValue({ items: [feedbackItem()] })
    mocks.setFeedbackDecision.mockImplementation(async (_id, decision) =>
      feedbackItem({ decision, status: decision, run_state: 'awaiting' })
    )
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    // Only this pull request is read, and the tab counts what it holds.
    expect(mocks.feedbackList).toHaveBeenCalledWith({ refresh: false, repo: 'acme/api', pr: '42' })
    const tabs = wrapper.findAll('.pr-panel-tabs button')
    expect(tabs.map((tab) => tab.text())).toEqual(['Description', 'Review', 'Reports 1', 'Feedback 1'])

    await tabs[3].trigger('click')
    await flushPromises()
    expect(wrapper.get('.feedback-card').text()).toContain('Tighten the check')
    expect(wrapper.find('.task-pr-steps').exists()).toBe(false)

    // The card's decision works the same as on the PR feedback page.
    await wrapper.get('.feedback-card button.implement').trigger('click')
    await flushPromises()
    expect(mocks.setFeedbackDecision).toHaveBeenCalledWith('comment-1', 'implement')
    expect(wrapper.get('.feedback-card .pill.decision').text()).toBe('implement')
  })

  it('offers the feedback pane even without review reports', async () => {
    mocks.taskReviews.mockResolvedValue({ root: null, counts: { total: 0 }, prs: [] })
    mocks.feedbackList.mockResolvedValue({ items: [feedbackItem()] })
    const wrapper = mount(TaskReviewPanel, { props: { task }, ...stub })
    await flushPromises()

    expect(wrapper.findAll('.pr-panel-tabs button').map((tab) => tab.text())).toEqual([
      'Description',
      'Review',
      'Feedback 1'
    ])
    expect(wrapper.text()).toContain('No review reports')

    await wrapper.get('.pr-panel-tabs button:nth-of-type(3)').trigger('click')
    await flushPromises()
    expect(wrapper.get('.feedback-card').exists()).toBe(true)
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

  it('lists every linked pull request with its state and renders only the selected one', async () => {
    const second = {
      id: 'a2',
      item: {
        id: 'i2',
        source: 'github',
        kind: 'pull_request',
        url: 'https://github.com/acme/api/pull/43',
        title: 'Second PR',
        content: '',
        metadata_json: {}
      }
    }
    const multi = { ...task, associations: [...task.associations, second] }
    mocks.taskLinks.mockResolvedValue({
      issues: [],
      pulls: [
        {
          repository: 'acme/api',
          number: 42,
          title: 'Do the thing',
          url: 'https://github.com/acme/api/pull/42',
          state: 'OPEN',
          draft: false,
          requested_users: ['carol'],
          requested_teams: [],
          approvers: [],
          ci: 'success',
          open_threads: 2,
          mergeable: true,
          merge_state: 'CLEAN',
          ready_to_merge: false,
          linked_issues: [7],
          has_description: true,
          description_updated: true
        },
        {
          repository: 'acme/api',
          number: 43,
          title: 'Second PR',
          url: 'https://github.com/acme/api/pull/43',
          state: 'MERGED',
          draft: false,
          requested_users: [],
          requested_teams: [],
          approvers: ['bob'],
          ci: 'success',
          open_threads: 0,
          mergeable: true,
          merge_state: 'CLEAN',
          ready_to_merge: false,
          linked_issues: [],
          has_description: true,
          description_updated: false
        }
      ]
    })
    mocks.githubIssue.mockImplementation(async (url) => ({
      number: Number(url.split('/').pop()),
      title: url.includes('/43') ? 'Second PR' : 'Do the thing',
      url,
      state: url.includes('/43') ? 'MERGED' : 'OPEN',
      is_draft: false,
      created_at: '2026-01-10T00:00:00Z',
      author: 'alice',
      labels: [],
      body: ''
    }))
    mocks.routeQuery = { view: 'pr', item: 'acme/api/43' }

    const wrapper = mount(TaskReviewPanel, { props: { task: multi, selected: 'acme/api/43' }, ...stub })
    await flushPromises()

    // The selected pull request replaces the list rather than sitting under it.
    expect(wrapper.find('.task-link-table').exists()).toBe(false)
    expect(mocks.githubIssue).toHaveBeenCalledWith('https://github.com/acme/api/pull/43')
    expect(mocks.githubIssue).not.toHaveBeenCalledWith('https://github.com/acme/api/pull/42')
    expect(wrapper.findAll('.task-item-panel')).toHaveLength(1)

    // The back control returns to the list.
    expect(wrapper.get('.task-link-back').text()).toContain('All pull requests')
    await wrapper.get('.task-link-back button').trigger('click')
    expect(mocks.routerPush).toHaveBeenCalledWith({ query: { view: 'pr' } })
  })

  it('shows only the list, not a pull request, until one is selected', async () => {
    const second = {
      id: 'a2',
      item: {
        id: 'i2',
        source: 'github',
        kind: 'pull_request',
        url: 'https://github.com/acme/api/pull/43',
        title: 'Second PR',
        content: '',
        metadata_json: {}
      }
    }
    const multi = { ...task, associations: [...task.associations, second] }
    mocks.taskLinks.mockResolvedValue({
      issues: [],
      pulls: [
        {
          repository: 'acme/api',
          number: 42,
          title: 'Do the thing',
          url: 'https://github.com/acme/api/pull/42',
          state: 'OPEN',
          draft: false,
          requested_users: ['carol'],
          requested_teams: [],
          approvers: [],
          ci: 'success',
          open_threads: 2,
          mergeable: true,
          merge_state: 'CLEAN',
          ready_to_merge: false,
          linked_issues: [7],
          has_description: true,
          description_updated: true
        },
        {
          repository: 'acme/api',
          number: 43,
          title: 'Second PR',
          url: 'https://github.com/acme/api/pull/43',
          state: 'MERGED',
          draft: false,
          requested_users: [],
          requested_teams: [],
          approvers: ['bob'],
          ci: 'success',
          open_threads: 0,
          mergeable: true,
          merge_state: 'CLEAN',
          ready_to_merge: false,
          linked_issues: [],
          has_description: true,
          description_updated: false
        }
      ]
    })
    mocks.routeQuery = { view: 'pr' }

    const wrapper = mount(TaskReviewPanel, { props: { task: multi }, ...stub })
    await flushPromises()

    // The list is the My PRs table, stating every fact the page asks for.
    expect(wrapper.findAll('.task-link-table th').map((cell) => cell.text())).toEqual([
      'PR',
      'Status',
      'Review',
      'Reviewers',
      'Checks',
      'Comments',
      'Conflicts',
      'Issue',
      'Description',
      'Blocker',
      'Updated'
    ])
    const links = wrapper.findAll('.task-link-row')
    expect(links).toHaveLength(2)
    // The mobile cards hide the header, so every state cell carries its own
    // column name.
    expect(links[0].findAll('td[data-label]').map((cell) => cell.attributes('data-label'))).toEqual([
      'Status',
      'Review',
      'Reviewers',
      'Checks',
      'Comments',
      'Conflicts',
      'Issue',
      'Description',
      'Blocker',
      'Updated'
    ])
    expect(links[0].text()).toContain('Passing')
    expect(links[0].text()).toContain('carol')
    expect(links[0].text()).toContain('2 open')
    expect(links[0].text()).toContain('none')
    expect(links[0].text()).toContain('up to date')
    // The Blocker cell names the first blocker; open comments come before the
    // review this pull request is still waiting on.
    expect(links[0].find('td[data-label="Blocker"]').text()).toBe('comments open')
    expect(links[1].text()).toContain('Merged')
    expect(links[1].text()).toContain('stale')
    // A merged pull request has no blocker, and it no longer waits on anyone.
    expect(links[1].find('td[data-label="Blocker"]').text()).toBe('none')
    expect(links[1].text()).not.toContain('waiting on')
    expect(links[1].text()).toContain('approved by')
    // No pull request panel and no GitHub read until a row is chosen.
    expect(wrapper.find('.task-item-panel').exists()).toBe(false)
    expect(mocks.githubIssue).not.toHaveBeenCalled()

    await links[0].trigger('click')
    expect(mocks.routerPush).toHaveBeenCalledWith({ query: { view: 'pr', item: 'acme/api/42' } })
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
