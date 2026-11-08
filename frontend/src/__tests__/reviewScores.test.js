import { describe, expect, it } from 'vitest'
import {
  authorOptions,
  dailyRubricSeries,
  filterRuns,
  formatScore,
  repositoryOptions,
  runsSummary,
  scoreTone
} from '../reviewScores'

function run(overrides = {}) {
  return {
    repository: 'TomzxCode/agentic',
    author: 'alice',
    step: 'review-pr',
    score: 0.5,
    reviewed_at: '2026-11-01T10:00:00Z',
    ...overrides
  }
}

const runs = [
  run(),
  run({ repository: 'acme/api', author: 'bob', score: 1.0 }),
  run({ score: 0.75, reviewed_at: '2026-11-02T10:00:00Z' }),
  run({ step: 'validate-pr', score: 0.25 })
]

describe('reviewScores', () => {
  it('averages a rubric per day and keeps the days with a run', () => {
    const series = dailyRubricSeries(runs)
    const review = series.find((entry) => entry.step === 'review-pr')
    expect(review.points).toEqual([
      { date: '2026-11-01', count: 2, mean: 0.75, min: 0.5, max: 1 },
      { date: '2026-11-02', count: 1, mean: 0.75, min: 0.75, max: 0.75 }
    ])
    expect(review.count).toBe(3)
    expect(review.mean).toBe(0.75)

    const validate = series.find((entry) => entry.step === 'validate-pr')
    expect(validate.points).toEqual([{ date: '2026-11-01', count: 1, mean: 0.25, min: 0.25, max: 0.25 }])
  })

  it('leaves a rubric out of the points when it has no run', () => {
    const series = dailyRubricSeries(runs)
    expect(series.find((entry) => entry.step === 'review-db-changes').points).toEqual([])
    expect(series.find((entry) => entry.step === 'review-db-changes').mean).toBeNull()
  })

  it('filters by repository and author, case-insensitively', () => {
    expect(filterRuns(runs, { repositories: ['tomzxcode/agentic'] })).toHaveLength(3)
    expect(filterRuns(runs, { authors: ['bob'] })).toHaveLength(1)
    expect(filterRuns(runs, { repositories: ['acme/api'], authors: ['alice'] })).toEqual([])
    expect(filterRuns(runs)).toHaveLength(runs.length)
  })

  it('offers the repositories and authors with their run counts', () => {
    expect(repositoryOptions(runs)).toEqual([
      { value: 'acme/api', count: 1 },
      { value: 'TomzxCode/agentic', count: 3 }
    ])
    expect(authorOptions(runs)).toEqual([
      { value: 'alice', count: 3 },
      { value: 'bob', count: 1 }
    ])
  })

  it('summarizes the shown runs', () => {
    expect(runsSummary(runs)).toEqual({
      reviews: 4,
      mean: 0.63,
      first: '2026-11-01',
      last: '2026-11-02'
    })
    expect(runsSummary([])).toEqual({ reviews: 0, mean: null, first: null, last: null })
  })

  it('reads scores in a green, amber, or red tone', () => {
    expect(scoreTone(1)).toBe('ok')
    expect(scoreTone(0.75)).toBe('ok')
    expect(scoreTone(0.5)).toBe('warn')
    expect(scoreTone(0.25)).toBe('danger')
    expect(scoreTone(null)).toBe('')
    expect(formatScore(0.5)).toBe('0.50')
    expect(formatScore(null)).toBe('—')
  })
})
