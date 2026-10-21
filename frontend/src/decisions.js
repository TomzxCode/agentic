// Filtering and matrix helpers for the colleague-decisions page.
//
// The page reads the reports the extract-colleague-decisions skill writes
// through /api/decisions. Everything here is pure: the view hands these
// functions the rows the endpoint returned, so no request is involved and each
// function is directly testable.

// The decision buckets a report can name, in the order the chips show them.
export const DECISION_BUCKETS = ['Decided', 'Deferred', 'Open', 'Committed']

// Each bucket's colour. The values are design tokens, so a badge follows the
// theme instead of a hardcoded palette.
export const BUCKET_COLORS = {
  Decided: 'var(--ok)',
  Deferred: 'var(--warn)',
  Open: 'var(--accent-2)',
  Committed: 'var(--accent)'
}

export function bucketColor(bucket) {
  return BUCKET_COLORS[bucket] || 'var(--faint)'
}

// A bucket's rank, so an unknown bucket sorts after the known ones instead of
// breaking the comparison.
function bucketRank(bucket) {
  const index = DECISION_BUCKETS.indexOf(bucket)
  return index < 0 ? DECISION_BUCKETS.length : index
}

function byDateAndBucket(a, b) {
  return (b.date || '').localeCompare(a.date || '') || bucketRank(a.bucket) - bucketRank(b.bucket)
}

// The text a decision is searched by, lowercased: every field the card shows.
export function decisionSearchBlob(decision) {
  return [
    decision?.text,
    decision?.author,
    decision?.bucket,
    decision?.date,
    ...(decision?.supported_by || []),
    ...(decision?.opposed_by || [])
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

// Keep the decisions matching the search text, the date range, and (when any
// are selected) the buckets. Dates are ISO strings, so a string comparison is
// the same as a date comparison.
export function filterDecisions(decisions, { q = '', from = '', to = '', buckets = [] } = {}) {
  const needle = String(q || '')
    .trim()
    .toLowerCase()
  const selected = new Set(buckets || [])
  return (decisions || []).filter((decision) => {
    const date = decision?.date || ''
    if (from && date < from) return false
    if (to && date > to) return false
    if (selected.size && !selected.has(decision?.bucket)) return false
    if (needle && !decisionSearchBlob(decision).includes(needle)) return false
    return true
  })
}

// The row counts the header and the status chips show.
export function decisionCounts(decisions) {
  const buckets = {}
  const people = new Set()
  const supporters = new Set()
  const opponents = new Set()
  for (const decision of decisions || []) {
    buckets[decision.bucket] = (buckets[decision.bucket] || 0) + 1
    if (decision.author) people.add(decision.author)
    for (const name of decision.supported_by || []) supporters.add(name)
    for (const name of decision.opposed_by || []) opponents.add(name)
  }
  return {
    total: (decisions || []).length,
    people: people.size,
    supporters: supporters.size,
    opponents: opponents.size,
    buckets
  }
}

// Group the decisions by their author, or by who supported or opposed them.
// Groups lead with the person involved in the most decisions; each group's
// decisions lead with the newest.
export function groupDecisions(decisions, field = 'author') {
  const groups = new Map()
  for (const decision of decisions || []) {
    const names = field === 'author' ? [decision.author] : decision[field] || []
    for (const name of new Set(names)) {
      if (!name) continue
      if (!groups.has(name)) groups.set(name, [])
      groups.get(name).push(decision)
    }
  }
  const rank = (name) => groups.get(name)?.length || 0
  return [...groups.entries()]
    .sort((a, b) => rank(b[0]) - rank(a[0]) || a[0].localeCompare(b[0]))
    .map(([name, items]) => ({ name, items: items.slice().sort(byDateAndBucket) }))
}

// A person's direction in the matrix: support or opposition.
export function matrixRelation(mode = 'support') {
  const oppose = mode === 'oppose'
  return {
    mode: oppose ? 'oppose' : 'support',
    field: oppose ? 'opposed_by' : 'supported_by',
    noun: oppose ? 'opponent' : 'supporter',
    pct: oppose ? 'Opposed' : 'Supported',
    verb: oppose ? 'opposed by' : 'supported by'
  }
}

// The authors-by-people matrix for one mode. Each row is a decision author with
// their total, their share of decisions with at least one relation (the pct
// cell), the total they received, and one cell per person. The diagonal is the
// author's own decisions, so it is not double-counted in `received`.
export function decisionMatrix(decisions, mode = 'support') {
  const relation = matrixRelation(mode)
  const rows = decisions || []
  const authors = [...new Set(rows.map((decision) => decision.author).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b)
  )
  const people = [
    ...new Set([...authors, ...rows.flatMap((decision) => decision[relation.field] || []).filter(Boolean)])
  ].sort((a, b) => a.localeCompare(b))

  const made = new Map()
  const engaged = new Map()
  const counts = new Map()
  for (const decision of rows) {
    made.set(decision.author, (made.get(decision.author) || 0) + 1)
    const related = decision[relation.field] || []
    if (related.length) engaged.set(decision.author, (engaged.get(decision.author) || 0) + 1)
    for (const name of new Set(related)) {
      const key = decision.author + '\u0000' + name
      counts.set(key, (counts.get(key) || 0) + 1)
    }
  }

  return {
    ...relation,
    authors,
    people,
    rows: authors.map((author) => {
      const total = made.get(author) || 0
      let received = 0
      const cells = people.map((person) => {
        if (person === author) return { person, diagonal: true, count: total, pct: total ? 100 : 0 }
        const count = counts.get(author + '\u0000' + person) || 0
        received += count
        return { person, diagonal: false, count, pct: total ? Math.round((count / total) * 100) : 0 }
      })
      const withRelation = engaged.get(author) || 0
      return {
        author,
        total,
        received,
        pct: total ? Math.round((withRelation / total) * 100) : 0,
        cells
      }
    })
  }
}

// The decisions behind one matrix cell: the author's own decisions on the
// diagonal, or the decisions they made that the column's person supported or
// opposed.
export function cellDecisions(decisions, cell, mode = 'support') {
  if (!cell) return []
  const relation = matrixRelation(mode)
  return (decisions || [])
    .filter((decision) => decision.author === cell.author)
    .filter((decision) => cell.diagonal || (decision[relation.field] || []).includes(cell.person))
    .sort(byDateAndBucket)
}

// The matrix's percentage cell colour: red at no engagement through green at
// full engagement.
export function pctColor(pct) {
  const hue = Math.round((Math.max(0, Math.min(100, Number(pct) || 0)) / 100) * 120)
  return `hsl(${hue}, 65%, 48%)`
}

// A name turned into a stable element id.
export function nameSlug(name) {
  return (
    'person-' +
    String(name || '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
  )
}

// Shift an ISO date by a number of days, for the date presets.
export function shiftDays(date, days) {
  if (!date) return ''
  const moment = new Date(date + 'T00:00:00Z')
  moment.setUTCDate(moment.getUTCDate() + days)
  return moment.toISOString().slice(0, 10)
}
