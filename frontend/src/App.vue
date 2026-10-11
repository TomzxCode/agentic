<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { store, statusLabel, timeAgo } from './store'
import SearchSelect from './components/SearchSelect.vue'
import CommandPalette from './components/CommandPalette.vue'

const route = useRoute()
const router = useRouter()
const showNew = ref(false)
const sidebarOpen = ref(false)
const paletteOpen = ref(false)
const draft = ref({
  title: '',
  description: '',
  status: 'open',
  priority: 2,
  repository_ids: [],
  group_id: '',
  github_url: ''
})

// "Import from GitHub" state.
const importRepo = ref('')
const issues = ref([])
const loadingIssues = ref(false)
const issueFilter = ref('')
const pickedIssue = ref(null)
const issueUrl = ref('')
const loadingIssue = ref(false)

watch(
  () => route.fullPath,
  () => {
    sidebarOpen.value = false
    store.hintMode = false
  }
)

const GITHUB_ISSUE_RE = /github\.com\/[^/\s]+\/[^/\s]+\/(?:issues|pull)\/\d+/i

const githubRepos = computed(() => store.repositories.filter((r) => (r.remote_url || '').includes('github.com')))

const priorityOptions = [
  { value: 0, label: 'Low' },
  { value: 1, label: 'Medium' },
  { value: 2, label: 'High' },
  { value: 3, label: 'Urgent' }
]
const statusOptions = [
  { value: 'open', label: 'Open' },
  { value: 'in_progress', label: 'In progress' },
  { value: 'blocked', label: 'Blocked' },
  { value: 'done', label: 'Done' },
  { value: 'archived', label: 'Archived' }
]
const selectedRepositories = computed(() =>
  (draft.value.repository_ids || [])
    .map((id) => store.repositories.find((r) => r.id === id))
    .filter(Boolean)
    .sort((a, b) => a.name.localeCompare(b.name))
)
const addRepositoryOptions = computed(() =>
  store.repositories
    .filter((r) => !(draft.value.repository_ids || []).includes(r.id))
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((r) => ({ value: r.id, label: r.name }))
)
// Repositories of the most recently created task, offered as quick picks.
const lastUsedRepositories = computed(() => {
  const last = [...store.tasks].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0]
  if (!last) return []
  return (last.repository_ids || [])
    .filter((id) => !(draft.value.repository_ids || []).includes(id))
    .map((id) => store.repositories.find((r) => r.id === id))
    .filter(Boolean)
    .sort((a, b) => a.name.localeCompare(b.name))
})
const groupOptions = computed(() => [
  { value: '', label: 'None' },
  ...store.groups.map((g) => ({ value: g.id, label: g.name }))
])
const importRepoOptions = computed(() => githubRepos.value.map((r) => ({ value: r.id, label: r.name })))

// Command palette: navigate anywhere (and a couple of actions) from the keyboard.
const taskFieldItems = computed(() =>
  route.name === 'task'
    ? [
        { id: 'field-title', label: 'Edit title', group: 'This task', run: () => store.focusField?.('title') },
        {
          id: 'field-description',
          label: 'Edit description',
          group: 'This task',
          run: () => store.focusField?.('description')
        },
        { id: 'field-status', label: 'Set status', group: 'This task', run: () => store.focusField?.('status') },
        { id: 'field-priority', label: 'Set priority', group: 'This task', run: () => store.focusField?.('priority') },
        {
          id: 'field-group',
          label: 'Set repository group',
          group: 'This task',
          run: () => store.focusField?.('group')
        },
        {
          id: 'field-repository',
          label: 'Add repository',
          group: 'This task',
          run: () => store.focusField?.('repository')
        }
      ]
    : []
)

const paletteItems = computed(() => [
  { id: 'new-task', label: 'New task', group: 'Actions', run: () => (showNew.value = true) },
  { id: 'focus-hints', label: 'Show focus hints', hint: 'f', group: 'Actions', run: () => (store.hintMode = true) },
  ...taskFieldItems.value,
  { id: 'go-tasks', label: 'Go to tasks', group: 'Navigation', run: () => router.push('/') },
  { id: 'go-gantt', label: 'Go to gantt', group: 'Navigation', run: () => router.push('/gantt') },
  { id: 'go-items', label: 'Go to resources', group: 'Navigation', run: () => router.push('/items') },
  { id: 'go-settings', label: 'Go to settings', group: 'Navigation', run: () => router.push('/settings') },
  ...store.tasks.map((task) => ({
    id: `task-${task.id}`,
    label: task.title,
    group: 'Tasks',
    hint: task.status.replace('_', ' '),
    run: () => router.push(`/task/${task.id}`)
  }))
])

function runPaletteItem(item) {
  item.run?.()
}

function isTyping(target) {
  return !!target && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)
}

// Focus-hint mode: press f, then the letter over a control, to focus it. The
// targets are scanned from the page so every field/button is covered.
const HINT_SELECTOR = 'a[href], button, input, textarea, select, [tabindex]:not([tabindex="-1"])'
const hintBadges = ref([])
let hintTargets = []
let hintBuffer = ''
let hintCleanup = null

function hintLabelFor(index) {
  const alphabet = 'abcdefghijklmnopqrstuvwxyz'
  if (index < alphabet.length) return alphabet[index]
  const rest = index - alphabet.length
  return alphabet[Math.floor(rest / alphabet.length)] + alphabet[rest % alphabet.length]
}

function positionHints() {
  hintTargets.forEach((target, index) => {
    const badge = hintBadges.value[index]
    if (!badge) return
    const rect = target.el.getBoundingClientRect()
    badge.left = rect.left
    badge.top = rect.top
    badge.hidden = rect.width === 0 && rect.height === 0
  })
}

function stopHints() {
  hintCleanup?.()
  hintCleanup = null
  hintTargets = []
  hintBadges.value = []
  hintBuffer = ''
}

function startHints() {
  stopHints()
  const container = document.querySelector('.main')
  if (!container) return
  const nodes = Array.from(container.querySelectorAll(HINT_SELECTOR)).filter(
    (el) => !el.disabled && !el.closest('.transcript')
  )
  hintTargets = nodes.map((el, index) => ({ key: hintLabelFor(index), el }))
  hintBadges.value = hintTargets.map(({ key }) => ({ key, left: 0, top: 0, hidden: false }))
  positionHints()
  window.addEventListener('scroll', positionHints, true)
  window.addEventListener('resize', positionHints)
  hintCleanup = () => {
    window.removeEventListener('scroll', positionHints, true)
    window.removeEventListener('resize', positionHints)
  }
}

function onGlobalKeydown(event) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    paletteOpen.value = !paletteOpen.value
    return
  }

  if (store.hintMode) {
    if (event.key === 'Escape') {
      event.preventDefault()
      store.hintMode = false
      return
    }
    const char = event.key.toLowerCase()
    if (/^[a-z]$/.test(char)) {
      hintBuffer += char
      const exact = hintTargets.find((target) => target.key === hintBuffer)
      if (exact) {
        event.preventDefault()
        exact.el.focus()
        store.hintMode = false
      } else if (hintTargets.some((target) => target.key.startsWith(hintBuffer))) {
        event.preventDefault()
      } else {
        hintBuffer = ''
      }
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
    document.querySelector('.main')?.querySelector(HINT_SELECTOR)
  ) {
    event.preventDefault()
    store.hintMode = true
  }
}

watch(
  () => store.hintMode,
  (on) => (on ? startHints() : stopHints())
)

// Newest issues first (by number), with a text filter.
const sortedIssues = computed(() => {
  const q = issueFilter.value.trim().toLowerCase()
  const list = [...issues.value].sort((a, b) => (b.number ?? 0) - (a.number ?? 0))
  if (!q) return list
  return list.filter((i) => i.title.toLowerCase().includes(q) || String(i.number).includes(q))
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
  draft.value = {
    title: '',
    description: '',
    status: 'open',
    priority: 2,
    repository_ids: [],
    group_id: '',
    github_url: ''
  }
  importRepo.value = ''
  issues.value = []
  issueFilter.value = ''
  pickedIssue.value = null
  issueUrl.value = ''
}

function addRepository(id) {
  if (!id) return
  draft.value.repository_ids = [...draft.value.repository_ids, id]
}

function removeRepository(id) {
  draft.value.repository_ids = draft.value.repository_ids.filter((x) => x !== id)
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
      repository_ids: [...draft.value.repository_ids],
      group_id: draft.value.group_id || null,
      github_url: draft.value.github_url || null
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
  await store.loadSettings().catch(() => {})
})
onUnmounted(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
  stopHints()
})
</script>

<template>
  <div class="app" :class="{ 'sidebar-open': sidebarOpen }">
    <aside class="sidebar">
      <div class="side-brand">
        <router-link to="/" class="brand">
          <svg viewBox="0 0 512 512" aria-hidden="true">
            <path
              d="M160 168 L256 128 L352 168 M160 168 L160 288 L256 344 L352 288 L352 168 M160 288 L256 248 L352 288"
              stroke="#6ee7b7"
              stroke-width="16"
              fill="none"
              stroke-linecap="round"
            />
            <g fill="#6ee7b7">
              <circle cx="256" cy="128" r="26" />
              <circle cx="160" cy="168" r="18" />
              <circle cx="352" cy="168" r="18" />
              <circle cx="256" cy="248" r="20" />
              <circle cx="160" cy="288" r="18" />
              <circle cx="352" cy="288" r="18" />
              <circle cx="256" cy="344" r="26" />
            </g>
          </svg>
          <span>Agentic</span>
        </router-link>
      </div>
      <div class="side-scroll">
        <div v-if="store.loading && !store.tasks.length" class="empty"><span class="spinner"></span></div>
        <div v-else-if="!store.tasks.length" class="empty">No tasks yet.</div>
        <router-link
          v-for="p in store.tasks"
          :key="p.id"
          :to="`/task/${p.id}`"
          class="task-card"
          :class="{ active: route.params.id === p.id }"
          @click="sidebarOpen = false"
        >
          <span
            class="task-status"
            :class="`st-${p.status}`"
            :title="statusLabel(p.status)"
            :aria-label="statusLabel(p.status)"
            role="img"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path
                v-if="p.status === 'done'"
                d="M3.5 8.5l3 3 6-7"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <path
                v-else-if="p.status === 'blocked'"
                d="M4.5 4.5l7 7M11.5 4.5l-7 7"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
              <path v-else-if="p.status === 'in_progress'" d="M5.5 4l6 4-6 4z" fill="currentColor" />
              <path
                v-else-if="p.status === 'archived'"
                d="M4 8h8"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
              />
              <circle v-else cx="8" cy="8" r="5" fill="none" stroke="currentColor" stroke-width="2" />
            </svg>
          </span>
          <span class="t">{{ p.title }}</span>
          <span v-if="p.next_steps?.length" class="badge steps">{{ p.next_steps.filter((s) => !s.done).length }}</span>
          <span class="faint when">{{ timeAgo(p.updated_at) }}</span>
        </router-link>
      </div>

      <nav class="sidebar-nav" aria-label="Primary">
        <div class="sidebar-nav-actions">
          <button
            class="palette-trigger"
            title="Command palette (Ctrl/Cmd+K)"
            aria-label="Open command palette"
            @click="paletteOpen = true"
          >
            <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
              <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2" />
              <path d="M20 20l-3.5-3.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            </svg>
            <span class="palette-label">Search</span>
            <kbd class="palette-kbd">⌘K</kbd>
          </button>
          <button class="btn primary new-task" title="New task" @click="showNew = true">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none" />
            </svg>
            New task
          </button>
        </div>
        <div class="sidebar-nav-links">
          <router-link to="/" class="nav-link" :class="{ active: route.name === 'tasks' }" @click="sidebarOpen = false"
            >Tasks</router-link
          >
          <router-link
            to="/gantt"
            class="nav-link"
            :class="{ active: route.name === 'gantt' }"
            @click="sidebarOpen = false"
            >Gantt</router-link
          >
          <router-link
            to="/items"
            class="nav-link"
            :class="{ active: route.name === 'items' }"
            @click="sidebarOpen = false"
            >Items</router-link
          >
          <router-link
            to="/settings"
            class="nav-link"
            :class="{ active: route.name === 'settings' }"
            @click="sidebarOpen = false"
            >Settings</router-link
          >
        </div>
      </nav>
    </aside>

    <div v-if="sidebarOpen" class="sidebar-backdrop" @click="sidebarOpen = false"></div>

    <button class="btn menu-btn" aria-label="Toggle task list" @click="sidebarOpen = !sidebarOpen">
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none" />
      </svg>
    </button>

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
          <label>Status</label>
          <SearchSelect v-model="draft.status" :options="statusOptions" :sort="false" placeholder="Status" />
        </div>
        <div class="field">
          <label>Priority</label>
          <SearchSelect v-model="draft.priority" :options="priorityOptions" :sort="false" placeholder="Priority" />
        </div>
        <div class="field">
          <label>Repositories (optional)</label>
          <div class="row">
            <span v-for="repo in selectedRepositories" :key="repo.id" class="chip">
              {{ repo.name }}
              <button class="chip-x" title="Remove" @click="removeRepository(repo.id)">×</button>
            </span>
            <SearchSelect
              v-if="addRepositoryOptions.length"
              variant="inline"
              :model-value="''"
              :options="addRepositoryOptions"
              placeholder="+ add repository"
              @update:model-value="addRepository"
            />
            <span v-if="!selectedRepositories.length && !addRepositoryOptions.length" class="faint"
              >none registered</span
            >
          </div>
          <div v-if="lastUsedRepositories.length" class="row" style="margin-top: 6px">
            <span class="faint">last used:</span>
            <button
              v-for="repo in lastUsedRepositories"
              :key="repo.id"
              class="chip chip-add"
              title="Add this repository"
              @click="addRepository(repo.id)"
            >
              + {{ repo.name }}
            </button>
          </div>
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
      Press the letter over a control to focus it · <span class="mono">Esc</span> to exit
    </div>

    <span
      v-for="badge in hintBadges"
      v-show="!badge.hidden"
      :key="badge.key"
      class="hint-badge"
      :style="{ left: badge.left + 'px', top: badge.top + 'px' }"
      >{{ badge.key }}</span
    >

    <CommandPalette v-if="paletteOpen" :items="paletteItems" @select="runPaletteItem" @close="paletteOpen = false" />
  </div>
</template>
