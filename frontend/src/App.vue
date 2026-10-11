<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { store, statusClass, timeAgo } from './store'
import SearchSelect from './components/SearchSelect.vue'

const route = useRoute()
const router = useRouter()
const search = ref('')
const showNew = ref(false)
const sidebarOpen = ref(false)
const draft = ref({ title: '', description: '', priority: 2, group_id: '', github_url: '' })

// "Import from GitHub" state.
const importRepo = ref('')
const issues = ref([])
const loadingIssues = ref(false)
const pickedIssue = ref(null)

// Close the mobile drawer when navigating.
watch(() => route.fullPath, () => (sidebarOpen.value = false))

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
  pickedIssue.value = null
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

function pickIssue(issue) {
  pickedIssue.value = issue.number
  draft.value.title = issue.title
  draft.value.description = issue.body
  draft.value.github_url = issue.url
}

function clearImport() {
  pickedIssue.value = null
  draft.value.github_url = ''
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
  await refresh()
  await store.loadGroups().catch(() => {})
  await store.loadRepositories().catch(() => {})
})
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
      <router-link to="/" class="btn ghost sm nav-tasks" :class="{ primary: route.name === 'tasks' }">Tasks</router-link>
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
          <div class="row">
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
          <div v-if="pickedIssue" class="faint" style="margin-top: 6px">
            Importing <a :href="draft.github_url" target="_blank">#{{ pickedIssue }}</a>
            <button class="btn sm ghost" @click="clearImport">clear</button>
          </div>
          <div v-else-if="issues.length" class="issue-list">
            <button v-for="issue in issues" :key="issue.number" class="issue-row" @click="pickIssue(issue)">
              <span class="badge ok">{{ issue.state.toLowerCase() }}</span>
              <span class="grow">#{{ issue.number }} {{ issue.title }}</span>
              <span v-if="issue.author" class="faint">{{ issue.author }}</span>
            </button>
          </div>
          <p v-if="!githubRepos.length" class="faint" style="margin: 6px 0 0">
            No GitHub repositories registered. Add one in <router-link to="/settings">Settings</router-link>.
          </p>
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
  </div>
</template>
