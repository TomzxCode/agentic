// GitHub URL and git-remote parsing, and the grouping that backs the
// Repositories page and the repository detail view.
//
// Everything here is pure: the views hand it the repositories and items already
// loaded in the store, so no request or backend change is involved.

const GITHUB_URL_RE = /github\.com\/([^/\s]+)\/([^/\s?#]+)\/(issues|pull)\/(\d+)/i
// Mirrors the backend's GITHUB_REPO_RE: matches a GitHub https or ssh remote,
// tolerating a trailing ".git", slash, whitespace, or query/fragment.
const GITHUB_REMOTE_RE = /github\.com[/:]([^/\s]+)\/([^/\s#?]+?)(?:\.git)?(?:[/\s#?]|$)/i

// Parse a GitHub issue/PR URL into {owner, repo, kind, number}, or null.
// owner and repo are lowercased so matching is case-insensitive.
export function parseGithubUrl(url) {
  const match = GITHUB_URL_RE.exec(String(url || ''))
  if (!match) return null
  return {
    owner: match[1].toLowerCase(),
    repo: match[2].toLowerCase(),
    kind: match[3].toLowerCase() === 'pull' ? 'pr' : 'issue',
    number: match[4]
  }
}

// Parse a git remote (https, http, ssh://, or git@) into {owner, repo}, or null
// when it is not a GitHub remote.
export function parseRemote(remote) {
  const match = GITHUB_REMOTE_RE.exec(String(remote || ''))
  if (!match) return null
  return { owner: match[1].toLowerCase(), repo: match[2].toLowerCase() }
}

// An item's kind as "issue" or "pr", preferring the URL path and falling back
// to the stored kind. Anything else is null (and excluded from the views).
export function itemKind(item) {
  const parsed = parseGithubUrl(item?.url)
  if (parsed) return parsed.kind
  const kind = String(item?.kind || '').toLowerCase()
  if (kind === 'pr' || kind === 'pull' || kind === 'pull_request') return 'pr'
  if (kind === 'issue') return 'issue'
  return null
}

// An item's issue/PR number, from the URL or the "#<n>" suffix of its external
// id. Returns null when neither carries one.
export function itemNumber(item) {
  const parsed = parseGithubUrl(item?.url)
  if (parsed?.number) return parsed.number
  const match = /#(\d+)$/.exec(String(item?.external_id || ''))
  return match ? match[1] : null
}

// The states an item can be in, in display order, and their labels.
export const STATE_ORDER = ['open', 'draft', 'merged', 'closed']
export const STATE_LABELS = { open: 'Open', draft: 'Draft', merged: 'Merged', closed: 'Closed' }

// An item's GitHub state, normalized for filtering and display: "open",
// "draft", "merged", or "closed", or null when nothing was stored. ghx reports
// OPEN / CLOSED / MERGED and flags a draft PR separately, so an open draft
// reads as "draft". State is stored on the item's metadata; no GitHub call is
// involved.
export function itemState(item) {
  const meta = item?.metadata_json || {}
  const state = String(meta.state || '').toUpperCase()
  if (state === 'MERGED') return 'merged'
  if (state === 'CLOSED') return 'closed'
  if (state === 'OPEN') return meta.is_draft ? 'draft' : 'open'
  return null
}

// An item's state ready for display: its state, label, and badge class, or
// null when no state is stored. Covers issues (open or closed) and PRs (all
// four states).
export function itemStatus(item) {
  const state = itemState(item)
  if (!state) return null
  return { state, label: STATE_LABELS[state], className: `st-${state}` }
}

// An item's GitHub author login from its stored metadata, or null when the
// item was never fetched or its source named no author.
export function itemAuthor(item) {
  const login = item?.metadata_json?.author
  return login ? String(login) : null
}

// The person who carries a handle (a GitHub login) as one of their aliases,
// matched case-insensitively, or null when nobody does. Aliases are the
// identities used to de-duplicate people across sources.
export function personForHandle(people, handle) {
  const needle = String(handle || '')
    .trim()
    .toLowerCase()
  if (!needle) return null
  return (
    (people || []).find((person) =>
      (person?.aliases || []).some(
        (alias) =>
          String(alias || '')
            .trim()
            .toLowerCase() === needle
      )
    ) || null
  )
}

// The state breakdown of a set of items: one entry per state present, in
// display order, with its value, label, and count. Items with no stored state
// are not counted.
export function stateBreakdown(items) {
  const counts = {}
  for (const item of items || []) {
    const state = itemState(item)
    if (state) counts[state] = (counts[state] || 0) + 1
  }
  return STATE_ORDER.filter((state) => counts[state]).map((state) => ({
    value: state,
    label: STATE_LABELS[state],
    count: counts[state]
  }))
}

// The GitHub issue/PR items a repository owns: source "github", associated to
// at least one task, with a URL whose owner/repo matches the repository remote.
// Each returned item carries a normalized kind and number.
export function itemsForRepository(repository, items) {
  const remote = parseRemote(repository?.remote_url)
  if (!remote) return []
  const key = `${remote.owner}/${remote.repo}`
  return (items || [])
    .filter((item) => item?.source === 'github' && (item.task_ids || []).length)
    .map((item) => {
      const parsed = parseGithubUrl(item.url)
      if (!parsed || `${parsed.owner}/${parsed.repo}` !== key) return null
      return { ...item, kind: itemKind(item), number: itemNumber(item) }
    })
    .filter(Boolean)
}

// Group items by repository into one summary per registered repository:
// the repository's fields, its derived owner/repo (null when not GitHub), its
// items, and its issue/PR counts. An item appears under every repository whose
// remote matches it.
export function groupItemsByRepository(repositories, items) {
  const summaries = (repositories || []).map((repository) => {
    const remote = parseRemote(repository.remote_url)
    return {
      ...repository,
      owner: remote?.owner || null,
      repo: remote?.repo || null,
      items: [],
      issue_count: 0,
      pull_count: 0
    }
  })

  const byKey = new Map()
  for (const summary of summaries) {
    if (!summary.owner || !summary.repo) continue
    const key = `${summary.owner}/${summary.repo}`
    byKey.set(key, [...(byKey.get(key) || []), summary])
  }

  for (const item of items || []) {
    if (item?.source !== 'github' || !(item.task_ids || []).length) continue
    const parsed = parseGithubUrl(item.url)
    if (!parsed) continue
    const targets = byKey.get(`${parsed.owner}/${parsed.repo}`)
    if (!targets?.length) continue
    const kind = itemKind(item)
    if (kind !== 'issue' && kind !== 'pr') continue
    const view = { ...item, kind, number: itemNumber(item), repository_id: targets[0].id }
    for (const summary of targets) {
      summary.items.push(view)
      if (kind === 'pr') summary.pull_count += 1
      else summary.issue_count += 1
    }
  }

  for (const summary of summaries) summary.states = stateBreakdown(summary.items)
  return summaries
}

// Sort a repository's items for display: by number descending when known,
// unknown numbers last, ties broken by title.
export function sortItems(items) {
  return [...(items || [])].sort((a, b) => {
    const an = a.number ? Number(a.number) : -1
    const bn = b.number ? Number(b.number) : -1
    if (an !== bn) return bn - an
    return String(a.title || '').localeCompare(String(b.title || ''))
  })
}
