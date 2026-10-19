// Pure helpers for user-defined agent prompts, edited on the Settings page and
// shown as buttons in the agent panel. Nothing here makes a request: the panel
// hands in the task and the values it already has.

// The item kinds a prompt can target. A prompt appears in the agent panel only
// when the task has exactly one associated item of its kind, so the item
// variables ({owner}, {repository}, {number}, …) are unambiguous.
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

// The fields a linked item contributes. They are unprefixed when the task names
// exactly one item ({item_url}) and prefixed per item when it names several
// ({li.a.item_url}), so a prompt can single one out.
export const LINKED_ITEM_VARIABLES = [
  { token: 'item_url', label: 'Item link', description: 'The linked issue or pull request URL' },
  { token: 'item_title', label: 'Item title', description: 'The linked issue or pull request title' },
  { token: 'item_author', label: 'Item author', description: 'The GitHub login that opened it' },
  { token: 'item_state', label: 'Item state', description: 'Its state, such as open, closed, or merged' },
  { token: 'owner', label: 'Owner', description: 'The GitHub owner of the linked item' },
  { token: 'repository', label: 'Repository', description: 'The GitHub repository of the linked item' },
  { token: 'number', label: 'Number', description: 'Its issue or pull request number' }
]

// Every variable a prompt or a typed message can use. The panel renders these
// as clickable chips and the settings page lists them, so both stay in step
// with what resolution actually fills.
export const PROMPT_VARIABLE_GROUPS = [
  {
    label: 'Task',
    variables: [
      { token: 'task_id', label: 'Task id', description: 'The task id' },
      { token: 'title', label: 'Title', description: 'The task title' },
      { token: 'description', label: 'Description', description: 'The task description' },
      { token: 'status', label: 'Status', description: 'open, in progress, blocked, done, or archived' },
      { token: 'priority', label: 'Priority', description: 'low, medium, high, or urgent' },
      { token: 'deadline', label: 'Deadline', description: 'The deadline in ISO 8601, empty when none' },
      { token: 'tags', label: 'Tags', description: 'The task tags, comma separated' },
      { token: 'task_url', label: 'Task link', description: 'A link to the task in Agentic' }
    ]
  },
  {
    label: 'People',
    variables: [
      { token: 'people', label: 'People', description: 'People linked to the task' },
      { token: 'requested_by', label: 'Requested by', description: 'People who requested the task' }
    ]
  },
  {
    label: 'Repositories',
    variables: [
      { token: 'repositories', label: 'Repositories', description: 'The task repositories, one per line' },
      { token: 'worktree', label: 'Worktree', description: 'The active worktree path, empty when none' }
    ]
  },
  {
    label: 'Linked item',
    variables: LINKED_ITEM_VARIABLES
  }
]

// The flat variable list, in the order the groups appear.
export const PROMPT_VARIABLES = PROMPT_VARIABLE_GROUPS.flatMap((group) => group.variables)
const VARIABLE_TOKENS = PROMPT_VARIABLES.map((variable) => variable.token)

// Task priorities, matching store.PRIORITY_NAMES. Duplicated here so this
// module stays free of the store and its API client.
const PRIORITY_NAMES = { 0: 'low', 1: 'medium', 2: 'high', 3: 'urgent' }

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

// The task's linked GitHub items, each with its coordinates. A kind keeps one
// kind ("issue" or "pull_request"); no kind keeps both. Duplicate links (the
// same item twice) collapse to one entry.
export function linkedPromptItems(task, kind = null) {
  const out = []
  const seen = new Set()
  for (const assoc of task?.associations || []) {
    const item = assoc.item
    const coords = githubCoordinates(item)
    if (!coords) continue
    if (kind && coords.kind !== kind) continue
    const key = `${coords.owner}/${coords.repository}#${coords.number}`.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ item, coords })
  }
  return out
}

// A short identifier for the nth linked item: a, b, ..., z, then aa, ab, ...
export function itemIdentifier(index) {
  let n = Number(index) || 0
  let out = ''
  do {
    out = String.fromCharCode(97 + (n % 26)) + out
    n = Math.floor(n / 26) - 1
  } while (n >= 0)
  return out
}

// The per-item variables for a list of linked items, plus the labels that say
// which identifier names which item. Every item gets li.<id>.<field>, so a
// prompt can name a specific one when the task links several; li.<id> on its
// own is the compact owner/repository#number reference.
export function linkedItemVariables(items) {
  const variables = {}
  const labels = []
  ;(items || []).forEach(({ item, coords }, index) => {
    const id = itemIdentifier(index)
    const prefix = `li.${id}`
    const meta = item?.metadata_json || {}
    variables[prefix] = `${coords.owner}/${coords.repository}#${coords.number}`
    variables[`${prefix}.item_url`] = item?.url || ''
    variables[`${prefix}.item_title`] = item?.title || ''
    variables[`${prefix}.item_author`] = String(meta.author || meta.login || meta.user || '')
    variables[`${prefix}.item_state`] = String(meta.state || '')
    variables[`${prefix}.owner`] = coords.owner
    variables[`${prefix}.repository`] = coords.repository
    variables[`${prefix}.number`] = String(coords.number)
    labels.push({ id, prefix, item, coords })
  })
  return { variables, labels }
}

function names(people) {
  return (people || [])
    .map((person) => person?.name)
    .filter(Boolean)
    .join(', ')
}

// The repositories a task names, as paths (falling back to their names). The
// task carries only ids, so the panel passes the store's repositories.
function repositoryLabels(task, repositories) {
  const byId = new Map((repositories || []).map((repo) => [repo.id, repo]))
  return (task?.repository_ids || [])
    .map((id) => byId.get(id))
    .filter(Boolean)
    .map((repo) => repo.path || repo.name)
}

// The values every variable resolves to for a task and, when one is in play, a
// single linked item (the panel only names an item when the task has exactly
// one of the panel's kind, so the item variables are never ambiguous).
export function taskVariables(task, item = null, { repositories = [], taskUrl = '' } = {}) {
  const coords = item ? githubCoordinates(item) : null
  const meta = item?.metadata_json || {}
  const worktree = (task?.worktrees || []).find((entry) => entry.status === 'active')
  return {
    task_id: task?.id || '',
    title: task?.title || '',
    description: task?.description || '',
    status: task?.status ? String(task.status) : '',
    priority: PRIORITY_NAMES[Number(task?.priority)] || '',
    deadline: task?.deadline ? String(task.deadline) : '',
    tags: (task?.tags || []).join(', '),
    task_url: taskUrl || (task?.id ? `/task/${task.id}` : ''),
    people: names(task?.people),
    requested_by: names(task?.requesters),
    repositories: repositoryLabels(task, repositories).join('\n'),
    worktree: worktree?.path || '',
    item_url: item?.url || '',
    item_title: item?.title || '',
    item_author: String(meta.author || meta.login || meta.user || ''),
    item_state: String(meta.state || ''),
    owner: coords?.owner || '',
    repository: coords?.repository || '',
    number: coords ? String(coords.number) : ''
  }
}

// A per-item token: {li.a.item_url}, or {li.a} for the compact reference.
const LINKED_ITEM_TOKEN = /\{li\.([a-z]{1,2})(?:\.([a-z_]+))?\}/g

// Fill a template's variables. Unknown placeholders are left as they are, so a
// template that names something this app does not know stays readable.
export function resolvePromptTemplate(template, variables = {}) {
  let out = String(template || '')
  for (const token of VARIABLE_TOKENS) {
    out = out.replaceAll(`{${token}}`, String(variables[token] ?? ''))
  }
  out = out.replace(LINKED_ITEM_TOKEN, (match, id, field) => {
    const key = field ? `li.${id}.${field}` : `li.${id}`
    return key in variables ? String(variables[key] ?? '') : match
  })
  return out
}

// Whether a message is a command (a skill or slash command) rather than a
// free-form prompt. Commands carry their own arguments, so the panel does not
// append context to them.
export function isCommandPrompt(text) {
  return /^[$/]/.test(String(text || '').trimStart())
}

// The block of context the panel attaches to a submitted message: the task it
// belongs to and the linked items the current view is about (the issue in the
// issue view, the pull requests in the PR view).
export function buildPromptContext(task, items, { repositories = [] } = {}) {
  if (!task) return ''
  const priority = PRIORITY_NAMES[Number(task.priority)]
  const status = [String(task.status || ''), priority && `priority ${priority}`].filter(Boolean).join(', ')
  const lines = ['# Context', `- Task: ${task.title || '(untitled)'} (${task.id})`]
  if (status) lines.push(`- Status: ${status}`)
  const repos = repositoryLabels(task, repositories)
  if (repos.length) lines.push(`- Repositories: ${repos.join(', ')}`)
  for (const { item, coords } of items || []) {
    const label = coords.kind === 'pull_request' ? 'Pull request' : 'Issue'
    const title = item?.title ? ` (${item.title})` : ''
    lines.push(`- ${label}: ${item?.url || ''}${title}`)
  }
  return lines.join('\n')
}

// The prompt buttons to show for a task. A prompt appears only when exactly one
// associated item of its kind carries GitHub coordinates; tasks with two issues
// (or two pull requests) of the same kind show nothing for that kind.
export function taskPrompts(task, prompts, variables = {}) {
  return (prompts || []).flatMap((prompt, index) => {
    const matches = linkedPromptItems(task, prompt.kind)
    if (matches.length !== 1) return []
    const { item, coords } = matches[0]
    const values = {
      ...variables,
      owner: coords.owner,
      repository: coords.repository,
      number: String(coords.number)
    }
    return [
      {
        key: `${index}:${prompt.kind}`,
        kind: prompt.kind,
        label: prompt.label || prompt.template,
        item,
        coords,
        text: resolvePromptTemplate(prompt.template, values)
      }
    ]
  })
}
