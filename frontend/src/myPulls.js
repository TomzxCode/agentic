// Helpers for the My PRs page. They are pure so the labels, the attention order,
// the grouping, and the search are testable without rendering the view or
// calling the API.

// The API reports a pull request's head-commit check rollup as one of these.
export const CI_LABELS = { success: 'Passing', pending: 'Running', failure: 'Failing', none: 'No checks' }
export const CI_TONES = { success: 'ok', pending: 'warn', failure: 'danger', none: '' }

// GitHub's review decision: APPROVED once the reviews the branch requires are
// in, CHANGES_REQUESTED when someone asked for changes, REVIEW_REQUIRED while a
// required review is still missing. A pull request GitHub decided nothing about
// carries no decision at all.
export const REVIEW_LABELS = {
  APPROVED: 'Approved',
  CHANGES_REQUESTED: 'Changes requested',
  REVIEW_REQUIRED: 'Review required'
}
export const REVIEW_TONES = { APPROVED: 'ok', CHANGES_REQUESTED: 'danger', REVIEW_REQUIRED: 'warn' }

// How the list can be split into sections. "None" is the flat list; every other
// value gives one section per distinct value of that facet.
export const PULL_GROUPINGS = [
  { value: '', label: 'None' },
  { value: 'repository', label: 'Repository' },
  { value: 'ci', label: 'CI status' },
  { value: 'review', label: 'Review status' }
]

// The order the state groupings present, the states that need the author first:
// failing checks before running ones, requested changes before an approval, and
// the pull requests GitHub decided nothing about last.
const CI_ORDER = ['failure', 'pending', 'success', 'none']
const REVIEW_ORDER = ['CHANGES_REQUESTED', 'REVIEW_REQUIRED', 'APPROVED', '']

export function ciLabel(pull) {
  return CI_LABELS[pull.ci] || 'Unknown'
}

export function ciTone(pull) {
  return CI_TONES[pull.ci] || ''
}

export function reviewLabel(pull) {
  return REVIEW_LABELS[pull.review_decision] || 'No review'
}

export function reviewTone(pull) {
  return REVIEW_TONES[pull.review_decision] || ''
}

// How much a pull request needs its author to act, lowest first: failing checks,
// then requested changes, then unresolved threads, then checks still running,
// then a required review not yet given, then an approval, then the rest. The
// list is sorted by this, so what needs work is at the top.
export function attentionRank(pull) {
  if (pull.ci === 'failure') return 0
  if (pull.review_decision === 'CHANGES_REQUESTED') return 1
  if (Number(pull.open_threads) > 0) return 2
  if (pull.ci === 'pending') return 3
  if (pull.review_decision === 'REVIEW_REQUIRED') return 4
  if (pull.approved) return 5
  return 6
}

// The pull requests that need the author: failing checks, requested changes, or
// an open thread. The other states are waiting on someone else.
export function needsAttention(pull) {
  return attentionRank(pull) <= 2
}

// The list in display order: what needs attention first, then newest update.
// ISO timestamps compare as strings, so no date parsing is needed.
export function sortPulls(pulls) {
  return [...pulls].sort((a, b) => {
    const rank = attentionRank(a) - attentionRank(b)
    if (rank !== 0) return rank
    return String(b.updated_at || '').localeCompare(String(a.updated_at || ''))
  })
}

// The pull requests split into sections for the chosen grouping, each keeping the
// order it was handed (so what needs attention still leads inside a section). A
// pull request belongs to exactly one section, and only non-empty sections are
// returned. A state section carries the tone for its badge; a repository section
// is a plain heading. With no grouping the whole list comes back as one unlabeled
// section.
export function groupPulls(pulls, groupBy) {
  const list = [...(pulls || [])]
  if (!groupBy) return [{ key: '', label: null, tone: '', badge: false, pulls: list }]

  if (groupBy === 'ci') {
    return CI_ORDER.map((ci) => ({
      key: ci || 'none',
      label: CI_LABELS[ci] || 'Unknown',
      tone: CI_TONES[ci] || '',
      badge: true,
      pulls: list.filter((pull) => (pull.ci || 'none') === ci)
    })).filter((group) => group.pulls.length)
  }

  if (groupBy === 'review') {
    return REVIEW_ORDER.map((decision) => ({
      key: decision || 'none',
      label: REVIEW_LABELS[decision] || 'No review',
      tone: REVIEW_TONES[decision] || '',
      badge: true,
      pulls: list.filter((pull) => (pull.review_decision || '') === decision)
    })).filter((group) => group.pulls.length)
  }

  if (groupBy === 'repository') {
    // Buckets keyed case-insensitively, so one repository never splits in two on
    // a casing difference, and labelled with the first spelling seen.
    const buckets = new Map()
    for (const pull of list) {
      const repository = pull.repository || ''
      const key = repository.toLowerCase()
      if (!buckets.has(key)) {
        buckets.set(key, { key, label: repository || 'Unknown repository', tone: '', badge: false, pulls: [] })
      }
      buckets.get(key).pulls.push(pull)
    }
    return [...buckets.values()].sort((a, b) => a.label.localeCompare(b.label))
  }

  return [{ key: '', label: null, tone: '', badge: false, pulls: list }]
}

// Whether a pull request matches a free-text search over the fields the row
// shows: repository, number, title, and approvers.
export function matchesPullSearch(pull, query) {
  const text = String(query || '')
    .trim()
    .toLowerCase()
  if (!text) return true
  const blob = [
    pull.repository,
    pull.number,
    pull.number ? `#${pull.number}` : '',
    pull.title,
    ...(pull.approvers || [])
  ]
    .filter((value) => value !== null && value !== undefined && value !== '')
    .join(' ')
    .toLowerCase()
  return blob.includes(text)
}

// The header's totals over every pull request, not just the filtered ones, so
// the header describes the whole list.
export function pullCounts(pulls) {
  return {
    total: pulls.length,
    attention: pulls.filter(needsAttention).length,
    approved: pulls.filter((pull) => pull.approved).length,
    openThreads: pulls.reduce((sum, pull) => sum + (Number(pull.open_threads) || 0), 0)
  }
}
