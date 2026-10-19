import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { config, enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

// The page links each task with a PR to its task page.
config.global.stubs = { RouterLink: { props: ['to'], template: '<a><slot /></a>' } }

const mocks = vi.hoisted(() => ({
  metricsGet: vi.fn(),
  metricsSetBaseline: vi.fn(),
  metricsRemoveBaseline: vi.fn(),
  changesList: vi.fn(),
  changesCreate: vi.fn(),
  itemsList: vi.fn(),
  itemsRefresh: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    metrics: {
      get: mocks.metricsGet,
      baselines: vi.fn().mockResolvedValue([]),
      setBaseline: mocks.metricsSetBaseline,
      removeBaseline: mocks.metricsRemoveBaseline
    },
    changes: { list: mocks.changesList, create: mocks.changesCreate },
    items: { list: mocks.itemsList, refresh: mocks.itemsRefresh }
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
  external_ref: 'https://github.com/acme/api/pull/1',
  human_intervened: false
}

// A merged PR on t1 that the change above already references.
const recordedPr = {
  id: 'i1',
  source: 'github',
  kind: 'pull_request',
  title: 'Recorded PR',
  url: 'https://github.com/acme/api/pull/1',
  metadata_json: {},
  task_ids: ['t1']
}

// A PR on t1 with no change recorded, and a PR on a task the store does not hold.
const openPr = {
  id: 'i2',
  source: 'github',
  kind: 'pull_request',
  title: 'Open PR',
  url: 'https://github.com/acme/api/pull/2',
  metadata_json: { state: 'OPEN' },
  task_ids: ['t1']
}
// A merged PR on t1 whose merge time is not stored yet, so recording refreshes it.
const mergedPr = {
  id: 'i4',
  source: 'github',
  kind: 'pull_request',
  title: 'Merged PR',
  url: 'https://github.com/acme/api/pull/4',
  metadata_json: { state: 'MERGED' },
  task_ids: ['t1']
}
const orphanPr = {
  id: 'i3',
  source: 'github',
  kind: 'pull_request',
  title: 'Orphan PR',
  url: 'https://github.com/acme/api/pull/3',
  metadata_json: {},
  task_ids: ['t2']
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
  mocks.itemsList.mockResolvedValue([recordedPr, openPr, mergedPr, orphanPr])
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
    // The metrics page does not carry the task page's inline change form.
    expect(wrapper.find('input[placeholder="What changed?"]').exists()).toBe(false)
    expect(wrapper.findAll('button').some((b) => b.text() === 'Accept')).toBe(false)
  })

  it('lists tasks with a linked PR that has no change record', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(mocks.itemsList).toHaveBeenCalled()
    const text = wrapper.text()
    expect(text).toContain('Pull requests without a change record')
    // The open PR on t1 is offered; the PR the change references is not.
    expect(text).toContain('Open PR')
    expect(text).not.toContain('Recorded PR')
    // A PR on a task the store does not hold falls back to the raw id.
    expect(text).toContain('Orphan PR')
    expect(text).toContain('t2')
  })

  it('records a linked PR as an accepted change dated to now when it has no merge time', async () => {
    mocks.changesCreate.mockResolvedValue({})
    const wrapper = mountView()
    await flushPromises()

    // The first row is the open PR on t1.
    await wrapper
      .findAll('button')
      .find((b) => b.text().includes('Record accepted'))
      .trigger('click')
    await flushPromises()

    const body = mocks.changesCreate.mock.calls[0][0]
    expect(body).toMatchObject({
      task_id: 't1',
      title: 'Open PR',
      external_ref: 'https://github.com/acme/api/pull/2',
      status: 'accepted'
    })
    expect(body.opened_at).toBe(body.accepted_at)
  })

  it('refreshes a merged PR to date the accepted change to its merge time', async () => {
    mocks.changesCreate.mockResolvedValue({})
    mocks.itemsRefresh.mockResolvedValue({
      ...mergedPr,
      metadata_json: { state: 'MERGED', merged_at: '2026-01-02T03:04:05Z' }
    })
    const wrapper = mountView()
    await flushPromises()

    const mergedRow = wrapper.findAll('.change-row').find((row) => row.text().includes('Merged PR'))
    await mergedRow.find('button').trigger('click')
    await flushPromises()

    expect(mocks.itemsRefresh).toHaveBeenCalledWith('i4')
    expect(mocks.changesCreate).toHaveBeenCalledWith({
      task_id: 't1',
      title: 'Merged PR',
      external_ref: 'https://github.com/acme/api/pull/4',
      status: 'accepted',
      opened_at: '2026-01-02T03:04:05Z',
      accepted_at: '2026-01-02T03:04:05Z'
    })
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
