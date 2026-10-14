// Helpers for the stack's drag-and-drop reordering.

// The index a dragged row should land on, given the vertical midpoint of each
// rendered row and the pointer's Y. Returns 0..n-1 (clamped to the last row).
export function targetIndexAt(midpoints, clientY) {
  if (!midpoints.length) return 0
  for (let i = 0; i < midpoints.length; i++) {
    if (clientY < midpoints[i]) return i
  }
  return midpoints.length - 1
}

// Move the item at `from` to `to`, returning a new array (the input untouched).
export function moveItem(items, from, to) {
  const next = items.slice()
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return next
}

// A progressive timestamp, matching the desktop app: an older year shows
// YYYY-MM-DD HH:MM, an older month MM-DD HH:MM, an older day DD HH:MM, an
// earlier hour HH:MM, and within the same hour just the minutes. Local time,
// 24-hour clock; a missing or unparseable value shows an em dash.
export function formatTimestamp(iso, now) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (value) => String(value).padStart(2, '0')
  const clock = `${pad(date.getHours())}:${pad(date.getMinutes())}`
  if (date.getFullYear() !== now.getFullYear()) {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${clock}`
  }
  if (date.getMonth() !== now.getMonth()) {
    return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${clock}`
  }
  if (date.getDate() !== now.getDate()) {
    return `${pad(date.getDate())} ${clock}`
  }
  if (date.getHours() !== now.getHours()) {
    return clock
  }
  return pad(date.getMinutes())
}
