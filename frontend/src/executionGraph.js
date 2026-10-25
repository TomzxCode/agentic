// Pure logic for the execution-graph editor: the definition's node and edge
// shapes, the cascade rules for removing things, the connect rules between
// ports, and the geometry the canvas draws with. The server owns the truth
// (validation, template rendering, execution); this module only keeps the
// editor fast and consistent, so every rule here mirrors one in
// `backend/src/agentic/graphs.py`.

export const NODE_WIDTH = 208
export const HEADER_HEIGHT = 34
export const ROW_HEIGHT = 26
// Distance between topological layers, and between stacked nodes in one.
export const LAYER_GAP = 300
export const ROW_GAP = 150

// Input names appear inside template placeholders, so they may not contain
// whitespace or any character that is part of the placeholder grammar.
export const INPUT_NAME_INVALID = /[\s.[\]{}"()]/

// {{name}}, {{name[2]}}, and {{name.join(", ")}} are the whole language.
const TEMPLATE_RE = /\{\{\s*([^\s.[\]{}"()]+)\s*(?:\[\s*(\d+)\s*\]|\.\s*join\(\s*"([^"]*)"\s*\))?\s*\}\}/g

export const FIELD_TYPES = ['text', 'textarea', 'number', 'date', 'time', 'select', 'slider', 'checkbox']
const NUMERIC_TYPES = ['number', 'slider']

export function newId(prefix = '') {
  return `${prefix}${Math.random().toString(16).slice(2, 10)}${Math.random().toString(16).slice(2, 6)}`
}

export function templateVars(template) {
  return [...(template || '').matchAll(TEMPLATE_RE)].map((match) => match[1])
}

export function blankRunNode(position = { x: 40, y: 40 }) {
  return {
    id: newId('n'),
    kind: 'run',
    title: 'New step',
    position,
    harnessId: '',
    model: '',
    cwd: '',
    promptTemplate: '',
    inputs: []
  }
}

export function blankCliNode(position = { x: 40, y: 40 }) {
  return {
    id: newId('n'),
    kind: 'cli',
    title: 'New command',
    position,
    cwd: '',
    command: '',
    inputs: []
  }
}

export function blankFormNode(position = { x: 40, y: 40 }) {
  return {
    id: newId('n'),
    kind: 'form',
    title: 'New form',
    position,
    fields: [{ ...blankField(), title: 'Answer' }]
  }
}

export function blankField() {
  return { id: newId('f'), title: '', type: 'text', required: false, placeholder: '', defaultValue: '' }
}

export function blankInput(name = '') {
  return { id: newId('in'), name }
}

export function blankEdge() {
  return { id: newId('e'), source: '', sourceFieldId: '', target: '', targetInputId: '', targetFieldId: '' }
}

// A fresh definition the editor can start from.
export function blankDefinition() {
  const first = blankRunNode({ x: 40, y: 60 })
  return { nodes: [first], edges: [] }
}

export function normalizeDefinition(raw) {
  const definition = {
    nodes: Array.isArray(raw?.nodes) ? raw.nodes.map((node) => normalizeNode(node)) : [],
    edges: Array.isArray(raw?.edges) ? raw.edges.map((edge) => normalizeEdge(edge)) : []
  }
  return definition
}

function normalizeNode(node) {
  const clean = {
    id: String(node?.id || ''),
    kind: node?.kind === 'form' ? 'form' : node?.kind === 'cli' ? 'cli' : 'run',
    title: String(node?.title || ''),
    position: {
      x: Number(node?.position?.x) || 0,
      y: Number(node?.position?.y) || 0
    }
  }
  if (clean.kind === 'run') {
    clean.harnessId = String(node?.harnessId || '')
    clean.model = String(node?.model || '')
    clean.cwd = String(node?.cwd || '')
    clean.promptTemplate = String(node?.promptTemplate || '')
    clean.inputs = Array.isArray(node?.inputs)
      ? node.inputs.map((input) => ({ id: String(input?.id || ''), name: String(input?.name || '') }))
      : []
  } else if (clean.kind === 'cli') {
    clean.command = String(node?.command || '')
    clean.cwd = String(node?.cwd || '')
    clean.inputs = Array.isArray(node?.inputs)
      ? node.inputs.map((input) => ({ id: String(input?.id || ''), name: String(input?.name || '') }))
      : []
  } else {
    clean.fields = Array.isArray(node?.fields)
      ? node.fields.map((field) => {
          const cleanField = {
            id: String(field?.id || ''),
            title: String(field?.title || ''),
            type: FIELD_TYPES.includes(field?.type) ? field.type : 'text',
            required: Boolean(field?.required),
            placeholder: String(field?.placeholder || ''),
            defaultValue: String(field?.defaultValue ?? '')
          }
          if (cleanField.type === 'select') {
            cleanField.options = (field?.options || []).map(String)
          }
          if (NUMERIC_TYPES.includes(cleanField.type)) {
            for (const key of ['min', 'max', 'step']) {
              cleanField[key] = field?.[key] === undefined || field?.[key] === null ? null : Number(field[key])
            }
          }
          return cleanField
        })
      : []
  }
  return clean
}

function normalizeEdge(edge) {
  return {
    id: String(edge?.id || ''),
    source: String(edge?.source || ''),
    sourceFieldId: String(edge?.sourceFieldId || ''),
    target: String(edge?.target || ''),
    targetInputId: String(edge?.targetInputId || ''),
    targetFieldId: String(edge?.targetFieldId || '')
  }
}

// --- edits with cascades ----------------------------------------------------
// Removing a node drops its edges; removing an input or field drops the edges
// wired to it, so the definition never holds a dangling reference.

export function removeNode(definition, nodeId) {
  return {
    ...definition,
    nodes: definition.nodes.filter((node) => node.id !== nodeId),
    edges: definition.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId)
  }
}

export function removeInput(node, inputId) {
  return { ...node, inputs: node.inputs.filter((input) => input.id !== inputId) }
}

export function removeField(node, fieldId) {
  return { ...node, fields: node.fields.filter((field) => field.id !== fieldId) }
}

// Drops every edge that points at a node, input, or field that no longer
// exists. Run after any structural edit that could orphan one.
export function dropDanglingEdges(definition) {
  const byId = new Map(definition.nodes.map((node) => [node.id, node]))
  const lives = (edge) => {
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target) return false
    if (source.kind === 'form') {
      if (!source.fields.some((field) => field.id === edge.sourceFieldId)) return false
    } else if (edge.sourceFieldId) {
      return false
    }
    if (target.kind === 'form') {
      if (edge.targetInputId) return false
      return target.fields.some((field) => field.id === edge.targetFieldId)
    }
    if (edge.targetFieldId) return false
    return target.inputs.some((input) => input.id === edge.targetInputId)
  }
  return { ...definition, edges: definition.edges.filter(lives) }
}

// --- connecting ports -------------------------------------------------------
// True when an output (a run node's answer, a cli node's stdout, or a form
// field's value) may wire into this target port (a named input of a run or
// cli node, or a form field's default).
export function canConnect(definition, sourceId, sourceFieldId, targetId, port) {
  if (sourceId === targetId) return false
  const source = definition.nodes.find((node) => node.id === sourceId)
  const target = definition.nodes.find((node) => node.id === targetId)
  if (!source || !target) return false
  if (source.kind !== 'form' && sourceFieldId) return false
  if (source.kind === 'form' && !source.fields.some((field) => field.id === sourceFieldId)) return false
  if (target.kind === 'form') {
    if (port.kind !== 'field') return false
    return target.fields.some((field) => field.id === port.id)
  }
  if (port.kind !== 'input') return false
  return target.inputs.some((input) => input.id === port.id)
}

export function connect(definition, sourceId, sourceFieldId, targetId, port) {
  if (!canConnect(definition, sourceId, sourceFieldId, targetId, port)) return definition
  const edge = blankEdge()
  edge.source = sourceId
  edge.sourceFieldId = sourceFieldId
  edge.target = targetId
  if (port.kind === 'input') edge.targetInputId = port.id
  else edge.targetFieldId = port.id
  const duplicate = definition.edges.some(
    (existing) =>
      existing.source === edge.source &&
      existing.sourceFieldId === edge.sourceFieldId &&
      existing.target === edge.target &&
      existing.targetInputId === edge.targetInputId &&
      existing.targetFieldId === edge.targetFieldId
  )
  if (duplicate) return definition
  return { ...definition, edges: [...definition.edges, edge] }
}

// --- instant editor feedback ------------------------------------------------
// The same problems the server's validate endpoint reports, computed locally
// so the editor can flag them as they are typed. The server stays the
// authority; this only avoids a round trip per keystroke.
export function editorIssues(definition) {
  const issues = []
  if (!definition.nodes.length) issues.push('The graph needs at least one node')
  const byId = new Map()
  const titles = new Map()
  for (const node of definition.nodes) {
    if (byId.has(node.id)) issues.push(`Duplicate node id '${node.id}'`)
    byId.set(node.id, node)
    if (!node.title) issues.push('Every node needs a title')
    if (titles.has(node.title)) issues.push(`Two nodes are titled '${node.title}'`)
    titles.set(node.title, node)
    if (node.kind !== 'form') {
      const text = node.kind === 'cli' ? node.command : node.promptTemplate
      const label = node.kind === 'cli' ? 'command' : 'prompt'
      if (!text.trim()) issues.push(`'${node.title || node.id}' needs a ${label}`)
      const names = new Set()
      for (const input of node.inputs) {
        if (!input.name || INPUT_NAME_INVALID.test(input.name)) {
          issues.push(`'${node.title || node.id}' has an invalid input name '${input.name}'`)
          continue
        }
        if (names.has(input.name)) issues.push(`'${node.title}' declares '${input.name}' twice`)
        names.add(input.name)
      }
      for (const name of templateVars(text)) {
        if (!names.has(name)) issues.push(`'${node.title}' uses {{${name}}} but declares no input named '${name}'`)
      }
      // A placeholder no connection feeds would fail the node at render time.
      for (const name of new Set(templateVars(text))) {
        const connected = definition.edges.some(
          (edge) =>
            edge.target === node.id &&
            node.inputs.some((input) => input.id === edge.targetInputId && input.name === name)
        )
        if (!connected) issues.push(`'${node.title}' uses {{${name}}} but nothing feeds the input '${name}'`)
      }
    } else {
      const seen = new Set()
      for (const field of node.fields) {
        if (!field.title) issues.push(`Form '${node.title || node.id}' has a field without a title`)
        if (seen.has(field.title)) issues.push(`Form '${node.title}' has two fields titled '${field.title}'`)
        seen.add(field.title)
        if (field.type === 'select' && !(field.options || []).length) {
          issues.push(`Field '${field.title || node.title}' is a dropdown and needs options`)
        }
        if (
          NUMERIC_TYPES.includes(field.type) &&
          (field.min === null || field.max === null || field.min >= field.max)
        ) {
          issues.push(`Field '${field.title || node.title}' needs a range where min is below max`)
        }
      }
    }
  }
  const seenEdges = new Set()
  for (const edge of definition.edges) {
    const key = `${edge.source}:${edge.sourceFieldId}->${edge.target}:${edge.targetInputId || edge.targetFieldId}`
    if (seenEdges.has(key)) issues.push('Two identical connections exist')
    seenEdges.add(key)
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target) {
      issues.push('A connection points at a missing node')
      continue
    }
    if (target.kind !== 'form' && !target.inputs.some((input) => input.id === edge.targetInputId)) {
      issues.push(`'${target.title}' has no input for one incoming connection`)
    }
    if (target.kind === 'form' && !target.fields.some((field) => field.id === edge.targetFieldId)) {
      issues.push(`'${target.title}' has no field for one incoming connection`)
    }
    if (source.kind === 'form' && !source.fields.some((field) => field.id === edge.sourceFieldId)) {
      issues.push(`'${source.title}' has no field for one connection`)
    }
  }
  if (topologicalOrder(definition) === null) issues.push('The graph has a circular connection')
  return issues
}

export function topologicalOrder(definition) {
  const ids = definition.nodes.map((node) => node.id)
  const indegree = new Map(ids.map((id) => [id, 0]))
  const forward = new Map(ids.map((id) => [id, []]))
  for (const edge of definition.edges) {
    if (!indegree.has(edge.source) || !indegree.has(edge.target) || edge.source === edge.target) continue
    forward.get(edge.source).push(edge.target)
    indegree.set(edge.target, indegree.get(edge.target) + 1)
  }
  const order = ids.filter((id) => indegree.get(id) === 0)
  const queue = [...order]
  while (queue.length) {
    const current = queue.shift()
    for (const next of forward.get(current)) {
      indegree.set(next, indegree.get(next) - 1)
      if (indegree.get(next) === 0) {
        order.push(next)
        queue.push(next)
      }
    }
  }
  return order.length === ids.length ? order : null
}

// Assigns left-to-right positions by longest path from a source, for nodes
// that have never been placed (a definition the user has not dragged yet).
export function autoLayout(definition) {
  const order = topologicalOrder(definition)
  if (!order) return definition
  const layer = new Map()
  for (const id of order) {
    const parents = definition.edges.filter((edge) => edge.target === id).map((edge) => edge.source)
    layer.set(id, parents.length ? Math.max(...parents.map((parent) => layer.get(parent) + 1)) : 0)
  }
  const perLayer = new Map()
  const nodes = definition.nodes.map((node) => {
    if (node.position && (node.position.x || node.position.y)) return node
    const depth = layer.get(node.id) || 0
    const row = perLayer.get(depth) || 0
    perLayer.set(depth, row + 1)
    return { ...node, position: { x: 40 + depth * LAYER_GAP, y: 40 + row * ROW_GAP } }
  })
  return { ...definition, nodes }
}

// --- canvas geometry --------------------------------------------------------
export function nodeRows(node) {
  if (node.kind !== 'form') {
    return [
      ...node.inputs.map((input) => ({ kind: 'input', id: input.id, label: input.name })),
      { kind: 'output', id: '', label: node.kind === 'cli' ? 'stdout' : 'answer' }
    ]
  }
  return node.fields.map((field) => ({ kind: 'field', id: field.id, label: field.title || 'field' }))
}

export function nodeHeight(node) {
  return HEADER_HEIGHT + nodeRows(node).length * ROW_HEIGHT + 8
}

// The absolute canvas point of a port: the row's outer edge, vertically centered.
export function portPoint(node, row) {
  const index = nodeRows(node).findIndex((candidate) => candidate.kind === row.kind && candidate.id === row.id)
  const y = node.position.y + HEADER_HEIGHT + index * ROW_HEIGHT + ROW_HEIGHT / 2
  return { x: row.kind === 'input' ? node.position.x : node.position.x + NODE_WIDTH, y }
}

export function edgeEndpoints(definition, edge) {
  const source = definition.nodes.find((node) => node.id === edge.source)
  const target = definition.nodes.find((node) => node.id === edge.target)
  if (!source || !target) return null
  const sourceRow = source.kind === 'form' ? { kind: 'field', id: edge.sourceFieldId } : { kind: 'output', id: '' }
  const targetRow =
    target.kind === 'form' ? { kind: 'field', id: edge.targetFieldId } : { kind: 'input', id: edge.targetInputId }
  return { from: portPoint(source, sourceRow), to: portPoint(target, targetRow) }
}

export function edgePath(from, to) {
  const bend = Math.max(40, Math.abs(to.x - from.x) / 2)
  return `M ${from.x} ${from.y} C ${from.x + bend} ${from.y}, ${to.x - bend} ${to.y}, ${to.x} ${to.y}`
}

export function canvasSize(definition) {
  let width = 800
  let height = 400
  for (const node of definition.nodes) {
    width = Math.max(width, node.position.x + NODE_WIDTH + 80)
    height = Math.max(height, node.position.y + nodeHeight(node) + 80)
  }
  return { width, height }
}
