<script setup>
import { computed, onMounted, ref } from 'vue'
import { store, statusLabel, timeAgo } from '../store'
import { itemsForRepository, sortItems } from '../repositories'
import StatusIcon from '../components/StatusIcon.vue'

const props = defineProps({ id: { type: String, required: true } })

const loading = ref(true)
const error = ref(false)
const query = ref('')

const repository = computed(() => store.repositories.find((r) => r.id === props.id) || null)
const tasksById = computed(() => Object.fromEntries(store.tasks.map((task) => [task.id, task])))

const items = computed(() => (repository.value ? itemsForRepository(repository.value, store.items) : []))

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = sortItems(items.value)
  if (!q) return list
  return list.filter(
    (item) =>
      String(item.title || '')
        .toLowerCase()
        .includes(q) || String(item.number || '').includes(q)
  )
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
        </div>

        <template v-if="!filtered.length">
          <p class="muted">No issues or PRs match the filter.</p>
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
