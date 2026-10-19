<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { changeStatusBadge, changeCreateBody, changeReferencesItem, isPullRequestItem } from '../changes'
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

// Every linked pull request that could still get a change record: a PR item on
// a task where no change recorded against that task references the PR yet. The
// task page offers its Record change button under this same rule.
const changeCandidates = computed(() => {
  const changeList = changes.value || []
  const rows = []
  for (const item of items.value || []) {
    if (!isPullRequestItem(item)) continue
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
onMounted(async () => {
  await store.loadTasks().catch(() => {})
  await load()
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
// times were stored is refreshed once to pick the time up; an open PR is
// accepted as of now.
async function recordAccepted(row) {
  if (recordingId.value) return
  recordingId.value = row.id
  try {
    const item = row.item
    let mergedAt = item.metadata_json?.merged_at
    const state = String(item.metadata_json?.state || '').toUpperCase()
    if (!mergedAt && state === 'MERGED' && item.url) {
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
      <div v-if="!changeCandidates.length" class="empty">Every linked pull request already has a change recorded.</div>
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
