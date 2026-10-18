import { describe, expect, it } from 'vitest'

import {
  commitUrl,
  groupQueueByRepository,
  groupReviewFiles,
  queueRowFor,
  reviewLabel,
  riskTone,
  shortCommit,
  stripReportMarker,
  taskPullRequests,
  verdictLabel,
  verdictTone
} from '../reviews'

const file = (over = {}) => ({ name: 'review-pr.abc1234.md', skill: 'review-pr', commit: 'abc1234', ...over })

describe('groupReviewFiles', () => {
  it('groups files by commit, keeping the API’s newest-first order', () => {
    const groups = groupReviewFiles([
      file({ name: 'review-pr.def5678.md', commit: 'def5678', modified_at: '2026-01-03T00:00:00Z' }),
      file({ name: 'review-pr.abc1234.md', commit: 'abc1234', modified_at: '2026-01-02T00:00:00Z' }),
      file({
        name: 'validate-pr.abc1234.md',
        skill: 'validate-pr',
        commit: 'abc1234',
        modified_at: '2026-01-01T00:00:00Z'
      })
    ])
    expect(groups.map((group) => group.commit)).toEqual(['def5678', 'abc1234'])
    expect(groups[1].files.map((f) => f.name)).toEqual(['review-pr.abc1234.md', 'validate-pr.abc1234.md'])
    // A group's timestamp is its newest file's.
    expect(groups[1].updated_at).toBe('2026-01-02T00:00:00Z')
  })

  it('collects commitless files under a single null-commit group', () => {
    const groups = groupReviewFiles([
      file({ name: 'gh-pr-view.md', skill: null, commit: null, modified_at: '2026-01-03T00:00:00Z' }),
      file({ name: 'validate-pr.no-issue.md', skill: null, commit: null, modified_at: '2026-01-01T00:00:00Z' })
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0].commit).toBeNull()
    expect(groups[0].files).toHaveLength(2)
  })

  it('returns nothing for no files', () => {
    expect(groupReviewFiles([])).toEqual([])
    expect(groupReviewFiles(undefined)).toEqual([])
  })
})

describe('reviewLabel', () => {
  it('uses the skill when present', () => {
    expect(reviewLabel(file())).toBe('review-pr')
  })

  it('falls back to the file name without its extension', () => {
    expect(reviewLabel({ name: 'gh-pr-view.md', skill: null })).toBe('gh-pr-view')
  })
})

describe('stripReportMarker', () => {
  it('removes a leading marker comment', () => {
    const text = '<!-- {"step":"review-pr","sha":"abc"} -->\n# Verdict\n'
    expect(stripReportMarker(text)).toBe('# Verdict\n')
  })

  it('leaves a body with no marker untouched', () => {
    expect(stripReportMarker('# Verdict\n')).toBe('# Verdict\n')
  })

  it('does not remove a comment that is not at the start', () => {
    const text = '# Verdict\n\n<!-- a note -->\n'
    expect(stripReportMarker(text)).toBe(text)
  })
})

describe('verdictLabel and verdictTone', () => {
  it('marks a pass, a fail, and informational, and keeps any other verdict', () => {
    expect(verdictLabel('pass')).toBe('✅')
    expect(verdictLabel('fail')).toBe('❌')
    expect(verdictLabel('informational')).toBe('ℹ️')
    expect(verdictLabel('partial')).toBe('partial')
    expect(verdictLabel('')).toBe('')
  })

  it('tones a verdict by what it asks of the reviewer', () => {
    expect(verdictTone('pass')).toBe('ok')
    expect(verdictTone('fail')).toBe('danger')
    expect(verdictTone('hold')).toBe('danger')
    expect(verdictTone('decide')).toBe('warn')
    expect(verdictTone('informational')).toBe('info')
    expect(verdictTone('')).toBe('')
  })
})

describe('riskTone', () => {
  it('tones a risk by severity', () => {
    expect(riskTone('high')).toBe('danger')
    expect(riskTone('medium')).toBe('warn')
    expect(riskTone('low')).toBe('ok')
    expect(riskTone('')).toBe('')
  })
})

describe('groupQueueByRepository', () => {
  it('groups the queue by repository, keeping the API order', () => {
    const groups = groupQueueByRepository([
      { repository: 'o/a', number: 2 },
      { repository: 'o/a', number: 1 },
      { repository: 'o/b', number: 3 }
    ])
    expect(groups.map((group) => group.repository)).toEqual(['o/a', 'o/b'])
    expect(groups[0].prs.map((pr) => pr.number)).toEqual([2, 1])
  })

  it('returns nothing for an empty queue', () => {
    expect(groupQueueByRepository([])).toEqual([])
    expect(groupQueueByRepository(undefined)).toEqual([])
  })
})

describe('shortCommit', () => {
  it('shortens a commit to seven characters', () => {
    expect(shortCommit('abc1234def')).toBe('abc1234')
    expect(shortCommit('')).toBe('')
  })
})

describe('commitUrl', () => {
  it('points at the GitHub commit for the reviewed sha', () => {
    expect(commitUrl({ repository: 'o/r', owner: 'o', head_commit: 'abc1234' })).toBe(
      'https://github.com/o/r/commit/abc1234'
    )
  })

  it('is null without a commit or an owner', () => {
    expect(commitUrl({ repository: 'o/r', owner: 'o', head_commit: '' })).toBeNull()
    expect(commitUrl({ repository: 'r', owner: '', head_commit: 'abc1234' })).toBeNull()
  })
})

describe('taskPullRequests', () => {
  const assoc = (url, over = {}) => ({ item: { id: 'i1', url, kind: 'pull_request', ...over } })

  it('reads the GitHub pull requests a task links, lowercased', () => {
    const prs = taskPullRequests({
      associations: [
        assoc('https://github.com/Acme/API/pull/42'),
        { item: { id: 'i2', url: 'https://github.com/acme/api/issues/7', kind: 'issue' } }
      ]
    })
    expect(prs).toEqual([
      { owner: 'acme', repo: 'api', number: 42, url: 'https://github.com/Acme/API/pull/42', item_id: 'i1' }
    ])
  })

  it('collapses the same PR linked twice', () => {
    const prs = taskPullRequests({
      associations: [assoc('https://github.com/acme/api/pull/42'), assoc('https://github.com/acme/api/pull/42')]
    })
    expect(prs).toHaveLength(1)
  })

  it('returns nothing for a task with no pull request', () => {
    expect(taskPullRequests({ associations: [] })).toEqual([])
    expect(taskPullRequests(null)).toEqual([])
  })
})

describe('queueRowFor', () => {
  it('matches a store row by coordinates, case-insensitively', () => {
    const row = { repository: 'TomzxCode/agentic', number: 42 }
    expect(queueRowFor([row], { owner: 'tomzxcode', repo: 'agentic', number: 42 })).toBe(row)
    expect(queueRowFor([row], { owner: 'tomzxcode', repo: 'agentic', number: 7 })).toBeNull()
    expect(queueRowFor([], { owner: 'a', repo: 'b', number: 1 })).toBeNull()
  })
})
