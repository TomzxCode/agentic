import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'

function mockFetch({ status = 200, body = '' } = {}) {
  const res = {
    status,
    ok: status >= 200 && status < 300,
    statusText: status === 204 ? 'No Content' : 'OK',
    text: () => Promise.resolve(body)
  }
  global.fetch = vi.fn().mockResolvedValue(res)
  return global.fetch
}

afterEach(() => {
  delete global.fetch
})

describe('api request', () => {
  it('URL-encodes query parameters and drops empty ones', async () => {
    const fetchMock = mockFetch({ body: '[]' })
    await api.tasks.list({ status: 'open', q: '' })
    expect(fetchMock).toHaveBeenCalledWith('/api/tasks?status=open', expect.objectContaining({ method: 'GET' }))
  })

  it('sends a JSON body for writes', async () => {
    const fetchMock = mockFetch({ body: '{"id":1}' })
    await api.tasks.create({ title: 'Hi' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/tasks',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{"title":"Hi"}'
      })
    )
  })

  it('parses the JSON response', async () => {
    mockFetch({ body: '{"id":7,"title":"Hello"}' })
    await expect(api.tasks.get(7)).resolves.toEqual({ id: 7, title: 'Hello' })
  })

  it('returns null for 204 No Content', async () => {
    mockFetch({ status: 204 })
    await expect(api.tasks.remove(1)).resolves.toBeNull()
  })

  it('throws the API detail on an error response', async () => {
    mockFetch({ status: 400, body: '{"detail":"bad input"}' })
    await expect(api.tasks.create({})).rejects.toThrow('bad input')
  })
})

describe('api query builders', () => {
  it('builds the github issues query with defaults', async () => {
    const fetchMock = mockFetch({ body: '[]' })
    await api.github.issues()
    expect(fetchMock).toHaveBeenCalledWith('/api/github/issues?state=open&limit=20', expect.anything())
  })

  it('includes only the provided item filters', async () => {
    const fetchMock = mockFetch({ body: '[]' })
    await api.items.list({ source: 'slack', q: 'design' })
    expect(fetchMock).toHaveBeenCalledWith('/api/items?source=slack&q=design', expect.anything())
  })

  it('passes the fs list path when browsing', async () => {
    const fetchMock = mockFetch({ body: '{}' })
    await api.fs.list('/home/me', true)
    expect(fetchMock).toHaveBeenCalledWith('/api/fs/list?path=%2Fhome%2Fme&hidden=true', expect.anything())
  })
})

describe('api changes and metrics', () => {
  it('builds the changes list query and writes', async () => {
    const fetchMock = mockFetch({ body: '[]' })
    await api.changes.list({ taskId: 't1', status: 'accepted' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/changes?task_id=t1&status=accepted',
      expect.objectContaining({ method: 'GET' })
    )

    await api.changes.transition('c1', 'accepted')
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/changes/c1/status',
      expect.objectContaining({ method: 'POST', body: '{"status":"accepted"}' })
    )
  })

  it('builds the metrics query including a zero observation window', async () => {
    const fetchMock = mockFetch({ body: '{}' })
    await api.metrics.get({ windowDays: 30, observationDays: 0, taskId: 't1' })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/metrics?window_days=30&observation_days=0&task_id=t1',
      expect.objectContaining({ method: 'GET' })
    )
  })

  it('upserts and clears a baseline', async () => {
    const fetchMock = mockFetch({ body: '{}' })
    await api.metrics.setBaseline('yield', { value: 0.2 })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/metrics/baselines/yield',
      expect.objectContaining({ method: 'PUT', body: '{"value":0.2}' })
    )

    mockFetch({ status: 204 })
    await expect(api.metrics.removeBaseline('yield')).resolves.toBeNull()
  })
})
