import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  metricsGet: vi.fn(),
  metricsSetBaseline: vi.fn(),
  metricsRemoveBaseline: vi.fn(),
  changesList: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    metrics: {
      get: mocks.metricsGet,
      baselines: vi.fn().mockResolvedValue([]),
      setBaseline: mocks.metricsSetBaseline,
      removeBaseline: mocks.metricsRemoveBaseline
    },
    changes: { list: mocks.changesList }
  }
}))

import MetricsView from '../views/MetricsView.vue'
import { store } from '../store'

const report = {
  window_days: 30,
  observation_days: 14,
  tolerance: 0.02,
  metrics: [
    {
      metric: 'autonomy_rate',
      label: 'Autonomy rate',
      value: 0.5,
      numerator: 1,
      denominator: 2,
      baseline: 0.2,
      delta: 0.3,
      direction: 'improving',
      unit: 'ratio'
    },
    {
      metric: 'yield',
      label: 'Yield',
      value: null,
      numerator: 0,
      denominator: 0,
      baseline: null,
      delta: null,
      direction: 'no-data',
      unit: 'ratio'
    }
  ],
  counts: { accepted: 2, touchless: 1, reverted: 0, rejected: 0, pending_observation: 0, open: 0 }
}

const change = {
  id: 'c1',
  task_id: 't1',
  title: 'Fix bug',
  change_class: 'bugfix',
  status: 'proposed',
  human_intervened: false
}

function mountView() {
  return mount(MetricsView)
}

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  store.tasks = [{ id: 't1', title: 'Task One' }]
  vi.spyOn(store, 'loadTasks').mockResolvedValue()
  mocks.metricsGet.mockResolvedValue(report)
  mocks.changesList.mockResolvedValue([change])
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('MetricsView', () => {
  it('loads the report and a read-only list of changes', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(mocks.metricsGet).toHaveBeenCalledWith({ windowDays: 30, observationDays: 14 })
    expect(mocks.changesList).toHaveBeenCalled()
    expect(wrapper.text()).toContain('Autonomy rate')
    expect(wrapper.text()).toContain('50.0%')
    expect(wrapper.text()).toContain('Improving')
    expect(wrapper.text()).toContain('Accepted 2')
    expect(wrapper.text()).toContain('Recent changes')
    expect(wrapper.text()).toContain('Fix bug')
    // The metrics page no longer records or mutates changes.
    expect(wrapper.find('input[placeholder="What changed?"]').exists()).toBe(false)
    expect(wrapper.findAll('button').some((b) => b.text() === 'Accept')).toBe(false)
  })

  it('sets a baseline to the current value and disables it when there is no value', async () => {
    mocks.metricsSetBaseline.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()

    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Set baseline to current')
      .trigger('click')
    await flushPromises()
    expect(mocks.metricsSetBaseline).toHaveBeenCalledWith('autonomy_rate', {
      value: 0.5,
      window_days: 30,
      observation_days: 14
    })

    const disabled = wrapper
      .findAll('button')
      .filter((b) => b.text() === 'Set baseline to current' && b.attributes('disabled') !== undefined)
    expect(disabled.length).toBe(1)
  })

  it('clears a baseline', async () => {
    mocks.metricsRemoveBaseline.mockResolvedValue(null)
    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Clear baseline')
      .trigger('click')
    await flushPromises()
    expect(mocks.metricsRemoveBaseline).toHaveBeenCalledWith('autonomy_rate')
  })

  it('shows an error with a working retry', async () => {
    mocks.metricsGet.mockRejectedValueOnce(new Error('offline'))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('offline')

    mocks.metricsGet.mockResolvedValue(report)
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Retry')
      .trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Autonomy rate')
  })
})
