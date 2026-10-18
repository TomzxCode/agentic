// Grouping, filtering, and sorting that backs the Repositories page and the
// repository detail view. Pure: the views hand it repositories and items already
// loaded in the store, so no request or backend change is involved.

import { itemKind, itemNumber, parseGithubUrl, parseRemote, stateBreakdown } from './parse'

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
