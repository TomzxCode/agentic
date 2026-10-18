import { describe, expect, it } from 'vitest'
import {
  parseGithubUrl,
  parseRemote,
  itemKind,
  itemNumber,
  itemState,
  itemStatus,
  itemAuthor,
  personForHandle
} from '../repositories/parse'

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

describe('itemState', () => {
  it('normalizes the stored GitHub state', () => {
    expect(itemState({ metadata_json: { state: 'OPEN' } })).toBe('open')
    expect(itemState({ metadata_json: { state: 'MERGED' } })).toBe('merged')
    expect(itemState({ metadata_json: { state: 'CLOSED' } })).toBe('closed')
  })

  it('reports an open draft PR as a draft', () => {
    expect(itemState({ metadata_json: { state: 'OPEN', is_draft: true } })).toBe('draft')
  })

  it('returns null when no state is stored', () => {
    expect(itemState({ metadata_json: {} })).toBeNull()
    expect(itemState({})).toBeNull()
    expect(itemState(null)).toBeNull()
  })
})

describe('itemStatus', () => {
  it('maps a stored state to a label and badge class', () => {
    expect(itemStatus({ metadata_json: { state: 'OPEN' } })).toEqual({
      state: 'open',
      label: 'Open',
      className: 'st-open'
    })
    expect(itemStatus({ metadata_json: { state: 'CLOSED' } })).toEqual({
      state: 'closed',
      label: 'Closed',
      className: 'st-closed'
    })
    expect(itemStatus({ metadata_json: { state: 'OPEN', is_draft: true } })).toEqual({
      state: 'draft',
      label: 'Draft',
      className: 'st-draft'
    })
    expect(itemStatus({ metadata_json: { state: 'MERGED' } })).toEqual({
      state: 'merged',
      label: 'Merged',
      className: 'st-merged'
    })
  })

  it('covers issues as well as PRs', () => {
    expect(itemStatus({ kind: 'issue', metadata_json: { state: 'OPEN' } })?.label).toBe('Open')
  })

  it('returns null when no state is stored', () => {
    expect(itemStatus({ metadata_json: {} })).toBeNull()
    expect(itemStatus(null)).toBeNull()
  })
})

describe('itemAuthor', () => {
  it('reads the stored author login', () => {
    expect(itemAuthor({ metadata_json: { author: 'tom' } })).toBe('tom')
  })

  it('returns null when no author is stored', () => {
    expect(itemAuthor({ metadata_json: {} })).toBeNull()
    expect(itemAuthor({})).toBeNull()
    expect(itemAuthor(null)).toBeNull()
  })
})

describe('personForHandle', () => {
  const people = [
    { id: 'p1', name: 'Alice', aliases: ['alice', 'alice@example.com'] },
    { id: 'p2', name: 'Bob', aliases: ['bob'] }
  ]

  it('finds the person carrying the handle as an alias, case-insensitively', () => {
    expect(personForHandle(people, 'alice')?.id).toBe('p1')
    expect(personForHandle(people, 'ALICE')?.id).toBe('p1')
    expect(personForHandle(people, 'alice@example.com')?.id).toBe('p1')
  })

  it('returns null when nobody carries the handle', () => {
    expect(personForHandle(people, 'ghost')).toBeNull()
    expect(personForHandle(people, '')).toBeNull()
    expect(personForHandle(people, null)).toBeNull()
    expect(personForHandle(null, 'alice')).toBeNull()
  })
})
