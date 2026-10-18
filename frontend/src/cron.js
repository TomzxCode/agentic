// Client-side cron evaluation for the schedule form's "next 5 runs" preview.
//
// The API owns scheduling: it decides when a task really runs. The preview is
// presentation, so it is computed here to stay instant and offline. croner is a
// cron engine that reads the same IANA zones the server does, so for the
// five-field expressions the form accepts the preview matches the real runs.

import { Cron } from 'croner'

// The server accepts exactly five fields (minute hour day-of-month month
// day-of-week), so reject anything else before handing it to croner, which also
// allows seconds and a year field.
export function scheduleError(expression) {
  const text = (expression || '').trim()
  if (!text) return 'A schedule is required'
  if (text.split(/\s+/).length !== 5) {
    return 'A schedule needs 5 fields: minute hour day-of-month month day-of-week'
  }
  try {
    new Cron(text, { paused: true })
  } catch {
    return `'${text}' is not a valid cron expression`
  }
  return ''
}

// The next `count` occurrences of an expression read in `timezone`, as ISO
// strings (UTC instants), matching what the server would store.
export function nextRuns(expression, timezone, count = 5, from = new Date()) {
  const cron = new Cron(expression, { timezone: timezone || 'UTC', paused: true })
  return cron.nextRuns(count, from).map((date) => date.toISOString())
}
