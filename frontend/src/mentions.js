import { sourceLabel } from './store'

// An `@` mention starts at the beginning of the text or after whitespace or
// opening punctuation, so an email address (or a handle in the middle of a
// word) never opens the picker.
const TRIGGER_BEFORE = /[\s([{"'“‘>]/
// A name is short; a longer run after `@` is prose, not a mention being typed.
const MAX_QUERY = 60
// How many of each kind the picker offers. People and items are shown as two
// groups, so one kind never crowds out the other.
const PER_KIND = 5

// The mention being typed at the caret, or null. `query` is the text between
// the `@` and the caret; it may contain spaces so a full name can be matched.
export function findMentionQuery(text, caret) {
  const value = String(text ?? '')
  const position = typeof caret === 'number' ? caret : value.length
  const before = value.slice(0, position)
  const at = before.lastIndexOf('@')
  if (at < 0) return null
  if (at > 0 && !TRIGGER_BEFORE.test(before[at - 1])) return null
  const query = before.slice(at + 1)
  if (query.length > MAX_QUERY) return null
  // A newline, a second @, or Markdown link punctuation ends the mention. A
  // leading space means the user is writing prose (or an email), not naming
  // someone.
  if (/[\n\r@[\]()/]/.test(query)) return null
  if (/^\s/.test(query)) return null
  return { start: at, end: position, query }
}

function includes(haystack, needle) {
  return String(haystack || '')
    .toLowerCase()
    .includes(needle)
}

function startsWith(haystack, needle) {
  return String(haystack || '')
    .toLowerCase()
    .startsWith(needle)
}

// Closest matches first: a prefix match beats a match in the middle, a short
// label beats a long one, and ties sort alphabetically.
function compareMatches(a, b, query) {
  const aPrefix = startsWith(a.label, query) ? 0 : 1
  const bPrefix = startsWith(b.label, query) ? 0 : 1
  if (aPrefix !== bPrefix) return aPrefix - bPrefix
  if (a.label.length !== b.label.length) return a.label.length - b.label.length
  return a.label.localeCompare(b.label, undefined, { sensitivity: 'base' })
}

function personDetail(person) {
  const alias = (person.aliases || []).find(Boolean)
  if (!alias) return ''
  return alias.includes('@') ? alias : `@${alias}`
}

function itemDetail(item) {
  const source = sourceLabel(item.source)
  const number = item?.metadata_json?.number
  return number ? `${source} #${number}` : source
}

function isNote(item) {
  // A note is prose kept with the task, not a thing to point at; its "title"
  // is derived from its body, which would make a useless reference.
  return item?.source === 'note'
}

// The people and items the picker offers for `query`, people first. Matching
// is case-insensitive over a person's name and aliases, and an item's title
// and URL.
export function buildMentionOptions({ people = [], items = [], query = '', perKind = PER_KIND } = {}) {
  const needle = String(query || '')
    .trim()
    .toLowerCase()

  const peopleMatches = []
  for (const person of people) {
    const label = person?.name || 'Unnamed person'
    const aliases = person?.aliases || []
    if (needle && !includes(label, needle) && !aliases.some((alias) => includes(alias, needle))) continue
    peopleMatches.push({ kind: 'person', id: person.id, label, detail: personDetail(person) })
  }
  peopleMatches.sort((a, b) => compareMatches(a, b, needle))

  const itemMatches = []
  for (const item of items) {
    if (isNote(item)) continue
    const label = item?.title || item?.url || 'Untitled item'
    if (needle && !includes(label, needle) && !includes(item?.url, needle)) continue
    itemMatches.push({ kind: 'item', id: item.id, label, detail: itemDetail(item) })
  }
  itemMatches.sort((a, b) => compareMatches(a, b, needle))

  return [...peopleMatches.slice(0, perKind), ...itemMatches.slice(0, perKind)]
}

// A person or item reference as it is written into a field. It is plain text
// (`@name`), the same way a person would type it: the field stores what the
// editor shows, and the renderer links the reference when it displays it.
export function mentionText(option) {
  return `@${option.label}`
}

// A saved link from an earlier build (or a hand-written one) is edited as its
// plain `@name` again, so opening a field never shows raw link syntax.
const MENTION_LINK = /\[@((?:\\.|[^\]\\])*)\]\(\/(?:person|items)\/[^)\s]+\)/g

export function decodeMentionLinks(text) {
  return String(text ?? '').replace(MENTION_LINK, (_, label) => `@${label.replace(/\\([\\[\]<>])/g, '$1')}`)
}

// Replace the `@query` being typed with the chosen reference, leaving the
// caret after it so writing can continue.
export function applyMention(text, token, option) {
  const value = String(text ?? '')
  const inserted = mentionText(option)
  const rest = value.slice(token.end)
  // Continue on the same line: separate the reference from the next word, but
  // not from whitespace or punctuation the user already typed.
  const spacer = rest && (/^\s/.test(rest) || /^[.,;:!?)\]]/.test(rest)) ? '' : ' '
  const next = value.slice(0, token.start) + inserted + spacer + rest
  return { value: next, caret: token.start + inserted.length + spacer.length }
}

// The references a rendered Markdown source can resolve: one entry per exact
// name, longest first so "Ada Lovelace" wins over a shorter "Ada". A name that
// points at two different entities is left unlinked rather than guessing.
export function mentionTargets({ people = [], items = [] } = {}) {
  const byName = new Map()
  const add = (name, href) => {
    const label = String(name || '').trim()
    if (!label) return
    const seen = byName.get(label)
    if (seen && seen.href !== href) {
      // Ambiguous: forget the name instead of linking the wrong entity.
      byName.set(label, null)
      return
    }
    byName.set(label, { name: label, href })
  }
  for (const person of people) add(person?.name, `/person/${person.id}`)
  for (const item of items) {
    if (isNote(item)) continue
    add(item?.title, `/items/${item.id}`)
  }
  return [...byName.values()]
    .filter(Boolean)
    .sort((a, b) => b.name.length - a.name.length || a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))
}
