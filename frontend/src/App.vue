<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { store, timeAgo } from './store'
import SearchSelect from './components/SearchSelect.vue'
import RepositorySelect from './components/RepositorySelect.vue'
import TagInput from './components/TagInput.vue'
import MentionTextarea from './components/MentionTextarea.vue'
import DeadlinePicker from './components/DeadlinePicker.vue'
import StatusSelect from './components/StatusSelect.vue'
import StatusIcon from './components/StatusIcon.vue'
import PriorityIcon from './components/PriorityIcon.vue'
import Icon from './components/Icon.vue'
import CommandPalette from './components/CommandPalette.vue'
import StatusBar from './components/StatusBar.vue'
import { useFocusHints } from './composables/useFocusHints'
import { useSidebar } from './composables/useSidebar'
import { buildPaletteItems } from './palette'
import { loadSidebarNav, sidebarNavColumns, visibleSidebarNav } from './sidebarNav'

const { hintBadges, handleHintKey, hasHintTargets, stopHints } = useFocusHints()

const route = useRoute()
const paletteItems = computed(() => buildPaletteItems({ route, router, showNew, sidebarHidden, toggleSidebar }))
const router = useRouter()
const showNew = ref(false)
const sidebarOpen = ref(false)
const paletteOpen = ref(false)
// Read the per-device nav choice before the first render, so a reordered or
// trimmed nav never flashes the default order.
loadSidebarNav()
const {
  SIDEBAR_MIN_PX,
  SIDEBAR_MAX_PX,
  sidebarWidth,
  sidebarResizing,
  sidebarHidden,
  sidebarDragStyle,
  sidebarDragging,
  toggleSidebar,
  sidebarExpanded,
  sidebarToggleLabel,
  startResize,
  onResizerKeydown,
  resetSidebarWidth
} = useSidebar({ sidebarOpen, showNew, paletteOpen })
const draft = ref({
  title: '',
  description: '',
  status: 'open',
  priority: 2,
  tags: [],
  deadline: null,
  repository_ids: [],
  group_id: '',
  github_url: '',
  slack_url: ''
})

// "Import from GitHub or Slack" state. One field accepts either source.
const importRepo = ref('')
const issues = ref([])
const loadingIssues = ref(false)
const issueFilter = ref('')
const pickedIssue = ref(null)
const importUrl = ref('')
const importKind = ref('') // '' | 'github' | 'slack'
const loadingIssue = ref(false)
// What a GitHub preview auto-filled, so switching source can undo it.
let importPrefill = { title: '', description: '' }

watch(
  () => route.fullPath,
  () => {
    sidebarOpen.value = false
    store.hintMode = false
  }
)

const GITHUB_ISSUE_RE = /github\.com\/[^/\s]+\/[^/\s]+\/(?:issues|pull)\/\d+/i
const SLACK_URL_RE = /https?:\/\/[^./\s]+\.slack\.com\/archives\/[^/\s]+\/p\d+/i

const githubRepos = computed(() => store.repositories.filter((r) => (r.remote_url || '').includes('github.com')))

const priorityOptions = [
  { value: 0, label: 'Low', icon: PriorityIcon, iconProps: { priority: 0, label: 'Low' } },
  { value: 1, label: 'Medium', icon: PriorityIcon, iconProps: { priority: 1, label: 'Medium' } },
  { value: 2, label: 'High', icon: PriorityIcon, iconProps: { priority: 2, label: 'High' } },
  { value: 3, label: 'Urgent', icon: PriorityIcon, iconProps: { priority: 3, label: 'Urgent' } }
]
const statusOptions = [
  { value: 'open', label: 'Open', icon: StatusIcon, iconProps: { status: 'open', label: 'Open' } },
  {
    value: 'in_progress',
    label: 'In progress',
    icon: StatusIcon,
    iconProps: { status: 'in_progress', label: 'In progress' }
  },
  { value: 'blocked', label: 'Blocked', icon: StatusIcon, iconProps: { status: 'blocked', label: 'Blocked' } },
  { value: 'done', label: 'Done', icon: StatusIcon, iconProps: { status: 'done', label: 'Done' } },
  { value: 'archived', label: 'Archived', icon: StatusIcon, iconProps: { status: 'archived', label: 'Archived' } }
]
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
// Picking a group fills the repository list with that group's repositories.
watch(
  () => draft.value.group_id,
  (id) => {
    const group = store.groups.find((g) => g.id === id)
    if (group) draft.value.repository_ids = [...(group.repository_ids || [])]
  }
)
const importRepoOptions = computed(() => githubRepos.value.map((r) => ({ value: r.id, label: r.name })))

// The sidebar is for work in flight: hide done and archived tasks.
const sidebarTasks = computed(() => store.tasks.filter((p) => p.status !== 'done' && p.status !== 'archived'))

// The count a nav icon carries: the inbox count lives on the store, and the
// other badges are keyed by the nav item id. Zero shows no badge.
function navBadge(item) {
  if (!item.badge) return 0
  return item.badge === 'inbox' ? store.inboxCount : store.navBadges[item.badge] || 0
}

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

  // Cmd/Ctrl+B hides or shows the sidebar (Shift is left to the browser).
  if ((event.metaKey || event.ctrlKey) && !event.shiftKey && event.key.toLowerCase() === 'b') {
    event.preventDefault()
    toggleSidebar()
    return
  }

  // Cmd/Ctrl+N opens the new-task modal (and must beat the browser's own).
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'n') {
    event.preventDefault()
    showNew.value = true
    return
  }

  if (store.hintMode && handleHintKey(event)) return

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
    hasHintTargets()
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

async function refresh() {
  store.loading = true
  try {
    await store.loadTasks()
    await store.loadTags()
    // The inbox badge in the nav tracks the same state the tasks do.
    await store.loadInbox().catch(() => {})
    // The other nav badges read their own stores; a failure leaves the last
    // count in place rather than blanking the nav. They land when they land, so
    // a slow GitHub read never holds up the shell.
    store.loadNavBadges().catch(() => {})
    // Drop a filter whose tag no longer exists on any task.
    if (store.tagFilter && !store.tags.some((tag) => tag.name === store.tagFilter)) store.tagFilter = ''
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
    tags: [],
    deadline: null,
    repository_ids: [],
    group_id: '',
    github_url: '',
    slack_url: ''
  }
  importRepo.value = ''
  issues.value = []
  issueFilter.value = ''
  pickedIssue.value = null
  importUrl.value = ''
  importKind.value = ''
  importPrefill = { title: '', description: '' }
}

function addRepository(id) {
  if (!id) return
  draft.value.repository_ids = [...draft.value.repository_ids, id]
}

// Change a task's status straight from the sidebar list.
async function changeStatus(task, status) {
  if (status === task.status) return
  const previous = task.status
  task.status = status
  try {
    await api.tasks.update(task.id, { status })
  } catch (e) {
    task.status = previous
    store.notify(e.message, true)
  }
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

// Paste an issue/PR or Slack thread URL into one field; the source is detected.
let urlTimer
function onImportInput() {
  clearTimeout(urlTimer)
  const url = importUrl.value.trim()
  if (!url) {
    resetImport()
    return
  }
  if (SLACK_URL_RE.test(url)) {
    applySlackImport(url)
    return
  }
  if (GITHUB_ISSUE_RE.test(url)) {
    urlTimer = setTimeout(previewFromUrl, 500)
  }
}

async function previewFromUrl() {
  const url = importUrl.value.trim()
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
  importKind.value = 'github'
  pickedIssue.value = issue.number
  importUrl.value = issue.url || importUrl.value
  draft.value.slack_url = ''
  draft.value.title = issue.title
  draft.value.description = issue.body
  draft.value.github_url = issue.url
  importPrefill = { title: issue.title, description: issue.body }
}

function applySlackImport(url) {
  if (importKind.value === 'github') undoGithubPrefill()
  importKind.value = 'slack'
  pickedIssue.value = null
  draft.value.github_url = ''
  draft.value.slack_url = url
}

// Undo the fields a GitHub preview filled, but only where the user has not edited them.
function undoGithubPrefill() {
  if (draft.value.title === importPrefill.title) draft.value.title = ''
  if (draft.value.description === importPrefill.description) draft.value.description = ''
  importPrefill = { title: '', description: '' }
}

function resetImport() {
  if (importKind.value === 'github') undoGithubPrefill()
  importKind.value = ''
  pickedIssue.value = null
  draft.value.github_url = ''
  draft.value.slack_url = ''
}

function pickIssue(issue) {
  applyIssue(issue)
}

function clearImport() {
  resetImport()
  importUrl.value = ''
}

async function createTask() {
  if (!draft.value.title.trim() && !draft.value.github_url && !draft.value.slack_url.trim()) return
  try {
    const task = await api.tasks.create({
      ...draft.value,
      priority: Number(draft.value.priority),
      repository_ids: [...draft.value.repository_ids],
      group_id: draft.value.group_id || null,
      github_url: draft.value.github_url || null,
      slack_url: draft.value.slack_url.trim() || null
    })
    showNew.value = false
    resetDraft()
    await store.loadTasks().catch(() => {})
    store.loadInbox().catch(() => {})
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
  await store.loadPeople().catch(() => {})
  await store.loadItems().catch(() => {})
  await store.loadSettings().catch(() => {})
})
onUnmounted(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
  stopHints()
})
</script>

<template>
  <div
    class="app"
    :class="{
      'sidebar-open': sidebarOpen,
      'sidebar-dragging': sidebarDragging,
      'sidebar-resizing': sidebarResizing,
      'sidebar-hidden': sidebarHidden
    }"
    :style="{ '--sidebar-width': `${sidebarWidth}px` }"
  >
    <aside class="sidebar" :style="sidebarDragStyle">
      <div class="side-brand">
        <router-link to="/" class="brand">
          <svg viewBox="0 0 512 512" aria-hidden="true">
            <path
              d="M124 380 Q112 380 117 368 L226 136 Q233 120 248 120 H268
                   Q281 120 288 136 L340 248 H276 L258 208 L184 368
                   Q179 380 166 380 Z"
              fill="#6ee7b7"
            />
            <path
              d="M244 280 H354 L395 368 Q401 380 388 380 H350
                   Q338 380 333 368 L316 332 H220 Z"
              fill="#eef2f6"
            />
          </svg>
          <span>Agentic</span>
        </router-link>
        <button class="btn sm sidebar-close" aria-label="Close task list" @click="sidebarOpen = false">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none" />
          </svg>
        </button>
      </div>
      <div class="side-scroll">
        <div v-if="store.loading && !store.tasks.length" class="empty"><span class="spinner"></span></div>
        <div v-else-if="!sidebarTasks.length" class="empty">
          {{ store.tasks.length ? 'All caught up.' : 'No tasks yet.' }}
        </div>
        <div v-for="p in sidebarTasks" :key="p.id" class="task-card" :class="{ active: route.params.id === p.id }">
          <StatusSelect :model-value="p.status" @update:model-value="(value) => changeStatus(p, value)" />
          <router-link :to="`/task/${p.id}`" class="task-link" @click="sidebarOpen = false">
            <span class="t">{{ p.title }}</span>
            <span v-if="p.next_steps?.length" class="badge steps">{{
              p.next_steps.filter((s) => !s.done).length
            }}</span>
            <span class="faint when">{{ timeAgo(p.updated_at) }}</span>
          </router-link>
        </div>
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
          <button class="btn primary new-task" title="New task (Ctrl/Cmd+N)" @click="showNew = true">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none" />
            </svg>
            New task
          </button>
        </div>
        <div v-if="visibleSidebarNav.length" class="sidebar-nav-links" :style="{ '--nav-cols': sidebarNavColumns }">
          <router-link
            v-for="item in visibleSidebarNav"
            :key="item.id"
            :to="item.to"
            class="nav-link"
            :class="{ active: item.routeNames.includes(route.name) }"
            :title="item.label"
            :aria-label="item.label"
            @click="sidebarOpen = false"
          >
            <Icon :name="item.icon" :size="20" />
            <span v-if="navBadge(item)" class="nav-badge" aria-hidden="true">{{ navBadge(item) }}</span>
          </router-link>
        </div>
      </nav>
      <div
        class="sidebar-resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize task list"
        :aria-valuenow="sidebarWidth"
        :aria-valuemin="SIDEBAR_MIN_PX"
        :aria-valuemax="SIDEBAR_MAX_PX"
        tabindex="0"
        title="Drag to resize, double-click to reset"
        @pointerdown="startResize"
        @keydown="onResizerKeydown"
        @dblclick="resetSidebarWidth"
      ></div>
    </aside>

    <div v-if="sidebarOpen || sidebarDragging" class="sidebar-backdrop" @click="sidebarOpen = false"></div>

    <main class="main">
      <button
        class="btn menu-btn"
        data-no-hint
        :title="sidebarToggleLabel()"
        :aria-label="sidebarToggleLabel()"
        :aria-expanded="sidebarExpanded()"
        @click="toggleSidebar"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <rect x="3" y="4.5" width="18" height="15" rx="2.6" fill="none" stroke="currentColor" stroke-width="1.7" />
          <path d="M9.1 5.4v13.2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" fill="none" />
        </svg>
      </button>
      <router-view :key="route.fullPath" @changed="refresh" />
    </main>

    <div v-if="showNew" class="modal-backdrop" @click.self="showNew = false">
      <div class="modal">
        <h1 style="margin-bottom: 14px">New task</h1>

        <div class="field">
          <label>Import from GitHub or Slack (optional)</label>
          <input
            v-model="importUrl"
            class="input"
            placeholder="Paste an issue, PR, or Slack thread URL…"
            @input="onImportInput"
            @keyup.enter="previewFromUrl"
          />
          <p v-if="loadingIssue" class="faint" style="margin: 6px 0 0"><span class="spinner"></span> Loading issue…</p>
          <p v-else-if="pickedIssue" class="faint" style="margin: 6px 0 0">
            Importing <a :href="draft.github_url" target="_blank">#{{ pickedIssue }}</a>
            <button class="btn sm ghost" @click="clearImport">clear</button>
          </p>
          <p v-else-if="draft.slack_url" class="faint" style="margin: 6px 0 0">
            Importing the Slack thread; an agent names the task and summarizes the discussion.
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
              No GitHub repositories registered. Add one in <router-link to="/repositories">Repositories</router-link>.
            </p>
          </details>
        </div>

        <div class="field">
          <label>Title</label>
          <input v-model="draft.title" class="input" placeholder="What needs to be solved?" @keyup.enter="createTask" />
        </div>
        <div class="field">
          <label>Description</label>
          <MentionTextarea
            v-model="draft.description"
            class="textarea"
            placeholder="Context, links, anything… Use @ to mention a person, an item, a task, or a date."
          />
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
          <label>Deadline (optional)</label>
          <DeadlinePicker v-model="draft.deadline" />
        </div>
        <div class="field">
          <label>Tags (optional)</label>
          <TagInput v-model="draft.tags" :suggestions="store.tags" placeholder="+ Add tag" />
        </div>
        <div class="field">
          <label>Repository group (optional)</label>
          <SearchSelect v-model="draft.group_id" :options="groupOptions" placeholder="None" />
          <p class="faint" style="margin: 6px 0 0">Picking a group fills in its repositories below.</p>
        </div>
        <div class="field">
          <label>Repositories (optional)</label>
          <RepositorySelect
            v-model="draft.repository_ids"
            :repositories="store.repositories"
            empty-label="none registered"
          />
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
        <div class="row" style="justify-content: flex-end">
          <button class="btn ghost" @click="showNew = false">Cancel</button>
          <button
            class="btn primary"
            :disabled="!draft.title.trim() && !draft.github_url && !draft.slack_url.trim()"
            @click="createTask"
          >
            Create
          </button>
        </div>
      </div>
    </div>

    <div v-if="store.toast" class="toast" :class="{ err: store.toast.isError }">{{ store.toast.message }}</div>

    <div v-if="store.hintMode" class="hint-banner">
      Type the label over a control to focus it · <span class="mono">Enter</span> to confirm a shorter label ·
      <span class="mono">Backspace</span> to undo · <span class="mono">Esc</span> to exit
    </div>

    <span
      v-for="badge in hintBadges"
      v-show="!badge.hidden"
      :key="badge.key"
      class="hint-badge"
      :class="{ dimmed: badge.dimmed }"
      :style="{ left: badge.left + 'px', top: badge.top + 'px' }"
      >{{ badge.key }}</span
    >

    <CommandPalette v-if="paletteOpen" :items="paletteItems" @select="runPaletteItem" @close="paletteOpen = false" />
    <StatusBar />
  </div>
</template>
