// Shared Gantt helpers: marker styling and time-domain math. The Gantt view
// (every task) and the task timeline panel (one task) both build on these, so
// the two charts stay consistent without duplicating the math.

// A marker's color and label are derived from its timeline event type.
export const MARKER_KIND = {
  created: 'accent',
  updated: 'blue',
  item_added: 'warn',
  item_removed: 'warn',
  worktree_created: 'violet',
  worktree_removed: 'muted',
  run_started: 'blue',
  context_refresh: 'blue',
  context_updated: 'ok',
  context_refresh_failed: 'danger'
}
export const MARKER_LABEL = {
  created: 'Created',
  updated: 'Updated',
  item_added: 'Item added',
  item_removed: 'Item removed',
  worktree_created: 'Worktree created',
  worktree_removed: 'Worktree removed',
  run_started: 'Run started',
  context_refresh: 'Context refresh requested',
  context_updated: 'Context updated',
  context_refresh_failed: 'Context refresh failed'
}

export function markerKind(type) {
  return MARKER_KIND[type] || 'muted'
}
export function markerLabel(type) {
  return MARKER_LABEL[type] || type.replace(/_/g, ' ')
}

// Fit the window to every row span and marker, plus now when asked, with a 2%
// pad so in-flight work reaches the right edge.
export function computeFitDomain(rows, { includeNow = true, now = Date.now() } = {}) {
  let lo = includeNow ? now : Infinity
  let hi = includeNow ? now : -Infinity
  const see = (t) => {
    if (t < lo) lo = t
    if (t > hi) hi = t
  }
  for (const row of rows) {
    see(new Date(row.created_at).getTime())
    see(new Date(row.updated_at).getTime())
    for (const marker of row.markers) see(new Date(marker.created_at).getTime())
  }
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) {
    return { lo: now, hi: now + 60_000 }
  }
  if (hi - lo < 60_000) hi = lo + 60_000
  const pad = (hi - lo) * 0.02
  return { lo: lo - pad, hi: hi + pad }
}

// A datetime-local value is a local-time string with no timezone. Format a
// timestamp the same way, down to the second, so it round-trips exactly.
export function toField(t) {
  const d = new Date(t)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// Resolve the visible domain from the fitted window and any range the user set.
// An unset bound defaults to the fitted bound, so editing one end still works;
// a reversed window is invalid and falls back to the fit.
export function resolveDomain(rows, rangeStart = '', rangeEnd = '', options = {}) {
  const fit = computeFitDomain(rows, options)
  const lo = rangeStart ? new Date(rangeStart).getTime() : fit.lo
  const hi = rangeEnd ? new Date(rangeEnd).getTime() : fit.hi
  const valid = Number.isFinite(lo) && Number.isFinite(hi) && hi > lo
  return {
    fit,
    lo: valid ? lo : fit.lo,
    hi: valid ? hi : fit.hi,
    invalid: Boolean((rangeStart || rangeEnd) && !valid)
  }
}

// Ticks across the window. Short windows show the time of day too, and use
// fewer ticks so the longer labels do not overlap. A compact chart (the single
// task row) uses two ticks and drops the date when it spans under a day.
export function ganttTicks(lo, hi, { compact = false } = {}) {
  const span = hi - lo
  const withTime = span < 3 * 24 * 60 * 60 * 1000
  const count = compact ? 2 : withTime ? 3 : 5
  const out = []
  for (let i = 0; i <= count; i++) {
    const t = lo + (span * i) / count
    let options
    if (compact && span < 24 * 60 * 60 * 1000) options = { hour: '2-digit', minute: '2-digit' }
    else if (withTime) options = { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
    else options = { month: 'short', day: 'numeric' }
    out.push({
      key: i,
      left: (i / count) * 100,
      label: new Date(t).toLocaleString(undefined, options),
      align: i === 0 ? 'start' : i === count ? 'end' : 'center'
    })
  }
  return out
}

// Where a timestamp sits across the window, as a percentage.
export function spanPct(t, lo, hi) {
  const ms = typeof t === 'number' ? t : new Date(t).getTime()
  return ((ms - lo) / (hi - lo)) * 100
}
