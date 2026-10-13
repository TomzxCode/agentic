// Pure helpers for change records, shared by the task page's Items and Changes
// panels, the metrics page, and the repository detail view. Nothing here makes
// a request: the views hand it the changes they already loaded.

// The badge class for a change's status. The base "badge" class is included so
// a template can bind the value straight to :class.
const STATUS_BADGES = {
  proposed: 'badge',
  verified: 'badge run',
  accepted: 'badge ok',
  rejected: 'badge danger',
  reverted: 'badge warn'
}

// The badge class for a status, falling back to the neutral badge for a status
// the frontend does not know.
export function changeStatusBadge(status) {
  return STATUS_BADGES[status] || 'badge'
}

// A change references an item when its external ref names that item. A change
// recorded from a GitHub pull request stores the PR's URL there, so matching on
// url or external id is enough to link the two.
export function changeReferencesItem(change, item) {
  const ref = String(change?.external_ref || '').trim()
  if (!ref) return false
  return [item?.url, item?.external_id].some((value) => String(value || '').trim() === ref)
}

// The changes that reference an item, in the order the API returned them
// (opened_at descending).
export function changesForItem(changes, item) {
  return (changes || []).filter((change) => changeReferencesItem(change, item))
}

// The body that records a change for an item on a task. A merged pull request
// has already landed, so its change opens accepted and dated to the merge; an
// open PR opens proposed. Pass mergedAt when the merge time is resolved from
// somewhere other than the item's stored metadata (e.g. a fresh GitHub fetch).
export function changeCreateBody(taskId, item, mergedAt = item?.metadata_json?.merged_at) {
  return {
    task_id: taskId,
    title: item?.title || item?.url || '',
    external_ref: item?.url || item?.external_id || null,
    ...(mergedAt ? { status: 'accepted', opened_at: mergedAt, accepted_at: mergedAt } : {})
  }
}
