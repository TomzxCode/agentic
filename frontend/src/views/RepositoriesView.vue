<script setup>
import { computed, onMounted, ref, resolveComponent } from 'vue'
import { api } from '../api'
import { store, timeAgo } from '../store'
import { groupItemsByRepository } from '../repositories'
import DirectoryPicker from '../components/DirectoryPicker.vue'
import RepositoriesGrid from '../components/RepositoriesGrid.vue'

const loading = ref(true)
const error = ref(false)
const path = ref('')
const showPicker = ref(false)
// How many rows the grid currently shows (its filters may hide some).
const shown = ref(null)

// The globally registered router-link, handed to the grid so its name cells keep
// internal navigation inside the SPA (and so tests can stub it by name).
const routerLink = resolveComponent('RouterLink')

// One summary per registered repository, with the GitHub issues and PRs that
// are associated to tasks and match the repository's remote.
const summaries = computed(() => groupItemsByRepository(store.repositories, store.items))

// A repository's associated items by state, e.g. "3 open · 1 merged", or ''
// when no item carries a stored state.
function stateLine(repo) {
  return (repo.states || []).map((state) => `${state.count} ${state.value}`).join(' · ')
}

// The grid rows: each summary with the display fields the grid needs. `raw` is
// the summary itself, so a row action works on the repository.
const rows = computed(() =>
  summaries.value.map((repo) => ({
    ...repo,
    states_line: stateLine(repo),
    added: repo.created_at ? `added ${timeAgo(repo.created_at)}` : '',
    added_at: repo.created_at ? new Date(repo.created_at).getTime() : null,
    raw: repo
  }))
)

// Totals cover the whole list; the grid's own filters narrow what is shown.
const totals = computed(() => ({
  all: summaries.value.length,
  issues: summaries.value.reduce((n, repo) => n + repo.issue_count, 0),
  pulls: summaries.value.reduce((n, repo) => n + repo.pull_count, 0)
}))

async function load() {
  loading.value = true
  error.value = false
  try {
    await Promise.all([store.loadRepositories(), store.loadItems()])
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function addRepository() {
  if (!path.value.trim()) return
  try {
    await api.repositories.create({ path: path.value.trim() })
    path.value = ''
    await load()
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function addRepositories(paths) {
  if (!paths.length) return
  try {
    const result = await api.repositories.createBulk(paths)
    showPicker.value = false
    await load()
    const added = result.added.length
    if (result.errors.length) {
      store.notify(`Added ${added}, ${result.errors.length} skipped (not a git repository)`, true)
    } else {
      store.notify(`Added ${added} repositor${added === 1 ? 'y' : 'ies'}`)
    }
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function removeRepository(repository) {
  if (!confirm(`Remove ${repository.name} from Agentic? (No files are deleted.)`)) return
  try {
    await api.repositories.remove(repository.id)
    await load()
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(load)
</script>

<template>
  <div class="page-fill">
    <div class="row" style="justify-content: space-between">
      <h1>Repositories</h1>
      <span v-if="!loading && !error" class="faint">
        {{ shown ?? totals.all }} of {{ totals.all }} repositories · {{ totals.issues }} issues · {{ totals.pulls }} PRs
      </span>
    </div>

    <div class="panel">
      <div class="row">
        <input
          v-model="path"
          class="input grow"
          placeholder="/absolute/path/to/git/repo"
          aria-label="Repository path"
          @keyup.enter="addRepository"
        />
        <button class="btn" @click="showPicker = true">Browse…</button>
        <button class="btn primary" @click="addRepository">Add repository</button>
      </div>
    </div>

    <div v-if="loading" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load repositories.</p>
      <button class="btn" @click="load">Retry</button>
    </div>

    <div v-else-if="!summaries.length" class="panel">
      <p class="muted" style="margin-top: 0">
        No repositories are registered yet. Add a local git checkout to group its issues and PRs by repository.
      </p>
    </div>

    <RepositoriesGrid
      v-else
      :rows="rows"
      :router-link="routerLink"
      @remove="removeRepository"
      @count="shown = $event"
    />

    <DirectoryPicker
      v-if="showPicker"
      :existing="store.repositories.map((r) => r.path)"
      @close="showPicker = false"
      @add="addRepositories"
    />
  </div>
</template>
