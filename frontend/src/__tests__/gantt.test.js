import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import GanttChart from '../components/GanttChart.vue'
import { computeFitDomain, ganttTicks, markerKind, markerLabel, resolveDomain, spanPct, toField } from '../gantt'

afterEach(() => {
  vi.unstubAllGlobals()
})

const row = (over = {}) => ({
  id: 't1',
  title: 'Task One',
  status: 'in_progress',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T12:00:00Z',
  markers: [
    { id: 'm1', type: 'created', message: 'created', created_at: '2026-01-01T00:00:00Z' },
    { id: 'm2', type: 'updated', message: 'updated', created_at: '2026-01-01T12:00:00Z' }
  ],
  ...over
})

const domain = { lo: Date.UTC(2026, 0, 1), hi: Date.UTC(2026, 0, 2) }

describe('gantt helpers', () => {
  it('maps known marker types and falls back for unknown ones', () => {
    expect(markerKind('created')).toBe('accent')
    expect(markerKind('mystery')).toBe('muted')
    expect(markerLabel('context_updated')).toBe('Context updated')
    expect(markerLabel('some_new_event')).toBe('some new event')
  })

  it('fits the window to the data and now, with a pad', () => {
    const now = Date.UTC(2026, 0, 3)
    const { lo, hi } = computeFitDomain([row()], { now })
    expect(lo).toBeLessThan(Date.UTC(2026, 0, 1))
    expect(hi).toBeGreaterThan(now)
  })

  it('fits to the data alone when now is excluded', () => {
    const { lo, hi } = computeFitDomain([row()], { includeNow: false, now: Date.UTC(2026, 5, 1) })
    expect(lo).toBeLessThan(Date.UTC(2026, 0, 1))
    expect(hi).toBeGreaterThan(Date.UTC(2026, 0, 1, 12))
    expect(hi).toBeLessThan(Date.UTC(2026, 0, 2))
  })

  it('resolves a reversed range as invalid and falls back to the fit', () => {
    const resolved = resolveDomain([row()], '2030-01-02T00:00:00', '2030-01-01T00:00:00')
    expect(resolved.invalid).toBe(true)
    expect(resolved).toMatchObject(resolved.fit)
  })

  it('defaults an unset bound to the fitted bound', () => {
    // Pin now so the two fits use the same clock (otherwise the wall clock can
    // tick between them and the fitted bounds differ).
    const now = Date.now()
    const fit = computeFitDomain([row()], { now })
    const resolved = resolveDomain([row()], '', toField(fit.hi), { now })
    expect(resolved.lo).toBe(fit.lo)
    expect(resolved.invalid).toBe(false)
  })

  it('lays out ticks with end alignment at the edges', () => {
    const ticks = ganttTicks(0, 10 * 24 * 60 * 60 * 1000)
    expect(ticks).toHaveLength(6)
    expect(ticks[0].align).toBe('start')
    expect(ticks.at(-1).align).toBe('end')
  })

  it('uses two ticks for a compact chart', () => {
    const ticks = ganttTicks(0, 12 * 60 * 60 * 1000, { compact: true })
    expect(ticks).toHaveLength(3)
  })

  it('places a timestamp across the window', () => {
    expect(spanPct(0, 0, 100)).toBe(0)
    expect(spanPct(50, 0, 100)).toBe(50)
  })
})

describe('GanttChart', () => {
  it('renders the axis, a bar, markers, and a legend', () => {
    const wrapper = mount(GanttChart, { props: { rows: [row()], domain } })
    expect(wrapper.findAll('.gantt-tick').length).toBeGreaterThan(0)
    expect(wrapper.find('.gantt-bar').exists()).toBe(true)
    expect(wrapper.findAll('.gantt-marker')).toHaveLength(2)
    expect(wrapper.text()).toContain('Created')
    expect(wrapper.text()).toContain('Task One')
  })

  it('drops the label column when compact', () => {
    const wrapper = mount(GanttChart, { props: { rows: [row()], domain, compact: true } })
    expect(wrapper.find('.gantt-label').exists()).toBe(false)
    expect(wrapper.find('.gantt').classes()).toContain('compact')
  })

  it('links rows to the task when asked', () => {
    const RouterLinkStub = { props: ['to'], template: '<a><slot /></a>' }
    const wrapper = mount(GanttChart, {
      props: { rows: [row()], domain, linkRows: true },
      global: { stubs: { RouterLink: RouterLinkStub } }
    })
    expect(wrapper.find('.gantt-link').exists()).toBe(true)
    expect(wrapper.find('.gantt-link').element.tagName).toBe('A')
  })

  it('hides the legend when asked', () => {
    const wrapper = mount(GanttChart, { props: { rows: [row()], domain, showLegend: false } })
    expect(wrapper.find('.gantt-legend').exists()).toBe(false)
  })

  it('renders markers as plain spans unless they are clickable', () => {
    const wrapper = mount(GanttChart, { props: { rows: [row()], domain } })
    expect(wrapper.find('button.gantt-marker').exists()).toBe(false)
    expect(wrapper.findAll('span.gantt-marker')).toHaveLength(2)
  })

  it('emits the marker that was clicked when clickable', async () => {
    const wrapper = mount(GanttChart, { props: { rows: [row()], domain, clickMarkers: true } })
    const buttons = wrapper.findAll('button.gantt-marker')
    expect(buttons).toHaveLength(2)
    await buttons[1].trigger('click')
    expect(wrapper.emitted('marker-click')[0][0].id).toBe('m2')
  })
})
