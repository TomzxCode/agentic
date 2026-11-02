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
  webhooksEndpoints: vi.fn(),
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
    harnesses: { list: mocks.harnessesList },
    webhooks: { endpoints: mocks.webhooksEndpoints }
  }
}))

import GraphExecutions from '../components/GraphExecutions.vue'
import GraphsList from '../components/GraphsList.vue'
import ExecutionGraphsView from '../views/ExecutionGraphsView.vue'
import { store } from '../store'

const RouterLinkStub = { props: ['to'], template: '<a :href="to"><slot /></a>' }
const stub = { global: { stubs: { RouterLink: RouterLinkStub } } }

async function openEditor(wrapper) {
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Edit graph')
    .trigger('click')
  await flushPromises()
}

// Two run steps far apart with nothing wired, for the connect gestures.
const untangledDefinition = () => ({
  nodes: [
    { id: 'a', kind: 'run', title: 'Step A', position: { x: 40, y: 40 }, promptTemplate: 'hi', inputs: [] },
    {
      id: 'b',
      kind: 'run',
      title: 'Step B',
      position: { x: 600, y: 40 },
      promptTemplate: 'then {{v}}',
      inputs: [{ id: 'v', name: 'v' }]
    }
  ],
  edges: []
})

// Two run steps wired in a chain, saved far from where a layout would put them.
const twoStepDefinition = () => ({
  nodes: [
    { id: 'a', kind: 'run', title: 'Step A', position: { x: 900, y: 700 }, promptTemplate: 'hi', inputs: [] },
    {
      id: 'b',
      kind: 'run',
      title: 'Step B',
      position: { x: 20, y: 30 },
      promptTemplate: 'then {{v}}',
      inputs: [{ id: 'v', name: 'v' }]
    }
  ],
  edges: [{ id: 'e1', source: 'a', sourceFieldId: '', target: 'b', targetInputId: 'v', targetFieldId: '' }]
})

const graphRow = (id, extra = {}) => ({
  id,
  name: `Graph ${id}`,
  description: '',
  next_run_at: '2026-10-25T09:00:00Z',
  last_run_at: null,
  created_at: '2026-10-25T00:00:00Z',
  updated_at: '2026-10-25T00:00:00Z',
  definition: {
    nodes: [
      {
        id: 's1',
        kind: 'trigger',
        triggerType: 'schedule',
        title: 'Schedule',
        position: { x: 40, y: 40 },
        schedule: '0 9 * * *',
        timezone: 'UTC',
        enabled: true,
        outputs: []
      },
      { id: 'a', kind: 'run', title: 'Step A', position: { x: 40, y: 200 }, promptTemplate: 'hi', inputs: [] }
    ],
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
  localStorage.clear()
  // Fresh arrays per call: the component's watchers key off the list
  // reference, and the real API returns new JSON (so new objects) every poll.
  mocks.graphsList.mockImplementation(async () => [graphRow('g1')])
  mocks.graphsExecutions.mockImplementation(async () => [executionRow('x1')])
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
  mocks.webhooksEndpoints.mockResolvedValue([{ id: 'ep1', name: 'GitHub', kind: 'github', enabled: true }])
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
    expect(wrapper.findAll('.editor-node-title').map((title) => title.text())).toContain('Step A')
    expect(wrapper.find('.editor-canvas').exists()).toBe(true)
  })

  it('arranges every step from the Arrange button', async () => {
    mocks.graphsList.mockImplementation(async () => [graphRow('g1', { definition: twoStepDefinition() })])
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await openEditor(wrapper)
    expect(wrapper.findAll('.editor-node')[0].attributes('style')).toContain('left: 900px')

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Arrange')
      .trigger('click')
    await flushPromises()
    const cards = wrapper.findAll('.editor-node')
    expect(cards[0].attributes('style')).toContain('left: 40px')
    expect(cards[1].attributes('style')).toContain('left: 340px')
    expect(cards[0].attributes('style')).toContain('top: 40px')
  })

  it('lays out as steps are added when that mode is chosen', async () => {
    localStorage.setItem('agentic.executionGraph.autoLayout', 'add')
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await openEditor(wrapper)
    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('Add step'))
      .trigger('click')
    // The first menu entry is an agent run step.
    await wrapper.get('.editor-add-menu').findAll('.editor-add-item')[0].trigger('click')
    await flushPromises()

    const cards = wrapper.findAll('.editor-node')
    expect(cards).toHaveLength(3)
    // The added step takes the next free row of its layer.
    const added = cards[cards.length - 1]
    expect(added.attributes('style')).toContain('left: 40px')
    expect(added.attributes('style')).toContain('top: 340px')
  })

  it('lays out as steps are removed when that mode is chosen', async () => {
    localStorage.setItem('agentic.executionGraph.autoLayout', 'remove')
    mocks.graphsList.mockImplementation(async () => [
      graphRow('g1', {
        definition: {
          nodes: [
            { id: 'a', kind: 'run', title: 'Step A', position: { x: 0, y: 0 }, promptTemplate: 'hi', inputs: [] },
            { id: 'b', kind: 'run', title: 'Step B', position: { x: 600, y: 400 }, promptTemplate: 'go', inputs: [] }
          ],
          edges: []
        }
      })
    ])
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await openEditor(wrapper)

    await wrapper.findAll('.editor-node')[0].trigger('pointerdown')
    await wrapper
      .find('.editor-inspector')
      .findAll('button')
      .find((button) => button.text() === 'Delete')
      .trigger('click')
    await flushPromises()

    const card = wrapper.find('.editor-node')
    expect(card.text()).toContain('Step B')
    expect(card.attributes('style')).toContain('left: 40px')
    expect(card.attributes('style')).toContain('top: 40px')
  })

  it('connects two steps with two taps', async () => {
    mocks.graphsList.mockImplementation(async () => [graphRow('g1', { definition: untangledDefinition() })])
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await openEditor(wrapper)

    const source = wrapper.find('[data-node-id="a"][data-port-kind="output"]')
    await source.trigger('pointerdown')
    window.dispatchEvent(new PointerEvent('pointerup'))
    await flushPromises()
    const banner = wrapper.find('.editor-armed')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('answer')

    // The eligible target is marked before the second tap.
    const target = wrapper.find('[data-node-id="b"][data-port-kind="input"]')
    expect(target.classes()).toContain('eligible')
    await target.trigger('pointerdown')
    await flushPromises()
    expect(wrapper.find('.editor-armed').exists()).toBe(false)
    expect(wrapper.findAll('.editor-edge')).toHaveLength(1)
  })

  it('cancels an armed connection from the banner or the source', async () => {
    mocks.graphsList.mockImplementation(async () => [graphRow('g1', { definition: untangledDefinition() })])
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await openEditor(wrapper)
    const source = wrapper.find('[data-node-id="a"][data-port-kind="output"]')

    await source.trigger('pointerdown')
    window.dispatchEvent(new PointerEvent('pointerup'))
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Cancel')
      .trigger('click')
    await flushPromises()
    expect(wrapper.find('.editor-armed').exists()).toBe(false)

    // Tapping the source again is the other way out.
    await source.trigger('pointerdown')
    window.dispatchEvent(new PointerEvent('pointerup'))
    await flushPromises()
    expect(wrapper.find('.editor-armed').exists()).toBe(true)
    await source.trigger('pointerdown')
    await flushPromises()
    expect(wrapper.find('.editor-armed').exists()).toBe(false)
    expect(wrapper.findAll('.editor-edge')).toHaveLength(0)
  })

  it('removes a connection after tapping its line', async () => {
    mocks.graphsList.mockImplementation(async () => [graphRow('g1', { definition: twoStepDefinition() })])
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await openEditor(wrapper)

    // The transparent band is the tap target, so the 1.6 px curve is not the
    // only thing a finger can hit.
    const hit = wrapper.find('.editor-edge-hit')
    expect(hit.exists()).toBe(true)
    await hit.trigger('click')
    await flushPromises()
    const banner = wrapper.find('.editor-armed')
    expect(banner.exists()).toBe(true)
    expect(banner.text()).toContain('Step A · answer')
    expect(banner.text()).toContain('Step B · v')

    await banner
      .findAll('button')
      .find((button) => button.text() === 'Remove')
      .trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.editor-edge')).toHaveLength(0)
    expect(wrapper.find('.editor-armed').exists()).toBe(false)
  })

  it('lays out after a connection when auto-layout is always', async () => {
    localStorage.setItem('agentic.executionGraph.autoLayout', 'always')
    mocks.graphsList.mockImplementation(async () => [graphRow('g1', { definition: untangledDefinition() })])
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await openEditor(wrapper)
    expect(wrapper.findAll('.editor-node')[1].attributes('style')).toContain('left: 600px')

    const source = wrapper.find('[data-node-id="a"][data-port-kind="output"]')
    await source.trigger('pointerdown')
    window.dispatchEvent(new PointerEvent('pointerup'))
    await flushPromises()
    await wrapper.find('[data-node-id="b"][data-port-kind="input"]').trigger('pointerdown')
    await flushPromises()

    const cards = wrapper.findAll('.editor-node')
    expect(cards[0].attributes('style')).toContain('left: 40px')
    // The new link puts the second step in a later column.
    expect(cards[1].attributes('style')).toContain('left: 340px')
  })

  it('lays out after a connection is removed when auto-layout is on remove', async () => {
    localStorage.setItem('agentic.executionGraph.autoLayout', 'remove')
    mocks.graphsList.mockImplementation(async () => [graphRow('g1', { definition: twoStepDefinition() })])
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await openEditor(wrapper)

    await wrapper.find('.editor-edge-hit').trigger('click')
    await flushPromises()
    await wrapper
      .find('.editor-armed')
      .findAll('button')
      .find((button) => button.text() === 'Remove')
      .trigger('click')
    await flushPromises()

    const cards = wrapper.findAll('.editor-node')
    // With the link gone both steps share the first column and stack in rows.
    expect(cards[0].attributes('style')).toContain('left: 40px')
    expect(cards[0].attributes('style')).toContain('top: 40px')
    expect(cards[1].attributes('style')).toContain('left: 40px')
    expect(cards[1].attributes('style')).toContain('top: 190px')
  })

  it('remembers the auto-layout mode per device', async () => {
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await openEditor(wrapper)
    await wrapper.find('.editor-layout-mode select').setValue('always')
    expect(localStorage.getItem('agentic.executionGraph.autoLayout')).toBe('always')
  })

  it('adds and edits a schedule trigger node on the canvas', async () => {
    mocks.graphsUpdate.mockResolvedValue(graphRow('g1'))
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await openEditor(wrapper)

    const add = wrapper.findAll('button').find((button) => button.text().includes('Add step'))
    await add.trigger('click')
    await wrapper.get('.editor-add-menu').findAll('.editor-add-item')[5].trigger('click')
    await flushPromises()

    // The new node is selected, so the inspector edits it in place.
    expect(wrapper.text()).toContain('Schedule trigger')
    // Two nodes titled "Schedule" would block the save, so give it its own.
    await wrapper.find('#node-title').setValue('Nightly')
    const cron = wrapper.find('#node-schedule-cron')
    expect(cron.element.value).toBe('0 9 * * *')
    await cron.setValue('*/15 * * * *')

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Save')
      .trigger('click')
    await flushPromises()
    const definition = mocks.graphsUpdate.mock.calls.at(-1)[1].definition
    const schedules = definition.nodes.filter((node) => node.kind === 'trigger' && node.triggerType === 'schedule')
    expect(schedules).toHaveLength(2)
    expect(schedules[1].schedule).toBe('*/15 * * * *')
    expect(schedules[1].enabled).toBe(true)
  })

  it('picks the event source and filters on the trigger node', async () => {
    mocks.graphsUpdate.mockResolvedValue(graphRow('g1'))
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await openEditor(wrapper)

    const add = wrapper.findAll('button').find((button) => button.text().includes('Add step'))
    await add.trigger('click')
    // The event trigger is the fifth menu entry.
    await wrapper.get('.editor-add-menu').findAll('.editor-add-item')[4].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Event trigger')

    // The inspector asks for the source endpoint and what it should match.
    await wrapper.find('#node-event-endpoint').setValue('ep1')
    await wrapper.find('#node-event-types').setValue('pull_request, issues')
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '+ Filter')
      .trigger('click')
    await wrapper.find('input[aria-label="Filter 1 path"]').setValue('action')
    await wrapper.find('input[aria-label="Filter 1 value"]').setValue('opened')

    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Save')
      .trigger('click')
    await flushPromises()

    const definition = mocks.graphsUpdate.mock.calls.at(-1)[1].definition
    const node = definition.nodes.find((item) => item.kind === 'trigger' && item.triggerType === 'event')
    expect(node.endpointId).toBe('ep1')
    expect(node.events).toEqual(['pull_request', 'issues'])
    expect(node.filters).toEqual([{ path: 'action', equals: 'opened' }])
    expect(node.enabled).toBe(true)
  })

  it('shows the event source in the graph row', async () => {
    mocks.graphsList.mockImplementation(async () => [
      graphRow('g1', {
        definition: {
          nodes: [
            {
              id: 't1',
              kind: 'trigger',
              triggerType: 'event',
              title: 'Event trigger',
              position: { x: 40, y: 40 },
              endpointId: 'ep1',
              events: [],
              filters: [],
              enabled: true,
              outputs: []
            }
          ],
          edges: []
        }
      })
    ])
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    expect(wrapper.text()).toContain('event GitHub')
  })

  it('adds a step from the Add step menu', async () => {
    const wrapper = mount(GraphsList, stub)
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Edit graph')
      .trigger('click')
    await flushPromises()

    const add = wrapper.findAll('button').find((button) => button.text().includes('Add step'))
    await add.trigger('click')
    const menu = wrapper.get('.editor-add-menu')
    expect(menu.findAll('.editor-add-item').map((item) => item.text())).toEqual([
      expect.stringContaining('Agent run'),
      expect.stringContaining('Agentic command'),
      expect.stringContaining('Shell script'),
      expect.stringContaining('Form'),
      expect.stringContaining('Event trigger'),
      expect.stringContaining('Schedule trigger')
    ])
    await menu.findAll('.editor-add-item')[2].trigger('click')
    await flushPromises()

    expect(wrapper.find('.editor-add-menu').exists()).toBe(false)
    expect(wrapper.findAll('.editor-node')).toHaveLength(3)
    expect(wrapper.text()).toContain('Shell script')
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
    const wrapper = mount(GraphExecutions, { ...stub, props: { active: true } })
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
    const wrapper = mount(GraphExecutions, { ...stub, props: { active: true } })
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

    // A background refresh of the same pending request (the 2s poll) must
    // keep what was typed instead of reseeding the defaults.
    mocks.graphsExecution.mockClear()
    await wrapper.setProps({ refreshToken: 1 })
    await flushPromises()
    expect(mocks.graphsExecution).toHaveBeenCalled()
    expect(wrapper.find('.modal select').element.value).toBe('no')

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
    const wrapper = mount(GraphExecutions, { ...stub, props: { active: true } })
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
