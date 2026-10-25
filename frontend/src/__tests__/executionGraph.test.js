import { describe, expect, it } from 'vitest'
import {
  autoLayout,
  blankRunNode,
  canConnect,
  connect,
  dropDanglingEdges,
  edgeEndpoints,
  editorIssues,
  nodeHeight,
  nodeRows,
  normalizeDefinition,
  portPoint,
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

const formNode = (id, fields) => ({
  id,
  kind: 'form',
  title: id,
  position: { x: 0, y: 0 },
  fields: fields.map((field) => ({ id: field, title: field, type: 'text', required: false }))
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

describe('blankRunNode', () => {
  it('makes a unique, editor-ready node', () => {
    const one = blankRunNode()
    const two = blankRunNode()
    expect(one.id).not.toBe(two.id)
    expect(one.kind).toBe('run')
    expect(one.inputs).toEqual([])
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
