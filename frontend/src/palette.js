// The command palette's entries, built from what the store already holds.
// Pure data: the caller passes the refs and actions the entries close over.

import { computed } from 'vue'

import { SETTINGS_SECTIONS } from './settings'
import { aliasLabel, sourceLabel, store } from './store'

export function buildPaletteItems({ route, router, showNew, sidebarHidden, toggleSidebar }) {
  // Command palette: navigate anywhere (and a couple of actions) from the keyboard.
  const taskFieldItems = computed(() =>
    route.name === 'task'
      ? [
          {
            id: 'field-title',
            label: 'Edit title',
            group: 'This task',
            icon: 'title',
            run: () => store.focusField?.('title')
          },
          {
            id: 'field-description',
            label: 'Edit description',
            group: 'This task',
            icon: 'description',
            run: () => store.focusField?.('description')
          },
          {
            id: 'field-status',
            label: 'Set status',
            group: 'This task',
            icon: 'status',
            run: () => store.focusField?.('status')
          },
          {
            id: 'field-priority',
            label: 'Set priority',
            group: 'This task',
            icon: 'priority',
            run: () => store.focusField?.('priority')
          },
          {
            id: 'field-deadline',
            label: 'Set deadline',
            group: 'This task',
            icon: 'deadline',
            run: () => store.focusField?.('deadline')
          },
          {
            id: 'field-repository',
            label: 'Add repository',
            group: 'This task',
            icon: 'repositories',
            run: () => store.focusField?.('repository')
          },
          {
            id: 'field-people',
            label: 'Link a person',
            group: 'This task',
            icon: 'personPlus',
            run: () => store.focusField?.('people')
          },
          {
            id: 'field-requesters',
            label: 'Link a requester',
            group: 'This task',
            icon: 'personCheck',
            run: () => store.focusField?.('requesters')
          },
          {
            id: 'field-dependencies',
            label: 'Link a dependency',
            group: 'This task',
            icon: 'link',
            run: () => store.focusField?.('dependencies')
          },
          {
            id: 'field-tags',
            label: 'Set tags',
            group: 'This task',
            icon: 'tag',
            run: () => store.focusField?.('tags')
          }
        ]
      : []
  )

  // One palette entry per tag in use: pick it to filter the task list by that tag.
  const tagItems = computed(() =>
    store.tags.map((tag) => ({
      id: `tag-${tag.name}`,
      label: `Filter by tag: ${tag.name}`,
      group: 'Tags',
      icon: 'tag',
      hint: store.tagFilter === tag.name ? 'active' : String(tag.count),
      keywords: tag.name,
      run: () => {
        store.tagFilter = tag.name
        router.push('/')
      }
    }))
  )

  // One palette entry per person: pick it to open that person's page. Aliases are
  // shown as the hint and are searchable, so a handle or email finds the person.
  const personItems = computed(() =>
    store.people.map((person) => ({
      id: `person-${person.id}`,
      label: person.name,
      group: 'People',
      icon: 'people',
      hint: (person.aliases || []).map(aliasLabel).join(' · ') || undefined,
      keywords: (person.aliases || []).join(' '),
      run: () => router.push(`/person/${person.id}`)
    }))
  )

  // One palette entry per resource: pick it to open that item's page. The source
  // is shown as the hint and is searchable, so "github" or "slack" narrows the
  // list.
  const itemItems = computed(() =>
    store.items.map((item) => ({
      id: `item-${item.id}`,
      label: item.title || item.url || 'Untitled item',
      group: 'Items',
      icon: 'items',
      hint: sourceLabel(item.source),
      keywords: [item.source, item.kind, item.url].filter(Boolean).join(' '),
      run: () => router.push(`/items/${item.id}`)
    }))
  )

  // One palette entry per repository: pick it to open that repository's page. Its
  // path and remote are searchable, so a directory or "github" narrows the list.
  const repositoryItems = computed(() =>
    store.repositories.map((repository) => ({
      id: `repository-${repository.id}`,
      label: repository.name || repository.path,
      group: 'Repositories',
      icon: 'repositories',
      hint: repository.path,
      keywords: [repository.path, repository.remote_url].filter(Boolean).join(' '),
      run: () => router.push(`/repositories/${repository.id}`)
    }))
  )

  // One palette entry per Settings section: pick it to open that section. The
  // group header names Settings, and "settings" is searchable, so the whole list
  // appears under that one word.
  const settingsItems = computed(() =>
    SETTINGS_SECTIONS.map((section) => ({
      id: `settings-${section.id}`,
      label: section.label,
      group: 'Settings',
      icon: 'settings',
      keywords: `settings ${section.id}`,
      run: () => router.push({ path: '/settings', query: { section: section.id } })
    }))
  )

  return [
    {
      id: 'new-task',
      label: 'New task',
      hint: '⌘N',
      group: 'Actions',
      icon: 'plus',
      run: () => (showNew.value = true)
    },
    {
      id: 'focus-hints',
      label: 'Show focus hints',
      hint: 'f',
      group: 'Actions',
      icon: 'keyboard',
      run: () => (store.hintMode = true)
    },
    {
      id: 'toggle-sidebar',
      label: sidebarHidden.value ? 'Show task list' : 'Hide task list',
      hint: '⌘B',
      group: 'Actions',
      icon: 'panel',
      keywords: 'sidebar panel collapse',
      run: toggleSidebar
    },
    ...(store.tagFilter
      ? [
          {
            id: 'clear-tag-filter',
            label: `Clear tag filter: ${store.tagFilter}`,
            group: 'Actions',
            icon: 'close',
            run: () => (store.tagFilter = '')
          }
        ]
      : []),
    ...taskFieldItems.value,
    { id: 'go-tasks', label: 'Go to tasks', group: 'Navigation', icon: 'tasks', run: () => router.push('/') },
    { id: 'go-inbox', label: 'Go to inbox', group: 'Navigation', icon: 'inbox', run: () => router.push('/inbox') },
    {
      id: 'go-reviews',
      label: 'Go to review queue',
      group: 'Navigation',
      icon: 'reviews',
      run: () => router.push('/reviews')
    },
    { id: 'go-stack', label: 'Go to stack', group: 'Navigation', icon: 'stack', run: () => router.push('/stack') },
    { id: 'go-gantt', label: 'Go to gantt', group: 'Navigation', icon: 'gantt', run: () => router.push('/gantt') },
    { id: 'go-graph', label: 'Go to graph', group: 'Navigation', icon: 'graph', run: () => router.push('/graph') },
    {
      id: 'go-metrics',
      label: 'Go to metrics',
      group: 'Navigation',
      icon: 'metrics',
      run: () => router.push('/metrics')
    },
    {
      id: 'go-items',
      label: 'Go to resources',
      group: 'Navigation',
      icon: 'items',
      run: () => router.push('/items')
    },
    { id: 'go-people', label: 'Go to people', group: 'Navigation', icon: 'people', run: () => router.push('/people') },
    {
      id: 'go-repositories',
      label: 'Go to repositories',
      group: 'Navigation',
      icon: 'repositories',
      run: () => router.push('/repositories')
    },
    {
      id: 'go-schedules',
      label: 'Go to scheduled tasks',
      group: 'Navigation',
      icon: 'schedule',
      run: () => router.push('/schedules')
    },
    {
      id: 'go-settings',
      label: 'Go to settings',
      group: 'Navigation',
      icon: 'settings',
      run: () => router.push('/settings')
    },
    ...tagItems.value,
    ...store.tasks.map((task) => ({
      id: `task-${task.id}`,
      label: task.title,
      group: 'Tasks',
      icon: 'tasks',
      hint: [task.status.replace('_', ' '), ...(task.tags || []).map((tag) => `#${tag}`)].join(' '),
      keywords: (task.tags || []).join(' '),
      run: () => router.push(`/task/${task.id}`)
    })),
    ...itemItems.value,
    ...repositoryItems.value,
    ...settingsItems.value,
    ...personItems.value
  ]
}
