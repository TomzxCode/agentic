import { reactive } from 'vue'
import { api } from './api'
import { itemStatus } from './repositories/parse'

// The grouping chosen on the tasks page is a per-device view preference, so it
// is remembered in localStorage rather than on the server.
const GROUP_BY_KEY = 'agentic.taskGroup'

function readStoredGroupBy() {
  try {
    return localStorage.getItem(GROUP_BY_KEY) || ''
  } catch {
    // Storage can be blocked (private mode); fall back to no grouping.
    return ''
  }
}

export const store = reactive({
  tasks: [],
  tags: [],
  people: [],
  harnesses: [],
  repositories: [],
  items: [],
  groups: [],
  settings: {},
  inbox: [],
  inboxCount: 0,
  loading: false,
  toast: null,
  // Tag filter applied to task lists ("" means every tag).
  tagFilter: '',
  // Person filter applied to the tasks page ("" means every person).
  personFilter: '',
  // Status filter applied to the tasks page ("" means the in-flight default).
  statusFilter: '',
  // Grouping applied to the tasks page ("" means one flat list).
  groupBy: readStoredGroupBy(),
  // Set by the active task page so the palette can jump to its fields.
  focusField: null,
  // Focus-hint mode: press f to reveal a letter over each control.
  hintMode: false,

  async loadTasks() {
    this.tasks = await api.tasks.list()
  },
  async loadTags() {
    this.tags = await api.tags.list()
  },
  async loadPeople() {
    this.people = await api.people.list()
  },
  async createPerson(name) {
    const person = await api.people.create({ name })
    this.people = [...this.people, person].sort((a, b) => a.name.localeCompare(b.name))
    return person
  },
  async loadHarnesses() {
    this.harnesses = await api.harnesses.list()
  },
  async loadRepositories() {
    this.repositories = await api.repositories.list()
  },
  async loadItems() {
    this.items = await api.items.list()
  },
  async loadGroups() {
    this.groups = await api.groups.list()
  },
  async loadSettings() {
    this.settings = (await api.settings.get()).effective
  },
  async loadInbox() {
    const report = await api.inbox.get()
    this.inbox = report.suggestions || []
    this.inboxCount = report.count ?? this.inbox.length
  },
  toggleTagFilter(name) {
    this.tagFilter = this.tagFilter === name ? '' : name
  },
  togglePersonFilter(id) {
    this.personFilter = this.personFilter === id ? '' : id
  },
  toggleStatusFilter(status) {
    this.statusFilter = this.statusFilter === status ? '' : status
  },
  // Set the tasks page grouping and remember it for the next visit.
  setGroupBy(value) {
    this.groupBy = value
    try {
      localStorage.setItem(GROUP_BY_KEY, value)
    } catch {
      // Not fatal: the choice still applies for this session.
    }
  },
  notify(message, isError = false) {
    this.toast = { message, isError }
    clearTimeout(this._t)
    this._t = setTimeout(() => (this.toast = null), 4000)
  },
  // A refresh that could not fetch (a missing or failing ghx/slackx) carries a
  // fetch_error; show it as an error rather than reporting a silent success.
  notifyRefresh(result, okMessage = 'Refreshed') {
    if (result?.fetch_error) this.notify(result.fetch_error, true)
    else this.notify(okMessage)
  }
})

export function taskHasTag(task, name) {
  return (task.tags || []).includes(name)
}

export function taskHasPerson(task, id) {
  return (task.person_ids || []).includes(id)
}

// A person's alias rendered with a leading @ when it is a handle (has no @)
// rather than an email.
export function aliasLabel(value) {
  return String(value).includes('@') ? String(value) : `@${value}`
}

// An item's source (github, slack, note, …) rendered as a human label, falling
// back to the raw value for a source with no label. SOURCE_ORDER is the display
// order for grouping and filtering items by source.
export const SOURCE_LABELS = {
  github: 'GitHub',
  slack: 'Slack',
  gdrive: 'Google Drive',
  url: 'Web',
  note: 'Note',
  commit: 'Commit',
  file: 'File'
}

export const SOURCE_ORDER = ['github', 'slack', 'gdrive', 'url', 'note', 'commit', 'file']

export function sourceLabel(source) {
  return SOURCE_LABELS[source] || source
}

export function statusLabel(status) {
  return (
    {
      open: 'Open',
      in_progress: 'In progress',
      blocked: 'Blocked',
      done: 'Done',
      archived: 'Archived'
    }[status] || status
  )
}

export function statusClass(status) {
  return (
    {
      open: 'badge',
      in_progress: 'badge run',
      blocked: 'badge warn',
      done: 'badge ok',
      archived: 'badge'
    }[status] || 'badge'
  )
}

// Task priority levels, 0 = low, 1 = medium, 2 = high, 3 = urgent. The store
// owns the names so the timeline, task cards, and the priority icon agree.
export const PRIORITY_NAMES = { 0: 'low', 1: 'medium', 2: 'high', 3: 'urgent' }

export function priorityLabel(priority) {
  return PRIORITY_NAMES[Number(priority)] || 'medium'
}

// A GitHub pull request item's display status, or null when the item is not a
// PR or carries no fetched state. ghx reports state as OPEN / CLOSED / MERGED,
// with a separate draft flag for an open PR.
export function prStatus(item) {
  const meta = item?.metadata_json || {}
  if (item?.kind !== 'pull_request' && meta.kind !== 'pull_request') return null
  return itemStatus(item)
}

export function timeAgo(iso) {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (secs < 60) return 'just now'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

// An absolute timestamp in the local zone as "YYYY-MM-DD HH:MM" (24-hour), for a
// value that should read as a date rather than an interval. Returns '' for a
// missing or unparseable value.
export function formatDateTime(iso, timeZone) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  if (timeZone) {
    // Render the wall clock in a chosen zone (such as a schedule's), instead of
    // the browser's, so a cron expression and the times it produces agree.
    try {
      const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23'
      }).formatToParts(date)
      const part = (type) => parts.find((p) => p.type === type)?.value || ''
      return `${part('year')}-${part('month')}-${part('day')} ${part('hour')}:${part('minute')}`
    } catch {
      // An unknown zone to this browser: fall back to the browser's own.
    }
  }
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

// The state of a deadline relative to now: overdue, due soon, or later. Returns
// null when there is no (parseable) deadline. The comparison is by calendar day
// so "due today" means today, whatever the time.
export function deadlineInfo(iso, now = Date.now()) {
  if (!iso) return null
  const at = new Date(iso).getTime()
  if (Number.isNaN(at)) return null
  const day = 86400000
  if (at < now) {
    const over = now - at
    const label = over < day ? 'Overdue' : `Overdue ${Math.ceil(over / day)}d`
    return { overdue: true, tone: 'danger', label }
  }
  const startOfDay = (t) => {
    const d = new Date(t)
    d.setHours(0, 0, 0, 0)
    return d.getTime()
  }
  const days = Math.round((startOfDay(at) - startOfDay(now)) / day)
  if (days === 0) return { overdue: false, tone: 'warn', label: 'Due today' }
  if (days === 1) return { overdue: false, tone: 'warn', label: 'Due tomorrow' }
  return { overdue: false, tone: '', label: `Due in ${days}d` }
}

// A deadline rendered in the reader's local time zone as "YYYY-MM-DD HH:MM"
// (24-hour), the same absolute format as formatDateTime.
export function formatDeadline(iso) {
  return formatDateTime(iso)
}

export function formatDuration(ms) {
  const secs = Math.max(0, Math.floor((ms || 0) / 1000))
  if (secs < 60) return '<1m'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ${mins % 60}m`
  const days = Math.floor(hours / 24)
  return `${days}d ${hours % 24}h`
}

// Total time a task spent in each status, reconstructed from its status changes.
// The first change's "from" is the status at creation; with no changes the task
// has held its current status since it was created. Spans are returned in the
// order the statuses were first entered.
export function statusDurations(task, events, now = Date.now()) {
  if (!task || !task.created_at) return []
  const created = new Date(task.created_at).getTime()
  if (Number.isNaN(created)) return []

  const transitions = (events || [])
    .map((event) => {
      const delta = event?.data_json?.changes?.status
      if (!delta || !delta.from || !delta.to || delta.from === delta.to) return null
      const at = new Date(event.created_at).getTime()
      if (Number.isNaN(at)) return null
      return { at, from: delta.from, to: delta.to }
    })
    .filter(Boolean)
    .sort((a, b) => a.at - b.at)

  const spans = []
  const add = (status, ms) => {
    if (!status || ms <= 0) return
    const existing = spans.find((span) => span.status === status)
    if (existing) existing.ms += ms
    else spans.push({ status, ms })
  }

  let current = transitions.length ? transitions[0].from : task.status
  let cursor = created
  for (const transition of transitions) {
    add(current, transition.at - cursor)
    current = transition.to
    cursor = transition.at
  }
  add(current, Math.max(0, now - cursor))
  return spans
}
