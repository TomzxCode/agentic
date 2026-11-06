// The must/should/may findings a pull request's review skills recorded, and the
// prompt an agent is handed to post the selected ones to the PR author.
//
// Everything here is pure: the view hands in the findings the reviews endpoint
// returned, so no request is involved.

// The severities a finding can carry, in the order the app shows them, with the
// label and tone each reads in.
export const FINDING_SEVERITIES = [
  { value: 'must', label: 'MUST', tone: 'danger' },
  { value: 'should', label: 'SHOULD', tone: 'warn' },
  { value: 'may', label: 'MAY', tone: 'ok' }
]

// A finding's identity within a pull request's findings: the skill that
// recorded it plus its title, which the state files keep unique.
export function findingKey(finding) {
  return `${finding.step}:${finding.title}`
}

// The findings grouped by severity, most important first, dropping a severity
// with no findings.
export function findingsBySeverity(findings) {
  return FINDING_SEVERITIES.flatMap((severity) => {
    const items = (findings || []).filter((finding) => finding.severity === severity.value)
    return items.length ? [{ ...severity, findings: items }] : []
  })
}

// The review steps that can record findings, in the order the queue shows them,
// with the short label the source filter uses. A step a future skill adds and
// this list does not name still appears, under its own name.
export const FINDING_SOURCES = [
  { value: 'summarize-behavior-changes', label: 'Behavior' },
  { value: 'assess-pr-risk', label: 'Risk' },
  { value: 'adversarial-pr-review', label: 'Adversarial' },
  { value: 'analyze-test-coverage', label: 'Coverage' },
  { value: 'validate-pr', label: 'Validate' },
  { value: 'verify-pr', label: 'Verify' },
  { value: 'review-pr', label: 'Review' },
  { value: 'review-cli-changes', label: 'CLI' },
  { value: 'review-sdk-changes', label: 'SDK' },
  { value: 'review-api-changes', label: 'API' },
  { value: 'review-db-changes', label: 'DB' }
]

// A step's short label for the source filter; its own name when the list does
// not name it.
export function findingSourceLabel(step) {
  const source = FINDING_SOURCES.find((entry) => entry.value === step)
  return source ? source.label : String(step || '')
}

// The sources that actually recorded a finding, with how many each recorded, in
// the canonical step order. An unrecognized step follows in name order, so a
// state file from a newer skill is still selectable.
export function findingSources(findings) {
  const counts = new Map()
  for (const finding of findings || []) {
    const step = finding?.step
    if (!step) continue
    counts.set(step, (counts.get(step) || 0) + 1)
  }
  const known = FINDING_SOURCES.filter((source) => counts.has(source.value)).map((source) => ({
    ...source,
    count: counts.get(source.value)
  }))
  const unknown = [...counts.keys()]
    .filter((step) => !FINDING_SOURCES.some((source) => source.value === step))
    .sort((a, b) => a.localeCompare(b))
    .map((step) => ({ value: step, label: step, count: counts.get(step) }))
  return [...known, ...unknown]
}

// The statuses that mean a finding still asks something of the author: open
// (review-pr, validate-pr), or failing/unverified (verify-pr's criteria). An
// addressed, stale, wontfix, or conforming entry is not something to forward.
const ACTIONABLE_STATUSES = new Set(['open', 'fails', 'unverified'])

// The findings selected by default when the share list opens: the must and
// should items that still ask something of the author, as an array of keys. A
// decision the reviewer recorded earlier wins over that rule, so reopening the
// list shows the selection they left behind.
export function defaultSelectedFindings(findings) {
  return (findings || [])
    .filter((finding) => {
      if (finding.decision === 'include') return true
      if (finding.decision === 'skip') return false
      return finding.severity !== 'may' && ACTIONABLE_STATUSES.has(finding.status)
    })
    .map(findingKey)
}

// The prompt an agent is handed: the selected findings, addressed to the PR, so
// the agent can post them inline with its own skills (ghx) without restating the
// whole review. Findings are grouped by severity; an empty description is
// skipped.
export function buildFindingsPrompt(pr, findings) {
  const repository = pr.repository || `${pr.owner}/${pr.repo}`
  const lines = [
    `Post the selected review findings below as inline review comments on pull request ${repository}#${pr.number}.`,
    'Every comment must be attached inline to the file and line (or hunk) it is about;',
    'locate that line in the diff when the finding does not name it.',
    'Do not post them as general pull request comments, and do not leave a summary comment.',
    'Use your skills and the ghx CLI to post them, and include only these findings:',
    'do not add others and do not restate the rest of the review.',
    ''
  ]
  for (const severity of FINDING_SEVERITIES) {
    const items = (findings || []).filter((finding) => finding.severity === severity.value)
    if (!items.length) continue
    lines.push(`## ${severity.label}`, '')
    for (const finding of items) {
      lines.push(`### ${finding.title} _(${finding.step})_`)
      if (finding.description) lines.push('', finding.description)
      lines.push('')
    }
  }
  return lines.join('\n').trim()
}
