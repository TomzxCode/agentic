import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  scores: vi.fn()
}))

vi.mock('../api', () => ({
  api: { reviews: { scores: mocks.scores } }
}))

import ReviewScoresView from '../views/ReviewScoresView.vue'
import { store } from '../store'

function run(overrides = {}) {
  return {
    repository: 'TomzxCode/agentic',
    owner: 'TomzxCode',
    name: 'agentic',
    number: 42,
    author: 'alice',
    step: 'review-pr',
    sha: 'abc1234',
    verdict: 'approved',
    score: 0.75,
    source: 'marker',
    reviewed_at: '2026-11-01T10:00:00Z',
    ...overrides
  }
}

const report = {
  root: '/home/alice/.sdlc',
  generated_at: '2026-11-08T10:00:00Z',
  rubrics: ['review-pr', 'validate-pr'],
  runs: [
    run(),
    run({ step: 'validate-pr', score: 0.5 }),
    run({ repository: 'acme/api', author: 'bob', number: 7, reviewed_at: '2026-11-02T10:00:00Z' })
  ]
}

async function openAuthors(wrapper) {
  await wrapper.get('.review-author-select .ss-trigger').trigger('click')
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  store.toast = null
  mocks.scores.mockResolvedValue(report)
})

describe('ReviewScoresView', () => {
  it('renders one chart per rubric that has a score', async () => {
    const wrapper = mount(ReviewScoresView)
    await flushPromises()

    expect(wrapper.text()).toContain('Review scores')
    expect(wrapper.text()).toContain('3 scored reviews')
    expect(wrapper.findAll('.score-card')).toHaveLength(2)
    expect(wrapper.findAll('.score-chart-svg')).toHaveLength(2)
    expect(wrapper.text()).toContain('Review')
    expect(wrapper.text()).toContain('Validate')
    expect(wrapper.text()).toContain('Reports read from /home/alice/.sdlc')
  })

  it('narrows the charts to one author', async () => {
    const wrapper = mount(ReviewScoresView)
    await flushPromises()

    await openAuthors(wrapper)
    const option = wrapper.findAll('.ss-option').find((entry) => entry.text().includes('bob'))
    await option.trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.score-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('1 scored review')
    expect(localStorage.getItem('agentic.reviewScoreFilters')).toContain('bob')
  })

  it('tells the reader how to create the first score', async () => {
    mocks.scores.mockResolvedValue({ ...report, runs: [] })
    const wrapper = mount(ReviewScoresView)
    await flushPromises()

    expect(wrapper.text()).toContain('No review scores yet')
    expect(wrapper.find('.score-card').exists()).toBe(false)
  })

  it('shows a retry when the store cannot be read', async () => {
    mocks.scores.mockRejectedValue(new Error('boom'))
    const wrapper = mount(ReviewScoresView)
    await flushPromises()

    expect(wrapper.text()).toContain('Could not load the review scores.')
    expect(wrapper.text()).toContain('Retry')
  })
})
