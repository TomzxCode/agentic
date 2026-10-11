import { reactive } from 'vue'
import { api } from './api'

export const store = reactive({
  tasks: [],
  harnesses: [],
  repositories: [],
  groups: [],
  settings: {},
  loading: false,
  toast: null,
  // Set by the active task page so the palette can jump to its fields.
  focusField: null,
  // Focus-hint mode: press f to reveal a letter over each control.
  hintMode: false,

  async loadTasks() {
    this.tasks = await api.tasks.list()
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
  notify(message, isError = false) {
    this.toast = { message, isError }
    clearTimeout(this._t)
    this._t = setTimeout(() => (this.toast = null), 4000)
  }
})

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
