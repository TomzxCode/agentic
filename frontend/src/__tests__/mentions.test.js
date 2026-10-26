import { describe, expect, it } from 'vitest'
import {
  applyMention,
  buildDateMentionOptions,
  buildMentionOptions,
  decodeMentionLinks,
  findMentionQuery,
  mentionTargets,
  mentionText
} from '../mentions'

const people = [
  { id: 'p1', name: 'Ada Lovelace', aliases: ['ada', 'ada@example.com'] },
  { id: 'p2', name: 'Grace Hopper', aliases: ['grace'] }
]
const items = [
  { id: 'i1', source: 'github', kind: 'issue', title: 'Fix login timeout', metadata_json: { number: 42 } },
  { id: 'i2', source: 'slack', kind: 'thread', title: 'Checkout incident' },
  { id: 'i3', source: 'note', kind: '', title: 'a note body' }
]

describe('findMentionQuery', () => {
  it('finds a mention at the start of the field', () => {
    expect(findMentionQuery('@ad', 3)).toEqual({ start: 0, end: 3, query: 'ad' })
  })

  it('finds a mention after whitespace or opening punctuation', () => {
    expect(findMentionQuery('ask @gr', 7)).toEqual({ start: 4, end: 7, query: 'gr' })
    expect(findMentionQuery('(@gr', 4)).toEqual({ start: 1, end: 4, query: 'gr' })
  })

  it('keeps spaces inside the query so a full name can be matched', () => {
    expect(findMentionQuery('ask @Ada Lov', 12)).toEqual({ start: 4, end: 12, query: 'Ada Lov' })
  })

  it('does not trigger inside a word, such as an email address', () => {
    expect(findMentionQuery('ada@example.com', 15)).toBeNull()
  })

  it('stops at a newline or a second @', () => {
    expect(findMentionQuery('@Ada\nmore', 9)).toBeNull()
    expect(findMentionQuery('@a@b', 4)).toBeNull()
  })

  it('ignores the @ inside an inserted mention link', () => {
    const value = 'thanks [@Ada Lovelace](/person/p1) '
    expect(findMentionQuery(value, value.length)).toBeNull()
  })

  it('does not trigger on a space right after the @', () => {
    expect(findMentionQuery('@ ok', 4)).toBeNull()
  })
})

describe('buildMentionOptions', () => {
  it('offers people before items, skipping notes', () => {
    const options = buildMentionOptions({ people, items })
    expect(options.map((option) => option.id)).toEqual(['p1', 'p2', 'i2', 'i1'])
  })

  it('matches an item by title and reports its source', () => {
    const options = buildMentionOptions({ people, items, query: 'login' })
    expect(options).toHaveLength(1)
    expect(options[0]).toMatchObject({ kind: 'item', id: 'i1', label: 'Fix login timeout', detail: 'GitHub #42' })
  })

  it('matches a person by alias', () => {
    const options = buildMentionOptions({ people, items, query: 'ada@' })
    expect(options.map((option) => option.id)).toEqual(['p1'])
  })

  it('offers dates before people and items for a date query', () => {
    const options = buildMentionOptions({ people, items, query: 'last', now: new Date(2026, 9, 26) })
    expect(options.slice(0, 3).map((option) => option.kind)).toEqual(['date', 'date', 'date'])
  })

  it('puts prefix matches before matches in the middle', () => {
    const list = [
      { id: 'p1', name: 'The Ada fan club', aliases: [] },
      { id: 'p2', name: 'Ada Lovelace', aliases: [] }
    ]
    const options = buildMentionOptions({ people: list, items: [], query: 'ada' })
    expect(options.map((option) => option.id)).toEqual(['p2', 'p1'])
  })
})

describe('buildDateMentionOptions', () => {
  // Monday, 26 October 2026, in the reader's own zone.
  const now = new Date(2026, 9, 26)
  const values = (query, at = now) => buildDateMentionOptions(query, at).map((option) => [option.label, option.value])

  it('offers the units when only last or next is typed', () => {
    expect(values('last')).toEqual([
      ['last week', '2026-10-19'],
      ['last month', '2026-09-26'],
      ['last year', '2025-10-26']
    ])
    expect(values('next')).toEqual([
      ['next week', '2026-11-02'],
      ['next month', '2026-11-26'],
      ['next year', '2027-10-26']
    ])
  })

  it('resolves a weekday to the nearest one before or after today', () => {
    expect(values('last Thursday')).toEqual([['last Thursday', '2026-10-22']])
    expect(values('next Thursday')).toEqual([['next Thursday', '2026-10-29']])
  })

  it('treats the same weekday as a week away', () => {
    expect(values('last Monday')).toEqual([['last Monday', '2026-10-19']])
    expect(values('next Monday')).toEqual([['next Monday', '2026-11-02']])
  })

  it('accepts abbreviations and filters as the weekday is typed', () => {
    expect(values('last t')).toEqual([
      ['last Tuesday', '2026-10-20'],
      ['last Thursday', '2026-10-22']
    ])
    expect(values('last thurs')).toEqual([['last Thursday', '2026-10-22']])
    expect(values('next fri')).toEqual([['next Friday', '2026-10-30']])
  })

  it('offers a matching unit alongside a matching weekday', () => {
    expect(values('next w')).toEqual([
      ['next week', '2026-11-02'],
      ['next Wednesday', '2026-10-28']
    ])
  })

  it('clamps the day when the target month is shorter', () => {
    expect(values('next month', new Date(2026, 0, 31))).toEqual([['next month', '2026-02-28']])
    expect(values('last month', new Date(2026, 2, 31))).toEqual([['last month', '2026-02-28']])
    expect(values('next year', new Date(2024, 1, 29))).toEqual([['next year', '2025-02-28']])
  })

  it('ignores text that is not a last or next phrase', () => {
    expect(buildDateMentionOptions('la', now)).toEqual([])
    expect(buildDateMentionOptions('previous week', now)).toEqual([])
    expect(buildDateMentionOptions('', now)).toEqual([])
  })
})

describe('mentionText and applyMention', () => {
  it('writes a plain @ name for a person or an item', () => {
    expect(mentionText({ kind: 'person', id: 'p1', label: 'Ada Lovelace' })).toBe('@Ada Lovelace')
    expect(mentionText({ kind: 'item', id: 'i1', label: 'Fix login timeout' })).toBe('@Fix login timeout')
  })

  it('writes a date as its value, not the typed phrase', () => {
    expect(mentionText({ kind: 'date', id: 'last-thursday', label: 'last Thursday', value: '2026-10-22' })).toBe(
      '2026-10-22'
    )
  })

  it('replaces the typed query and leaves the caret after the mention', () => {
    const token = { start: 4, end: 7, query: 'ad' }
    const result = applyMention('ask @ad please', token, { kind: 'person', id: 'p1', label: 'Ada' })
    // The space the user already typed after the query is kept.
    expect(result.value).toBe('ask @Ada please')
    expect(result.caret).toBe('ask @Ada'.length)
  })

  it('adds a space when the mention ends the value', () => {
    const result = applyMention('@ad', { start: 0, end: 3 }, { kind: 'person', id: 'p1', label: 'Ada' })
    expect(result.value).toBe('@Ada ')
    expect(result.caret).toBe(result.value.length)
  })

  it('replaces a date phrase with the date', () => {
    const result = applyMention(
      'due @last week',
      { start: 4, end: 14, query: 'last week' },
      {
        kind: 'date',
        id: 'last-week',
        label: 'last week',
        value: '2026-10-19'
      }
    )
    expect(result.value).toBe('due 2026-10-19 ')
    expect(result.caret).toBe(result.value.length)
  })
})

describe('decodeMentionLinks', () => {
  it('edits a saved person or item link as its plain @ name', () => {
    expect(decodeMentionLinks('ask [@Ada Lovelace](/person/p1) about [@Fix login](/items/i1)')).toBe(
      'ask @Ada Lovelace about @Fix login'
    )
  })

  it('unescapes a label that carried brackets', () => {
    expect(decodeMentionLinks('[@A \\[B\\]](/person/p1)')).toBe('@A [B]')
  })

  it('leaves other links alone', () => {
    expect(decodeMentionLinks('[docs](https://example.com)')).toBe('[docs](https://example.com)')
  })
})

describe('mentionTargets', () => {
  it('maps names to their person and item pages, longest first', () => {
    const targets = mentionTargets({ people, items })
    expect(targets).toEqual([
      { name: 'Checkout incident', href: '/items/i2' },
      { name: 'Fix login timeout', href: '/items/i1' },
      { name: 'Ada Lovelace', href: '/person/p1' },
      { name: 'Grace Hopper', href: '/person/p2' }
    ])
  })

  it('leaves notes out', () => {
    const names = mentionTargets({ people, items }).map((target) => target.name)
    expect(names).not.toContain('a note body')
  })

  it('leaves an ambiguous name unlinked', () => {
    const targets = mentionTargets({
      people: [
        { id: 'p1', name: 'Sam' },
        { id: 'p2', name: 'Sam' }
      ]
    })
    expect(targets).toEqual([])
  })
})
