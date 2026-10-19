// Grouping, sorting, and labels for the PR-feedback triage view.
//
// The view reads the reviewer-feedback analysis files the skills write to the
// user-global ~/.sdlc store, through the /api/feedback endpoint. Everything
// here is pure: the view hands it the items the endpoint returned, so no
// request is involved and each function is directly testable.

// The section order the analysis cards show; a section the file carries that is
// not listed here still renders, after these.
export const FEEDBACK_SECTIONS = ['Comment', 'Analysis', 'Recommended action', 'Suggested reply', 'Suggested change']

// The colours a recommendation and a decision pill use. The values are design
// tokens, so a pill follows the theme instead of a hardcoded palette.
export const RECOMMENDATION_COLORS = {
  implement: 'var(--ok)',
  reject: 'var(--danger)',
  clarify: 'var(--warn)',
  'no-action': 'var(--faint)'
}

export const DECISION_COLORS = {
  implement: 'var(--ok)',
  decline: 'var(--danger)',
  defer: 'var(--warn)',
  pending: 'var(--faint)'
}

// The decision buttons, in the order the card shows them.
export const DECISIONS = [
  { value: 'implement', label: 'Implement' },
  { value: 'decline', label: 'Decline' },
  { value: 'defer', label: 'Defer' }
]

// A recommendation's colour, or a neutral one for a missing/unrecognized value.
export function recommendationColor(value) {
  return RECOMMENDATION_COLORS[value] || 'var(--faint)'
}

export function decisionColor(value) {
  return DECISION_COLORS[value] || 'var(--faint)'
}

// The sections of an item's body in display order: the named ones first, then
// anything else the file carried.
export function orderedSections(item) {
  const sections = item?.sections || {}
  const named = FEEDBACK_SECTIONS.filter((name) => name in sections)
  const rest = Object.keys(sections).filter((name) => !FEEDBACK_SECTIONS.includes(name))
  return [...named, ...rest].map((name) => ({ name, body: sections[name] }))
}

// The review thread a "Comment" section links to (`[thread](url)`), or "".
export function threadUrl(item) {
  const match = /\[thread\]\((https?:\/\/[^)]+)\)/.exec(item?.sections?.Comment || '')
  return match ? match[1] : ''
}

// The text a card is searched by, lowercased: the fields a typist would reach
// for, plus the PR state and run state that the filters also match.
export function feedbackSearchBlob(item) {
  return [
    item?.title,
    item?.repo,
    item?.pr,
    item?.author,
    item?.kind,
    item?.recommendation,
    item?.state,
    item?.run_state
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

// A group key turned into a stable element id.
export function slugify(value) {
  return (
    'g-' +
    String(value)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
  )
}

// How the list groups, keyed by the group-by select's value. `key` is the group
// a card belongs to; `link` is the URL its heading opens (a PR or a repo), when
// the group names one; `order` pins a known value set to its own order.
export const FEEDBACK_GROUPINGS = {
  pr: {
    title: 'Pull requests',
    key: (item) => (item.repo || '?') + '#' + (item.pr || '?'),
    link: (item) => item.pr_url || null
  },
  repo: {
    title: 'Repositories',
    key: (item) => item.repo || '(none)',
    link: (item) => (item.repo ? 'https://github.com/' + item.repo : null)
  },
  author: { title: 'Authors', key: (item) => item.author || '(none)' },
  recommendation: {
    title: 'Recommendations',
    key: (item) => item.recommendation || '(none)',
    order: ['implement', 'reject', 'clarify', 'no-action']
  },
  status: {
    title: 'Statuses',
    key: (item) => item.status || 'pending',
    order: ['pending', 'implement', 'decline', 'defer']
  },
  kind: { title: 'Comment types', key: (item) => item.kind || '(none)' }
}

const CONFIDENCE_RANK = { high: 0, medium: 1, low: 2 }
const RECOMMENDATION_RANK = { implement: 0, reject: 1, clarify: 2, 'no-action': 3 }

// How the list sorts within a group, keyed by the sort-by select's value.
export const FEEDBACK_SORTS = {
  'date-desc': (a, b) => (b.created_at || '').localeCompare(a.created_at || ''),
  'date-asc': (a, b) => (a.created_at || '').localeCompare(b.created_at || ''),
  title: (a, b) => (a.title || '').localeCompare(b.title || '', undefined, { sensitivity: 'base' }),
  confidence: (a, b) => (CONFIDENCE_RANK[a.confidence] ?? 9) - (CONFIDENCE_RANK[b.confidence] ?? 9),
  recommendation: (a, b) => (RECOMMENDATION_RANK[a.recommendation] ?? 9) - (RECOMMENDATION_RANK[b.recommendation] ?? 9),
  author: (a, b) => (a.author || '').localeCompare(b.author || '', undefined, { sensitivity: 'base' })
}

// Group and sort the items for display. Returns one entry per group, in the
// group's own order (a pinned value set, or numeric-aware alphabetical), each
// with its sorted items, its heading link (when the group names a PR or repo),
// and how many of its items still await a decision.
export function groupFeedback(items, groupBy = 'pr', sortBy = 'date-desc') {
  const grouping = FEEDBACK_GROUPINGS[groupBy] || FEEDBACK_GROUPINGS.pr
  const compare = FEEDBACK_SORTS[sortBy] || FEEDBACK_SORTS['date-desc']

  const buckets = new Map()
  for (const item of items || []) {
    const key = grouping.key(item) || '(none)'
    if (!buckets.has(key)) buckets.set(key, [])
    buckets.get(key).push(item)
  }

  const rank = (value) => {
    const index = grouping.order.indexOf(value)
    return index < 0 ? 99 : index
  }
  const keys = [...buckets.keys()]
  if (grouping.order) keys.sort((a, b) => rank(a) - rank(b))
  else keys.sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }))

  return keys.map((key) => {
    const rows = buckets.get(key).slice().sort(compare)
    return {
      key,
      label: key,
      url: grouping.link ? grouping.link(rows[0]) : null,
      items: rows,
      pending: rows.filter((item) => item.status === 'pending').length
    }
  })
}

// The counts the header shows, over the items currently in view.
export function feedbackCounts(items) {
  const counts = { pending: 0, implement: 0, decline: 0, defer: 0, to_run: 0 }
  for (const item of items || []) {
    counts[item.status] = (counts[item.status] || 0) + 1
    if (item.run_state === 'awaiting') counts.to_run += 1
  }
  return counts
}
