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

// The metadata a live ghx listing supplies for a row, preferring it over what
// the stored item last recorded. Absent values are left out so they do not
// overwrite a state or author the stored item already carries.
function liveMetadata(ghx) {
  const meta = { is_draft: !!ghx.is_draft }
  if (ghx.state) meta.state = ghx.state
  if (ghx.merged_at) meta.merged_at = ghx.merged_at
  if (ghx.created_at) meta.created_at = ghx.created_at
  if (ghx.author) meta.author = ghx.author
  return meta
}

function rowKey(kind, number) {
  return `${kind}:${number}`
}

// A display row for one issue or PR: its live ghx data when the repository
// listing carries it, its stored item when it is associated to a task, or both.
// The row is shaped like an item (url, metadata_json, task_ids), so itemState,
// itemAuthor, and the change/task helpers work on it unchanged.
function makeRow(ghx, stored) {
  const kind = ghx ? ghx.kind : itemKind(stored)
  const number = ghx ? String(ghx.number) : itemNumber(stored)
  return {
    id: stored?.id || null,
    item: stored || null,
    live: !!ghx,
    linked: !!stored,
    kind,
    number,
    title: ghx?.title || stored?.title || '',
    url: ghx?.url || stored?.url || '',
    // Carried through so change matching (url or external id) still finds the
    // row's changes, exactly as it did on the stored item.
    external_id: stored?.external_id || null,
    metadata_json: { ...(stored?.metadata_json || {}), ...(ghx ? liveMetadata(ghx) : {}) },
    task_ids: stored?.task_ids || [],
    fetched_at: stored?.fetched_at || null
  }
}

// Filter a repository list: a needle matched against the name, path, and
// remote, plus whether the repository has a GitHub remote at all ("github") or
// does not ("other"). An empty needle and an empty remote filter pass everything.
export function filterRepositories(repositories, { query = '', remote = '' } = {}) {
  const q = String(query || '')
    .trim()
    .toLowerCase()
  return (repositories || []).filter((repo) => {
    const isGithub = !!parseRemote(repo?.remote_url)
    if (remote === 'github' && !isGithub) return false
    if (remote === 'other' && isGithub) return false
    if (!q) return true
    return [repo?.name, repo?.path, repo?.remote_url].some((value) =>
      String(value || '')
        .toLowerCase()
        .includes(q)
    )
  })
}

// The sort orders a repository list supports, with display labels. The keys are
// direction-neutral on purpose: the separate ascending/descending toggle carries
// the direction, so "Item count" plus "Desc" reads as "most items first".
export const REPOSITORY_SORTS = [
  { value: 'name', label: 'Name' },
  { value: 'items', label: 'Item count' },
  { value: 'newest', label: 'Date added' }
]

// The direction each order reads best in, and the one it returns to when the
// order changes: alphabetical ascending, counts and dates descending.
export const REPOSITORY_SORT_DIRECTIONS = { name: 'asc', items: 'desc', newest: 'desc' }

// Sort a repository list: alphabetically, by associated issue and PR count, or
// by when the repository was added, in the given direction ("asc"/"desc"; the
// order's default when omitted). Comparators are written ascending and flipped
// by the direction. Ties stay alphabetical ascending regardless of direction,
// so a direction flip never scrambles equal rows.
export function sortRepositories(repositories, sort = 'name', direction) {
  const sign = (direction || REPOSITORY_SORT_DIRECTIONS[sort] || 'asc') === 'desc' ? -1 : 1
  const byName = (a, b) => String(a?.name || '').localeCompare(String(b?.name || ''))
  const items = (repo) => (repo?.issue_count || 0) + (repo?.pull_count || 0)
  const sorted = [...(repositories || [])]
  if (sort === 'items') sorted.sort((a, b) => (items(a) - items(b)) * sign || byName(a, b))
  else if (sort === 'newest')
    sorted.sort((a, b) => (new Date(a?.created_at || 0) - new Date(b?.created_at || 0)) * sign || byName(a, b))
  else sorted.sort((a, b) => byName(a, b) * sign)
  return sorted
}

// Merge a repository's live GitHub listing (ghx) with the stored items already
// associated to tasks, so every issue and PR the repository has appears once.
// A ghx row supplies the current state; a stored item supplies the task links
// and the item id. A stored item the listing does not carry (older than the
// listing window, or the listing unavailable) is kept, so task-linked work
// never drops off the view.
export function repositoryRows(ghxItems, storedItems) {
  const byKey = new Map()
  for (const item of storedItems || []) {
    const kind = itemKind(item)
    const number = itemNumber(item)
    if (!kind || !number) continue
    byKey.set(rowKey(kind, number), item)
  }

  const rows = []
  for (const ghx of ghxItems || []) {
    if (!ghx?.kind || ghx.number === null || ghx.number === undefined) continue
    const key = rowKey(ghx.kind, String(ghx.number))
    const stored = byKey.get(key) || null
    if (stored) byKey.delete(key)
    rows.push(makeRow(ghx, stored))
  }
  for (const stored of byKey.values()) rows.push(makeRow(null, stored))
  return rows
}
