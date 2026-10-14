import { describe, expect, it } from 'vitest'
import { edgePath, layoutGraph, wrapTitle } from '../graph'

const node = (id) => ({ id, title: id })

describe('layoutGraph', () => {
  it('places a chain in successive columns', () => {
    const nodes = [node('a'), node('b'), node('c')]
    const edges = [
      { before_id: 'a', after_id: 'b' },
      { before_id: 'b', after_id: 'c' }
    ]
    const { nodes: placed } = layoutGraph(nodes, edges)
    const byId = Object.fromEntries(placed.map((n) => [n.id, n]))
    expect(byId.a.x).toBeLessThan(byId.b.x)
    expect(byId.b.x).toBeLessThan(byId.c.x)
  })

  it('puts a task past all of its predecessors (longest path)', () => {
    // a -> c and b -> c: c sits one column past its latest predecessor.
    const nodes = [node('a'), node('b'), node('c'), node('d')]
    const edges = [
      { before_id: 'a', after_id: 'b' },
      { before_id: 'b', after_id: 'c' },
      { before_id: 'd', after_id: 'c' }
    ]
    const { nodes: placed } = layoutGraph(nodes, edges)
    const byId = Object.fromEntries(placed.map((n) => [n.id, n]))
    expect(byId.b.x).toBeGreaterThan(byId.a.x)
    expect(byId.c.x).toBeGreaterThan(byId.b.x)
    // d has no predecessors, so it starts a column; c is still past b.
    expect(byId.d.x).toBe(byId.a.x)
  })

  it('stacks independent nodes in the same column', () => {
    const nodes = [node('a'), node('b')]
    const { nodes: placed, columns } = layoutGraph(nodes, [])
    expect(columns).toBe(1)
    expect(placed[0].x).toBe(placed[1].x)
    expect(placed[0].y).not.toBe(placed[1].y)
  })

  it('drops edges whose endpoints are not drawn', () => {
    const { edges } = layoutGraph([node('a')], [{ before_id: 'a', after_id: 'ghost' }])
    expect(edges).toEqual([])
  })

  it('sizes the canvas to fit the nodes', () => {
    const { width, height } = layoutGraph([node('a'), node('b')], [])
    expect(width).toBeGreaterThan(0)
    expect(height).toBeGreaterThan(0)
  })
})

describe('edgePath', () => {
  it('runs from the source right edge to the target left edge', () => {
    const from = { x: 0, y: 0, width: 100, height: 40 }
    const to = { x: 200, y: 100, width: 100, height: 40 }
    const path = edgePath(from, to)
    expect(path.startsWith('M 100 20')).toBe(true)
    expect(path.endsWith('200 120')).toBe(true)
  })
})

describe('wrapTitle', () => {
  it('keeps short titles on one line', () => {
    expect(wrapTitle('Fix the bug')).toEqual(['Fix the bug'])
  })

  it('wraps long titles and caps the line count', () => {
    const lines = wrapTitle('one two three four five six seven eight nine ten', 10, 3)
    expect(lines.length).toBe(3)
    expect(lines.join(' ')).toContain('one')
  })

  it('returns one empty line for an empty title', () => {
    expect(wrapTitle('')).toEqual([''])
  })
})
