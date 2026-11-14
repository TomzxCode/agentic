// Helpers for the My PRs page. They are pure so the labels, the attention order,
// the grouping, and the search are testable without rendering the view or
// calling the API.

// The API reports a pull request's head-commit check rollup as one of these.
export const CI_LABELS = { success: 'Passing', pending: 'Running', failure: 'Failing', none: 'No checks' }
export const CI_TONES = { success: 'ok', pending: 'warn', failure: 'danger', none: '' }

// The four states a pull request can be in, as the status badge reads it. ghx
// reports OPEN / MERGED / CLOSED and a draft PR separately, so an open draft
// reads as "draft".
export const PULL_STATUS_LABELS = { open: 'Open', draft: 'Draft', merged: 'Merged', closed: 'Closed' }

export function pullStatus(pull) {
  const state = String(pull?.state || '').toUpperCase()
  if (state === 'MERGED') return 'merged'
  if (state === 'CLOSED') return 'closed'
  return pull?.draft ? 'draft' : 'open'
}

export function pullStatusLabel(pull) {
  return PULL_STATUS_LABELS[pullStatus(pull)] || 'Open'
}

// GitHub's merge state, as the Ready cell explains it. CLEAN is the only state
// in which merging does not wait on something.
export const MERGE_STATE_LABELS = {
  CLEAN: 'Ready to merge',
  BLOCKED: 'Blocked by required reviews or checks',
  BEHIND: 'Behind its base branch',
  DIRTY: 'Has merge conflicts',
  DRAFT: 'Draft',
  HAS_HOOKS: 'Waiting on a pre-receive hook',
  UNSTABLE: 'Checks failing or still running',
  UNKNOWN: 'GitHub has not computed mergeability yet'
}

// Whether the branches conflict. GitHub's mergeability is the source; the merge
// state covers a read that only carried that. Null when neither is known.
export function hasMergeConflicts(pull) {
  if (pull?.mergeable === false || pull?.merge_state === 'DIRTY') return true
  if (pull?.mergeable === true) return false
  if (pull?.merge_state) return false
  return null
}

// The Conflicts cell: "none" when the branches merge cleanly, "conflicts" when
// they do not, and a dash when GitHub's mergeability could not be read.
export function conflictsLabel(pull) {
  const conflicts = hasMergeConflicts(pull)
  if (conflicts === null) return '—'
  return conflicts ? 'conflicts' : 'none'
}

export function conflictsTone(pull) {
  const conflicts = hasMergeConflicts(pull)
  if (conflicts === null) return 'faint'
  return conflicts ? 'danger' : 'ok'
}

// The badge class for a pull request's status, matching the item badges.
export function pullStatusClass(pull) {
  return `st-${pullStatus(pull)}`
}

// Whether the head commit's checks pass. No checks at all counts as passing,
// since nothing blocks the merge.
export function checksPassing(pull) {
  return !pull?.ci || pull.ci === 'success' || pull.ci === 'none'
}

// Whether a person, not just a team, is reviewing the pull request: a pending
// request naming a user, or a review someone already submitted.
export function hasIndividualReviewer(pull) {
  return Boolean((pull?.requested_users || []).length || (pull?.approvers || []).length)
}

// The individual logins a review is still requested from, or the approvers when
// nobody is left to review, so the Reviewers cell names the people involved.
export function assignedReviewers(pull) {
  const waiting = pull?.requested_users || []
  if (waiting.length) return waiting
  return pull?.approvers || []
}

// Whether the pull request is ready to merge right now, as the API computed it.
export function isReadyToMerge(pull) {
  return Boolean(pull?.ready_to_merge)
}

// Why the Ready cell reads the way it does, for its tooltip.
export function readyToMergeTitle(pull) {
  if (pull?.ready_to_merge) return 'GitHub reports this pull request is ready to merge'
  const status = pullStatus(pull)
  if (status === 'merged') return 'Already merged'
  if (status === 'closed') return 'Closed without merging'
  if (status === 'draft') return 'Draft: mark it ready for review first'
  if (hasMergeConflicts(pull) === true) return 'The branches have merge conflicts'
  const reason = MERGE_STATE_LABELS[pull?.merge_state]
  if (reason) return reason
  const missing = []
  if (!pull?.approved) missing.push('an approved review')
  if (!checksPassing(pull)) missing.push('passing checks')
  if (Number(pull?.open_threads) > 0) missing.push('no open review comments')
  if (!hasIndividualReviewer(pull)) missing.push('an assigned reviewer')
  return missing.length ? `Waiting on ${missing.join(', ')}` : 'Not ready to merge'
}

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

// The filters over the list. Each facet has one active value, and its "Any"
// option (an empty value) keeps every pull request.
export const CI_FILTERS = [
  { value: '', label: 'Any' },
  { value: 'failure', label: 'Failing' },
  { value: 'pending', label: 'Running' },
  { value: 'success', label: 'Passing' },
  { value: 'none', label: 'No checks' }
]

export const REVIEW_FILTERS = [
  { value: '', label: 'Any' },
  { value: 'CHANGES_REQUESTED', label: 'Changes requested' },
  { value: 'REVIEW_REQUIRED', label: 'Review required' },
  { value: 'APPROVED', label: 'Approved' },
  { value: 'none', label: 'No review' }
]

export const THREAD_FILTERS = [
  { value: '', label: 'Any' },
  { value: 'open', label: 'Open' },
  { value: 'none', label: 'None open' }
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

// One check behind a pull request's CI badge, as the checks popover labels it.
// Its state uses the same success / pending / failure vocabulary as the rollup.
export const CHECK_LABELS = { success: 'Passed', pending: 'Running', failure: 'Failed' }
export const CHECK_TONES = { success: 'ok', pending: 'warn', failure: 'danger' }
const CHECK_ORDER = ['failure', 'pending', 'success']

export function checkLabel(check) {
  return CHECK_LABELS[check.state] || 'Unknown'
}

export function checkTone(check) {
  return CHECK_TONES[check.state] || ''
}

// The checks in the order that answers "what is failing" first, keeping the read
// order within a state.
export function sortChecks(checks) {
  const rank = (check) => {
    const index = CHECK_ORDER.indexOf(check.state)
    return index === -1 ? CHECK_ORDER.length : index
  }
  return [...(checks || [])].sort((a, b) => rank(a) - rank(b))
}

export function checkCounts(checks) {
  const counts = { failure: 0, pending: 0, success: 0, total: 0 }
  for (const check of checks || []) {
    if (Object.hasOwn(counts, check.state)) counts[check.state] += 1
    counts.total += 1
  }
  return counts
}

// The popover's one-line summary, naming only the states present: "2 failing ·
// 1 running · 8 passed". An empty list reads as nothing rather than as zeroes.
export function checksSummary(checks) {
  const counts = checkCounts(checks)
  const parts = []
  if (counts.failure) parts.push(`${counts.failure} failing`)
  if (counts.pending) parts.push(`${counts.pending} running`)
  if (counts.success) parts.push(`${counts.success} passed`)
  return parts.join(' · ')
}

// The state behind a pull request's rank, and the words its indicator's tooltip
// shows. All seven ranks are covered, from the work the author owes (failing
// checks, requested changes, open threads) to the ones waiting on someone else.
export function attentionState(pull) {
  if (pull.ci === 'failure') return { rank: 0, label: 'Failing checks' }
  if (pull.review_decision === 'CHANGES_REQUESTED') return { rank: 1, label: 'Changes requested' }
  const threads = Number(pull.open_threads) || 0
  if (threads > 0) {
    return { rank: 2, label: `${threads} review thread${threads === 1 ? '' : 's'} open` }
  }
  if (pull.ci === 'pending') return { rank: 3, label: 'Checks running' }
  if (pull.review_decision === 'REVIEW_REQUIRED') return { rank: 4, label: 'Review required' }
  if (pull.approved) return { rank: 5, label: 'Approved' }
  return { rank: 6, label: 'No action needed' }
}

// How much a pull request needs its author to act, lowest first: failing checks,
// then requested changes, then unresolved threads, then checks still running,
// then a required review not yet given, then an approval, then the rest. The
// list is sorted by this, so what needs work is at the top.
export function attentionRank(pull) {
  return attentionState(pull).rank
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

// Whether a pull request matches one filter facet. An empty value is "Any"; a
// pull request GitHub left no CI state or review decision for counts as "none",
// the same key the filters and the groupings use for it.
export function matchesCiFilter(pull, value) {
  return !value || (pull.ci || 'none') === value
}

export function matchesReviewFilter(pull, value) {
  return !value || (pull.review_decision || 'none') === value
}

export function matchesThreadFilter(pull, value) {
  if (!value) return true
  const open = Number(pull.open_threads) || 0
  return value === 'open' ? open > 0 : open === 0
}

// How many pull requests each filter option would show, over the whole list
// rather than the current filter, so a chip states what it is worth. The "Any"
// option is the list's total, which the view reads itself.
export function pullFilterCounts(pulls) {
  const ci = {}
  const review = {}
  const threads = { open: 0, none: 0 }
  for (const pull of pulls || []) {
    const ciKey = pull.ci || 'none'
    ci[ciKey] = (ci[ciKey] || 0) + 1
    const reviewKey = pull.review_decision || 'none'
    review[reviewKey] = (review[reviewKey] || 0) + 1
    if (Number(pull.open_threads) > 0) threads.open += 1
    else threads.none += 1
  }
  return { ci, review, threads }
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
