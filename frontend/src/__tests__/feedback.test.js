import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  setDecision: vi.fn()
}))

vi.mock('../api', () => ({
  api: { feedback: { list: mocks.list, setDecision: mocks.setDecision } }
}))

import FeedbackView from '../views/FeedbackView.vue'
import { feedbackCounts, groupFeedback, orderedSections, threadUrl } from '../feedback'
import { store } from '../store'

function item(overrides = {}) {
  return {
    feedback_id: 'comment-1',
    kind: 'comment',
    repo: 'TomzxCode/agentic',
    pr: '42',
    author: 'alice',
    created_at: '2026-10-01T00:00:00Z',
    head_commit: 'abc1234',
    analyzed_at: '2026-10-02T00:00:00Z',
    recommendation: 'implement',
    confidence: 'high',
    session_link: '',
    decision: null,
    decided_at: null,
    executed_at: null,
    title: 'Tighten the error message',
    path: '/home/u/.sdlc/TomzxCode/agentic/pull-requests/42/feedback/comment-1.md',
    sections: {
      Comment: '> please fix this\n\n[thread](https://github.com/TomzxCode/agentic/pull/42#discussion_r1)',
      Analysis: 'This fails at `foo.py:12`.',
      'Suggested reply': 'Thanks, fixed in abc1234.'
    },
    status: 'pending',
    run_state: 'none',
    state: 'open',
    pr_url: 'https://github.com/TomzxCode/agentic/pull/42',
    ...overrides
  }
}

describe('feedback helpers', () => {
  it('orders sections, named ones first', () => {
    const sections = orderedSections({
      sections: { Analysis: 'a', Comment: 'c', Extra: 'e', 'Suggested reply': 'r' }
    })
    expect(sections.map((section) => section.name)).toEqual(['Comment', 'Analysis', 'Suggested reply', 'Extra'])
  })

  it('extracts the thread link from the comment section', () => {
    expect(threadUrl(item())).toBe('https://github.com/TomzxCode/agentic/pull/42#discussion_r1')
    expect(threadUrl(item({ sections: { Comment: 'no link here' } }))).toBe('')
  })

  it('groups by recommendation in a pinned order and sorts within a group', () => {
    const items = [
      item({ feedback_id: 'a', recommendation: 'reject', created_at: '2026-10-01T00:00:00Z' }),
      item({ feedback_id: 'b', recommendation: 'implement', created_at: '2026-10-03T00:00:00Z' }),
      item({ feedback_id: 'c', recommendation: 'implement', created_at: '2026-10-02T00:00:00Z' })
    ]
    const groups = groupFeedback(items, 'recommendation', 'date-asc')
    expect(groups.map((group) => group.key)).toEqual(['implement', 'reject'])
    expect(groups[0].items.map((entry) => entry.feedback_id)).toEqual(['c', 'b'])
    expect(groups[0].pending).toBe(2)
  })

  it('groups by pull request and links the heading to the PR', () => {
    const groups = groupFeedback([item()], 'pr', 'date-desc')
    expect(groups).toHaveLength(1)
    expect(groups[0].label).toBe('TomzxCode/agentic#42')
    expect(groups[0].url).toBe('https://github.com/TomzxCode/agentic/pull/42')
  })

  it('counts decisions and the ones awaiting a run', () => {
    const counts = feedbackCounts([
      item({ status: 'implement', decision: 'implement', run_state: 'awaiting' }),
      item({ status: 'decline', decision: 'decline', run_state: 'executed' }),
      item()
    ])
    expect(counts).toMatchObject({ pending: 1, implement: 1, decline: 1, defer: 0, to_run: 1 })
  })
})

describe('FeedbackView', () => {
  const settle = async () => {
    await flushPromises()
  }

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    store.toast = null
    mocks.list.mockResolvedValue({ root: '/home/u/.sdlc', counts: {}, items: [item()] })
    mocks.setDecision.mockImplementation((id, decision) =>
      Promise.resolve(item({ decision, status: decision || 'pending', run_state: decision ? 'awaiting' : 'none' }))
    )
  })

  it('lists the feedback with its recommendation and sections', async () => {
    const wrapper = mount(FeedbackView)
    await settle()
    expect(wrapper.text()).toContain('Tighten the error message')
    expect(wrapper.text()).toContain('implement')
    expect(wrapper.text()).toContain('high confidence')
    expect(wrapper.text()).toContain('/home/u/.sdlc')
    expect(wrapper.findAll('.feedback-card')).toHaveLength(1)
    // The first section is open; every section body is rendered.
    expect(wrapper.get('.feedback-section').attributes('open')).toBeDefined()
    const bodies = wrapper.findAll('.feedback-section-body')
    expect(bodies[0].html()).toContain('please fix this')
    expect(bodies[1].html()).toContain('foo.py:12')
  })

  it('records a decision and reflects it on the card', async () => {
    const wrapper = mount(FeedbackView)
    await settle()
    await wrapper.get('button.implement').trigger('click')
    await settle()
    expect(mocks.setDecision).toHaveBeenCalledWith('comment-1', 'implement')
    expect(wrapper.get('.pill.decision').text()).toBe('implement')
    expect(wrapper.get('.pill.run').text()).toBe('awaiting run')
  })

  it('resets a decision to null', async () => {
    const wrapper = mount(FeedbackView)
    await settle()
    await wrapper.get('button.pending').trigger('click')
    await settle()
    expect(mocks.setDecision).toHaveBeenCalledWith('comment-1', null)
  })

  it('filters by PR state, hiding closed PRs under the active default', async () => {
    mocks.list.mockResolvedValue({
      root: '/home/u/.sdlc',
      items: [item({ feedback_id: 'open-1' }), item({ feedback_id: 'closed-1', state: 'closed' })]
    })
    const wrapper = mount(FeedbackView)
    await settle()
    expect(wrapper.findAll('.feedback-card')).toHaveLength(1)

    await wrapper.get('select[title="Filter by PR state"]').setValue('all')
    expect(wrapper.findAll('.feedback-card')).toHaveLength(2)
  })

  it('filters by the search box', async () => {
    mocks.list.mockResolvedValue({
      root: '/home/u/.sdlc',
      items: [item({ feedback_id: 'keep', title: 'Alpha' }), item({ feedback_id: 'drop', title: 'Beta' })]
    })
    const wrapper = mount(FeedbackView)
    await settle()
    await wrapper.get('input[type="search"]').setValue('alpha')
    expect(wrapper.findAll('.feedback-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('Alpha')
    expect(wrapper.text()).not.toContain('Beta')
  })

  it('filters the list to the pull request picked in the sidebar', async () => {
    mocks.list.mockResolvedValue({
      root: '/home/u/.sdlc',
      items: [
        item({ feedback_id: 'on-42', pr: '42', title: 'On pull 42' }),
        item({ feedback_id: 'on-43', pr: '43', title: 'On pull 43' })
      ]
    })
    const wrapper = mount(FeedbackView)
    await settle()
    expect(wrapper.findAll('.feedback-card')).toHaveLength(2)

    const navItems = () => wrapper.findAll('.feedback-nav .nav-item')
    // All items, then one entry per pull request.
    expect(navItems()).toHaveLength(3)

    await navItems()
      .find((nav) => nav.text().includes('#43'))
      .trigger('click')
    expect(wrapper.findAll('.feedback-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('On pull 43')
    expect(wrapper.text()).not.toContain('On pull 42')
    // The sidebar still lists every pull request, so another one is one click away.
    expect(navItems()).toHaveLength(3)
    expect(wrapper.get('.feedback-nav .nav-item.active').text()).toContain('#43')

    // Picking the selected pull request again shows the whole queue.
    await navItems()
      .find((nav) => nav.text().includes('#43'))
      .trigger('click')
    expect(wrapper.findAll('.feedback-card')).toHaveLength(2)
    expect(wrapper.get('.feedback-nav .nav-item.active').text()).toContain('All items')

    // The picked pull request also clears from the toolbar.
    await navItems()
      .find((nav) => nav.text().includes('#42'))
      .trigger('click')
    expect(wrapper.findAll('.feedback-card')).toHaveLength(1)
    await wrapper.get('.feedback-scope').trigger('click')
    expect(wrapper.findAll('.feedback-card')).toHaveLength(2)
  })

  it('clears the sidebar pick when the grouping changes', async () => {
    mocks.list.mockResolvedValue({
      root: '/home/u/.sdlc',
      items: [
        item({ feedback_id: 'on-42', pr: '42', author: 'alice', title: 'On pull 42' }),
        item({ feedback_id: 'on-43', pr: '43', author: 'bob', title: 'On pull 43' })
      ]
    })
    const wrapper = mount(FeedbackView)
    await settle()
    await wrapper.findAll('.feedback-nav .nav-item').at(1).trigger('click')
    expect(wrapper.findAll('.feedback-card')).toHaveLength(1)

    await wrapper.get('select[title="Group feedback into sections by"]').setValue('author')
    expect(wrapper.findAll('.feedback-card')).toHaveLength(2)
    expect(wrapper.get('.feedback-nav .nav-item.active').text()).toContain('All items')
  })

  it('shows the empty state when the store has no feedback', async () => {
    mocks.list.mockResolvedValue({ root: '/home/u/.sdlc', items: [] })
    const wrapper = mount(FeedbackView)
    await settle()
    expect(wrapper.text()).toContain('No reviewer feedback in the store yet')
  })
})
