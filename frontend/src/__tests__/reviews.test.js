import { describe, expect, it } from 'vitest'

import { groupReviewFiles, reviewLabel, stripReportMarker } from '../reviews'

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
