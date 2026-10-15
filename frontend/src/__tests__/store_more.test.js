import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  api: {
    tasks: { list: vi.fn(async () => [{ id: 't1' }]) },
    tags: { list: vi.fn(async () => [{ name: 'bug', count: 1 }]) },
    harnesses: { list: vi.fn(async () => [{ id: 'h1' }]) },
    repositories: { list: vi.fn(async () => [{ id: 'r1' }]) },
    groups: { list: vi.fn(async () => [{ id: 'g1' }]) },
    settings: { get: vi.fn(async () => ({ effective: { openchamber_url: 'x' } })) },
    inbox: { get: vi.fn(async () => ({ suggestions: [{ id: 's1' }], count: 1 })) }
  }
}))

import { store, priorityLabel, taskHasTag } from '../store'

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

    await store.loadInbox()
    expect(store.inbox).toEqual([{ id: 's1' }])
    expect(store.inboxCount).toBe(1)
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

describe('priorityLabel', () => {
  it('names each level and defaults to medium', () => {
    expect(priorityLabel(0)).toBe('low')
    expect(priorityLabel(1)).toBe('medium')
    expect(priorityLabel(2)).toBe('high')
    expect(priorityLabel(3)).toBe('urgent')
    expect(priorityLabel('3')).toBe('urgent')
    expect(priorityLabel(undefined)).toBe('medium')
    expect(priorityLabel(9)).toBe('medium')
  })
})
