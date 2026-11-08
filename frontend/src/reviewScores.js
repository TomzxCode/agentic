// Aggregate the 0-1 scores the review steps record into one series per rubric.
//
// Everything here is pure: the view hands it the runs the API returned, so the
// repository and author filters and the daily means are computed locally.

// The rubric each review step contributes, in dispatch order. A step's score
// measures how well the change addresses that step's concern, from 0 (not
// addressed, or a blocking problem) to 1 (fully addressed).
export const RUBRICS = [
  {
    step: 'summarize-behavior-changes',
    label: 'Behavior',
    group: 'Assessments',
    description: 'Declared and undeclared behavior changes.'
  },
  {
    step: 'assess-pr-risk',
    label: 'Risk',
    group: 'Assessments',
    description: 'How much damage a wrong change could do, and how hard it is to undo.'
  },
  {
    step: 'adversarial-pr-review',
    label: 'Adversarial',
    group: 'Assessments',
    description: 'Whether a plausible failure could be reproduced.'
  },
  {
    step: 'review-cli-changes',
    label: 'CLI',
    group: 'Surface reviews',
    description: 'The command-line surface: commands, options, and output.'
  },
  {
    step: 'review-sdk-changes',
    label: 'SDK',
    group: 'Surface reviews',
    description: 'The published client library: symbols, signatures, and versioning.'
  },
  {
    step: 'review-api-changes',
    label: 'API',
    group: 'Surface reviews',
    description: 'The HTTP or RPC contract and its consumers.'
  },
  {
    step: 'review-db-changes',
    label: 'DB',
    group: 'Surface reviews',
    description: 'Schema and data migrations, and their rollback.'
  },
  {
    step: 'analyze-test-coverage',
    label: 'Coverage',
    group: 'Review chain',
    description: 'Tests introduced and the behavior they exercise.'
  },
  {
    step: 'validate-pr',
    label: 'Validate',
    group: 'Review chain',
    description: 'Whether the pull request builds the right product.'
  },
  {
    step: 'verify-pr',
    label: 'Verify',
    group: 'Review chain',
    description: 'Whether it conforms to the acceptance criteria.'
  },
  {
    step: 'review-pr',
    label: 'Review',
    group: 'Review chain',
    description: 'Code craft, architecture, and tests.'
  }
]

export const RUBRIC_GROUPS = ['Assessments', 'Surface reviews', 'Review chain']

const BY_STEP = new Map(RUBRICS.map((rubric) => [rubric.step, rubric]))

export function rubricMeta(step) {
  return BY_STEP.get(step) || { step, label: step, group: '', description: '' }
}

// The run's day, UTC, as YYYY-MM-DD. The API dates a run from the marker's
// reviewed_at, which is already a UTC timestamp.
export function runDay(run) {
  const raw = String(run?.reviewed_at || '')
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return ''
  return parsed.toISOString().slice(0, 10)
}

// The runs the filters keep. Empty selections mean every repository or author.
export function filterRuns(runs, { repositories = [], authors = [] } = {}) {
  const repos = new Set((repositories || []).map((value) => String(value).toLowerCase()))
  const people = new Set((authors || []).map((value) => String(value).toLowerCase()))
  return (runs || []).filter((run) => {
    if (repos.size && !repos.has(String(run.repository || '').toLowerCase())) return false
    if (people.size && !people.has(String(run.author || '').toLowerCase())) return false
    return true
  })
}

// The repositories in the runs, with their run counts, for the filter's
// options. Sorted by name so the list does not move as runs arrive.
export function repositoryOptions(runs) {
  return countValues(runs, 'repository')
}

// The authors in the runs, with their run counts, for the filter's options.
export function authorOptions(runs) {
  return countValues(runs, 'author')
}

function countValues(runs, key) {
  const counts = new Map()
  for (const run of runs || []) {
    const value = String(run[key] || '')
    if (!value) continue
    const entry = counts.get(value)
    if (entry) entry.count += 1
    else counts.set(value, { value, count: 1 })
  }
  return [...counts.values()].sort((a, b) => a.value.localeCompare(b.value))
}

// One point per rubric per day: the mean of that day's runs, with how many
// runs it averaged. Days with no run are left out rather than drawn as zero, so
// a quiet week does not read as a bad one.
export function dailyRubricSeries(runs) {
  const byStep = new Map()
  for (const run of runs || []) {
    const day = runDay(run)
    if (!day) continue
    const step = String(run.step || '')
    if (!step) continue
    let buckets = byStep.get(step)
    if (!buckets) {
      buckets = new Map()
      byStep.set(step, buckets)
    }
    const values = buckets.get(day) || []
    values.push(Number(run.score))
    buckets.set(day, values)
  }

  return RUBRICS.map((rubric) => {
    const buckets = byStep.get(rubric.step) || new Map()
    const points = [...buckets.entries()]
      .map(([date, values]) => ({
        date,
        count: values.length,
        mean: round(mean(values)),
        min: Math.min(...values),
        max: Math.max(...values)
      }))
      .sort((a, b) => a.date.localeCompare(b.date))
    const count = points.reduce((total, point) => total + point.count, 0)
    return {
      ...rubric,
      points,
      count,
      // The rubric mean weights every run, not every day, so one busy low-scoring
      // day is not averaged away by a quiet high-scoring one.
      mean: count ? round(points.reduce((total, point) => total + point.mean * point.count, 0) / count) : null
    }
  })
}

// The runs' overall mean and the day range they span, for the page header.
export function runsSummary(runs) {
  const values = (runs || []).map((run) => Number(run.score)).filter((value) => Number.isFinite(value))
  const days = (runs || []).map(runDay).filter(Boolean).sort()
  return {
    reviews: values.length,
    mean: values.length ? round(mean(values)) : null,
    first: days[0] || null,
    last: days[days.length - 1] || null
  }
}

function mean(values) {
  return values.reduce((total, value) => total + value, 0) / values.length
}

function round(value) {
  return Math.round(value * 100) / 100
}

// The tone a score reads in: a fully addressed concern is green, a partial one
// amber, and a low score red.
export function scoreTone(score) {
  if (score == null) return ''
  if (score >= 0.75) return 'ok'
  if (score >= 0.5) return 'warn'
  return 'danger'
}

// A score with two decimals, the precision the skills write.
export function formatScore(score) {
  return score == null ? '—' : Number(score).toFixed(2)
}

// A day as the chart's axis label: month and day, with the year only when the
// range crosses one.
export function dayLabel(day, withYear = false) {
  if (!day) return ''
  const parsed = new Date(`${day}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return day
  return parsed.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    ...(withYear ? { year: 'numeric' } : {})
  })
}
