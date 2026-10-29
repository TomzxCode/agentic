import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import TimeRangeTimeline from '../components/TimeRangeTimeline.vue'

function at(hour, minute = 0) {
  return new Date(2026, 9, 28, hour, minute).toISOString()
}

function visit(overrides = {}) {
  return {
    id: 'v1',
    path: '/',
    route_name: 'tasks',
    title: 'Tasks',
    started_at: at(10, 30),
    ended_at: at(11, 0),
    duration_ms: 30 * 60_000,
    detail: null,
    ...overrides
  }
}

function mountRange(visits) {
  return mount(TimeRangeTimeline, {
    props: { visits, start: at(10), end: at(12) }
  })
}

describe('TimeRangeTimeline', () => {
  it('lays out one lane per page and positions each visit in the range', () => {
    const wrapper = mountRange([
      visit({ id: 'tasks-a', started_at: at(10, 30), ended_at: at(10, 50), duration_ms: 20 * 60_000 }),
      visit({
        id: 'task-a',
        route_name: 'task',
        title: 'Task',
        started_at: at(11),
        ended_at: at(12),
        duration_ms: 60 * 60_000
      }),
      // Started before the range and clipped at its left edge.
      visit({ id: 'tasks-b', started_at: at(9), ended_at: at(10, 30) })
    ])

    const lanes = wrapper.findAll('.time-lane')
    expect(lanes).toHaveLength(2)
    // The page with the most time in the range comes first.
    expect(lanes[0].text()).toContain('Task')
    expect(lanes[1].text()).toContain('Tasks')

    const blocks = lanes[0].findAll('.time-block')
    expect(blocks).toHaveLength(1)
    expect(blocks[0].attributes('style')).toContain('left: 50%')
    expect(blocks[0].attributes('style')).toContain('width: 50%')

    const clipped = lanes[1].findAll('.time-block')
    expect(clipped[0].attributes('style')).toContain('left: 0%')
    expect(clipped[0].attributes('style')).toContain('width: 25%')
  })

  it('labels the axis at a readable interval', () => {
    const wrapper = mountRange([visit()])
    const ticks = wrapper.findAll('.time-axis-tick')
    expect(ticks.length).toBeGreaterThan(1)
    expect(ticks[0].text()).toBe('10:00')
    expect(ticks.at(-1).text()).toBe('12:00')
  })

  it('says so when the range has no visits', () => {
    const wrapper = mountRange([])
    expect(wrapper.findAll('.time-lane')).toHaveLength(0)
    expect(wrapper.text()).toContain('No visits in this range.')
  })
})
