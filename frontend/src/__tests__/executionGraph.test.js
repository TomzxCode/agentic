import { describe, expect, it } from 'vitest'
import {
  autoLayout,
  blankRunNode,
  blankScheduleNode,
  blankShellNode,
  canConnect,
  connect,
  dropDanglingEdges,
  edgeEndpoints,
  editorIssues,
  nearestPort,
  nodeHeight,
  nodeKindLabel,
  nodeLabel,
  nodeRows,
  normalizeDefinition,
  portPoint,
  relayout,
  removeField,
  removeInput,
  removeNode,
  templateVars,
  topologicalOrder
} from '../executionGraph'

const runNode = (id, prompt = '', inputs = []) => ({
  id,
  kind: 'run',
  title: id,
  position: { x: 0, y: 0 },
  harnessId: '',
  model: '',
  cwd: '',
  promptTemplate: prompt,
  inputs: inputs.map((name) => ({ id: name, name }))
})

const cliNode = (id, command = '', inputs = []) => ({
  id,
  kind: 'cli',
  title: id,
  position: { x: 0, y: 0 },
  cwd: '',
  command,
  inputs: inputs.map((name) => ({ id: name, name }))
})

const shellNode = (id, script = '', inputs = []) => ({
  id,
  kind: 'shell',
  title: id,
  position: { x: 0, y: 0 },
  cwd: '',
  script,
  inputs: inputs.map((name) => ({ id: name, name }))
})

const formNode = (id, fields) => ({
  id,
  kind: 'form',
  title: id,
  position: { x: 0, y: 0 },
  fields: fields.map((field) => ({ id: field, title: field, type: 'text', required: false }))
})

const triggerNode = (id, outputs) => ({
  id,
  kind: 'trigger',
  title: id,
  position: { x: 0, y: 0 },
  outputs: outputs.map(([outputId, name, path]) => ({ id: outputId, name, path }))
})

const edge = (source, target, { sourceFieldId = '', targetInputId = '', targetFieldId = '' } = {}) => ({
  id: `e-${source}-${target}-${targetInputId || targetFieldId}`,
  source,
  sourceFieldId,
  target,
  targetInputId,
  targetFieldId
})

describe('templateVars', () => {
  it('reads the three placeholder forms', () => {
    expect(templateVars('a {{x}} b {{y[2]}} c {{z.join(", ")}}')).toEqual(['x', 'y', 'z'])
  })

  it('reads nothing when the template has no placeholders', () => {
    expect(templateVars('plain prompt')).toEqual([])
  })
})

describe('cascade removal', () => {
  const definition = {
    nodes: [runNode('a', 'hi'), runNode('b', 'then {{v}}', ['v']), formNode('f', ['f1'])],
    edges: [edge('a', 'b', { targetInputId: 'v' }), edge('f', 'b', { sourceFieldId: 'f1', targetInputId: 'v' })]
  }

  it('removes a node and its edges', () => {
    const next = removeNode(definition, 'a')
    expect(next.nodes.map((node) => node.id)).toEqual(['b', 'f'])
    expect(next.edges).toHaveLength(1)
  })

  it('removes an input and the edges wired to it', () => {
    const node = removeInput(definition.nodes[1], 'v')
    expect(node.inputs).toEqual([])
    const next = dropDanglingEdges({ ...definition, nodes: [definition.nodes[0], node, definition.nodes[2]] })
    expect(next.edges).toEqual([])
  })

  it('removes a field and the edges wired to it', () => {
    const node = removeField(definition.nodes[2], 'f1')
    expect(node.fields).toEqual([])
    const next = dropDanglingEdges({ ...definition, nodes: [definition.nodes[0], definition.nodes[1], node] })
    expect(next.edges).toHaveLength(1)
  })
})

describe('canConnect and connect', () => {
  const definition = {
    nodes: [runNode('a', 'hi'), runNode('b', 'then {{v}}', ['v']), formNode('f', ['f1'])],
    edges: []
  }

  it('wires a run answer into a named input', () => {
    expect(canConnect(definition, 'a', '', 'b', { kind: 'input', id: 'v' })).toBe(true)
    const next = connect(definition, 'a', '', 'b', { kind: 'input', id: 'v' })
    expect(next.edges).toHaveLength(1)
  })

  it('wires a form field into a named input and a form default', () => {
    expect(canConnect(definition, 'f', 'f1', 'b', { kind: 'input', id: 'v' })).toBe(true)
    expect(canConnect(definition, 'a', '', 'f', { kind: 'field', id: 'f1' })).toBe(true)
  })

  it('refuses self connections, unknown ports, and run sources with fields', () => {
    expect(canConnect(definition, 'a', '', 'a', { kind: 'input', id: 'v' })).toBe(false)
    expect(canConnect(definition, 'a', '', 'b', { kind: 'input', id: 'nope' })).toBe(false)
    expect(canConnect(definition, 'a', 'x', 'b', { kind: 'input', id: 'v' })).toBe(false)
    expect(canConnect(definition, 'f', 'f1', 'b', { kind: 'field', id: 'f1' })).toBe(false)
    expect(canConnect(definition, 'f', 'nope', 'b', { kind: 'input', id: 'v' })).toBe(false)
  })

  it('does not duplicate an identical connection', () => {
    const one = connect(definition, 'a', '', 'b', { kind: 'input', id: 'v' })
    const two = connect(one, 'a', '', 'b', { kind: 'input', id: 'v' })
    expect(two.edges).toHaveLength(1)
  })
})

describe('editorIssues', () => {
  it('stays quiet for a sound graph', () => {
    const definition = {
      nodes: [runNode('a', 'hi'), runNode('b', 'then {{v}}', ['v'])],
      edges: [edge('a', 'b', { targetInputId: 'v' })]
    }
    expect(editorIssues(definition)).toEqual([])
  })

  it('reports missing prompts, unknown placeholders, and unconnected inputs', () => {
    const definition = { nodes: [runNode('a', ''), runNode('b', 'then {{v}}', ['v'])], edges: [] }
    const issues = editorIssues(definition)
    expect(issues.some((issue) => issue.includes('needs a prompt'))).toBe(true)
    expect(issues.some((issue) => issue.includes('nothing feeds'))).toBe(true)
  })

  it('reports cycles', () => {
    const definition = {
      nodes: [runNode('a', 'x'), runNode('b', '{{v}}', ['v'])],
      edges: [edge('a', 'b', { targetInputId: 'v' }), edge('b', 'a')]
    }
    expect(editorIssues(definition).some((issue) => issue.includes('circular'))).toBe(true)
  })

  it('reports a dropdown without options', () => {
    const definition = {
      nodes: [
        {
          ...formNode('f', ['pick']),
          fields: [{ id: 'pick', title: 'Pick', type: 'select', required: false, options: [] }]
        }
      ],
      edges: []
    }
    expect(editorIssues(definition).some((issue) => issue.includes('needs options'))).toBe(true)
  })
})

describe('topologicalOrder and autoLayout', () => {
  it('orders a chain and detects a cycle', () => {
    const definition = {
      nodes: [runNode('a'), runNode('b', '', ['v'])],
      edges: [edge('a', 'b', { targetInputId: 'v' })]
    }
    expect(topologicalOrder(definition)).toEqual(['a', 'b'])
    expect(topologicalOrder({ ...definition, edges: [...definition.edges, edge('b', 'a')] })).toBe(null)
  })

  it('places never-positioned nodes in columns, but keeps placed ones', () => {
    const unplaced = {
      nodes: [runNode('a'), runNode('b', '', ['v'])],
      edges: [edge('a', 'b', { targetInputId: 'v' })]
    }
    const laid = autoLayout(unplaced)
    expect(laid.nodes[1].position.x).toBeGreaterThan(laid.nodes[0].position.x)
    const placed = {
      ...unplaced,
      nodes: [
        { ...unplaced.nodes[0], position: { x: 500, y: 500 } },
        { ...unplaced.nodes[1], position: { x: 0, y: 0 } }
      ]
    }
    expect(autoLayout(placed).nodes[0].position).toEqual({ x: 500, y: 500 })
  })
})

describe('relayout', () => {
  const definition = {
    nodes: [
      { ...runNode('a', 'hi'), position: { x: 900, y: 700 } },
      { ...runNode('b', 'then {{v}}', ['v']), position: { x: 0, y: 0 } },
      { ...formNode('f', ['f1']), position: { x: 40, y: 40 } }
    ],
    edges: [edge('a', 'b', { targetInputId: 'v' })]
  }

  it('places every node by its dependency layer, discarding hand-placed positions', () => {
    const laid = relayout(definition)
    expect(laid.nodes[0].position.x).toBe(40)
    expect(laid.nodes[1].position.x).toBeGreaterThan(laid.nodes[0].position.x)
    // The form has no edges, so it starts in the first column again instead of
    // keeping the position it was saved with.
    expect(laid.nodes[2].position).toEqual({ x: 40, y: 190 })
    // The input definition is left untouched.
    expect(definition.nodes[0].position).toEqual({ x: 900, y: 700 })
  })

  it('keeps a chain on one row and gives stacked nodes their own row', () => {
    const laid = relayout(definition)
    expect(laid.nodes[0].position.y).toBe(laid.nodes[1].position.y)
    expect(laid.nodes[2].position.y).toBeGreaterThan(laid.nodes[0].position.y)
  })

  it('leaves a circular definition alone', () => {
    const cyclic = {
      nodes: [runNode('a', 'x'), runNode('b', '{{v}}', ['v'])],
      edges: [edge('a', 'b', { targetInputId: 'v' }), edge('b', 'a')]
    }
    expect(relayout(cyclic)).toBe(cyclic)
  })
})

describe('nearestPort', () => {
  const definition = {
    nodes: [
      { ...runNode('a', 'hi'), position: { x: 0, y: 0 } },
      { ...runNode('b', 'then {{v}}', ['v', 'w']), position: { x: 400, y: 0 } }
    ],
    edges: []
  }

  it('picks the closest eligible target within the radius', () => {
    const port = portPoint(definition.nodes[1], { kind: 'input', id: 'v' })
    const found = nearestPort(definition, 'a', '', { x: port.x - 20, y: port.y + 10 }, 48)
    expect(found).toMatchObject({ nodeId: 'b', kind: 'input', id: 'v' })
  })

  it('returns nothing when the point is too far from any target', () => {
    expect(nearestPort(definition, 'a', '', { x: 0, y: 0 }, 48)).toBe(null)
    expect(nearestPort(definition, 'a', '', { x: 400, y: 50 }, 10)).toMatchObject({ id: 'v' })
  })

  it('never targets the source node', () => {
    expect(nearestPort({ ...definition, nodes: [definition.nodes[0]] }, 'a', '', { x: 0, y: 50 }, 48)).toBe(null)
  })
})

describe('canvas geometry', () => {
  const node = { ...runNode('a', '', ['v', 'w']), position: { x: 100, y: 50 } }

  it('sizes a node from its rows', () => {
    // header + two inputs + the answer row.
    expect(nodeRows(node)).toHaveLength(3)
    expect(nodeHeight(node)).toBeGreaterThan(3 * 26)
  })

  it('puts input ports on the left edge and the answer port on the right edge', () => {
    const input = portPoint(node, { kind: 'input', id: 'v' })
    const answer = portPoint(node, { kind: 'output', id: '' })
    expect(input.x).toBe(100)
    expect(answer.x).toBe(100 + 208)
    expect(answer.y).toBeGreaterThan(input.y)
  })

  it('resolves both ends of an edge', () => {
    const definition = {
      nodes: [node, runNode('b', '', [])],
      edges: [edge('a', 'b', { targetInputId: 'v' })]
    }
    definition.nodes[1].position = { x: 400, y: 50 }
    const points = edgeEndpoints(definition, definition.edges[0])
    expect(points.from.x).toBe(308)
    expect(points.to.x).toBe(400)
  })
})

describe('trigger nodes', () => {
  it('normalize their payload outputs and drop pathless ones', () => {
    const definition = normalizeDefinition({
      nodes: [
        {
          id: 't',
          kind: 'trigger',
          title: 'Event',
          position: { x: 1, y: 2 },
          outputs: [
            { id: 'o1', name: 'title', path: 'pull_request.title' },
            { id: 'o2', name: 'gone', path: '' }
          ]
        }
      ],
      edges: []
    })
    expect(definition.nodes[0].kind).toBe('trigger')
    expect(definition.nodes[0].outputs).toEqual([{ id: 'o1', name: 'title', path: 'pull_request.title' }])
  })

  it('wire an event field into a run input or a form default, never the reverse', () => {
    const definition = {
      nodes: [
        triggerNode('t', [['o1', 'title', 'title']]),
        runNode('a', 'Handle {{title}}', ['title']),
        formNode('f', ['f1'])
      ],
      edges: []
    }
    expect(canConnect(definition, 't', 'o1', 'a', { kind: 'input', id: 'title' })).toBe(true)
    expect(canConnect(definition, 't', 'o1', 'f', { kind: 'field', id: 'f1' })).toBe(true)
    expect(canConnect(definition, 't', 'nope', 'a', { kind: 'input', id: 'title' })).toBe(false)
    expect(canConnect(definition, 'a', '', 't', { kind: 'input', id: 'o1' })).toBe(false)
  })

  it('feed a downstream input and stay quiet when wired', () => {
    const definition = {
      nodes: [triggerNode('t', [['o1', 'title', 'pull_request.title']]), runNode('a', 'Handle {{title}}', ['title'])],
      edges: [edge('t', 'a', { sourceFieldId: 'o1', targetInputId: 'title' })]
    }
    expect(editorIssues(definition)).toEqual([])
    expect(nodeRows(definition.nodes[0]).map((row) => row.label)).toEqual(['title'])
    const points = edgeEndpoints(
      { ...definition, nodes: [definition.nodes[0], { ...definition.nodes[1], position: { x: 400, y: 50 } }] },
      definition.edges[0]
    )
    expect(points.from.x).toBe(208)
    expect(points.to.x).toBe(400)
  })

  it('report a trigger without fields, two triggers, and an incoming connection', () => {
    const noFields = editorIssues({ nodes: [triggerNode('t', [])], edges: [] })
    expect(noFields.some((issue) => issue.includes('needs at least one event field'))).toBe(true)

    const two = editorIssues({
      nodes: [triggerNode('t', [['o1', 'title', 'title']]), triggerNode('t2', [['o2', 'title', 'title']])],
      edges: []
    })
    expect(two.some((issue) => issue.includes('at most one event trigger'))).toBe(true)

    const incoming = editorIssues({
      nodes: [triggerNode('t', [['o1', 'title', 'title']]), runNode('a', 'go')],
      edges: [edge('a', 't')]
    })
    expect(incoming.some((issue) => issue.includes('cannot take a connection'))).toBe(true)
  })

  it('drop the edges wired to a removed output', () => {
    const definition = {
      nodes: [
        triggerNode('t', [
          ['o1', 'title', 'title'],
          ['o2', 'body', 'body']
        ]),
        runNode('a', '{{v}}', ['v'])
      ],
      edges: [edge('t', 'a', { sourceFieldId: 'o2', targetInputId: 'v' })]
    }
    const without = {
      ...definition,
      nodes: [triggerNode('t', [['o1', 'title', 'title']]), definition.nodes[1]]
    }
    expect(dropDanglingEdges(without).edges).toEqual([])
  })
})

const scheduleNode = (id, cron = '0 9 * * *', timezone = 'UTC', extra = {}) => ({
  id,
  kind: 'trigger',
  triggerType: 'schedule',
  title: id,
  position: { x: 0, y: 0 },
  schedule: cron,
  timezone,
  enabled: true,
  outputs: [],
  ...extra
})

describe('event trigger sources and filters', () => {
  it('normalize the source, event types, filters, and enabled flag', () => {
    const definition = normalizeDefinition({
      nodes: [
        {
          id: 't',
          kind: 'trigger',
          triggerType: 'event',
          title: 'Event',
          position: { x: 1, y: 2 },
          endpointId: ' ep-1 ',
          events: [' issues ', '', 'issues', 'push'],
          filters: [
            { path: 'action', equals: 'opened' },
            { path: 'draft', exists: false },
            { path: 'title', contains: ' bug ' },
            { path: ' ', equals: 'x' },
            { path: 'nooperator' }
          ],
          enabled: false,
          outputs: [{ id: 'o1', name: 'title', path: 'issue.title' }]
        }
      ],
      edges: []
    })
    const node = definition.nodes[0]
    expect(node.endpointId).toBe('ep-1')
    expect(node.events).toEqual(['issues', 'push'])
    expect(node.filters).toEqual([
      { path: 'action', equals: 'opened' },
      { path: 'draft', exists: false },
      { path: 'title', contains: 'bug' }
    ])
    expect(node.enabled).toBe(false)
    expect(node.outputs).toEqual([{ id: 'o1', name: 'title', path: 'issue.title' }])
  })

  it('report a filter row without a path', () => {
    const issues = editorIssues({
      nodes: [{ ...triggerNode('t', [['o1', 'title', 'title']]), filters: [{ path: '', equals: 'x' }] }],
      edges: []
    })
    expect(issues.some((issue) => issue.includes('Event filter 1 needs a payload path'))).toBe(true)
  })
})

describe('schedule trigger nodes', () => {
  it('normalize their cron and drop outputs', () => {
    const definition = normalizeDefinition({
      nodes: [
        {
          id: 's',
          kind: 'trigger',
          triggerType: 'schedule',
          title: 'S',
          position: { x: 1, y: 2 },
          schedule: '0 9 * * *',
          timezone: 'Europe/Paris',
          enabled: false,
          outputs: [{ id: 'o', path: 'x' }]
        }
      ],
      edges: []
    })
    const node = definition.nodes[0]
    expect(node.triggerType).toBe('schedule')
    expect(node.schedule).toBe('0 9 * * *')
    expect(node.timezone).toBe('Europe/Paris')
    expect(node.enabled).toBe(false)
    expect(node.outputs).toEqual([])
    expect(nodeRows(node)).toEqual([])
  })

  it('report a bad cron and timezone, and allow several schedules', () => {
    const issues = editorIssues({
      nodes: [scheduleNode('s1', 'nope', 'Mars/Base'), scheduleNode('s2', '0 9 * * *', 'UTC', { title: 'Nightly' })],
      edges: []
    })
    expect(issues.some((issue) => issue.includes('5 fields'))).toBe(true)
    expect(issues.some((issue) => issue.includes('Mars/Base'))).toBe(true)
    expect(issues.some((issue) => issue.includes('at most one event trigger'))).toBe(false)
  })

  it('cannot be a connection source or target', () => {
    const definition = { nodes: [scheduleNode('s'), runNode('a', 'go')], edges: [] }
    expect(canConnect(definition, 's', '', 'a', { kind: 'input', id: 'v' })).toBe(false)
    expect(canConnect(definition, 'a', '', 's', { kind: 'input', id: 'x' })).toBe(false)
    const issues = editorIssues({ ...definition, edges: [edge('a', 's')] })
    expect(issues.some((issue) => issue.includes('cannot take a connection'))).toBe(true)
  })

  it('make a blank node labelled by its trigger type', () => {
    const node = blankScheduleNode()
    expect(node.kind).toBe('trigger')
    expect(node.triggerType).toBe('schedule')
    expect(node.enabled).toBe(true)
    expect(nodeLabel(node)).toBe('Schedule trigger')
    expect(nodeLabel({ kind: 'trigger', triggerType: 'event' })).toBe('Event trigger')
    expect(nodeKindLabel('trigger')).toBe('Trigger')
  })
})

describe('blankRunNode', () => {
  it('makes a unique, editor-ready node', () => {
    const one = blankRunNode()
    const two = blankRunNode()
    expect(one.id).not.toBe(two.id)
    expect(one.kind).toBe('run')
    expect(one.inputs).toEqual([])
  })
})

describe('shell nodes', () => {
  it('wire like run nodes and report a missing script', () => {
    const definition = {
      nodes: [runNode('a', 'go'), shellNode('s', 'echo "{{v}}"', ['v']), formNode('f', ['f1'])],
      edges: []
    }
    expect(canConnect(definition, 'a', '', 's', { kind: 'input', id: 'v' })).toBe(true)
    expect(canConnect(definition, 's', '', 'f', { kind: 'field', id: 'f1' })).toBe(true)
    expect(canConnect(definition, 'f', 'f1', 's', { kind: 'input', id: 'v' })).toBe(true)
    expect(
      editorIssues({ nodes: [shellNode('s', '')], edges: [] }).some((issue) => issue.includes('needs a script'))
    ).toBe(true)
    expect(
      editorIssues({
        nodes: [runNode('a', 'go'), shellNode('s', 'echo {{v}}', ['v'])],
        edges: [edge('a', 's', { targetInputId: 'v' })]
      })
    ).toEqual([])
  })

  it('normalize their script and expose stdout', () => {
    const definition = normalizeDefinition({
      nodes: [{ id: 's', kind: 'shell', title: 'S', position: { x: 1, y: 2 }, script: 'make build', junk: true }],
      edges: []
    })
    expect(definition.nodes[0].kind).toBe('shell')
    expect(definition.nodes[0].script).toBe('make build')
    expect(definition.nodes[0].command).toBeUndefined()
    expect(nodeRows(definition.nodes[0]).map((row) => row.label)).toEqual(['stdout'])
  })

  it('make a blank, editor-ready node and have a display label', () => {
    const node = blankShellNode()
    expect(node.kind).toBe('shell')
    expect(node.script).toBe('')
    expect(nodeKindLabel('shell')).toBe('Shell script')
    expect(nodeKindLabel('run')).toBe('Agent run')
    expect(nodeKindLabel('cli')).toBe('Agentic command')
  })
})

describe('cli nodes', () => {
  it('connect like run nodes: outputs into inputs, forms into their defaults', () => {
    const definition = {
      nodes: [runNode('a', 'go'), cliNode('c', 'task create --title {{v}}', ['v']), formNode('f', ['f1'])],
      edges: []
    }
    expect(canConnect(definition, 'a', '', 'c', { kind: 'input', id: 'v' })).toBe(true)
    expect(canConnect(definition, 'c', '', 'f', { kind: 'field', id: 'f1' })).toBe(true)
    expect(canConnect(definition, 'f', 'f1', 'c', { kind: 'input', id: 'v' })).toBe(true)
    expect(canConnect(definition, 'c', '', 'a', { kind: 'field', id: 'nope' })).toBe(false)
    const wired = connect(connect(definition, 'a', '', 'c', { kind: 'input', id: 'v' }), 'f', 'f1', 'c', {
      kind: 'input',
      id: 'v'
    })
    expect(wired.edges).toHaveLength(2)
  })

  it('report a missing command and unconnected placeholders', () => {
    const issues = editorIssues({
      nodes: [cliNode('c', ''), cliNode('d', 'task close {{t}}', ['t'])],
      edges: []
    })
    expect(issues.some((issue) => issue.includes('needs a command'))).toBe(true)
    expect(issues.some((issue) => issue.includes('nothing feeds'))).toBe(true)
  })

  it('stay quiet when wired', () => {
    const definition = {
      nodes: [runNode('a', 'go'), cliNode('c', 'task create --title {{v}}', ['v'])],
      edges: [edge('a', 'c', { targetInputId: 'v' })]
    }
    expect(editorIssues(definition)).toEqual([])
  })

  it('have inputs and a stdout row, dropping edges when the command node goes', () => {
    const node = { ...cliNode('c', 'x', ['v', 'w']), position: { x: 0, y: 0 } }
    const rows = nodeRows(node)
    expect(rows.map((row) => row.label)).toEqual(['v', 'w', 'stdout'])
    expect(nodeRows(runNode('a'))[runNode('a').inputs.length + 0].label).toBe('answer')
    expect(nodeHeight(node)).toBeGreaterThan(3 * 26)
    const definition = {
      nodes: [runNode('a', 'go'), node, cliNode('d', 'task list', [])],
      edges: [edge('a', 'c', { targetInputId: 'v' })]
    }
    const next = dropDanglingEdges(removeNode(definition, 'c'))
    expect(next.edges).toEqual([])
  })

  it('survive normalization with their command', () => {
    const definition = normalizeDefinition({
      nodes: [{ id: 'c', kind: 'cli', title: 'C', position: { x: 1, y: 2 }, command: 'task list', junk: true }],
      edges: []
    })
    expect(definition.nodes[0].kind).toBe('cli')
    expect(definition.nodes[0].command).toBe('task list')
    expect(definition.nodes[0].promptTemplate).toBeUndefined()
  })

  it('resolve their stdout port on the right edge', () => {
    const node = { ...cliNode('c', 'x'), position: { x: 100, y: 50 } }
    const stdout = portPoint(node, { kind: 'output', id: '' })
    expect(stdout.x).toBe(100 + 208)
    const definition = {
      nodes: [node, runNode('b', '', [])],
      edges: [edge('c', 'b', { targetInputId: 'v' })]
    }
    definition.nodes[1].position = { x: 400, y: 50 }
    const points = edgeEndpoints(definition, definition.edges[0])
    expect(points.from.x).toBe(308)
  })
})
