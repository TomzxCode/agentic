<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { store, statusLabel, timeAgo } from '../store'
import { itemState, itemsForRepository, sortItems } from '../repositories'
import StatusIcon from '../components/StatusIcon.vue'

const props = defineProps({ id: { type: String, required: true } })

const STATE_ORDER = ['open', 'draft', 'merged', 'closed']
const STATE_LABELS = { open: 'Open', draft: 'Draft', merged: 'Merged', closed: 'Closed' }

const loading = ref(true)
const error = ref(false)
const refreshing = ref(false)
const query = ref('')
// Kind filter: '' shows both sections, otherwise 'issue' or 'pr'.
const kindFilter = ref('')
// State filter: '' shows every state, otherwise a value from STATE_ORDER.
const stateFilter = ref('')

const repository = computed(() => store.repositories.find((r) => r.id === props.id) || null)
const tasksById = computed(() => Object.fromEntries(store.tasks.map((task) => [task.id, task])))

const items = computed(() => (repository.value ? itemsForRepository(repository.value, store.items) : []))

// Filter-control counts cover the whole repository (like the Items page), so a
// button's number does not move while the search or the other filter narrows
// the list.
const kindCounts = computed(() => {
  const counts = { issue: 0, pr: 0 }
  for (const item of items.value) if (counts[item.kind] !== undefined) counts[item.kind] += 1
  return counts
})

// The states present among the repository's items, in a stable order.
const stateOptions = computed(() => {
  const counts = {}
  for (const item of items.value) {
    const state = itemState(item)
    if (state) counts[state] = (counts[state] || 0) + 1
  }
  return STATE_ORDER.filter((state) => counts[state]).map((state) => ({
    value: state,
    label: STATE_LABELS[state],
    count: counts[state]
  }))
})

// The kind toggle only earns its place when both kinds are present.
const showKindFilter = computed(() => kindCounts.value.issue > 0 && kindCounts.value.pr > 0)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return sortItems(items.value).filter((item) => {
    if (kindFilter.value && item.kind !== kindFilter.value) return false
    if (stateFilter.value && itemState(item) !== stateFilter.value) return false
    if (!q) return true
    return (
      String(item.title || '')
        .toLowerCase()
        .includes(q) || String(item.number || '').includes(q)
    )
  })
})
const issues = computed(() => filtered.value.filter((item) => item.kind === 'issue'))
const pulls = computed(() => filtered.value.filter((item) => item.kind === 'pr'))

function tasksFor(item) {
  return (item.task_ids || []).map((id) => tasksById.value[id]).filter(Boolean)
}

async function load() {
  loading.value = true
  error.value = false
  try {
    await Promise.all([store.loadRepositories(), store.loadItems(), store.loadTasks()])
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

// Re-fetch every issue and PR shown for this repository from GitHub, a few at
// a time so a large repository does not spawn a burst of ghx processes. A failed
// item keeps its stored data: the rows are reloaded from the API afterwards.
async function refreshAll() {
  if (refreshing.value || !items.value.length) return
  refreshing.value = true
  const ids = items.value.map((item) => item.id)
  const queue = [...ids]
  let failed = 0
  const worker = async () => {
    while (queue.length) {
      const id = queue.shift()
      try {
        await api.items.refresh(id)
      } catch {
        failed += 1
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(4, queue.length) }, worker))
  try {
    await store.loadItems()
  } catch (e) {
    store.notify(e.message, true)
  }
  refreshing.value = false
  const done = ids.length - failed
  if (failed) store.notify(`Refreshed ${done} of ${ids.length} items; ${failed} failed`, true)
  else store.notify(`Refreshed ${done} item${done === 1 ? '' : 's'}`)
}

onMounted(load)
</script>

<template>
  <div>
    <div v-if="loading" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load this repository's items.</p>
      <button class="btn" @click="load">Retry</button>
    </div>

    <div v-else-if="!repository" class="panel">
      <p class="muted" style="margin-top: 0">No repository with that id.</p>
      <router-link to="/repositories">← Back to Repositories</router-link>
    </div>

    <template v-else>
      <div class="faint"><router-link to="/repositories">Repositories</router-link> / {{ repository.name }}</div>
      <div class="row" style="justify-content: space-between; margin-top: 6px">
        <h1>{{ repository.name }}</h1>
        <span class="row" style="gap: 6px">
          <span v-if="repository.default_branch" class="badge">{{ repository.default_branch }}</span>
          <span v-if="repository.remote_url" class="faint">{{ repository.remote_url }}</span>
          <button
            class="btn sm"
            :disabled="refreshing || !items.length"
            aria-label="Refresh issues and pull requests"
            @click="refreshAll"
          >
            <span v-if="refreshing" class="spinner" aria-hidden="true"></span>
            <span v-else>↻</span>
            {{ refreshing ? 'Refreshing…' : 'Refresh' }}
          </button>
        </span>
      </div>

      <div v-if="!items.length" class="panel" style="margin-top: 14px">
        <p class="muted" style="margin-top: 0">No issues or PRs from this repository are associated to tasks yet.</p>
        <p class="muted" style="margin: 0">
          Paste a GitHub issue or PR link on a task, or import one when creating a task.
        </p>
      </div>

      <template v-else>
        <div class="panel" style="margin-top: 14px">
          <input v-model="query" class="input" placeholder="Filter by title or number…" aria-label="Filter items" />

          <div
            v-if="showKindFilter"
            class="row"
            style="gap: 6px; margin-top: 10px"
            role="group"
            aria-label="Filter by kind"
          >
            <button
              class="btn sm"
              :class="{ primary: !kindFilter }"
              :aria-pressed="!kindFilter"
              @click="kindFilter = ''"
            >
              All {{ items.length }}
            </button>
            <button
              class="btn sm"
              :class="{ primary: kindFilter === 'issue' }"
              :aria-pressed="kindFilter === 'issue'"
              @click="kindFilter = 'issue'"
            >
              Issues {{ kindCounts.issue }}
            </button>
            <button
              class="btn sm"
              :class="{ primary: kindFilter === 'pr' }"
              :aria-pressed="kindFilter === 'pr'"
              @click="kindFilter = 'pr'"
            >
              Pull requests {{ kindCounts.pr }}
            </button>
          </div>

          <div
            v-if="stateOptions.length"
            class="row"
            style="gap: 6px; margin-top: 10px"
            role="group"
            aria-label="Filter by state"
          >
            <button
              class="btn sm"
              :class="{ primary: !stateFilter }"
              :aria-pressed="!stateFilter"
              @click="stateFilter = ''"
            >
              Any state
            </button>
            <button
              v-for="state in stateOptions"
              :key="state.value"
              class="btn sm"
              :class="{ primary: stateFilter === state.value }"
              :aria-pressed="stateFilter === state.value"
              @click="stateFilter = state.value"
            >
              {{ state.label }} {{ state.count }}
            </button>
          </div>
        </div>

        <template v-if="!filtered.length">
          <p class="muted">No issues or PRs match the filters.</p>
        </template>

        <template v-else>
          <template v-if="issues.length">
            <h2 class="group-head">
              Issues <span class="faint">{{ issues.length }}</span>
            </h2>
            <div v-for="item in issues" :key="item.id" class="item">
              <div class="row">
                <span class="badge">issue</span>
                <span v-if="item.number" class="faint">#{{ item.number }}</span>
                <a v-if="item.url" :href="item.url" target="_blank">{{ item.title || item.url }}</a>
                <span v-else>{{ item.title }}</span>
              </div>
              <div v-if="tasksFor(item).length" class="row" style="margin-top: 8px; gap: 6px">
                <router-link
                  v-for="task in tasksFor(item)"
                  :key="task.id"
                  :to="`/task/${task.id}`"
                  class="btn sm ghost"
                >
                  <StatusIcon :status="task.status" :label="statusLabel(task.status)" />
                  {{ task.title }}
                </router-link>
              </div>
              <div v-if="item.fetched_at" class="faint" style="margin-top: 6px">
                fetched {{ timeAgo(item.fetched_at) }}
              </div>
            </div>
          </template>

          <template v-if="pulls.length">
            <h2 class="group-head">
              Pull requests <span class="faint">{{ pulls.length }}</span>
            </h2>
            <div v-for="item in pulls" :key="item.id" class="item">
              <div class="row">
                <span class="badge">PR</span>
                <span v-if="item.number" class="faint">#{{ item.number }}</span>
                <a v-if="item.url" :href="item.url" target="_blank">{{ item.title || item.url }}</a>
                <span v-else>{{ item.title }}</span>
              </div>
              <div v-if="tasksFor(item).length" class="row" style="margin-top: 8px; gap: 6px">
                <router-link
                  v-for="task in tasksFor(item)"
                  :key="task.id"
                  :to="`/task/${task.id}`"
                  class="btn sm ghost"
                >
                  <StatusIcon :status="task.status" :label="statusLabel(task.status)" />
                  {{ task.title }}
                </router-link>
              </div>
              <div v-if="item.fetched_at" class="faint" style="margin-top: 6px">
                fetched {{ timeAgo(item.fetched_at) }}
              </div>
            </div>
          </template>
        </template>
      </template>
    </template>
  </div>
</template>
