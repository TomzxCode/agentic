import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({ list: vi.fn() }))

vi.mock('../api', () => ({ api: { decisions: { list: mocks.list } } }))

import DecisionsView from '../views/DecisionsView.vue'
import {
  cellDecisions,
  decisionCounts,
  decisionMatrix,
  filterDecisions,
  groupDecisions,
  nameSlug,
  pctColor,
  shiftDays
} from '../decisions'
import { store } from '../store'

function decision(overrides = {}) {
  return {
    date: '2026-10-02',
    author: 'Alice Smith',
    bucket: 'Decided',
    text: 'Move the queue to Redis.',
    permalink: 'https://example.slack.com/archives/C1/p1',
    supported_by: [],
    opposed_by: [],
    source: '/home/u/notes/decisions/2026/10/02.md',
    ...overrides
  }
}

const DECISIONS = [
  decision(),
  decision({
    author: 'Alice Smith',
    bucket: 'Deferred',
    text: 'The migration plan.',
    date: '2026-10-01',
    supported_by: ['Bob Jones'],
    permalink: ''
  }),
  decision({
    author: 'Bob Jones',
    bucket: 'Committed',
    text: 'Bob Jones to write the runbook.',
    date: '2026-10-03',
    opposed_by: ['Alice Smith'],
    permalink: ''
  })
]

function payload(decisions = DECISIONS) {
  return {
    root: '/home/u/notes',
    generated_at: '2026-10-03T00:00:00Z',
    reports: 2,
    counts: {},
    range: { start: '2026-10-01', end: '2026-10-03' },
    decisions,
    headlines: { 'Alice Smith': 'Adopt the shared queue' },
    not_heard: ['Erin Fox'],
    cross_cutting: ['Two people agreed on the queue move.']
  }
}

describe('decisions helpers', () => {
  it('filters by search text, date range, and bucket', () => {
    expect(filterDecisions(DECISIONS, { q: 'redis' })).toHaveLength(1)
    expect(filterDecisions(DECISIONS, { q: 'bob jones' })).toHaveLength(2)
    expect(filterDecisions(DECISIONS, { from: '2026-10-02' })).toHaveLength(2)
    expect(filterDecisions(DECISIONS, { to: '2026-10-02' })).toHaveLength(2)
    expect(filterDecisions(DECISIONS, { buckets: ['Committed'] })).toHaveLength(1)
    // No bucket selected means every bucket, not none.
    expect(filterDecisions(DECISIONS, { buckets: [] })).toHaveLength(3)
  })

  it('counts the decisions, people, and the names on each side', () => {
    expect(decisionCounts(DECISIONS)).toEqual({
      total: 3,
      people: 2,
      supporters: 1,
      opponents: 1,
      buckets: { Decided: 1, Deferred: 1, Committed: 1 }
    })
  })

  it('groups by author or by the names on one side, busiest first', () => {
    const authors = groupDecisions(DECISIONS, 'author')
    expect(authors.map((group) => group.name)).toEqual(['Alice Smith', 'Bob Jones'])
    expect(authors[0].items.map((entry) => entry.bucket)).toEqual(['Decided', 'Deferred'])

    const supporters = groupDecisions(DECISIONS, 'supported_by')
    expect(supporters.map((group) => group.name)).toEqual(['Bob Jones'])

    const opponents = groupDecisions(DECISIONS, 'opposed_by')
    expect(opponents.map((group) => group.name)).toEqual(['Alice Smith'])
  })

  it('builds the matrix with the diagonal as the author total', () => {
    const matrix = decisionMatrix(DECISIONS, 'support')
    expect(matrix.people).toEqual(['Alice Smith', 'Bob Jones'])
    expect(matrix.rows.map((row) => row.author)).toEqual(['Alice Smith', 'Bob Jones'])

    const alice = matrix.rows[0]
    expect(alice.total).toBe(2)
    // One of Alice's two decisions has at least one supporter.
    expect(alice.pct).toBe(50)
    expect(alice.cells[0]).toMatchObject({ person: 'Alice Smith', diagonal: true, count: 2 })
    expect(alice.cells[1]).toMatchObject({ person: 'Bob Jones', diagonal: false, count: 1, pct: 50 })
    expect(alice.received).toBe(1)

    const oppose = decisionMatrix(DECISIONS, 'oppose')
    expect(oppose.rows[1]).toMatchObject({ author: 'Bob Jones', total: 1, pct: 100 })
  })

  it('lists the decisions behind a cell', () => {
    const diagonal = cellDecisions(DECISIONS, { author: 'Alice Smith', person: 'Alice Smith', diagonal: true })
    expect(diagonal).toHaveLength(2)

    const backed = cellDecisions(DECISIONS, { author: 'Alice Smith', person: 'Bob Jones', diagonal: false })
    expect(backed.map((entry) => entry.bucket)).toEqual(['Deferred'])
  })

  it('shifts an ISO date and colours percentages', () => {
    expect(shiftDays('2026-10-03', -6)).toBe('2026-09-27')
    expect(shiftDays('', -6)).toBe('')
    expect(pctColor(0)).toBe('hsl(0, 65%, 48%)')
    expect(pctColor(100)).toBe('hsl(120, 65%, 48%)')
    expect(nameSlug('Alice Smith')).toBe('person-alice-smith')
  })
})

describe('DecisionsView', () => {
  const settle = async () => {
    await flushPromises()
  }

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    store.toast = null
    mocks.list.mockResolvedValue(payload())
  })

  it('lists the decisions grouped by author with their headline', async () => {
    const wrapper = mount(DecisionsView)
    await settle()
    expect(wrapper.text()).toContain('Adopt the shared queue')
    expect(wrapper.text()).toContain('Move the queue to Redis.')
    expect(wrapper.findAll('.decision-card')).toHaveLength(3)
    expect(wrapper.text()).toContain('/home/u/notes')
    // The shared sections close the page.
    expect(wrapper.text()).toContain('Erin Fox')
    expect(wrapper.text()).toContain('Two people agreed on the queue move.')
  })

  it('filters by the search box and the status chips', async () => {
    const wrapper = mount(DecisionsView)
    await settle()

    await wrapper.get('input[type="search"]').setValue('redis')
    expect(wrapper.findAll('.decision-card')).toHaveLength(1)

    await wrapper.get('input[type="search"]').setValue('')
    const chip = wrapper.findAll('.status-chip').find((button) => button.text().startsWith('Committed'))
    await chip.trigger('click')
    expect(wrapper.findAll('.decision-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('runbook')
  })

  it('switches to the supporters view', async () => {
    const wrapper = mount(DecisionsView)
    await settle()
    const tab = wrapper.findAll('.decisions-tabs button').find((button) => button.text() === 'By supporter')
    await tab.trigger('click')
    expect(wrapper.findAll('.decisions-group')).toHaveLength(1)
    expect(wrapper.get('.decisions-group h2').text()).toBe('Bob Jones')
  })

  it('shows the matrix and lists the decisions behind a cell', async () => {
    const wrapper = mount(DecisionsView)
    await settle()
    const tab = wrapper.findAll('.decisions-tabs button').find((button) => button.text() === 'Matrix')
    await tab.trigger('click')

    expect(wrapper.find('.matrix-wrap').exists()).toBe(true)
    expect(wrapper.findAll('.matrix-wrap tbody tr')).toHaveLength(2)

    await wrapper.get('.matrix-wrap td.diag').trigger('click')
    expect(wrapper.get('.cell-detail').text()).toContain('Alice Smith: 2 decisions made')
  })

  it('restores the view it remembers, and ignores an unknown one', async () => {
    localStorage.setItem('agentic.decisionsView', 'supporters')
    const wrapper = mount(DecisionsView)
    await settle()
    expect(wrapper.get('.decisions-tabs button.active').text()).toBe('By supporter')
    wrapper.unmount()

    localStorage.setItem('agentic.decisionsView', 'nope')
    const fallback = mount(DecisionsView)
    await settle()
    expect(fallback.get('.decisions-tabs button.active').text()).toBe('By author')
  })

  it('explains how to configure the notes directory when none is found', async () => {
    mocks.list.mockResolvedValue({ ...payload([]), root: null, range: null })
    const wrapper = mount(DecisionsView)
    await settle()
    expect(wrapper.text()).toContain('No notes directory found')
    expect(wrapper.text()).toContain('AGENTIC_NOTES_DIR')
  })
})
