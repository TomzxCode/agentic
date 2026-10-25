<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { changeStatusBadge, changeCreateBody, changeReferencesItem, isPullRequestItem } from '../changes'
import CycleTimeTrend from '../components/CycleTimeTrend.vue'
import { formatCycleHours } from '../cycleTime'
import { authoredByLogin, itemState } from '../repositories/parse'
import { store } from '../store'

const report = ref(null)
const changes = ref([])
const items = ref([])
const loading = ref(false)
const error = ref('')
// The candidate row whose change is being recorded, so its button shows a
// spinner and cannot be clicked twice.
const recordingId = ref('')

const windowDays = ref(30)
const observationDays = ref(14)

// Cycle time is read from GitHub, so it has its own window and loads per
// repository rather than with the factory metrics above.
const cycle = ref(null)
const cycleLoading = ref(false)
const cycleError = ref('')
const cycleDays = ref(90)
// Remember the last repository on this device, like the other per-device UI
// preferences (the server's settings are shared by every client).
const CYCLE_REPOSITORY_KEY = 'agentic.metricsRepository'
const cycleRepositoryId = ref(localStorage.getItem(CYCLE_REPOSITORY_KEY) || '')
watch(cycleRepositoryId, (value) => {
  if (value) localStorage.setItem(CYCLE_REPOSITORY_KEY, value)
  else localStorage.removeItem(CYCLE_REPOSITORY_KEY)
})
// The viewer's own repositories come first, so the default selection is one
// whose activity is theirs; upstream checkouts stay available below them.
const cycleRepositories = computed(() => {
  const login = (store.settings?.github_login || '').toLowerCase()
  const owner = (repository) =>
    (/(?:github\.com[/:])([^/]+)\//.exec(repository.remote_url || '')?.[1] || '').toLowerCase()
  return (store.repositories || [])
    .filter((repository) => /github\.com/.test(repository.remote_url || ''))
    .sort((a, b) => {
      const own = Number(owner(b) === login) - Number(owner(a) === login)
      return own || (a.name || '').localeCompare(b.name || '')
    })
})

const DIRECTIONS = {
  improving: { label: 'Improving', badge: 'badge ok' },
  worsening: { label: 'Worsening', badge: 'badge danger' },
  flat: { label: 'Flat', badge: 'badge' },
  'no-baseline': { label: 'No baseline', badge: 'badge warn' },
  'no-data': { label: 'No data', badge: 'badge warn' }
}

function directionMeta(direction) {
  return DIRECTIONS[direction] || { label: direction, badge: 'badge' }
}

function percent(value) {
  return value == null ? 'n/a' : `${(value * 100).toFixed(1)}%`
}

const metricEntries = computed(() => report.value?.metrics || [])
const counts = computed(() => report.value?.counts || {})

// Every merged pull request that could still get a change record: a PR item on
// a task where no change recorded against that task references the PR yet. An
// open or draft PR has not landed, so it is not a change yet. Only the viewer's
// own PRs are offered, the same rule that gates the repository view's Record
// change button: a PR someone else wrote is not the viewer's change.
const changeCandidates = computed(() => {
  const changeList = changes.value || []
  const login = store.settings?.github_login
  const rows = []
  for (const item of items.value || []) {
    if (!isPullRequestItem(item)) continue
    if (itemState(item) !== 'merged') continue
    if (!authoredByLogin(item, login)) continue
    for (const taskId of item.task_ids || []) {
      const recorded = changeList.some((change) => change.task_id === taskId && changeReferencesItem(change, item))
      if (!recorded) rows.push({ id: `${taskId}:${item.id}`, taskId, item })
    }
  }
  return rows
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [metrics, changeList, itemList] = await Promise.all([
      api.metrics.get({ windowDays: Number(windowDays.value), observationDays: Number(observationDays.value) }),
      api.changes.list(),
      api.items.list()
    ])
    report.value = metrics
    changes.value = changeList
    items.value = itemList
  } catch (e) {
    error.value = e.message
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}
// Requests can overlap when the selection changes quickly, so only the latest
// one is allowed to replace what is on screen.
let cycleRequest = 0
async function loadCycle(refresh = false) {
  const request = ++cycleRequest
  cycleLoading.value = true
  cycleError.value = ''
  try {
    const result = await api.metrics.cycleTime({
      days: Math.max(1, Number(cycleDays.value) || 90),
      repositoryId: cycleRepositoryId.value || undefined,
      refresh
    })
    if (request === cycleRequest) cycle.value = result
  } catch (e) {
    if (request === cycleRequest) cycleError.value = e.message
  } finally {
    if (request === cycleRequest) cycleLoading.value = false
  }
}

onMounted(async () => {
  await store.loadTasks().catch(() => {})
  const repositoriesLoaded = await store
    .loadRepositories()
    .then(() => true)
    .catch(() => false)
  if (repositoriesLoaded && !cycleRepositories.value.some((repository) => repository.id === cycleRepositoryId.value)) {
    cycleRepositoryId.value = cycleRepositories.value[0]?.id || ''
  }
  await load()
  if (cycleRepositories.value.length) await loadCycle()
})

async function setBaseline(metric) {
  try {
    await api.metrics.setBaseline(metric.metric, {
      value: metric.value ?? 0,
      window_days: Number(windowDays.value),
      observation_days: Number(observationDays.value)
    })
    await load()
    store.notify(`Baseline set for ${metric.label}`)
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function clearBaseline(metric) {
  try {
    await api.metrics.removeBaseline(metric.metric)
    await load()
    store.notify(`Baseline cleared for ${metric.label}`)
  } catch (e) {
    store.notify(e.message, true)
  }
}

function taskTitle(id) {
  return store.tasks.find((task) => task.id === id)?.title || id
}

// Record the linked PR as an accepted change, skipping the proposed step. A
// merged PR dates the change to its merge, so an item fetched before merge
// times were stored is refreshed once to pick the time up; with no merge time
// to resolve, the change is accepted as of now.
async function recordAccepted(row) {
  if (recordingId.value) return
  recordingId.value = row.id
  try {
    const item = row.item
    let mergedAt = item.metadata_json?.merged_at
    if (!mergedAt && item.url) {
      const refreshed = await api.items.refresh(item.id).catch(() => null)
      if (refreshed) mergedAt = refreshed.metadata_json?.merged_at
    }
    await api.changes.create(changeCreateBody(row.taskId, item, mergedAt || new Date().toISOString()))
    await load()
    store.notify('Change recorded (accepted)')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    recordingId.value = ''
  }
}
</script>

<template>
  <div>
    <div class="row page-head" style="margin-bottom: 16px">
      <h1 class="grow">Metrics</h1>
      <label class="metric-window">
        <span>Window (days)</span>
        <input v-model.number="windowDays" type="number" min="1" class="input" @change="load" />
      </label>
      <label class="metric-window">
        <span>Observation (days)</span>
        <input v-model.number="observationDays" type="number" min="0" class="input" @change="load" />
      </label>
      <button class="btn sm ghost" @click="load"><span v-if="loading" class="spinner"></span> Refresh</button>
    </div>

    <section class="panel">
      <div v-if="error" class="empty">
        Couldn't load the metrics: {{ error }}.
        <div style="margin-top: 10px"><button class="btn sm ghost" @click="load">Retry</button></div>
      </div>
      <div v-else-if="!report" class="empty"><span class="spinner"></span></div>
      <template v-else>
        <div class="metric-grid">
          <article v-for="metric in metricEntries" :key="metric.metric" class="metric-card">
            <header class="row">
              <h2 class="grow">{{ metric.label }}</h2>
              <span :class="directionMeta(metric.direction).badge">{{ directionMeta(metric.direction).label }}</span>
            </header>
            <p class="metric-value">{{ percent(metric.value) }}</p>
            <p class="faint">
              {{ metric.numerator }} of {{ metric.denominator }} changes
              <template v-if="metric.baseline != null">
                · baseline {{ percent(metric.baseline) }}
                <template v-if="metric.delta != null"
                  >({{ metric.delta >= 0 ? '+' : '' }}{{ percent(metric.delta) }})</template
                >
              </template>
            </p>
            <div class="row">
              <button class="btn sm" :disabled="metric.value == null" @click="setBaseline(metric)">
                Set baseline to current
              </button>
              <button v-if="metric.baseline != null" class="btn sm ghost" @click="clearBaseline(metric)">
                Clear baseline
              </button>
            </div>
          </article>
        </div>

        <p class="faint metric-counts">
          Accepted {{ counts.accepted }}, touchless {{ counts.touchless }}, reverted {{ counts.reverted }}, rejected
          {{ counts.rejected }}, pending observation {{ counts.pending_observation }}, open {{ counts.open }}.
        </p>
      </template>
    </section>

    <section class="panel" style="margin-top: 16px">
      <div class="panel-head">
        <h2>Cycle time</h2>
        <div class="cycle-controls">
          <label class="metric-window">
            <span>Repository</span>
            <select v-model="cycleRepositoryId" class="input" @change="loadCycle()">
              <option value="">All repositories</option>
              <option v-for="repository in cycleRepositories" :key="repository.id" :value="repository.id">
                {{ repository.name }}
              </option>
            </select>
          </label>
          <label class="metric-window">
            <span>Window (days)</span>
            <input v-model.number="cycleDays" type="number" min="1" max="730" class="input" @change="loadCycle()" />
          </label>
          <button class="btn sm ghost" :disabled="cycleLoading" @click="loadCycle(true)">
            <span v-if="cycleLoading" class="spinner"></span> Refresh
          </button>
        </div>
      </div>
      <p class="faint">
        Medians per week, from closed issues and merged pull requests on GitHub. Review wait starts at the first review
        request and ends at the first review; review to merge starts at the first review and ends at the merge.
      </p>
      <div v-if="!cycleRepositories.length" class="empty">No repository has a GitHub remote yet.</div>
      <div v-else-if="cycleError" class="empty">Couldn't load cycle time: {{ cycleError }}.</div>
      <div v-else-if="!cycle" class="empty"><span class="spinner"></span></div>
      <template v-else>
        <div v-for="repository in cycle.repositories" :key="repository.repository_id" class="cycle-repo">
          <div class="cycle-repo-head">
            <h3>{{ repository.name }}</h3>
            <span v-if="repository.full_name" class="faint">{{ repository.full_name }}</span>
          </div>
          <div v-if="repository.error" class="empty">{{ repository.error }}</div>
          <div v-else class="metric-grid">
            <article v-for="series in repository.series" :key="series.metric" class="metric-card">
              <h2>{{ series.label }}</h2>
              <p class="metric-value">{{ formatCycleHours(series.median_hours) }}</p>
              <p class="faint">{{ series.count }} observed</p>
              <CycleTimeTrend :series="series" />
            </article>
          </div>
        </div>
        <div v-if="!cycle.repositories.length" class="empty">No repository has a GitHub remote yet.</div>
      </template>
    </section>

    <section class="panel" style="margin-top: 16px">
      <div class="panel-head">
        <h2>Recent changes</h2>
        <span class="faint">Record changes from a task's page.</span>
      </div>
      <div v-if="!changes.length" class="empty">No changes recorded yet.</div>
      <div v-for="change in changes" :key="change.id" class="change-row">
        <span class="grow">
          <span :class="changeStatusBadge(change.status)">{{ change.status }}</span>
          <span class="faint">{{ change.change_class }}</span>
          {{ change.title || change.id }}
          <span class="faint">· {{ taskTitle(change.task_id) }}</span>
          <span v-if="change.human_intervened" class="badge warn" title="A human touched this change">touched</span>
        </span>
      </div>
    </section>

    <section class="panel" style="margin-top: 16px">
      <div class="panel-head">
        <h2>
          Pull requests without a change record <span class="faint">{{ changeCandidates.length }}</span>
        </h2>
        <span class="faint">Record one here, or open the task for the full lifecycle.</span>
      </div>
      <div v-if="!changeCandidates.length" class="empty">
        Every merged pull request of yours already has a change recorded.
      </div>
      <div v-for="row in changeCandidates" :key="row.id" class="change-row">
        <span class="grow">
          <router-link :to="`/task/${row.taskId}`">{{ taskTitle(row.taskId) }}</router-link>
          <span class="faint">· linked PR</span>
          <a v-if="row.item.url" :href="row.item.url" target="_blank" rel="noopener">
            {{ row.item.title || row.item.url }}
          </a>
          <span v-else>{{ row.item.title }}</span>
        </span>
        <button
          class="btn sm"
          :disabled="recordingId === row.id"
          title="Record this PR as an accepted change"
          @click="recordAccepted(row)"
        >
          <span v-if="recordingId === row.id" class="spinner"></span> Record accepted
        </button>
      </div>
    </section>
  </div>
</template>
