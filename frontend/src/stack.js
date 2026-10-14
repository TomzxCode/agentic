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
