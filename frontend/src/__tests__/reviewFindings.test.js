import { describe, expect, it } from 'vitest'

import { buildFindingsPrompt, defaultSelectedFindings, findingKey, findingsBySeverity } from '../reviewFindings'

const finding = (over = {}) => ({
  step: 'review-pr',
  title: 'Fix the thing',
  description: 'It is broken.',
  severity: 'must',
  status: 'open',
  sha: 'abc1234',
  ...over
})

describe('findingKey', () => {
  it('identifies a finding by its skill and title', () => {
    expect(findingKey(finding())).toBe('review-pr:Fix the thing')
  })
})

describe('findingsBySeverity', () => {
  it('groups findings in must, should, may order and drops empty severities', () => {
    const groups = findingsBySeverity([
      finding({ title: 'b', severity: 'should' }),
      finding({ title: 'a', severity: 'must' }),
      finding({ title: 'c', severity: 'should' })
    ])
    expect(groups.map((group) => group.value)).toEqual(['must', 'should'])
    expect(groups[0].findings.map((f) => f.title)).toEqual(['a'])
    expect(groups[1].findings.map((f) => f.title)).toEqual(['b', 'c'])
  })

  it('returns nothing for no findings', () => {
    expect(findingsBySeverity([])).toEqual([])
    expect(findingsBySeverity(undefined)).toEqual([])
  })
})

describe('defaultSelectedFindings', () => {
  it('selects the open must and should items, not may or resolved ones', () => {
    const selected = defaultSelectedFindings([
      finding({ title: 'must-open', severity: 'must', status: 'open' }),
      finding({ title: 'should-open', severity: 'should', status: 'open' }),
      finding({ title: 'may-open', severity: 'may', status: 'open' }),
      finding({ title: 'must-done', severity: 'must', status: 'addressed' }),
      finding({ title: 'criterion-fails', severity: 'should', status: 'fails' })
    ])
    expect(selected).toEqual(['review-pr:must-open', 'review-pr:should-open', 'review-pr:criterion-fails'])
  })
})

describe('buildFindingsPrompt', () => {
  it('addresses the PR and groups the findings by severity', () => {
    const prompt = buildFindingsPrompt({ repository: 'acme/api', number: 42 }, [
      finding({ title: 'Fix the thing', description: 'It is broken.', severity: 'must' }),
      finding({ title: 'Tidy the helper', description: '', severity: 'may' })
    ])
    expect(prompt).toContain('pull request acme/api#42')
    expect(prompt).toContain('## MUST')
    expect(prompt).toContain('### Fix the thing _(review-pr)_')
    expect(prompt).toContain('It is broken.')
    expect(prompt).toContain('## MAY')
    expect(prompt).toContain('Tidy the helper')
  })

  it('builds the repository from owner and repo when the row has none', () => {
    const prompt = buildFindingsPrompt({ owner: 'acme', repo: 'api', number: 7 }, [finding()])
    expect(prompt).toContain('pull request acme/api#7')
  })
})
