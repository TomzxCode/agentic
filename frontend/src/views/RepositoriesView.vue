<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { store } from '../store'
import { groupItemsByRepository } from '../repositories'
import DirectoryPicker from '../components/DirectoryPicker.vue'

const loading = ref(true)
const error = ref(false)
const path = ref('')
const showPicker = ref(false)

// One summary per registered repository, with the GitHub issues and PRs that
// are associated to tasks and match the repository's remote.
const summaries = computed(() => groupItemsByRepository(store.repositories, store.items))

// A repository's associated items by state, e.g. "3 open · 1 merged", or ''
// when no item carries a stored state.
function stateLine(repo) {
  return (repo.states || []).map((state) => `${state.count} ${state.value}`).join(' · ')
}

const totals = computed(() => ({
  repositories: summaries.value.length,
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
  <div>
    <div class="row" style="justify-content: space-between">
      <h1>Repositories</h1>
      <span v-if="!loading && !error" class="faint">
        {{ totals.repositories }} repositories · {{ totals.issues }} issues · {{ totals.pulls }} PRs
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

    <div v-else>
      <div v-for="repo in summaries" :key="repo.id" class="item">
        <div class="row" style="justify-content: space-between">
          <router-link :to="`/repositories/${repo.id}`"
            ><strong>{{ repo.name }}</strong></router-link
          >
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
        </div>
        <div class="faint mono" style="margin-top: 6px">{{ repo.path }}</div>
        <div v-if="repo.remote_url" class="faint">{{ repo.remote_url }}</div>
        <div v-if="repo.states.length" class="faint" style="margin-top: 6px">
          {{ stateLine(repo) }}
        </div>
      </div>
    </div>

    <DirectoryPicker
      v-if="showPicker"
      :existing="store.repositories.map((r) => r.path)"
      @close="showPicker = false"
      @add="addRepositories"
    />
  </div>
</template>
