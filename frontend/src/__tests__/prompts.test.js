import { describe, expect, it } from 'vitest'

import {
  DEFAULT_AGENT_PROMPTS,
  buildPromptContext,
  githubCoordinates,
  isCommandPrompt,
  itemIdentifier,
  linkedItemVariables,
  linkedPromptItems,
  parseAgentPrompts,
  resolvePromptTemplate,
  taskPrompts,
  taskVariables
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

  it('fills task variables the caller passes in', () => {
    const buttons = taskPrompts(
      task([prItem()]),
      [{ kind: 'pull_request', label: 'Go', template: 'work on {title}' }],
      {
        title: 'Fix login'
      }
    )
    expect(buttons[0].text).toBe('work on Fix login')
  })
})

describe('linkedPromptItems', () => {
  it('keeps one kind and collapses duplicate links', () => {
    const linked = task([issueItem(), issueItem(), prItem()])
    expect(linkedPromptItems(linked, 'issue').map((entry) => entry.coords.number)).toEqual([7])
    expect(linkedPromptItems(linked)).toHaveLength(2)
  })
})

describe('taskVariables', () => {
  const full = {
    id: 't1',
    title: 'Fix login',
    description: 'Users cannot sign in',
    status: 'in_progress',
    priority: 3,
    deadline: '2026-11-01T00:00:00Z',
    tags: ['auth', 'urgent'],
    repository_ids: ['r1'],
    people: [{ name: 'Ada' }],
    requesters: [{ name: 'Bob' }],
    worktrees: [{ status: 'active', path: '/w/t1' }]
  }

  it('fills the task variables', () => {
    const values = taskVariables(full, null, {
      repositories: [{ id: 'r1', path: '/repo/one' }],
      taskUrl: 'http://x/task/t1'
    })
    expect(values).toMatchObject({
      task_id: 't1',
      title: 'Fix login',
      description: 'Users cannot sign in',
      status: 'in_progress',
      priority: 'urgent',
      tags: 'auth, urgent',
      task_url: 'http://x/task/t1',
      people: 'Ada',
      requested_by: 'Bob',
      repositories: '/repo/one',
      worktree: '/w/t1'
    })
  })

  it('fills the item variables from the linked item', () => {
    const values = taskVariables(full, prItem(), { repositories: [] })
    expect(values).toMatchObject({ owner: 'acme', repository: 'api', number: '123', item_url: '' })
  })

  it('leaves absent fields empty', () => {
    const values = taskVariables({ id: 't2', title: 'x' }, null)
    expect(values.status).toBe('')
    expect(values.people).toBe('')
    expect(values.number).toBe('')
  })
})

describe('resolvePromptTemplate', () => {
  it('leaves an unknown placeholder alone', () => {
    expect(resolvePromptTemplate('do {title} with {mystery}', { title: 'X' })).toBe('do X with {mystery}')
  })
})

describe('itemIdentifier', () => {
  it('counts a to z, then aa', () => {
    expect(itemIdentifier(0)).toBe('a')
    expect(itemIdentifier(25)).toBe('z')
    expect(itemIdentifier(26)).toBe('aa')
    expect(itemIdentifier(27)).toBe('ab')
  })
})

describe('linkedItemVariables', () => {
  it('gives each item a short id and its fields', () => {
    const items = [
      { item: { ...prItem(1), url: 'https://x/1', title: 'One' }, coords: githubCoordinates(prItem(1)) },
      { item: { ...issueItem(2), url: 'https://x/2', title: 'Two' }, coords: githubCoordinates(issueItem(2)) }
    ]
    const { variables, labels } = linkedItemVariables(items)
    expect(labels.map((label) => label.prefix)).toEqual(['li.a', 'li.b'])
    expect(variables['li.a']).toBe('acme/api#1')
    expect(variables['li.a.item_url']).toBe('https://x/1')
    expect(variables['li.a.item_title']).toBe('One')
    expect(variables['li.b.number']).toBe('2')
  })

  it('resolves per-item tokens and li.<id>', () => {
    const variables = { 'li.a.item_url': 'https://x/1', 'li.a': 'acme/api#1' }
    expect(resolvePromptTemplate('{li.a.item_url}', variables)).toBe('https://x/1')
    expect(resolvePromptTemplate('review {li.a}', variables)).toBe('review acme/api#1')
  })

  it('leaves an unknown per-item token as it is', () => {
    expect(resolvePromptTemplate('{li.z.number}', { 'li.a.number': '1' })).toBe('{li.z.number}')
  })
})

describe('isCommandPrompt', () => {
  it('matches a $ or / command and nothing else', () => {
    expect(isCommandPrompt('$review-pr-full 1 acme/api')).toBe(true)
    expect(isCommandPrompt('/help')).toBe(true)
    expect(isCommandPrompt('  $skill')).toBe(true)
    expect(isCommandPrompt('review this')).toBe(false)
    expect(isCommandPrompt('')).toBe(false)
  })
})

describe('buildPromptContext', () => {
  it('names the task and the linked item', () => {
    const item = { ...prItem(), url: 'https://github.com/acme/api/pull/123', title: 'Add login' }
    const linked = { id: 't1', title: 'Fix login', status: 'open', priority: 2, repository_ids: ['r1'] }
    const context = buildPromptContext(linked, [{ item, coords: githubCoordinates(item) }], {
      repositories: [{ id: 'r1', path: '/repo/one' }]
    })
    expect(context).toContain('- Task: Fix login (t1)')
    expect(context).toContain('priority high')
    expect(context).toContain('- Repositories: /repo/one')
    expect(context).toContain('- Pull request: https://github.com/acme/api/pull/123 (Add login)')
  })

  it('is empty without a task', () => {
    expect(buildPromptContext(null, [])).toBe('')
  })
})
