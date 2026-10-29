import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({ report: vi.fn(), visits: vi.fn() }))

vi.mock('../api', () => ({ api: { pageVisits: { report: mocks.report, visits: mocks.visits } } }))

import TimeView from '../views/TimeView.vue'
import { DAY_MS, dayStartMs, localDayKey } from '../pageTiming'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

function dayKey(offset) {
  const date = new Date()
  date.setDate(date.getDate() + offset)
  return localDayKey(date)
}

const today = dayKey(0)
const todayStart = new Date(dayStartMs(today))

function report(overrides = {}) {
  return {
    window_days: 7,
    tz_offset: 0,
    generated_at: new Date().toISOString(),
    start: new Date().toISOString(),
    end: new Date().toISOString(),
    duration_ms: 7_200_000,
    visits: 12,
    pages: [
      { key: 'tasks', label: 'Tasks', duration_ms: 5_400_000, visits: 8, share: 0.75 },
      { key: 'task', label: 'Task', duration_ms: 1_800_000, visits: 4, share: 0.25 }
    ],
    places: [
      {
        path: '/task/abc',
        key: 'task',
        label: 'Task',
        detail: 'Fix login',
        duration_ms: 1_800_000,
        visits: 4,
        share: 0.25
      }
    ],
    days: [
      { date: dayKey(-6), duration_ms: 0, visits: 0 },
      { date: dayKey(-5), duration_ms: 0, visits: 0 },
      { date: dayKey(-4), duration_ms: 0, visits: 0 },
      { date: dayKey(-3), duration_ms: 0, visits: 0 },
      { date: dayKey(-2), duration_ms: 0, visits: 0 },
      { date: dayKey(-1), duration_ms: 0, visits: 0 },
      { date: today, duration_ms: 7_200_000, visits: 12 }
    ],
    ...overrides
  }
}

function visit(overrides = {}) {
  const start = new Date(todayStart.getTime() + 60 * 60_000)
  return {
    id: 'v1',
    path: '/task/abc',
    route_name: 'task',
    title: 'Task',
    started_at: start.toISOString(),
    ended_at: new Date(start.getTime() + 1_800_000).toISOString(),
    duration_ms: 1_800_000,
    detail: 'Fix login',
    ...overrides
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  mocks.report.mockResolvedValue(report())
  mocks.visits.mockImplementation(async ({ start, end }) => ({ start, end, visits: [visit()] }))
})

describe('TimeView', () => {
  it('shows the window totals, the page shares, and the place behind them', async () => {
    const wrapper = mount(TimeView, stub)
    await flushPromises()

    expect(mocks.report).toHaveBeenCalledWith(expect.objectContaining({ days: 7 }))
    expect(mocks.visits).toHaveBeenCalledWith({
      start: todayStart.toISOString(),
      end: new Date(todayStart.getTime() + DAY_MS).toISOString()
    })
    expect(wrapper.text()).toContain('2h')
    expect(wrapper.text()).toContain('Tasks')
    expect(wrapper.text()).toContain('Task')
    expect(wrapper.text()).toContain('75%')
    expect(wrapper.text()).toContain('Fix login')
    expect(wrapper.text()).toContain('Visits in range')
    expect(wrapper.findAll('a[href="/task/abc"]').map((link) => link.text())).toContain('Fix login')
  })

  it('narrows the timeline to a day when a trend column is clicked', async () => {
    const wrapper = mount(TimeView, stub)
    await flushPromises()

    const columns = wrapper.findAll('.time-trend-col')
    expect(columns).toHaveLength(7)
    await columns[0].trigger('click')
    await flushPromises()

    const dayStart = dayStartMs(dayKey(-6))
    expect(mocks.visits).toHaveBeenLastCalledWith({
      start: new Date(dayStart).toISOString(),
      end: new Date(dayStart + DAY_MS).toISOString()
    })
  })

  it('reads the timeline from the start and end fields', async () => {
    const wrapper = mount(TimeView, stub)
    await flushPromises()

    const start = new Date(2026, 9, 28, 9, 30)
    const end = new Date(2026, 9, 28, 11, 15)
    await wrapper.get('input[aria-label="Range start"]').setValue('2026-10-28T09:30')
    await wrapper.get('input[aria-label="Range end"]').setValue('2026-10-28T11:15')
    await flushPromises()

    expect(mocks.visits).toHaveBeenLastCalledWith({ start: start.toISOString(), end: end.toISOString() })
  })

  it('refuses a range that ends before it starts', async () => {
    const wrapper = mount(TimeView, stub)
    await flushPromises()

    await wrapper.get('input[aria-label="Range start"]').setValue('2026-10-28T11:00')
    await flushPromises()
    const before = mocks.visits.mock.calls.length

    await wrapper.get('input[aria-label="Range end"]').setValue('2026-10-28T10:00')
    await flushPromises()

    expect(wrapper.text()).toContain('The end must come after the start.')
    expect(mocks.visits.mock.calls.length).toBe(before)
  })

  it('reads an empty history without pretending there is data', async () => {
    mocks.report.mockResolvedValue(report({ duration_ms: 0, visits: 0, pages: [], places: [] }))
    mocks.visits.mockImplementation(async ({ start, end }) => ({ start, end, visits: [] }))

    const wrapper = mount(TimeView, stub)
    await flushPromises()

    expect(wrapper.text()).toContain('No time recorded in this window yet.')
    expect(wrapper.text()).toContain('No visits in this range.')
  })
})
