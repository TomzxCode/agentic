import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  api: {
    tasks: { list: vi.fn(async () => [{ id: 't1' }]) },
    harnesses: { list: vi.fn(async () => [{ id: 'h1' }]) },
    repositories: { list: vi.fn(async () => [{ id: 'r1' }]) },
    groups: { list: vi.fn(async () => [{ id: 'g1' }]) },
    settings: { get: vi.fn(async () => ({ effective: { openchamber_url: 'x' } })) }
  }
}))

import { store } from '../store'

describe('store loaders', () => {
  it('loads each collection into the reactive store', async () => {
    await store.loadTasks()
    expect(store.tasks).toEqual([{ id: 't1' }])

    await store.loadHarnesses()
    expect(store.harnesses).toEqual([{ id: 'h1' }])

    await store.loadRepositories()
    expect(store.repositories).toEqual([{ id: 'r1' }])

    await store.loadGroups()
    expect(store.groups).toEqual([{ id: 'g1' }])

    await store.loadSettings()
    expect(store.settings).toEqual({ openchamber_url: 'x' })
  })
})
