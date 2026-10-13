<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { changeStatusBadge } from '../changes'
import { store } from '../store'

const report = ref(null)
const changes = ref([])
const loading = ref(false)
const error = ref('')

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

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [metrics, changeList] = await Promise.all([
      api.metrics.get({ windowDays: Number(windowDays.value), observationDays: Number(observationDays.value) }),
      api.changes.list()
    ])
    report.value = metrics
    changes.value = changeList
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
  </div>
</template>
