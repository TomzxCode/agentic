<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { store, statusClass, timeAgo } from './store'
import SearchSelect from './components/SearchSelect.vue'
import CommandPalette from './components/CommandPalette.vue'

const route = useRoute()
const router = useRouter()
const search = ref('')
const showNew = ref(false)
const sidebarOpen = ref(false)
const paletteOpen = ref(false)
const draft = ref({ title: '', description: '', priority: 2, group_id: '', github_url: '' })

// "Import from GitHub" state.
const importRepo = ref('')
const issues = ref([])
const loadingIssues = ref(false)
const issueFilter = ref('')
const pickedIssue = ref(null)
const issueUrl = ref('')
const loadingIssue = ref(false)

watch(() => route.fullPath, () => {
  sidebarOpen.value = false
  store.hintMode = false
})

const GITHUB_ISSUE_RE = /github\.com\/[^/\s]+\/[^/\s]+\/(?:issues|pull)\/\d+/i

const githubRepos = computed(() =>
  store.repositories.filter((r) => (r.remote_url || '').includes('github.com')),
)

const priorityOptions = [
  { value: 0, label: 'Low' },
  { value: 1, label: 'Medium' },
  { value: 2, label: 'High' },
  { value: 3, label: 'Urgent' },
]
const groupOptions = computed(() => [
  { value: '', label: 'None' },
  ...store.groups.map((g) => ({ value: g.id, label: g.name })),
])
const importRepoOptions = computed(() => githubRepos.value.map((r) => ({ value: r.id, label: r.name })))

// Command palette: navigate anywhere (and a couple of actions) from the keyboard.
const taskFieldItems = computed(() =>
  route.name === 'task'
    ? [
        { id: 'field-title', label: 'Edit title', group: 'This task', run: () => store.focusField?.('title') },
        { id: 'field-description', label: 'Edit description', group: 'This task', run: () => store.focusField?.('description') },
        { id: 'field-status', label: 'Set status', group: 'This task', run: () => store.focusField?.('status') },
        { id: 'field-priority', label: 'Set priority', group: 'This task', run: () => store.focusField?.('priority') },
        { id: 'field-group', label: 'Set repository group', group: 'This task', run: () => store.focusField?.('group') },
        { id: 'field-repository', label: 'Add repository', group: 'This task', run: () => store.focusField?.('repository') },
      ]
    : [],
)

const paletteItems = computed(() => [
  { id: 'new-task', label: 'New task', group: 'Actions', run: () => (showNew.value = true) },
  { id: 'focus-hints', label: 'Show field shortcuts', hint: 'f', group: 'Actions', run: () => (store.hintMode = true) },
  ...taskFieldItems.value,
  { id: 'go-tasks', label: 'Go to tasks', group: 'Navigation', run: () => router.push('/') },
  { id: 'go-items', label: 'Go to resources', group: 'Navigation', run: () => router.push('/items') },
  { id: 'go-settings', label: 'Go to settings', group: 'Navigation', run: () => router.push('/settings') },
  ...store.tasks.map((task) => ({
    id: `task-${task.id}`,
    label: task.title,
    group: 'Tasks',
    hint: task.status.replace('_', ' '),
    run: () => router.push(`/task/${task.id}`),
  })),
])

function runPaletteItem(item) {
  item.run?.()
}

function isTyping(target) {
  return !!target && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)
}

function onGlobalKeydown(event) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    paletteOpen.value = !paletteOpen.value
    return
  }
  if (store.hintMode) {
    if (event.key === 'Escape' || event.key === 'f') {
      event.preventDefault()
      store.hintMode = false
      return
    }
    const action = store.hintMap[event.key.toLowerCase()]
    if (action) {
      event.preventDefault()
      action()
      store.hintMode = false
    }
    return
  }
  if (event.key === 'Escape') {
    if (paletteOpen.value) paletteOpen.value = false
    else if (showNew.value) showNew.value = false
    return
  }
  if (
    event.key.toLowerCase() === 'f' &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.altKey &&
    !isTyping(event.target) &&
    !paletteOpen.value &&
    !showNew.value &&
    Object.keys(store.hintMap).length
  ) {
    event.preventDefault()
    store.hintMode = true
  }
}

// Newest issues first (by number), with a text filter.
const sortedIssues = computed(() => {
  const q = issueFilter.value.trim().toLowerCase()
  const list = [...issues.value].sort((a, b) => (b.number ?? 0) - (a.number ?? 0))
  if (!q) return list
  return list.filter((i) => i.title.toLowerCase().includes(q) || String(i.number).includes(q))
})

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return store.tasks
  return store.tasks.filter(
    (p) => p.title.toLowerCase().includes(q) || (p.summary || '').toLowerCase().includes(q),
  )
})

async function refresh() {
  store.loading = true
  try {
    await store.loadTasks()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    store.loading = false
  }
}

function resetDraft() {
  draft.value = { title: '', description: '', priority: 2, group_id: '', github_url: '' }
  importRepo.value = ''
  issues.value = []
  issueFilter.value = ''
  pickedIssue.value = null
  issueUrl.value = ''
}

async function loadIssues() {
  if (!importRepo.value) return
  loadingIssues.value = true
  try {
    issues.value = await api.github.issues({ repository_id: importRepo.value, limit: 25 })
    if (!issues.value.length) store.notify('No open issues in that repository')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    loadingIssues.value = false
  }
}

// Paste an issue/PR URL to import directly.
let urlTimer
function onUrlInput() {
  clearTimeout(urlTimer)
  if (!GITHUB_ISSUE_RE.test(issueUrl.value.trim())) return
  urlTimer = setTimeout(previewFromUrl, 500)
}

async function previewFromUrl() {
  const url = issueUrl.value.trim()
  if (!GITHUB_ISSUE_RE.test(url)) return
  loadingIssue.value = true
  try {
    applyIssue(await api.github.issue(url))
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    loadingIssue.value = false
  }
}

function applyIssue(issue) {
  pickedIssue.value = issue.number
  issueUrl.value = issue.url || issueUrl.value
  draft.value.title = issue.title
  draft.value.description = issue.body
  draft.value.github_url = issue.url
}

function pickIssue(issue) {
  applyIssue(issue)
}

function clearImport() {
  pickedIssue.value = null
  draft.value.github_url = ''
  issueUrl.value = ''
}

async function createTask() {
  if (!draft.value.title.trim() && !draft.value.github_url) return
  try {
    const task = await api.tasks.create({
      ...draft.value,
      priority: Number(draft.value.priority),
      group_id: draft.value.group_id || null,
      github_url: draft.value.github_url || null,
    })
    showNew.value = false
    resetDraft()
    await refresh()
    router.push(`/task/${task.id}`)
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onGlobalKeydown)
  await refresh()
  await store.loadGroups().catch(() => {})
  await store.loadRepositories().catch(() => {})
})
onUnmounted(() => window.removeEventListener('keydown', onGlobalKeydown))
</script>

<template>
  <div class="app" :class="{ 'sidebar-open': sidebarOpen }">
    <header class="topbar">
      <button class="btn ghost menu-btn" aria-label="Toggle task list" @click="sidebarOpen = !sidebarOpen">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none" />
        </svg>
      </button>
      <router-link to="/" class="brand">
        <svg viewBox="0 0 512 512" aria-hidden="true">
          <path d="M160 168 L256 128 L352 168 M160 168 L160 288 L256 344 L352 288 L352 168 M160 288 L256 248 L352 288"
                stroke="#6ee7b7" stroke-width="16" fill="none" stroke-linecap="round" />
          <g fill="#6ee7b7">
            <circle cx="256" cy="128" r="26" /><circle cx="160" cy="168" r="18" />
            <circle cx="352" cy="168" r="18" /><circle cx="256" cy="248" r="20" />
            <circle cx="160" cy="288" r="18" /><circle cx="352" cy="288" r="18" />
            <circle cx="256" cy="344" r="26" />
          </g>
        </svg>
        <span>Agentic</span>
      </router-link>
      <div class="grow"></div>
      <button class="btn ghost sm palette-trigger" title="Command palette (Ctrl/Cmd+K)" @click="paletteOpen = true">
        ⌘K
      </button>
      <router-link to="/" class="btn ghost sm nav-tasks" :class="{ primary: route.name === 'tasks' }">Tasks</router-link>
      <router-link to="/items" class="btn ghost sm" :class="{ primary: route.name === 'items' }">Items</router-link>
      <router-link to="/settings" class="btn ghost sm" :class="{ primary: route.name === 'settings' }">Settings</router-link>
      <button class="btn primary mobile-only" title="New task" aria-label="New task" @click="showNew = true">+</button>
    </header>

    <div v-if="sidebarOpen" class="sidebar-backdrop" @click="sidebarOpen = false"></div>

    <aside class="sidebar">
      <div class="side-head">
        <input v-model="search" class="input grow" placeholder="Search tasks…" />
        <button class="btn primary" @click="showNew = true" title="New task">+</button>
      </div>
      <div v-if="store.loading && !store.tasks.length" class="empty"><span class="spinner"></span></div>
      <div v-else-if="!filtered.length" class="empty">No tasks yet.</div>
      <router-link
        v-for="p in filtered"
        :key="p.id"
        :to="`/task/${p.id}`"
        class="task-card"
        :class="{ active: route.params.id === p.id }"
        @click="sidebarOpen = false"
      >
        <span class="t">{{ p.title }}</span>
        <span class="s">{{ p.summary || p.description || 'No summary yet' }}</span>
        <span class="meta">
          <span :class="statusClass(p.status)">{{ p.status.replace('_', ' ') }}</span>
          <span v-if="p.next_steps?.length" class="badge">{{ p.next_steps.filter((s) => !s.done).length }} steps</span>
          <span class="faint">{{ timeAgo(p.updated_at) }}</span>
        </span>
      </router-link>
    </aside>

    <main class="main">
      <router-view :key="route.fullPath" @changed="refresh" />
    </main>

    <div v-if="showNew" class="modal-backdrop" @click.self="showNew = false">
      <div class="modal">
        <h1 style="margin-bottom: 14px">New task</h1>

        <div class="field">
          <label>Import from GitHub (optional)</label>
          <input
            v-model="issueUrl"
            class="input"
            placeholder="Paste a GitHub issue or PR URL…"
            @input="onUrlInput"
            @keyup.enter="previewFromUrl"
          />
          <p v-if="loadingIssue" class="faint" style="margin: 6px 0 0"><span class="spinner"></span> Loading issue…</p>
          <p v-else-if="pickedIssue" class="faint" style="margin: 6px 0 0">
            Importing <a :href="draft.github_url" target="_blank">#{{ pickedIssue }}</a>
            <button class="btn sm ghost" @click="clearImport">clear</button>
          </p>

          <details style="margin-top: 8px">
            <summary class="faint" style="cursor: pointer">or pick from a repository</summary>
            <div class="row" style="margin-top: 8px">
              <SearchSelect
                v-model="importRepo"
                class="grow"
                :options="importRepoOptions"
                placeholder="Choose a repository…"
              />
              <button class="btn" :disabled="!importRepo || loadingIssues" @click="loadIssues">
                <span v-if="loadingIssues" class="spinner"></span> Load issues
              </button>
            </div>
            <input
              v-if="issues.length"
              v-model="issueFilter"
              class="input"
              style="margin-top: 8px"
              placeholder="Filter issues…"
            />
            <div v-if="issues.length" class="issue-list">
              <button v-for="issue in sortedIssues" :key="issue.number" class="issue-row" @click="pickIssue(issue)">
                <span class="badge ok">{{ issue.state.toLowerCase() }}</span>
                <span class="grow">#{{ issue.number }} {{ issue.title }}</span>
                <span v-if="issue.author" class="faint">{{ issue.author }}</span>
              </button>
            </div>
            <p v-if="!githubRepos.length" class="faint" style="margin: 6px 0 0">
              No GitHub repositories registered. Add one in <router-link to="/settings">Settings</router-link>.
            </p>
          </details>
        </div>

        <div class="field">
          <label>Title</label>
          <input v-model="draft.title" class="input" placeholder="What needs to be solved?" @keyup.enter="createTask" />
        </div>
        <div class="field">
          <label>Description</label>
          <textarea v-model="draft.description" class="textarea" placeholder="Context, links, anything…"></textarea>
        </div>
        <div class="field">
          <label>Priority</label>
          <SearchSelect v-model="draft.priority" :options="priorityOptions" :sort="false" placeholder="Priority" />
        </div>
        <div class="field">
          <label>Repository group (optional)</label>
          <SearchSelect v-model="draft.group_id" :options="groupOptions" placeholder="None" />
        </div>
        <div class="row" style="justify-content: flex-end">
          <button class="btn ghost" @click="showNew = false">Cancel</button>
          <button class="btn primary" :disabled="!draft.title.trim() && !draft.github_url" @click="createTask">
            Create
          </button>
        </div>
      </div>
    </div>

    <div v-if="store.toast" class="toast" :class="{ err: store.toast.isError }">{{ store.toast.message }}</div>

    <div v-if="store.hintMode" class="hint-banner">
      Press a field's letter to focus it · <span class="mono">Esc</span> to exit
    </div>

    <CommandPalette
      v-if="paletteOpen"
      :items="paletteItems"
      @select="runPaletteItem"
      @close="paletteOpen = false"
    />
  </div>
</template>
