// Helpers for the My PRs page. They are pure so the labels, the attention order,
// and the search are testable without rendering the view or calling the API.

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
