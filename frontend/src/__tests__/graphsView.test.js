import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'

enableAutoUnmount(afterEach)

const mocks = vi.hoisted(() => ({
  graphsList: vi.fn(),
  graphsCreate: vi.fn(),
  graphsUpdate: vi.fn(),
  graphsRemove: vi.fn(),
  graphsRun: vi.fn(),
  graphsExecutions: vi.fn(),
  graphsExecution: vi.fn(),
  graphsCancel: vi.fn(),
  graphsSubmitForm: vi.fn(),
  harnessesList: vi.fn(),
  confirm: vi.fn()
}))

vi.mock('../api', () => ({
  api: {
    graphs: {
      list: mocks.graphsList,
      create: mocks.graphsCreate,
      update: mocks.graphsUpdate,
      remove: mocks.graphsRemove,
      run: mocks.graphsRun,
      executions: mocks.graphsExecutions,
      execution: mocks.graphsExecution,
      cancelExecution: mocks.graphsCancel,
      submitForm: mocks.graphsSubmitForm
    },
    harnesses: { list: mocks.harnessesList }
  }
}))

import GraphExecutions from '../components/GraphExecutions.vue'
import GraphsList from '../components/GraphsList.vue'
import ExecutionGraphsView from '../views/ExecutionGraphsView.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

const graphRow = (id, extra = {}) => ({
  id,
  name: `Graph ${id}`,
  description: '',
  schedule: '0 9 * * *',
  timezone: 'UTC',
  enabled: true,
  next_run_at: '2026-10-25T09:00:00Z',
  last_run_at: null,
  created_at: '2026-10-25T00:00:00Z',
  updated_at: '2026-10-25T00:00:00Z',
  definition: {
    nodes: [{ id: 'a', kind: 'run', title: 'Step A', position: { x: 0, y: 0 }, promptTemplate: 'hi', inputs: [] }],
    edges: []
  },
  running_execution_id: null,
  ...extra
})

const executionRow = (id, extra = {}) => ({
  id,
  graph_id: 'g1',
  graph_name: 'Graph g1',
  task_id: 't1',
  trigger: 'manual',
  status: 'running',
  error: '',
  started_at: '2026-10-25T01:00:00Z',
  ended_at: null,
  ...extra
})

beforeEach(() => {
  vi.clearAllMocks()
  store.toast = null
  mocks.graphsList.mockResolvedValue([graphRow('g1')])
  mocks.graphsExecutions.mockResolvedValue([executionRow('x1')])
  mocks.graphsExecution.mockResolvedValue({
    id: 'x1',
    graph_id: 'g1',
    graph_name: 'Graph g1',
    task_id: 't1',
    trigger: 'manual',
    status: 'running',
    error: '',
    nodes: [
      { node_id: 'a', kind: 'run', title: 'Step A', status: 'done', run_id: 'r1', error: '', output: 'answer text' },
      { node_id: 'b', kind: 'run', title: 'Step B', status: 'running', run_id: 'r2', error: '', output: '' }
    ],
    pending_form: null,
    started_at: '2026-10-25T01:00:00Z',
    ended_at: null
  })
  mocks.harnessesList.mockResolvedValue([{ id: 'h1', name: 'opencode' }])
  vi.stubGlobal('confirm', mocks.confirm)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('ExecutionGraphsView', () => {
  it('shows the graphs tab with the list, and the executions tab with rows', async () => {
    const wrapper = mount(ExecutionGraphsView, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('Graph g1')
    expect(wrapper.text()).toContain('1 graph')

    await wrapper.find('[role="tablist"] button:nth-child(2)').trigger('click')
    await flushPromises()
    expect(mocks.graphsExecutions).toHaveBeenCalled()
    expect(wrapper.text()).toContain('execution')
  })
})

describe('GraphsList', () => {
  it('renders rows with schedule and step counts, and opens the editor', async () => {
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('Graph g1')
    expect(wrapper.text()).toContain('0 9 * * *')
    expect(wrapper.text()).toContain('1 step')

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Edit graph')
      .trigger('click')
    await flushPromises()
    // The editor shows the node card and the toolbar.
    expect(wrapper.find('.editor-node').exists()).toBe(true)
    expect(wrapper.find('.editor-node-title').text()).toBe('Step A')
    expect(wrapper.find('.editor-canvas').exists()).toBe(true)
  })

  it('runs a graph from its row', async () => {
    mocks.graphsRun.mockResolvedValue({ id: 'x9' })
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Run')
      .trigger('click')
    await flushPromises()
    expect(mocks.graphsRun).toHaveBeenCalledWith('g1')
  })

  it('deletes a graph after confirming', async () => {
    mocks.confirm.mockReturnValue(true)
    mocks.graphsRemove.mockResolvedValue()
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Delete')
      .trigger('click')
    await flushPromises()
    expect(mocks.confirm).toHaveBeenCalled()
    expect(mocks.graphsRemove).toHaveBeenCalledWith('g1')
  })
})

describe('GraphExecutions', () => {
  it('expands an execution into its nodes and outputs', async () => {
    const wrapper = mount(GraphExecutions, stub)
    await flushPromises()
    await wrapper.find('.graphs-exec-head').trigger('click')
    await flushPromises()
    expect(mocks.graphsExecution).toHaveBeenCalledWith('x1')
    expect(wrapper.text()).toContain('Step A')
    expect(wrapper.text()).toContain('done')
    expect(wrapper.find('.graphs-output').text()).toBe('answer text')
  })

  it('shows the pending form dialog and submits the values', async () => {
    mocks.graphsExecution.mockResolvedValue({
      id: 'x1',
      task_id: 't1',
      status: 'running',
      nodes: [{ node_id: 'a', kind: 'run', title: 'Step A', status: 'done', run_id: 'r1', error: '', output: '' }],
      pending_form: {
        node_id: 'f',
        title: 'Approve',
        requested_at: '2026-10-25T01:00:00Z',
        defaults: { f1: 'yes' },
        fields: [{ id: 'f1', title: 'Approve?', type: 'select', required: true, options: ['yes', 'no'] }]
      }
    })
    mocks.graphsSubmitForm.mockResolvedValue({
      id: 'x1',
      status: 'running',
      nodes: [],
      pending_form: null
    })
    const wrapper = mount(GraphExecutions, stub)
    await flushPromises()
    await wrapper.find('.graphs-exec-head').trigger('click')
    await flushPromises()
    const dialog = wrapper.find('.modal')
    expect(dialog.exists()).toBe(true)
    expect(dialog.text()).toContain('Approve?')

    // The dropdown comes prefilled from the request's defaults.
    const select = dialog.find('select')
    expect(select.element.value).toBe('yes')
    await select.setValue('no')
    await dialog
      .findAll('button')
      .find((button) => button.text() === 'Submit')
      .trigger('click')
    await flushPromises()
    expect(mocks.graphsSubmitForm).toHaveBeenCalledWith('x1', 'f', { values: { f1: 'no' }, cancel: false })
  })

  it('cancels a waiting form, which fails it', async () => {
    mocks.graphsExecution.mockResolvedValue({
      id: 'x1',
      task_id: 't1',
      status: 'running',
      nodes: [],
      pending_form: {
        node_id: 'f',
        title: 'Approve',
        requested_at: '',
        defaults: {},
        fields: [{ id: 'f1', title: 'Approve?', type: 'text', required: false }]
      }
    })
    mocks.graphsSubmitForm.mockResolvedValue({ id: 'x1', status: 'running', nodes: [], pending_form: null })
    const wrapper = mount(GraphExecutions, stub)
    await flushPromises()
    await wrapper.find('.graphs-exec-head').trigger('click')
    await flushPromises()
    await wrapper
      .find('.modal')
      .findAll('button')
      .find((button) => button.text() === 'Cancel form')
      .trigger('click')
    await flushPromises()
    expect(mocks.graphsSubmitForm).toHaveBeenCalledWith('x1', 'f', expect.objectContaining({ cancel: true }))
  })
})
