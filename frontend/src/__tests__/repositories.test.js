import { describe, expect, it } from 'vitest'
import {
  groupItemsByRepository,
  itemKind,
  itemNumber,
  itemsForRepository,
  parseGithubUrl,
  parseRemote,
  sortItems
} from '../repositories'

const repos = [
  { id: 'r1', name: 'api', remote_url: 'https://github.com/acme/api.git', path: '/src/api', default_branch: 'main' },
  { id: 'r2', name: 'web', remote_url: 'git@github.com:acme/web.git', path: '/src/web' },
  { id: 'r3', name: 'tools', remote_url: null, path: '/src/tools' }
]

describe('parseGithubUrl', () => {
  it('parses an issue URL', () => {
    expect(parseGithubUrl('https://github.com/Acme/API/issues/42')).toEqual({
      owner: 'acme',
      repo: 'api',
      kind: 'issue',
      number: '42'
    })
  })

  it('parses a pull URL, tolerating a trailing query', () => {
    expect(parseGithubUrl('https://github.com/acme/api/pull/128?diff=split')).toMatchObject({
      kind: 'pr',
      number: '128'
    })
  })

  it('returns null for a non issue/PR URL', () => {
    expect(parseGithubUrl('https://github.com/acme/api')).toBeNull()
    expect(parseGithubUrl('')).toBeNull()
  })
})

describe('parseRemote', () => {
  it('parses https and ssh remotes and strips .git', () => {
    expect(parseRemote('https://github.com/acme/api.git')).toEqual({ owner: 'acme', repo: 'api' })
    expect(parseRemote('git@github.com:Acme/Web.git')).toEqual({ owner: 'acme', repo: 'web' })
    expect(parseRemote('ssh://git@github.com/acme/api')).toEqual({ owner: 'acme', repo: 'api' })
  })

  it('returns null for a non-GitHub remote', () => {
    expect(parseRemote('https://gitlab.com/acme/api.git')).toBeNull()
    expect(parseRemote(null)).toBeNull()
  })
})

describe('itemKind', () => {
  it('prefers the URL path', () => {
    expect(itemKind({ url: 'https://github.com/a/b/pull/3', kind: 'issue' })).toBe('pr')
  })

  it('falls back to the stored kind', () => {
    expect(itemKind({ url: null, kind: 'pull_request' })).toBe('pr')
    expect(itemKind({ url: null, kind: 'issue' })).toBe('issue')
  })

  it('returns null for anything else', () => {
    expect(itemKind({ url: 'https://example.com', kind: 'doc' })).toBeNull()
  })
})

describe('itemNumber', () => {
  it('reads the number from the URL', () => {
    expect(itemNumber({ url: 'https://github.com/a/b/issues/7' })).toBe('7')
  })

  it('falls back to the external id suffix', () => {
    expect(itemNumber({ url: null, external_id: 'a/b#9' })).toBe('9')
  })

  it('returns null when neither carries a number', () => {
    expect(itemNumber({ url: 'https://github.com/a/b', external_id: null })).toBeNull()
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
})

describe('sortItems', () => {
  it('sorts by number descending with unknown numbers last', () => {
    const sorted = sortItems([{ number: '2' }, { number: null }, { number: '10' }])
    expect(sorted.map((i) => i.number)).toEqual(['10', '2', null])
  })
})
