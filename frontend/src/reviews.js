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

// The GitHub pull requests a task is linked to, from its associated items.
// Each entry names the PR's coordinates and its item, so the task view can offer
// a pull-request mode and match the PR against the review queue. Pure: it reads
// the task the view already holds. Duplicate items (one PR linked twice) are
// collapsed by their owner/repo/number key.
export function taskPullRequests(task) {
  const prs = []
  const seen = new Set()
  for (const assoc of task?.associations || []) {
    const item = assoc.item
    const parsed = parseGithubUrl(item?.url)
    if (!parsed || parsed.kind !== 'pr') continue
    const key = `${parsed.owner}/${parsed.repo}#${parsed.number}`
    if (seen.has(key)) continue
    seen.add(key)
    prs.push({
      owner: parsed.owner,
      repo: parsed.repo,
      number: Number(parsed.number),
      url: item.url,
      item_id: item.id
    })
  }
  return prs
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
