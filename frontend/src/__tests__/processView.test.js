import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { config, enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

// The aging list links each item to its task page.
config.global.stubs = { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } }

const mocks = vi.hoisted(() => ({
  processGet: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    process: { get: mocks.processGet }
  }
}))

import ProcessView from '../views/ProcessView.vue'

const report = {
  generated_at: '2026-10-25T12:00:00Z',
  window_days: 90,
  stages: [
    { stage: 'backlog', label: 'Backlog', count: 3, oldest_hours: 240, median_age_hours: 120, newest_hours: 24 },
    { stage: 'in_progress', label: 'In progress', count: 1, oldest_hours: 48, median_age_hours: 48, newest_hours: 48 },
    { stage: 'blocked', label: 'Blocked', count: 0 },
    { stage: 'done', label: 'Done', count: 2 },
    { stage: 'archived', label: 'Archived', count: 0 }
  ],
  flows: [
    { from_stage: 'backlog', to_stage: 'in_progress', count: 4 },
    { from_stage: 'in_progress', to_stage: 'done', count: 2 },
    { from_stage: 'done', to_stage: 'backlog', count: 1 }
  ],
  arrivals: 5,
  completions: 2,
  cycle_time: {
    count: 2,
    mean_hours: 120,
    median_hours: 96,
    p10_hours: 24,
    p90_hours: 216,
    fastest_hours: 24,
    slowest_hours: 216
  },
  histogram: [
    { label: '<1d', from_hours: 0, to_hours: 24, count: 0 },
    { label: '1-2d', from_hours: 24, to_hours: 48, count: 1 },
    { label: '2-4d', from_hours: 48, to_hours: 96, count: 0 },
    { label: '4-7d', from_hours: 96, to_hours: 168, count: 1 },
    { label: '1-2w', from_hours: 168, to_hours: 336, count: 0 },
    { label: '2-4w', from_hours: 336, to_hours: 720, count: 0 },
    { label: '1-2mo', from_hours: 720, to_hours: 1440, count: 0 },
    { label: '>2mo', from_hours: 1440, to_hours: null, count: 0 }
  ],
  dwell: [
    { stage: 'backlog', label: 'Backlog', count: 2, mean_hours: 100, median_hours: 96 },
    { stage: 'in_progress', label: 'In progress', count: 2, mean_hours: 20, median_hours: 24 },
    { stage: 'blocked', label: 'Blocked', count: 0, mean_hours: null, median_hours: null }
  ],
  weekly: [{ start: '2026-10-19T12:00:00Z', end: '2026-10-26T12:00:00Z', created: 2, completed: 1 }],
  littles: { avg_wip: 1.5, throughput_per_day: 0.02, projected_cycle_hours: 72 },
  wait_shares: [
    { stage: 'backlog', label: 'Backlog', count: 2, mean_hours: 96, total_hours: 192, share: 0.4 },
    { stage: 'in_progress', label: 'In progress', count: 2, mean_hours: 144, total_hours: 288, share: 0.6 },
    { stage: 'blocked', label: 'Blocked', count: 0, mean_hours: null, total_hours: 0, share: 0 },
    { stage: 'done', label: 'Done', count: 0, mean_hours: null, total_hours: 0, share: 0 },
    { stage: 'archived', label: 'Archived', count: 0, mean_hours: null, total_hours: 0, share: 0 }
  ],
  queue_pressure: [
    {
      stage: 'backlog',
      label: 'Backlog',
      count: 3,
      arrived: 5,
      departed: 4,
      net: 1,
      trend: 'filling',
      weekly_wip: [1, 2, 2, 3]
    },
    {
      stage: 'in_progress',
      label: 'In progress',
      count: 1,
      arrived: 4,
      departed: 4,
      net: 0,
      trend: 'steady',
      weekly_wip: [1, 1, 2, 1]
    },
    {
      stage: 'blocked',
      label: 'Blocked',
      count: 0,
      arrived: 0,
      departed: 0,
      net: 0,
      trend: 'steady',
      weekly_wip: [0, 0, 0, 0]
    }
  ],
  flow_samples: [
    { at: '2026-10-01T12:00:00Z', backlog: 1, in_progress: 0, blocked: 0, completed: 0 },
    { at: '2026-10-02T12:00:00Z', backlog: 2, in_progress: 1, blocked: 0, completed: 0 },
    { at: '2026-10-03T12:00:00Z', backlog: 2, in_progress: 1, blocked: 1, completed: 1 }
  ],
  wip_items: [
    { id: 't9', title: 'Blocked thing', stage: 'blocked', entered_at: '2026-10-08T12:00:00Z', age_hours: 408 },
    { id: 't2', title: 'Old backlog item', stage: 'backlog', entered_at: '2026-10-20T12:00:00Z', age_hours: 120 }
  ],
  touch: { completions: 2, covered: 1, touch_hours: 96, cycle_hours: 240, efficiency: 0.4, mean_touch_hours: 48 },
  forecast: {
    items: 3,
    sims: 500,
    weeks_observed: 13,
    p50_weeks: 4,
    p85_weeks: 7,
    p50_date: '2026-11-22T12:00:00Z',
    p85_date: '2026-12-13T12:00:00Z'
  },
  outcomes: { created: 5, done: 2, archived: 1, active: 2 }
}

async function mountView() {
  const wrapper = mount(ProcessView)
  await flushPromises()
  return wrapper
}

describe('ProcessView', () => {
  beforeEach(() => {
    mocks.processGet.mockResolvedValue(report)
  })

  it('draws the five stations with their queue counts and waits', async () => {
    const wrapper = await mountView()
    const counts = wrapper.findAll('.station-count').map((node) => node.text())
    expect(counts).toEqual(['3', '1', '2', '0', '0'])
    const subs = wrapper.findAll('.station-sub').map((node) => node.text())
    expect(subs[0]).toContain('median wait 5.0d')
    expect(subs[2]).toContain('n/a')
    expect(subs[3]).toBe('empty')
    expect(mocks.processGet).toHaveBeenCalledWith({ days: 90 })
  })

  it('labels the drawn edges with move counts and lists the other moves', async () => {
    const wrapper = await mountView()
    const edgeLabels = wrapper.findAll('.flow-count').map((node) => node.text())
    expect(edgeLabels).toEqual(['4', '2'])
    const others = wrapper.find('.other-flows').text()
    expect(others).toContain('Done → Backlog ×1')
  })

  it('summarizes the cycle-time distribution and its histogram', async () => {
    const wrapper = await mountView()
    const values = wrapper.findAll('.metric-value').map((node) => node.text())
    expect(values).toContain('4.0d')
    expect(values).toContain('9.0d')
    expect(values).toContain('5.0d')
    expect(values).toContain('2')
    const bars = wrapper.findAll('.process-bar')
    expect(bars).toHaveLength(8)
    expect(bars.filter((bar) => !bar.classes().includes('process-bar-empty'))).toHaveLength(2)
    const labels = wrapper.find('.process-bar-labels').text()
    expect(labels).toContain('>2mo')
  })

  it('shows the flow cards and the weekly chart', async () => {
    const wrapper = await mountView()
    const text = wrapper.text()
    expect(text).toContain('1.50')
    expect(text).toContain('0.02/day')
    expect(text).toContain('3.0d')
    expect(wrapper.findAll('.flow-week')).toHaveLength(1)
  })

  it('breaks down where completed items waited', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.dwell-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('median 4.0d')
    expect(rows[0].text()).toContain('2 visited')
  })

  it('names the bottleneck and shows which queues grow', async () => {
    const wrapper = await mountView()
    const takeaway = wrapper.get('.bottleneck-takeaway').text()
    expect(takeaway).toContain('5.0d')
    expect(takeaway).toContain('60%')
    expect(takeaway).toContain('In progress')
    const segments = wrapper.findAll('.bottleneck-bar .share-segment')
    expect(segments).toHaveLength(2)
    expect(segments[0].attributes('style')).toContain('width: 40%')
    expect(segments[1].attributes('style')).toContain('width: 60%')
    const legend = wrapper.get('.share-legend').text()
    expect(legend).toContain('Backlog 40%')
    expect(legend).toContain('In progress 60%')
    const rows = wrapper.findAll('.pressure-row')
    expect(rows).toHaveLength(3)
    expect(rows[0].text()).toContain('3 in station · 5 in · 4 out')
    expect(rows[0].get('.badge').text()).toBe('Filling')
    expect(rows[1].get('.badge').text()).toBe('Steady')
    expect(rows[0].findAll('.spark-bar')).toHaveLength(4)
  })

  it('draws the cumulative flow diagram', async () => {
    const wrapper = await mountView()
    const bands = wrapper.findAll('.cfd-band')
    expect(bands).toHaveLength(4)
    const legend = wrapper.get('.cfd-legend').text()
    expect(legend).toContain('Backlog')
    expect(legend).toContain('Completed')
    expect(wrapper.findAll('.cfd-column')).toHaveLength(3)
  })

  it('lists the items on the line, longest wait first', async () => {
    const wrapper = await mountView()
    const rows = wrapper.findAll('.wip-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('Blocked thing')
    expect(rows[0].text()).toContain('17.0d')
    expect(rows[0].get('a').attributes('href')).toBe('/task/t9')
  })

  it('shows flow efficiency', async () => {
    const wrapper = await mountView()
    const text = wrapper.text()
    expect(text).toContain('Flow efficiency')
    expect(text).toContain('40%')
    expect(text).toContain('2.0d per item')
  })

  it('forecasts the backlog clear date and splits outcomes', async () => {
    const wrapper = await mountView()
    const text = wrapper.text()
    expect(text).toContain('Backlog forecast')
    expect(text).toContain('P85')
    expect(text).toContain('clearing 3 items from 13 weeks of history')
    const outcomeLegend = wrapper.get('.outcome-block .share-legend').text()
    expect(outcomeLegend).toContain('Done 2')
    expect(outcomeLegend).toContain('On the line 2')
    expect(outcomeLegend).toContain('Archived 1')
  })

  it('reloads when the window changes', async () => {
    const wrapper = await mountView()
    await wrapper.find('select').setValue('180')
    await flushPromises()
    expect(mocks.processGet).toHaveBeenLastCalledWith({ days: 180 })
  })
})
