// Layered layout for the before/after task graph.
//
// Each node is placed in a column by its longest path from a source, so every
// edge points from an earlier column to a later one and the drawing reads left
// to right. Within a column nodes keep the order they were given, which the
// caller sets to something stable (the API returns tasks oldest first).

export function layoutGraph(nodes, edges, options = {}) {
  const nodeWidth = options.nodeWidth ?? 180
  const nodeHeight = options.nodeHeight ?? 44
  const gapX = options.gapX ?? 90
  const gapY = options.gapY ?? 18
  const pad = options.pad ?? 24

  const ids = new Set(nodes.map((node) => node.id))
  const forward = new Map(nodes.map((node) => [node.id, []]))
  const indegree = new Map(nodes.map((node) => [node.id, 0]))
  const cleanEdges = []
  for (const edge of edges) {
    // An edge to a node that is not drawn would dangle, so drop it.
    if (!ids.has(edge.before_id) || !ids.has(edge.after_id)) continue
    forward.get(edge.before_id).push(edge.after_id)
    indegree.set(edge.after_id, indegree.get(edge.after_id) + 1)
    cleanEdges.push({ before_id: edge.before_id, after_id: edge.after_id })
  }

  // Longest-path layering, in topological order (Kahn's algorithm). A node with
  // no predecessors starts a column; every other node sits one past its latest
  // predecessor, so a chain of dependencies grows to the right.
  const layer = new Map(nodes.map((node) => [node.id, 0]))
  const remaining = new Map(indegree)
  const queue = nodes.filter((node) => indegree.get(node.id) === 0).map((node) => node.id)
  while (queue.length) {
    const id = queue.shift()
    for (const next of forward.get(id)) {
      layer.set(next, Math.max(layer.get(next), layer.get(id) + 1))
      remaining.set(next, remaining.get(next) - 1)
      if (remaining.get(next) === 0) queue.push(next)
    }
  }

  // Group by column, keeping the input order within each column.
  const columns = new Map()
  for (const node of nodes) {
    const column = layer.get(node.id) ?? 0
    if (!columns.has(column)) columns.set(column, [])
    columns.get(column).push(node.id)
  }
  const columnKeys = [...columns.keys()].sort((a, b) => a - b)
  const rows = Math.max(1, ...columnKeys.map((key) => columns.get(key).length))

  // Center every column against the tallest one.
  const contentHeight = rows * nodeHeight + Math.max(0, rows - 1) * gapY
  const positions = new Map()
  for (const key of columnKeys) {
    const columnIds = columns.get(key)
    const offset = (contentHeight - (columnIds.length * nodeHeight + (columnIds.length - 1) * gapY)) / 2
    columnIds.forEach((id, row) => {
      positions.set(id, {
        x: pad + key * (nodeWidth + gapX),
        y: pad + offset + row * (nodeHeight + gapY)
      })
    })
  }

  return {
    nodes: nodes.map((node) => ({ ...node, ...positions.get(node.id), width: nodeWidth, height: nodeHeight })),
    edges: cleanEdges,
    width: pad * 2 + (columnKeys.length ? columnKeys.length * nodeWidth + (columnKeys.length - 1) * gapX : 0),
    height: pad * 2 + contentHeight,
    columns: columnKeys.length,
    nodeWidth,
    nodeHeight
  }
}

// An edge drawn as a horizontal cubic curve from the source's right edge to the
// target's left edge, so the arrowhead lands cleanly on the target.
export function edgePath(from, to) {
  const x1 = from.x + from.width
  const y1 = from.y + from.height / 2
  const x2 = to.x
  const y2 = to.y + to.height / 2
  const bend = Math.max(24, Math.abs(x2 - x1) / 2)
  return `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`
}

// Break a title into at most `max` lines that each fit `maxChars`, so a long
// title stays inside its node box. Words are kept whole where possible.
export function wrapTitle(title, maxChars = 24, max = 3) {
  const words = String(title || '')
    .split(/\s+/)
    .filter(Boolean)
  const lines = []
  let line = ''
  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word
    if (candidate.length <= maxChars) {
      line = candidate
      continue
    }
    if (line) lines.push(line)
    line = word
    if (lines.length === max) break
  }
  if (line && lines.length < max) lines.push(line)
  if (!lines.length) return ['']
  if (lines.length === max) {
    const last = lines[max - 1]
    lines[max - 1] = last.length > maxChars ? `${last.slice(0, maxChars - 1)}…` : last
  }
  return lines
}
