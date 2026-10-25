// Layered layout for the before/after task graph.
//
// Each node is placed in a layer by its longest path from a source, so every
// edge points from an earlier layer to a later one. Nodes are aligned to the
// row of the node they link from, so a chain reads on one line instead of
// being centered as a block. `direction` controls whether layers run
// left-to-right ('LR', default) or top-to-bottom ('TB').

export function layoutGraph(nodes, edges, options = {}) {
  const nodeWidth = options.nodeWidth ?? 180
  const nodeHeight = options.nodeHeight ?? 44
  const gapX = options.gapX ?? 90
  const gapY = options.gapY ?? 18
  const pad = options.pad ?? 24
  const direction = options.direction === 'TB' ? 'TB' : 'LR'

  const ids = new Set(nodes.map((node) => node.id))
  const forward = new Map(nodes.map((node) => [node.id, []]))
  const indegree = new Map(nodes.map((node) => [node.id, 0]))
  const cleanEdges = []
  for (const edge of edges) {
    if (!ids.has(edge.before_id) || !ids.has(edge.after_id)) continue
    forward.get(edge.before_id).push(edge.after_id)
    indegree.set(edge.after_id, indegree.get(edge.after_id) + 1)
    cleanEdges.push({ before_id: edge.before_id, after_id: edge.after_id })
  }

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

  // Group by layer, keeping input order within each layer.
  const layers = new Map()
  for (const node of nodes) {
    const l = layer.get(node.id) ?? 0
    if (!layers.has(l)) layers.set(l, [])
    layers.get(l).push(node.id)
  }
  const layerKeys = [...layers.keys()].sort((a, b) => a - b)

  // Assign a row (LR) or column (TB) to each node, aligned to the row/column
  // of the node it links from, so connected nodes sit beside each other.
  const primary = new Map() // node id -> primary axis index (row for LR, col for TB)
  for (const key of layerKeys) {
    const idsInLayer = layers.get(key)
    const used = new Set()
    for (const id of idsInLayer) {
      let p = null
      for (const e of cleanEdges) {
        if (e.after_id === id && primary.has(e.before_id)) {
          const candidate = primary.get(e.before_id)
          if (!used.has(candidate)) {
            p = candidate
            break
          }
        }
      }
      if (p === null) {
        p = 0
        while (used.has(p)) p++
      }
      used.add(p)
      primary.set(id, p)
    }
  }

  const positions = new Map()

  if (direction === 'LR') {
    const maxPrimary = Math.max(0, ...[...primary.values()])
    const contentHeight = (maxPrimary + 1) * nodeHeight + maxPrimary * gapY
    for (const key of layerKeys) {
      const idsInLayer = layers.get(key)
      idsInLayer.forEach((id) => {
        positions.set(id, {
          x: pad + key * (nodeWidth + gapX),
          y: pad + primary.get(id) * (nodeHeight + gapY)
        })
      })
    }
    const numLayers = layerKeys.length
    return {
      nodes: nodes.map((node) => ({ ...node, ...positions.get(node.id), width: nodeWidth, height: nodeHeight })),
      edges: cleanEdges,
      width: pad * 2 + (numLayers ? numLayers * nodeWidth + (numLayers - 1) * gapX : 0),
      height: pad * 2 + contentHeight,
      columns: numLayers,
      nodeWidth,
      nodeHeight
    }
  }

  // TB: layers run top-to-bottom; align columns to the linked node.
  const maxPrimary = Math.max(0, ...[...primary.values()])
  const contentWidth = (maxPrimary + 1) * nodeWidth + maxPrimary * gapX
  for (const key of layerKeys) {
    const idsInLayer = layers.get(key)
    idsInLayer.forEach((id) => {
      positions.set(id, {
        x: pad + primary.get(id) * (nodeWidth + gapX),
        y: pad + key * (nodeHeight + gapY)
      })
    })
  }
  const numLayers = layerKeys.length
  return {
    nodes: nodes.map((node) => ({ ...node, ...positions.get(node.id), width: nodeWidth, height: nodeHeight })),
    edges: cleanEdges,
    width: pad * 2 + contentWidth,
    height: pad * 2 + (numLayers ? numLayers * nodeHeight + (numLayers - 1) * gapY : 0),
    columns: numLayers,
    nodeWidth,
    nodeHeight
  }
}

export function edgePath(from, to) {
  const x1 = from.x + from.width
  const y1 = from.y + from.height / 2
  const x2 = to.x
  const y2 = to.y + to.height / 2
  const bend = Math.max(24, Math.abs(x2 - x1) / 2)
  return `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`
}

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
