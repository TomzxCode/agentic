// Rendering helpers for the cycle-time section of the Metrics page.

// A duration in hours, shown in the largest unit that keeps it readable: a
// 20-minute review wait reads better as "20m" than as "0.3h".
export function formatCycleHours(hours) {
  if (hours == null) return 'n/a'
  if (hours < 1) return `${Math.round(hours * 60)}m`
  if (hours < 48) return `${hours.toFixed(1)}h`
  return `${(hours / 24).toFixed(1)}d`
}

// The bucket's label for a hover title: its start date and sample size.
export function bucketLabel(bucket) {
  const start = new Date(bucket.start)
  const date = Number.isNaN(start.getTime()) ? bucket.start : start.toLocaleDateString()
  const count = bucket.count === 1 ? '1 observation' : `${bucket.count} observations`
  const value = bucket.median_hours == null ? 'no data' : formatCycleHours(bucket.median_hours)
  return `${date} · ${value} · ${count}`
}
