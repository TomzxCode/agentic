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
// the agent can post them with its own skills (ghx) without restating the whole
// review. Findings are grouped by severity; an empty description is skipped.
export function buildFindingsPrompt(pr, findings) {
  const repository = pr.repository || `${pr.owner}/${pr.repo}`
  const lines = [
    `Post the selected review findings below as comments on pull request ${repository}#${pr.number}.`,
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
