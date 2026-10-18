// Grouping for the tasks list. Pure: the view hands it the tasks it has already
// filtered, plus the people and repositories loaded in the store, so no request
// is involved.

import { priorityLabel, statusLabel } from './store'

// The orders the tasks list can be grouped by, as a display choice. "None" is
// the flat list; every other value splits it into one section per group.
export const TASK_GROUPINGS = [
  { value: '', label: 'None' },
  { value: 'status', label: 'Status' },
  { value: 'priority', label: 'Priority' },
  { value: 'person', label: 'Person' },
  { value: 'tag', label: 'Tag' },
  { value: 'repository', label: 'Repository' }
]

// Most urgent first, so the work that matters leads.
const PRIORITY_ORDER = [3, 2, 1, 0]
const STATUS_ORDER = ['open', 'in_progress', 'blocked', 'done', 'archived']

function addTask(buckets, key, label, task) {
  const bucket = buckets.get(key)
  if (bucket) bucket.tasks.push(task)
  else buckets.set(key, { key, label, tasks: [task] })
}

// Buckets in name order, with the "No …" fallback (an empty key) kept last so a
// group of unassigned tasks never leads the list.
function byName(buckets) {
  return [...buckets.values()].sort((a, b) => {
    if (!a.key) return 1
    if (!b.key) return -1
    return a.label.localeCompare(b.label)
  })
}

function capitalize(value) {
  const text = String(value || '')
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text
}

// The tasks grouped by one facet, each group preserving the input order. A task
// with several values (people, tags) appears under each of them; with none it
// falls into the facet's "No …" group. Only non-empty groups are returned.
export function groupTasks(tasks, groupBy, { people = [], repositories = [] } = {}) {
  const list = [...(tasks || [])]
  if (!groupBy) return [{ key: '', label: null, tasks: list }]

  if (groupBy === 'status') {
    return STATUS_ORDER.map((status) => ({ status, tasks: list.filter((task) => task.status === status) }))
      .filter((group) => group.tasks.length)
      .map((group) => ({ key: group.status, label: statusLabel(group.status), tasks: group.tasks }))
  }

  if (groupBy === 'priority') {
    return PRIORITY_ORDER.map((priority) => ({
      priority,
      tasks: list.filter((task) => Number(task.priority ?? 2) === priority)
    }))
      .filter((group) => group.tasks.length)
      .map((group) => ({
        key: String(group.priority),
        label: capitalize(priorityLabel(group.priority)),
        tasks: group.tasks
      }))
  }

  const buckets = new Map()

  if (groupBy === 'person') {
    const names = new Map(people.map((person) => [person.id, person.name]))
    for (const task of list) {
      const ids = (task.person_ids || []).filter((id) => names.has(id))
      if (!ids.length) addTask(buckets, '', 'No person', task)
      else for (const id of ids) addTask(buckets, id, names.get(id), task)
    }
    return byName(buckets)
  }

  if (groupBy === 'tag') {
    for (const task of list) {
      const tags = task.tags || []
      if (!tags.length) addTask(buckets, '', 'No tags', task)
      else for (const tag of tags) addTask(buckets, tag, tag, task)
    }
    return byName(buckets)
  }

  if (groupBy === 'repository') {
    // The main repository: the first one linked to the task, in link order.
    const names = new Map(repositories.map((repository) => [repository.id, repository.name]))
    for (const task of list) {
      const main = (task.repository_ids || [])[0]
      if (!main || !names.has(main)) addTask(buckets, '', 'No repository', task)
      else addTask(buckets, main, names.get(main), task)
    }
    return byName(buckets)
  }

  return [{ key: '', label: null, tasks: list }]
}
