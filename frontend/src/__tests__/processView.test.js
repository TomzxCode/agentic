import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

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
  littles: { avg_wip: 1.5, throughput_per_day: 0.02, projected_cycle_hours: 72 }
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

  it('reloads when the window changes', async () => {
    const wrapper = await mountView()
    await wrapper.find('select').setValue('180')
    await flushPromises()
    expect(mocks.processGet).toHaveBeenLastCalledWith({ days: 180 })
  })
})
