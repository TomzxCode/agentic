// Pure helpers for user-defined agent prompts, edited on the Settings page and
// shown as buttons in the agent panel. Nothing here makes a request: the panel
// hands in the task and the prompt list it already has.

// The item kinds a prompt can target. A prompt appears in the agent panel only
// when the task has exactly one associated item of its kind, so {owner},
// {repository}, and {number} are unambiguous.
export const PROMPT_KINDS = [
  { value: 'issue', label: 'Issue' },
  { value: 'pull_request', label: 'Pull request' }
]

// The prompts seeded when the user has not saved any of their own. Kept in sync
// with DEFAULT_AGENT_PROMPTS in the backend's settings_store.
export const DEFAULT_AGENT_PROMPTS = [
  { kind: 'pull_request', label: 'Review PR', template: '$review-pr-full {number} {owner}/{repository}' },
  { kind: 'issue', label: 'Triage issue', template: '$triage-issue {number} {owner}/{repository}' }
]

function normalize(list) {
  if (!Array.isArray(list)) return []
  return list
    .filter((entry) => entry && typeof entry === 'object')
    .map((entry) => ({
      kind: entry.kind === 'pull_request' ? 'pull_request' : 'issue',
      label: String(entry.label || ''),
      template: String(entry.template || '')
    }))
    .filter((entry) => entry.template.trim())
}

// The prompt list stored in settings is a JSON string. Tolerate a missing,
// empty, or malformed value (or an already-parsed list) so a bad setting never
// breaks the panel or the settings page.
export function parseAgentPrompts(raw) {
  if (Array.isArray(raw)) return normalize(raw)
  if (typeof raw !== 'string' || !raw.trim()) return []
  try {
    return normalize(JSON.parse(raw))
  } catch {
    return []
  }
}

// The GitHub coordinates an item contributes, or null when the item is not a
// GitHub issue/pull request with fetched metadata (the source of {owner},
// {repository}, and {number}).
export function githubCoordinates(item) {
  if (item?.source !== 'github') return null
  const meta = item.metadata_json || {}
  const kind = item.kind === 'pull_request' || meta.kind === 'pull_request' ? 'pull_request' : 'issue'
  const { owner, repo: repository, number } = meta
  if (!owner || !repository || number == null) return null
  return { kind, owner, repository, number }
}

// Fill a template's placeholders. Unknown placeholders are left as they are.
export function resolvePromptTemplate(template, { owner, repository, number }) {
  return String(template || '')
    .replaceAll('{owner}', String(owner ?? ''))
    .replaceAll('{repository}', String(repository ?? ''))
    .replaceAll('{number}', number == null ? '' : String(number))
}

// The prompt buttons to show for a task. A prompt appears only when exactly one
// associated item of its kind carries GitHub coordinates; tasks with two issues
// (or two pull requests) of the same kind show nothing for that kind.
export function taskPrompts(task, prompts) {
  const byKind = {}
  for (const assoc of task?.associations || []) {
    const coords = githubCoordinates(assoc.item)
    if (!coords) continue
    ;(byKind[coords.kind] ||= []).push({ item: assoc.item, coords })
  }
  return (prompts || []).flatMap((prompt, index) => {
    const matches = byKind[prompt.kind] || []
    if (matches.length !== 1) return []
    const { item, coords } = matches[0]
    return [
      {
        key: `${index}:${prompt.kind}`,
        kind: prompt.kind,
        label: prompt.label || prompt.template,
        item,
        text: resolvePromptTemplate(prompt.template, coords)
      }
    ]
  })
}
