import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  api: {
    tasks: { list: vi.fn(async () => [{ id: 't1' }]) },
    tags: { list: vi.fn(async () => [{ name: 'bug', count: 1 }]) },
    harnesses: { list: vi.fn(async () => [{ id: 'h1' }]) },
    repositories: { list: vi.fn(async () => [{ id: 'r1' }]) },
    groups: { list: vi.fn(async () => [{ id: 'g1' }]) },
    settings: { get: vi.fn(async () => ({ effective: { openchamber_url: 'x' } })) }
  }
}))

import { store, taskHasTag } from '../store'

describe('store loaders', () => {
  it('loads each collection into the reactive store', async () => {
    await store.loadTasks()
    expect(store.tasks).toEqual([{ id: 't1' }])

    await store.loadTags()
    expect(store.tags).toEqual([{ name: 'bug', count: 1 }])

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

describe('store.toggleTagFilter', () => {
  it('sets, toggles off, and switches the active tag filter', () => {
    store.tagFilter = ''
    store.toggleTagFilter('bug')
    expect(store.tagFilter).toBe('bug')
    store.toggleTagFilter('bug')
    expect(store.tagFilter).toBe('')
    store.toggleTagFilter('bug')
    store.toggleTagFilter('ui')
    expect(store.tagFilter).toBe('ui')
    store.tagFilter = ''
  })
})

describe('taskHasTag', () => {
  it('handles missing and present tags', () => {
    expect(taskHasTag({ tags: ['bug', 'ui'] }, 'ui')).toBe(true)
    expect(taskHasTag({ tags: ['bug'] }, 'ui')).toBe(false)
    expect(taskHasTag({}, 'ui')).toBe(false)
  })
})
