import { describe, expect, it } from 'vitest'

import {
  DEFAULT_AGENT_PROMPTS,
  githubCoordinates,
  parseAgentPrompts,
  resolvePromptTemplate,
  taskPrompts
} from '../prompts'

const prItem = (number = 123) => ({
  id: `i${number}`,
  source: 'github',
  kind: 'pull_request',
  metadata_json: { owner: 'acme', repo: 'api', number }
})

const issueItem = (number = 7) => ({
  id: `i${number}`,
  source: 'github',
  kind: 'issue',
  metadata_json: { owner: 'acme', repo: 'api', number }
})

const task = (items) => ({ id: 't1', associations: items.map((item, index) => ({ id: `a${index}`, item })) })

describe('parseAgentPrompts', () => {
  it('parses the JSON string stored in settings', () => {
    const prompts = parseAgentPrompts(
      JSON.stringify([{ kind: 'pull_request', label: 'Review', template: 'x {number}' }])
    )
    expect(prompts).toEqual([{ kind: 'pull_request', label: 'Review', template: 'x {number}' }])
  })

  it('accepts an already-parsed list', () => {
    expect(parseAgentPrompts(DEFAULT_AGENT_PROMPTS)).toHaveLength(2)
  })

  it('returns an empty list for missing, empty, or malformed values', () => {
    for (const raw of [undefined, null, '', '   ', 'not json', '{}']) {
      expect(parseAgentPrompts(raw)).toEqual([])
    }
  })

  it('drops entries with no template and defaults an unknown kind to issue', () => {
    const prompts = parseAgentPrompts('[{ "kind": "weird", "template": "x" }, { "kind": "issue", "template": "  " }]')
    expect(prompts).toEqual([{ kind: 'issue', label: '', template: 'x' }])
  })
})

describe('githubCoordinates', () => {
  it('reads owner, repository, and number from a GitHub item', () => {
    expect(githubCoordinates(prItem())).toEqual({ kind: 'pull_request', owner: 'acme', repository: 'api', number: 123 })
  })

  it('treats a metadata kind of pull_request as a PR', () => {
    const item = {
      source: 'github',
      kind: 'issue',
      metadata_json: { kind: 'pull_request', owner: 'a', repo: 'b', number: 1 }
    }
    expect(githubCoordinates(item).kind).toBe('pull_request')
  })

  it('is null for non-GitHub items and items without fetched metadata', () => {
    expect(githubCoordinates({ source: 'slack', metadata_json: {} })).toBeNull()
    expect(githubCoordinates({ source: 'github', metadata_json: {} })).toBeNull()
    expect(githubCoordinates(null)).toBeNull()
  })
})

describe('resolvePromptTemplate', () => {
  it('substitutes every placeholder', () => {
    expect(
      resolvePromptTemplate('$review-pr-full {number} {owner}/{repository}', {
        owner: 'acme',
        repository: 'api',
        number: 123
      })
    ).toBe('$review-pr-full 123 acme/api')
  })

  it('tolerates a missing number', () => {
    expect(resolvePromptTemplate('{owner}/{repository}#{number}', { owner: 'a', repository: 'b' })).toBe('a/b#')
  })
})

describe('taskPrompts', () => {
  const prompts = [
    { kind: 'pull_request', label: 'Review PR', template: '$review-pr-full {number} {owner}/{repository}' }
  ]

  it('builds a button when exactly one item of the kind is associated', () => {
    const buttons = taskPrompts(task([prItem()]), prompts)
    expect(buttons).toHaveLength(1)
    expect(buttons[0].label).toBe('Review PR')
    expect(buttons[0].text).toBe('$review-pr-full 123 acme/api')
  })

  it('shows nothing when two items of the kind are associated', () => {
    expect(taskPrompts(task([prItem(1), prItem(2)]), prompts)).toEqual([])
  })

  it('ignores items of the other kind', () => {
    expect(taskPrompts(task([issueItem()]), prompts)).toEqual([])
  })

  it('falls back to the template as the label when none is set', () => {
    const buttons = taskPrompts(task([prItem()]), [{ kind: 'pull_request', label: '', template: '$x {number}' }])
    expect(buttons[0].label).toBe('$x {number}')
  })
})
