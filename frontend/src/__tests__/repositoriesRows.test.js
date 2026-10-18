import { describe, expect, it } from 'vitest'
import { itemAuthor, itemState, stateBreakdown } from '../repositories/parse'
import {
  groupItemsByRepository,
  itemsForRepository,
  filterRepositories,
  sortRepositories,
  repositoryRows,
  sortItems
} from '../repositories/rows'

const repos = [
  { id: 'r1', name: 'api', remote_url: 'https://github.com/acme/api.git', path: '/src/api', default_branch: 'main' },
  { id: 'r2', name: 'web', remote_url: 'git@github.com:acme/web.git', path: '/src/web' },
  { id: 'r3', name: 'tools', remote_url: null, path: '/src/tools' }
]

describe('stateBreakdown', () => {
  it('counts items per state in display order', () => {
    const items = [
      { metadata_json: { state: 'OPEN' } },
      { metadata_json: { state: 'CLOSED' } },
      { metadata_json: { state: 'MERGED' } },
      { metadata_json: { state: 'OPEN', is_draft: true } },
      { metadata_json: { state: 'OPEN' } },
      { metadata_json: {} }
    ]
    expect(stateBreakdown(items)).toEqual([
      { value: 'open', label: 'Open', count: 2 },
      { value: 'draft', label: 'Draft', count: 1 },
      { value: 'merged', label: 'Merged', count: 1 },
      { value: 'closed', label: 'Closed', count: 1 }
    ])
  })

  it('returns nothing when no item carries a state', () => {
    expect(stateBreakdown([{ metadata_json: {} }])).toEqual([])
    expect(stateBreakdown(null)).toEqual([])
  })
})

describe('itemsForRepository', () => {
  it('keeps only task-associated GitHub issue/PR items matching the remote', () => {
    const items = [
      { id: 'i1', source: 'github', url: 'https://github.com/acme/api/issues/1', task_ids: ['t1'] },
      { id: 'i2', source: 'github', url: 'https://github.com/acme/api/pull/2', task_ids: ['t1'] },
      { id: 'i3', source: 'github', url: 'https://github.com/acme/api/issues/3', task_ids: [] },
      { id: 'i4', source: 'github', url: 'https://github.com/acme/web/issues/4', task_ids: ['t1'] },
      { id: 'i5', source: 'slack', url: 'https://acme.slack.com/archives/C1/p1', task_ids: ['t1'] }
    ]
    const got = itemsForRepository(repos[0], items)
    expect(got.map((i) => i.id)).toEqual(['i1', 'i2'])
    expect(got[0]).toMatchObject({ kind: 'issue', number: '1' })
    expect(got[1]).toMatchObject({ kind: 'pr', number: '2' })
  })

  it('returns nothing for a repository without a GitHub remote', () => {
    const items = [{ id: 'i1', source: 'github', url: 'https://github.com/acme/api/issues/1', task_ids: ['t1'] }]
    expect(itemsForRepository(repos[2], items)).toEqual([])
  })
})

describe('filterRepositories', () => {
  const list = [
    { id: 'r1', name: 'api', path: '/src/api', remote_url: 'https://github.com/acme/api.git' },
    { id: 'r2', name: 'web', path: '/src/web', remote_url: 'git@github.com:acme/web.git' },
    { id: 'r3', name: 'tools', path: '/src/tools', remote_url: null }
  ]

  it('matches the needle against name, path, and remote', () => {
    expect(filterRepositories(list, { query: 'acme/api' }).map((r) => r.id)).toEqual(['r1'])
    expect(filterRepositories(list, { query: '/src/tools' }).map((r) => r.id)).toEqual(['r3'])
    expect(filterRepositories(list, { query: 'WEB' }).map((r) => r.id)).toEqual(['r2'])
    expect(filterRepositories(list, { query: 'nothing' })).toEqual([])
  })

  it('filters by whether the remote is GitHub', () => {
    expect(filterRepositories(list, { remote: 'github' }).map((r) => r.id)).toEqual(['r1', 'r2'])
    expect(filterRepositories(list, { remote: 'other' }).map((r) => r.id)).toEqual(['r3'])
  })

  it('passes everything through with no filters', () => {
    expect(filterRepositories(list, {})).toHaveLength(3)
    expect(filterRepositories(null, {})).toEqual([])
  })
})

describe('sortRepositories', () => {
  const list = [
    { id: 'r1', name: 'b', created_at: '2026-01-01T00:00:00Z', issue_count: 2, pull_count: 0 },
    { id: 'r2', name: 'a', created_at: '2026-01-03T00:00:00Z', issue_count: 0, pull_count: 1 },
    { id: 'r3', name: 'c', created_at: '2026-01-02T00:00:00Z', issue_count: 0, pull_count: 0 }
  ]
  const ids = (repos) => repos.map((r) => r.id)

  it('sorts by name by default', () => {
    expect(ids(sortRepositories(list))).toEqual(['r2', 'r1', 'r3'])
    expect(ids(sortRepositories(list, 'name'))).toEqual(['r2', 'r1', 'r3'])
  })

  it('sorts by associated item count, name breaking ties', () => {
    expect(ids(sortRepositories(list, 'items'))).toEqual(['r1', 'r2', 'r3'])
    expect(
      ids(
        sortRepositories(
          [
            { id: 'x', name: 'z', issue_count: 1 },
            { id: 'y', name: 'a', issue_count: 1 }
          ],
          'items'
        )
      )
    ).toEqual(['y', 'x'])
  })

  it('sorts by when the repository was added', () => {
    expect(ids(sortRepositories(list, 'newest'))).toEqual(['r2', 'r3', 'r1'])
  })

  it('reverses the order when the direction is desc', () => {
    expect(ids(sortRepositories(list, 'name', 'desc'))).toEqual(['r3', 'r1', 'r2'])
    expect(ids(sortRepositories(list, 'items', 'asc'))).toEqual(['r3', 'r2', 'r1'])
    expect(ids(sortRepositories(list, 'newest', 'asc'))).toEqual(['r1', 'r3', 'r2'])
  })

  it('keeps ties alphabetical ascending in either direction', () => {
    const tied = [
      { id: 'x', name: 'z', issue_count: 1 },
      { id: 'y', name: 'a', issue_count: 1 }
    ]
    expect(ids(sortRepositories(tied, 'items', 'desc'))).toEqual(['y', 'x'])
    expect(ids(sortRepositories(tied, 'items', 'asc'))).toEqual(['y', 'x'])
  })

  it('does not reorder the input', () => {
    sortRepositories(list, 'items')
    expect(ids(list)).toEqual(['r1', 'r2', 'r3'])
  })
})

describe('repositoryRows', () => {
  it('merges the live listing with the stored, task-associated items', () => {
    const ghx = [
      { number: 1, kind: 'issue', title: 'Open issue', url: 'https://github.com/acme/api/issues/1', state: 'OPEN' },
      { number: 7, kind: 'pr', title: 'Unlinked PR', url: 'https://github.com/acme/api/pull/7', state: 'OPEN' }
    ]
    const stored = [
      {
        id: 'i1',
        source: 'github',
        external_id: 'acme/api#1',
        url: 'https://github.com/acme/api/issues/1',
        task_ids: ['t1'],
        metadata_json: { author: 'alice' }
      }
    ]
    const rows = repositoryRows(ghx, stored)

    const linked = rows.find((r) => r.number === '1')
    // The row carries the live state and the stored task link and id.
    expect(linked).toMatchObject({
      kind: 'issue',
      linked: true,
      live: true,
      id: 'i1',
      external_id: 'acme/api#1',
      task_ids: ['t1']
    })
    expect(itemState(linked)).toBe('open')
    expect(itemAuthor(linked)).toBe('alice')

    const unlinked = rows.find((r) => r.number === '7')
    expect(unlinked).toMatchObject({ kind: 'pr', linked: false, live: true, id: null, task_ids: [] })
  })

  it('prefers the live state over the stored one', () => {
    const ghx = [{ number: 5, kind: 'pr', title: 'PR', url: 'https://github.com/acme/api/pull/5', state: 'MERGED' }]
    const stored = [
      {
        id: 'i5',
        source: 'github',
        url: 'https://github.com/acme/api/pull/5',
        task_ids: ['t1'],
        metadata_json: { state: 'OPEN' }
      }
    ]
    expect(itemState(repositoryRows(ghx, stored)[0])).toBe('merged')
  })

  it('keeps a stored item the listing does not carry', () => {
    const stored = [{ id: 'i9', source: 'github', url: 'https://github.com/acme/api/issues/9', task_ids: ['t1'] }]
    const rows = repositoryRows([], stored)
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ kind: 'issue', number: '9', linked: true, live: false, id: 'i9' })
  })
})

describe('groupItemsByRepository', () => {
  const items = [
    { id: 'i1', source: 'github', url: 'https://github.com/acme/api/issues/1', task_ids: ['t1'] },
    { id: 'i2', source: 'github', url: 'https://github.com/acme/api/pull/2', task_ids: ['t1'] },
    { id: 'i3', source: 'github', url: 'https://github.com/acme/web/issues/3', task_ids: ['t1'] },
    { id: 'i4', source: 'github', url: 'https://github.com/acme/other/issues/4', task_ids: ['t1'] },
    { id: 'i5', source: 'github', url: 'https://github.com/acme/api/issues/5', task_ids: [] },
    { id: 'i6', source: 'url', url: 'https://github.com/acme/api/issues/6', task_ids: ['t1'] }
  ]

  it('counts issues and PRs per repository', () => {
    const summaries = groupItemsByRepository(repos, items)
    const api = summaries.find((s) => s.id === 'r1')
    const web = summaries.find((s) => s.id === 'r2')
    const tools = summaries.find((s) => s.id === 'r3')
    expect(api).toMatchObject({ issue_count: 1, pull_count: 1 })
    expect(web).toMatchObject({ issue_count: 1, pull_count: 0 })
    expect(tools).toMatchObject({ issue_count: 0, pull_count: 0, owner: null })
  })

  it('excludes items with no matching repository, no task, or a non-GitHub source', () => {
    const api = groupItemsByRepository(repos, items).find((s) => s.id === 'r1')
    expect(api.items.map((i) => i.id).sort()).toEqual(['i1', 'i2'])
  })

  it('breaks the matched items down by state', () => {
    const withStates = [
      {
        id: 's1',
        source: 'github',
        url: 'https://github.com/acme/api/issues/1',
        task_ids: ['t1'],
        metadata_json: { state: 'OPEN' }
      },
      {
        id: 's2',
        source: 'github',
        url: 'https://github.com/acme/api/pull/2',
        task_ids: ['t1'],
        metadata_json: { state: 'MERGED' }
      },
      {
        id: 's3',
        source: 'github',
        url: 'https://github.com/acme/api/pull/3',
        task_ids: ['t1'],
        metadata_json: { state: 'OPEN', is_draft: true }
      }
    ]
    const api = groupItemsByRepository(repos, withStates).find((s) => s.id === 'r1')
    expect(api.states).toEqual([
      { value: 'open', label: 'Open', count: 1 },
      { value: 'draft', label: 'Draft', count: 1 },
      { value: 'merged', label: 'Merged', count: 1 }
    ])
    expect(groupItemsByRepository(repos, items).find((s) => s.id === 'r3').states).toEqual([])
  })
})

describe('sortItems', () => {
  it('sorts by number descending with unknown numbers last', () => {
    const sorted = sortItems([{ number: '2' }, { number: null }, { number: '10' }])
    expect(sorted.map((i) => i.number)).toEqual(['10', '2', null])
  })
})
