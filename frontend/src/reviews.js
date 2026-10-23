// Grouping for a PR's review reports, read from the user-global ~/.sdlc store.
//
// Everything here is pure: the item view hands it the files the reviews
// endpoint returned, so no request is involved.

import { parseGithubUrl } from './repositories/parse'

// Group review report files by the commit they cover. The API orders files
// newest first, so groups keep that order (a group is positioned by its newest
// file) and the files inside a group stay newest first. Files with no commit in
// their name (a raw PR cache, a "no-issue" variant) collect in one ungrouped
// bucket whose commit is null.
export function groupReviewFiles(files) {
  const groups = []
  const byCommit = new Map()
  for (const file of files || []) {
    const key = file.commit || ''
    let group = byCommit.get(key)
    if (!group) {
      group = { commit: file.commit || null, files: [], updated_at: file.modified_at || null }
      byCommit.set(key, group)
      groups.push(group)
    }
    group.files.push(file)
    if (file.modified_at && (!group.updated_at || file.modified_at > group.updated_at)) {
      group.updated_at = file.modified_at
    }
  }
  return groups
}

// A report's label: the skill it ran (the part of "<skill>.<sha>.md" before the
// commit), or the file name without its ".md" suffix when it names no commit.
export function reviewLabel(file) {
  if (file?.skill) return file.skill
  return String(file?.name || '').replace(/\.md$/i, '')
}

// Each report opens with an HTML marker comment (`<!-- {"step":...} -->`) that
// the review orchestrator scans. GitHub hides an HTML comment, but the renderer
// escapes raw HTML (so nothing in a report can inject markup), which would show
// the marker as text. Strip a single leading marker to keep the body clean.
export function stripReportMarker(text) {
  return String(text || '').replace(/^\s*<!--[\s\S]*?-->\s*/, '')
}

// --- Review queue ----------------------------------------------------------
// The queue view lists every PR with review reports in the store, one row per
// PR, with a column per review step. Everything here is pure: the view hands it
// the response the reviews endpoint returned.

// The review steps the queue table shows, in display order: the two parallel
// steps first (behavior, then risk), then the chain (coverage, validate,
// verify, review). `label` is the column header, matching the names the
// review_requested_prs script prints.
export const QUEUE_STEPS = [
  { key: 'summarize-behavior-changes', label: 'Behavior' },
  { key: 'assess-pr-risk', label: 'Risk' },
  { key: 'analyze-test-coverage', label: 'Coverage' },
  { key: 'validate-pr', label: 'Validate' },
  { key: 'verify-pr', label: 'Verify' },
  { key: 'review-pr', label: 'Review' }
]

// The merge-readiness light shown beside each PR number: green when the PR
// could be approved automatically, yellow when something still needs attention,
// red when a collected signal blocks approval.
export const READINESS_LIGHTS = { green: '🟢', yellow: '🟡', red: '🔴' }
export const READINESS_TITLES = {
  green: 'Could be approved automatically',
  yellow: 'Still needs attention',
  red: 'A signal blocks approval'
}

// How each way the review scan found a pull request reads, as the emoji the
// queue shows beside it. "requested" is a review asked of the user, "reviewed"
// is one they already reviewed that is still open.
export const REQUEST_SOURCE_BADGES = { requested: '📨', reviewed: '👀' }

// Whether GitHub has already approved the pull request: its review decision is
// APPROVED, which means the reviews the branch requires are in. Reads the
// decision case-insensitively, since the store's cache spells it in lower case.
export function isApproved(pr) {
  return String(pr?.review_decision || '').toUpperCase() === 'APPROVED'
}

// The in-progress marker a step published while it runs, or null when it is
// not running. The marker is empty; its presence is the signal.
export function runningStep(pr, key) {
  return pr?.in_progress?.[key] || null
}

// A verdict rendered as its mark when it has one; a route or a "partial"
// verdict has no mark and shows its own word.
const VERDICT_MARKS = { pass: '✅', fail: '❌', informational: 'ℹ️' }

export function verdictLabel(verdict) {
  return VERDICT_MARKS[verdict] || verdict || ''
}

// The tone a verdict reads in, so a pass/fail looks the same everywhere.
export function verdictTone(verdict) {
  if (verdict === 'pass' || verdict === 'fast-track' || verdict === 'confirm') return 'ok'
  if (verdict === 'fail' || verdict === 'block' || verdict === 'hold') return 'danger'
  if (verdict === 'decide' || verdict === 'investigate' || verdict === 'partial') return 'warn'
  if (verdict === 'informational') return 'info'
  return ''
}

// The tone of an assess-pr-risk severity (low/medium/high), for the risk letter.
export function riskTone(risk) {
  if (risk === 'low') return 'ok'
  if (risk === 'medium') return 'warn'
  if (risk === 'high') return 'danger'
  return ''
}

// The GitHub items of one kind ("pr" or "issue") a task links, from its
// associated items. Each entry names the item's coordinates, its item, and its
// id, so a view can offer a mode for that kind and match the item against other
// data. Pure: it reads the task the view already holds. Duplicate items (the
// same one linked twice) are collapsed by their owner/repo/number key.
function linkedGithubItems(task, kind) {
  const items = []
  const seen = new Set()
  for (const assoc of task?.associations || []) {
    const item = assoc.item
    const parsed = parseGithubUrl(item?.url)
    if (!parsed || parsed.kind !== kind) continue
    const key = `${parsed.owner}/${parsed.repo}#${parsed.number}`
    if (seen.has(key)) continue
    seen.add(key)
    items.push({
      owner: parsed.owner,
      repo: parsed.repo,
      number: Number(parsed.number),
      url: item.url,
      item_id: item.id,
      item
    })
  }
  return items
}

// The GitHub pull requests a task links, for the task view's PR mode.
export function taskPullRequests(task) {
  return linkedGithubItems(task, 'pr')
}

// The GitHub issues a task links, for the task view's issue mode.
export function taskIssues(task) {
  return linkedGithubItems(task, 'issue')
}

// A review-queue row for a pull request, matched by its coordinates. The store
// keys a repository by its canonical casing, so the match is case-insensitive.
export function queueRowFor(prs, pr) {
  const repository = `${pr.owner}/${pr.repo}`.toLowerCase()
  return (
    (prs || []).find(
      (row) => Number(row.number) === Number(pr.number) && String(row.repository || '').toLowerCase() === repository
    ) || null
  )
}

// The pull-request status filters the queue offers, in display order. "Open" is
// the default, so the queue shows the pull requests still awaiting a review
// unless the user asks for the closed ones too.
export const PR_STATE_FILTERS = [
  { value: 'open', label: 'Open' },
  { value: 'merged', label: 'Merged' },
  { value: 'closed', label: 'Closed' },
  { value: 'all', label: 'All' }
]

// The filter group a row's status belongs to: "open", "merged", or "closed".
// ghx (and the store's gh pr view cache) report "OPEN", "MERGED", or "CLOSED";
// a row whose status was never read is treated as open, so an offline queue
// still shows the pull requests already in the store.
export function prStateGroup(pr) {
  const state = String(pr?.state || '').toUpperCase()
  if (state === 'MERGED') return 'merged'
  if (state === 'CLOSED') return 'closed'
  return 'open'
}

// Whether a row passes the status filter; "all" passes every row.
export function matchesStateFilter(pr, value) {
  return value === 'all' || prStateGroup(pr) === value
}

// How many rows fall under each status filter value, keyed by that value. The
// counts cover the whole queue, so a chip reads the same whichever filter is on.
export function stateFilterCounts(prs) {
  const counts = { open: 0, merged: 0, closed: 0, all: (prs || []).length }
  for (const pr of prs || []) counts[prStateGroup(pr)] += 1
  return counts
}

// The three states a kind filter (drafts, approved) takes, in click order: the
// kind is hidden, then only that kind is shown, then everything. Both start
// hidden, because the queue is about what still needs a review.
export const KIND_FILTER_STATES = ['hide', 'only', 'all']
export const KIND_FILTER_LABELS = { hide: 'hidden', only: 'only', all: 'all' }

// The state a kind filter takes on its next click, wrapping around. An unknown
// state starts the cycle over at hidden.
export function nextKindFilter(state) {
  const index = KIND_FILTER_STATES.indexOf(state)
  return KIND_FILTER_STATES[(index + 1) % KIND_FILTER_STATES.length]
}

// Whether a row passes the draft filter for a kind-filter state: hidden keeps
// drafts out, only keeps just drafts, and all keeps everything.
export function matchesDraftFilter(pr, state) {
  if (state === 'all') return true
  if (state === 'only') return !!pr?.draft
  return !pr?.draft
}

// How many rows in the queue are drafts, for the toggle's count. Like the state
// counts, it covers the whole queue.
export function draftFilterCount(prs) {
  return (prs || []).filter((pr) => pr?.draft).length
}

// Whether a row passes the approved filter for a kind-filter state: hidden keeps
// approved pull requests out, only keeps just the approved ones, and all keeps
// everything.
export function matchesApprovedFilter(pr, state) {
  if (state === 'all') return true
  if (state === 'only') return isApproved(pr)
  return !isApproved(pr)
}

// How many rows in the queue GitHub has already approved, for the toggle's
// count. Like the draft count, it covers the whole queue.
export function approvedFilterCount(prs) {
  return (prs || []).filter((pr) => isApproved(pr)).length
}

// Whether the user already reviewed the pull request: the review scan found it
// through the reviewed-by search, which is what the 👀 mark reports.
export function isReviewedByMe(pr) {
  return pr?.request_source === 'reviewed'
}

// Whether a row passes the reviewed filter for a kind-filter state: hidden keeps
// the pull requests the user already reviewed out, only keeps just those, and
// all keeps everything.
export function matchesReviewedFilter(pr, state) {
  if (state === 'all') return true
  if (state === 'only') return isReviewedByMe(pr)
  return !isReviewedByMe(pr)
}

// How many rows in the queue the user already reviewed, for the toggle's count.
// Like the draft count, it covers the whole queue.
export function reviewedFilterCount(prs) {
  return (prs || []).filter((pr) => isReviewedByMe(pr)).length
}

// Whether a row matches the search text: its repository, number, title, or
// author. An empty query matches every row.
export function matchesQueueSearch(pr, query) {
  const q = String(query || '')
    .trim()
    .toLowerCase()
  if (!q) return true
  return [pr?.repository, pr?.number, pr?.title, pr?.author].some((value) =>
    String(value ?? '')
      .toLowerCase()
      .includes(q)
  )
}

// The distinct authors in the queue, each with the number of rows they carry,
// ordered by name. A row with no author is left out of the list: it matches only
// the "all authors" choice.
export function queueAuthors(prs) {
  const counts = new Map()
  for (const pr of prs || []) {
    const author = String(pr?.author || '').trim()
    if (!author) continue
    counts.set(author, (counts.get(author) || 0) + 1)
  }
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => a.value.toLowerCase().localeCompare(b.value.toLowerCase()))
}

// Whether a row matches the author filter. An empty selection matches every
// row; otherwise its login must be one of the chosen authors
// (case-insensitively). Accepts a single value or a list of them.
export function matchesAuthorFilter(pr, value) {
  const wanted = (Array.isArray(value) ? value : [value])
    .map((entry) =>
      String(entry || '')
        .trim()
        .toLowerCase()
    )
    .filter(Boolean)
  if (!wanted.length) return true
  const author = String(pr?.author || '')
    .trim()
    .toLowerCase()
  return wanted.includes(author)
}

// The distinct repositories in a row list (the review queue or My PRs), each
// with the number of rows it carries, ordered by name case-insensitively. Rows
// with no repository are left out of the list: they match only the unfiltered
// list.
export function repositoriesWithCounts(prs) {
  const counts = new Map()
  for (const pr of prs || []) {
    const repository = String(pr?.repository || '').trim()
    if (!repository) continue
    counts.set(repository, (counts.get(repository) || 0) + 1)
  }
  return [...counts.entries()]
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => a.value.toLowerCase().localeCompare(b.value.toLowerCase()))
}

// Whether a row matches the repository filter. An empty selection matches every
// row; otherwise its repository must be one of the chosen ones
// (case-insensitively). Accepts a single value or a list of them.
export function matchesRepositoryFilter(pr, value) {
  const wanted = (Array.isArray(value) ? value : [value])
    .map((entry) =>
      String(entry || '')
        .trim()
        .toLowerCase()
    )
    .filter(Boolean)
  if (!wanted.length) return true
  const repository = String(pr?.repository || '')
    .trim()
    .toLowerCase()
  return wanted.includes(repository)
}

// The queue grouped by repository, repositories in name order and the PRs in
// each group newest first (the API already orders them that way).
export function groupQueueByRepository(prs) {
  const groups = new Map()
  for (const pr of prs || []) {
    if (!groups.has(pr.repository)) groups.set(pr.repository, [])
    groups.get(pr.repository).push(pr)
  }
  return [...groups.entries()].map(([repository, repositoryPrs]) => ({ repository, prs: repositoryPrs }))
}

// A commit as the short form the table shows.
export function shortCommit(commit) {
  return String(commit || '').slice(0, 7)
}

// The GitHub commit page for a PR's reviewed commit, or null when it cannot be
// built. The store names a report by the short sha, which GitHub resolves; a
// store keyed without an owner has no GitHub URL to point at.
export function commitUrl(pr) {
  if (!pr?.head_commit || !pr?.owner) return null
  return `https://github.com/${pr.repository}/commit/${pr.head_commit}`
}

// --- A pull request's reviewers on GitHub -----------------------------
// The item view lists one row per reviewer `gh` names for a PR, plus the
// reviewers a review is still requested from. Everything here is pure: the view
// hands in the reviews endpoint returned.

// How each GitHub review state reads, and the badge tone it carries. PENDING is
// not a GitHub review state: the API uses it for a reviewer a review is still
// requested from.
export const GITHUB_REVIEW_STATES = {
  APPROVED: { label: 'Approved', className: 'tone-ok' },
  CHANGES_REQUESTED: { label: 'Changes requested', className: 'tone-danger' },
  COMMENTED: { label: 'Commented', className: '' },
  DISMISSED: { label: 'Dismissed', className: 'faint' },
  PENDING: { label: 'Awaiting review', className: 'tone-warn' }
}

export function githubReviewState(state) {
  return GITHUB_REVIEW_STATES[String(state || '').toUpperCase()] || { label: String(state || ''), className: '' }
}

// Reviewers in display order: the ones still owing a review first (those are the
// ones worth a poke), then the rest by when they last reviewed, newest first.
// `key` is stable for the list even if the API repeats a login.
export function orderGithubReviewers(reviewers) {
  return [...(reviewers || [])]
    .sort((a, b) => {
      if (!!a.requested !== !!b.requested) return a.requested ? -1 : 1
      return String(b.submitted_at || '').localeCompare(String(a.submitted_at || ''))
    })
    .map((reviewer, index) => ({
      ...reviewer,
      key: `${reviewer.login}|${reviewer.submitted_at || ''}|${index}`
    }))
}
