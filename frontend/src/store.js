import { reactive } from 'vue'
import { api } from './api'

export const store = reactive({
  tasks: [],
  tags: [],
  people: [],
  harnesses: [],
  repositories: [],
  groups: [],
  settings: {},
  loading: false,
  toast: null,
  // Tag filter applied to task lists ("" means every tag).
  tagFilter: '',
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
  async loadGroups() {
    this.groups = await api.groups.list()
  },
  async loadSettings() {
    this.settings = (await api.settings.get()).effective
  },
  toggleTagFilter(name) {
    this.tagFilter = this.tagFilter === name ? '' : name
  },
  notify(message, isError = false) {
    this.toast = { message, isError }
    clearTimeout(this._t)
    this._t = setTimeout(() => (this.toast = null), 4000)
  }
})

export function taskHasTag(task, name) {
  return (task.tags || []).includes(name)
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
