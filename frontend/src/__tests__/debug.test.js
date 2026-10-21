import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { debugStats, refreshDebugRequests, resetDebugStats, clearApiCalls, clearDbQueries } from '../debug.js'

function snapshot(data) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => data }))
}

beforeEach(() => resetDebugStats())
afterEach(() => vi.unstubAllGlobals())

it('retains API and DB history across overlapping and empty snapshots', async () => {
  const first = { id: 'first', path: '/api/tasks', db_queries: 2, queries: [{ sql: 'SELECT 1' }] }
  const second = { id: 'second', path: '/api/people', db_queries: 1 }
  snapshot([first])
  await refreshDebugRequests()
  snapshot([second, first])
  await refreshDebugRequests()
  snapshot([second])
  await refreshDebugRequests()
  snapshot([])
  await refreshDebugRequests()
  expect(debugStats.requests).toEqual([second, first])
})

it('retains history beyond 200 requests', async () => {
  snapshot(Array.from({ length: 200 }, (_, i) => ({ id: String(200 - i) })))
  await refreshDebugRequests()
  snapshot([{ id: '201' }, { id: '200' }])
  await refreshDebugRequests()
  expect(debugStats.requests).toHaveLength(201)
  expect(debugStats.requests[0].id).toBe('201')
  expect(debugStats.requests.at(-1).id).toBe('1')
})

it('clears API history independently without restoring cleared entries on refresh', async () => {
  const first = { id: 'first', db_queries: 1, queries: [{ sql: 'SELECT 1' }] }
  const second = { id: 'second', db_queries: 2 }
  snapshot([first])
  await refreshDebugRequests()
  clearApiCalls()
  expect(debugStats.requests).toEqual([])
  expect(debugStats.dbRequests).toEqual([first])
  snapshot([second, first])
  await refreshDebugRequests()
  expect(debugStats.requests).toEqual([second])
  expect(debugStats.dbRequests).toEqual([second, first])
})

it('clears DB history independently without restoring cleared entries on refresh', async () => {
  const first = { id: 'first', db_queries: 1, queries: [{ sql: 'SELECT 1' }] }
  const second = { id: 'second', db_queries: 2 }
  snapshot([first])
  await refreshDebugRequests()
  clearDbQueries()
  expect(debugStats.dbRequests).toEqual([])
  expect(debugStats.requests).toEqual([first])
  snapshot([second, first])
  await refreshDebugRequests()
  expect(debugStats.dbRequests).toEqual([second])
  expect(debugStats.requests).toEqual([second, first])
})
