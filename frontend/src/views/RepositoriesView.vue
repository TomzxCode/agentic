<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'
import {
  filterRepositories,
  groupItemsByRepository,
  parseRemote,
  REPOSITORY_SORT_DIRECTIONS,
  REPOSITORY_SORTS,
  sortRepositories
} from '../repositories'
import DirectoryPicker from '../components/DirectoryPicker.vue'
import EntityCard from '../components/EntityCard.vue'

const loading = ref(true)
const error = ref(false)
const path = ref('')
const showPicker = ref(false)
// Filter and sort controls for the list below.
const query = ref('')
const remoteFilter = ref('')
const sortBy = ref('name')
const sortDesc = ref(REPOSITORY_SORT_DIRECTIONS.name === 'desc')

// Switching the order returns to that order's natural direction.
watch(sortBy, (value) => {
  sortDesc.value = REPOSITORY_SORT_DIRECTIONS[value] === 'desc'
})

// One summary per registered repository, with the GitHub issues and PRs that
// are associated to tasks and match the repository's remote.
const summaries = computed(() => groupItemsByRepository(store.repositories, store.items))

// Filter-control counts cover the whole list, so a button's number does not
// move while the search narrows it.
const remoteCounts = computed(() => {
  let github = 0
  for (const repo of summaries.value) if (parseRemote(repo.remote_url)) github += 1
  return { github, other: summaries.value.length - github }
})

const visible = computed(() =>
  sortRepositories(
    filterRepositories(summaries.value, { query: query.value, remote: remoteFilter.value }),
    sortBy.value,
    sortDesc.value ? 'desc' : 'asc'
  )
)

// A repository's associated items by state, e.g. "3 open · 1 merged", or ''
// when no item carries a stored state.
function stateLine(repo) {
  return (repo.states || []).map((state) => `${state.count} ${state.value}`).join(' · ')
}

const totals = computed(() => ({
  shown: visible.value.length,
  all: summaries.value.length,
  issues: visible.value.reduce((n, repo) => n + repo.issue_count, 0),
  pulls: visible.value.reduce((n, repo) => n + repo.pull_count, 0)
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
  <div>
    <div class="row" style="justify-content: space-between">
      <h1>Repositories</h1>
      <span v-if="!loading && !error" class="faint">
        {{ totals.shown }} of {{ totals.all }} repositories · {{ totals.issues }} issues · {{ totals.pulls }} PRs
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

    <template v-else>
      <div class="panel" style="margin-bottom: 14px">
        <input
          v-model="query"
          class="input"
          placeholder="Filter by name, path, or remote…"
          aria-label="Filter repositories"
        />

        <div class="row" style="gap: 6px; margin-top: 12px; flex-wrap: wrap">
          <span class="filter-label">Remote</span>
          <div class="row" style="gap: 6px" role="group" aria-label="Filter by remote">
            <button
              class="btn sm"
              :class="{ primary: !remoteFilter }"
              :aria-pressed="!remoteFilter"
              @click="remoteFilter = ''"
            >
              All {{ summaries.length }}
            </button>
            <button
              v-if="remoteCounts.github"
              class="btn sm"
              :class="{ primary: remoteFilter === 'github' }"
              :aria-pressed="remoteFilter === 'github'"
              @click="remoteFilter = 'github'"
            >
              GitHub {{ remoteCounts.github }}
            </button>
            <button
              v-if="remoteCounts.other"
              class="btn sm"
              :class="{ primary: remoteFilter === 'other' }"
              :aria-pressed="remoteFilter === 'other'"
              @click="remoteFilter = 'other'"
            >
              Other {{ remoteCounts.other }}
            </button>
          </div>

          <span class="filter-label" style="margin-left: auto">Sort</span>
          <select v-model="sortBy" class="select" style="width: auto" aria-label="Sort repositories">
            <option v-for="option in REPOSITORY_SORTS" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
          <button
            class="btn sm"
            :aria-pressed="sortDesc"
            aria-label="Toggle sort direction"
            :title="sortDesc ? 'Descending, click for ascending' : 'Ascending, click for descending'"
            @click="sortDesc = !sortDesc"
          >
            {{ sortDesc ? '↓ Desc' : '↑ Asc' }}
          </button>
        </div>
      </div>

      <div v-if="!visible.length" class="panel">
        <p class="muted" style="margin: 0">No repositories match the filters.</p>
      </div>

      <EntityCard v-for="repo in visible" :key="repo.id">
        <template #title>
          <router-link :to="`/repositories/${repo.id}`" class="title">{{ repo.name }}</router-link>
        </template>
        <template #actions>
          <span class="row" style="gap: 6px">
            <span v-if="repo.default_branch" class="badge">{{ repo.default_branch }}</span>
            <span class="badge">{{ repo.issue_count }} issues</span>
            <span class="badge">{{ repo.pull_count }} PRs</span>
            <button
              class="btn sm danger"
              :aria-label="`Remove repository ${repo.name}`"
              @click="removeRepository(repo)"
            >
              Remove
            </button>
          </span>
        </template>
        <div class="faint mono" style="margin-top: 6px">{{ repo.path }}</div>
        <div v-if="repo.remote_url" class="faint">{{ repo.remote_url }}</div>
        <template #meta>
          <div v-if="repo.states.length" class="faint" style="margin-top: 6px">
            {{ stateLine(repo) }}
          </div>
        </template>
      </EntityCard>
    </template>

    <DirectoryPicker
      v-if="showPicker"
      :existing="store.repositories.map((r) => r.path)"
      @close="showPicker = false"
      @add="addRepositories"
    />
  </div>
</template>
