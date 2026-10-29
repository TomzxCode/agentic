// The rule vocabulary shared by the checklist settings form. The backend
// validates the same field and operator names in agentic/checklists.py; keep
// the two lists in step when adding a rule type.

export const CHECKLIST_STATUSES = [
  { value: 'open', label: 'Open' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'done', label: 'Done' },
  { value: 'archived', label: 'Archived' }
]

export const CHECKLIST_PRIORITIES = [
  { value: '0', label: 'Low' },
  { value: '1', label: 'Medium' },
  { value: '2', label: 'High' },
  { value: '3', label: 'Urgent' }
]

// `kind` picks the value control: a fixed option list, a person picker, a tag
// input, or pickers for people, repositories, and other tasks.
export const CHECKLIST_FIELDS = [
  { value: 'status', label: 'Status', kind: 'status' },
  { value: 'priority', label: 'Priority', kind: 'priority' },
  { value: 'waiting_on', label: 'Waiting on', kind: 'person' },
  { value: 'tags', label: 'Tags', kind: 'tags' },
  { value: 'people', label: 'People', kind: 'people' },
  { value: 'requested_by', label: 'Requested by', kind: 'people' },
  { value: 'repositories', label: 'Repositories', kind: 'repositories' },
  { value: 'before', label: 'Before task', kind: 'tasks' },
  { value: 'after', label: 'After task', kind: 'tasks' },
  { value: 'related', label: 'Related task', kind: 'tasks' }
]

const LIST_OPERATORS = [
  { value: 'has_any', label: 'has any of' },
  { value: 'has_all', label: 'has all of' },
  { value: 'has_none', label: 'has none of' }
]

const SCALAR_OPERATORS = [
  { value: 'is_any', label: 'is any of' },
  { value: 'is_not_any', label: 'is not any of' }
]

const WAITING_OPERATORS = [
  ...SCALAR_OPERATORS,
  { value: 'is_set', label: 'is set' },
  { value: 'is_not_set', label: 'is not set' }
]

export function fieldDefinition(field) {
  return CHECKLIST_FIELDS.find((entry) => entry.value === field) || CHECKLIST_FIELDS[0]
}

export function operatorsFor(field) {
  if (field === 'waiting_on') return WAITING_OPERATORS
  const kind = fieldDefinition(field).kind
  return kind === 'status' || kind === 'priority' ? SCALAR_OPERATORS : LIST_OPERATORS
}

export function ruleNeedsValues(field, op) {
  return !(field === 'waiting_on' && (op === 'is_set' || op === 'is_not_set'))
}

// A rule's starting values when its field, or its operator, changes.
export function defaultValues(field) {
  const kind = fieldDefinition(field).kind
  if (kind === 'status') return ['open']
  if (kind === 'priority') return ['2']
  return []
}

export function newRule(field = CHECKLIST_FIELDS[0].value) {
  const op = operatorsFor(field)[0].value
  return { field, op, values: defaultValues(field) }
}
// One item per line, trimmed, without blanks or duplicates (the backend does
// the same normalization, so the saved list matches what was typed).
export function parseItemsText(text) {
  const seen = new Set()
  const items = []
  for (const line of String(text || '').split('\n')) {
    const item = line.trim()
    if (!item || seen.has(item)) continue
    seen.add(item)
    items.push(item)
  }
  return items
}
