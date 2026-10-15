import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, openRunStream, openTaskStream } from '../api'

function mockFetch({ status = 200, body = '' } = {}) {
  const res = {
    status,
    ok: status >= 200 && status < 300,
    statusText: 'OK',
    text: () => Promise.resolve(body)
  }
  global.fetch = vi.fn().mockResolvedValue(res)
  return global.fetch
}

afterEach(() => {
  delete global.fetch
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('api endpoints', () => {
  it('issues a request for every method', async () => {
    const fetchMock = mockFetch({ body: '{}' })
    await api.tasks.get('t1')
    await api.tasks.update('t1', { title: 'x' })
    await api.tasks.timeline('t1')
    await api.tasks.associate('t1', { item_id: 'i1' })
    await api.tasks.unassociate('t1', 'i1')
    await api.gantt.get()
    await api.items.create({ url: 'u' })
    await api.items.update('i1', { title: 'x' })
    await api.items.refresh('i1')
    await api.items.remove('i1')
    await api.repositories.list()
    await api.repositories.create({ path: '/p' })
    await api.repositories.createBulk(['/a', '/b'])
    await api.repositories.remove('r1')
    await api.groups.list()
    await api.groups.create({ name: 'g' })
    await api.groups.update('g1', { name: 'g' })
    await api.groups.remove('g1')
    await api.github.issue('https://github.com/o/r/issues/1')
    await api.github.issues({ repository_id: 'r1' })
    await api.harnesses.list()
    await api.harnesses.full()
    await api.harnesses.create({ name: 'n' })
    await api.harnesses.update('h1', { name: 'n' })
    await api.harnesses.remove('h1')
    await api.settings.get()
    await api.settings.update({ openchamber_url: 'x' })
    await api.inbox.get()
    await api.worktrees.list('t1')
    await api.worktrees.create('t1', {})
    await api.worktrees.remove('t1', 'w1')
    await api.runs.list('t1')
    await api.runs.create('t1', { prompt: 'p' })
    await api.runs.refreshContext('t1')
    await api.runs.context('t1')
    await api.runs.get('r1')
    await api.runs.events('r1')
    await api.runs.cancel('r1')
    expect(fetchMock).toHaveBeenCalledTimes(38)
  })

  it('adds include_done to the gantt query when asked', async () => {
    const fetchMock = mockFetch({ body: '[]' })
    await api.gantt.get({ includeDone: true })
    expect(fetchMock).toHaveBeenCalledWith('/api/gantt?include_done=true', expect.anything())
  })

  it('URL-encodes the github issue url', async () => {
    const fetchMock = mockFetch({ body: '{}' })
    await api.github.issue('https://github.com/o/r/issues/1')
    expect(fetchMock.mock.calls[0][0]).toContain('/api/github/issue?url=')
  })

  it('falls back to statusText when there is no error detail', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      status: 500,
      ok: false,
      statusText: 'Server Error',
      text: () => Promise.resolve('')
    })
    await expect(api.health()).rejects.toThrow('Server Error')
  })

  it('parses an empty body as null', async () => {
    mockFetch({ body: '' })
    await expect(api.health()).resolves.toBeNull()
  })
})

class FakeEventSource {
  static instances = []

  constructor(url) {
    this.url = url
    this.closed = false
    FakeEventSource.instances.push(this)
  }

  close() {
    this.closed = true
  }
}

function lastEventSource() {
  return FakeEventSource.instances[FakeEventSource.instances.length - 1]
}

describe('openRunStream', () => {
  it('delivers events and closes when the run finishes', () => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    const events = []
    const onClose = vi.fn()
    const close = openRunStream('r1', (e) => events.push(e), onClose)

    const source = lastEventSource()
    expect(source.url).toBe('/api/runs/r1/stream')

    source.onmessage({ data: JSON.stringify({ type: 'message', text: 'hi' }) })
    expect(events).toHaveLength(1)
    expect(source.closed).toBe(false)

    source.onmessage({ data: JSON.stringify({ type: 'run_finished' }) })
    expect(source.closed).toBe(true)
    expect(onClose).toHaveBeenCalled()

    close()
    expect(source.closed).toBe(true)
  })

  it('ignores bad payloads and closes on error', () => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const onClose = vi.fn()
    openRunStream('r2', () => {}, onClose)

    const source = lastEventSource()
    source.onmessage({ data: 'not json' })
    expect(warn).toHaveBeenCalled()

    source.onerror()
    expect(source.closed).toBe(true)
    expect(onClose).toHaveBeenCalled()
  })
})

describe('openTaskStream', () => {
  it('forwards parsed events and tolerates bad ones', () => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const events = []
    const close = openTaskStream('t1', (e) => events.push(e))

    const source = lastEventSource()
    expect(source.url).toBe('/api/tasks/t1/stream')
    source.onmessage({ data: JSON.stringify({ action: 'updated' }) })
    expect(events).toEqual([{ action: 'updated' }])

    source.onmessage({ data: 'bad' })
    expect(warn).toHaveBeenCalled()

    close()
    expect(source.closed).toBe(true)
  })
})
