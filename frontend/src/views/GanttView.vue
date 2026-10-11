<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { store, statusClass } from '../store'

const rows = ref([])
const loading = ref(false)
const error = ref('')
const includeDone = ref(false)
// The visible window is edited through two datetime fields. Until the user edits
// one, refreshes refit the window to the data.
const rangeStart = ref('')
const rangeEnd = ref('')
const rangePinned = ref(false)

// A marker's color and label are derived from its timeline event type.
const MARKER_KIND = {
  created: 'accent',
  updated: 'blue',
  item_added: 'warn',
  item_removed: 'warn',
  worktree_created: 'violet',
  worktree_removed: 'muted',
  run_started: 'blue',
  context_refresh: 'blue',
  context_updated: 'ok',
  context_refresh_failed: 'danger'
}
const MARKER_LABEL = {
  created: 'Created',
  updated: 'Updated',
  item_added: 'Item added',
  item_removed: 'Item removed',
  worktree_created: 'Worktree created',
  worktree_removed: 'Worktree removed',
  run_started: 'Run started',
  context_refresh: 'Context refresh requested',
  context_updated: 'Context updated',
  context_refresh_failed: 'Context refresh failed'
}

function markerKind(type) {
  return MARKER_KIND[type] || 'muted'
}
function markerLabel(type) {
  return MARKER_LABEL[type] || type.replace(/_/g, ' ')
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await api.gantt.get({ includeDone: includeDone.value })
    if (!rangePinned.value) fitRange()
  } catch (e) {
    error.value = e.message
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}
onMounted(load)

// The fit window spans every task and marker and always includes now, so work
// in flight reaches the right edge.
function computeFitDomain() {
  let lo = Date.now()
  let hi = lo
  const see = (t) => {
    if (t < lo) lo = t
    if (t > hi) hi = t
  }
  for (const row of rows.value) {
    see(new Date(row.created_at).getTime())
    see(new Date(row.updated_at).getTime())
    for (const marker of row.markers) see(new Date(marker.created_at).getTime())
  }
  if (hi - lo < 60_000) hi = lo + 60_000
  const pad = (hi - lo) * 0.02
  return { lo: lo - pad, hi: hi + pad }
}

// A datetime-local value is a local-time string with no timezone. Format a
// timestamp the same way, down to the second, so it round-trips exactly.
function toField(t) {
  const d = new Date(t)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// An unset bound defaults to the fitted bound, so editing one end still works.
const bounds = computed(() => {
  const fit = computeFitDomain()
  return {
    lo: rangeStart.value ? new Date(rangeStart.value).getTime() : fit.lo,
    hi: rangeEnd.value ? new Date(rangeEnd.value).getTime() : fit.hi,
    fit
  }
})

const domain = computed(() => {
  const { lo, hi, fit } = bounds.value
  if (Number.isFinite(lo) && Number.isFinite(hi) && hi > lo) return { lo, hi }
  return fit
})

const rangeInvalid = computed(() => {
  if (!rangeStart.value && !rangeEnd.value) return false
  const { lo, hi } = bounds.value
  return !(Number.isFinite(lo) && Number.isFinite(hi) && hi > lo)
})

function onRangeInput() {
  rangePinned.value = !!(rangeStart.value || rangeEnd.value)
}

function fitRange() {
  const fit = computeFitDomain()
  rangePinned.value = false
  rangeStart.value = toField(fit.lo)
  rangeEnd.value = toField(fit.hi)
}

function pct(iso) {
  const t = typeof iso === 'number' ? iso : new Date(iso).getTime()
  const { lo, hi } = domain.value
  return ((t - lo) / (hi - lo)) * 100
}

// Ticks across the window. Short windows show the time of day too, and use
// fewer ticks so the longer labels do not overlap.
const ticks = computed(() => {
  const { lo, hi } = domain.value
  const span = hi - lo
  const withTime = span < 3 * 24 * 60 * 60 * 1000
  const count = withTime ? 3 : 5
  const out = []
  for (let i = 0; i <= count; i++) {
    const t = lo + (span * i) / count
    out.push({
      key: i,
      left: (i / count) * 100,
      label: new Date(t).toLocaleString(
        undefined,
        withTime
          ? { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
          : { month: 'short', day: 'numeric' }
      ),
      align: i === 0 ? 'start' : i === count ? 'end' : 'center'
    })
  }
  return out
})

const nowPct = computed(() => pct(Date.now()))
// "now" may sit outside a range the user picked, so only draw the line when the
// current time falls inside the visible window.
const showNow = computed(() => {
  const value = nowPct.value
  return value >= 0 && value <= 100
})

function barWidth(row) {
  return `${Math.max(pct(row.updated_at) - pct(row.created_at), 0.6)}%`
}

function markerTitle(marker) {
  return `${markerLabel(marker.type)} · ${new Date(marker.created_at).toLocaleString()}\n${marker.message}`
}

const legend = computed(() => {
  const seen = new Set()
  const out = []
  for (const row of rows.value) {
    for (const marker of row.markers) {
      if (seen.has(marker.type)) continue
      seen.add(marker.type)
      out.push({ type: marker.type, kind: markerKind(marker.type), label: markerLabel(marker.type) })
    }
  }
  return out
})
</script>

<template>
  <div>
    <div class="row page-head" style="margin-bottom: 16px">
      <h1 class="grow">Gantt</h1>
      <div class="gantt-range">
        <label class="gantt-range-field">
          <span>From</span>
          <input v-model="rangeStart" type="datetime-local" step="1" class="input" @input="onRangeInput" />
        </label>
        <label class="gantt-range-field">
          <span>To</span>
          <input v-model="rangeEnd" type="datetime-local" step="1" class="input" @input="onRangeInput" />
        </label>
        <button class="btn sm ghost" title="Fit the range to the data" @click="fitRange">Fit</button>
      </div>
      <label class="gantt-toggle">
        <input v-model="includeDone" type="checkbox" @change="load" />
        Include done
      </label>
      <button class="btn sm ghost" @click="load"><span v-if="loading" class="spinner"></span> Refresh</button>
    </div>

    <p v-if="rangeInvalid" class="gantt-range-error">End must be after start. Showing the fitted range.</p>

    <section class="panel">
      <div v-if="error" class="empty">
        Couldn't load the gantt: {{ error }}.
        <div style="margin-top: 10px"><button class="btn sm ghost" @click="load">Retry</button></div>
      </div>
      <div v-else-if="loading && !rows.length" class="empty"><span class="spinner"></span></div>
      <div v-else-if="!rows.length" class="empty">No tasks in flight. Create one to see it here.</div>

      <div v-else class="gantt-scroll">
        <div class="gantt">
          <div class="gantt-row gantt-axis">
            <div class="gantt-label"></div>
            <div class="gantt-track">
              <span
                v-for="tick in ticks"
                :key="tick.key"
                class="gantt-tick"
                :class="tick.align"
                :style="{ left: tick.left + '%' }"
                >{{ tick.label }}</span
              >
            </div>
          </div>

          <router-link
            v-for="row in rows"
            :key="row.id"
            :to="`/task/${row.id}`"
            class="gantt-row gantt-link"
            :title="row.title"
          >
            <div class="gantt-label">
              <span :class="statusClass(row.status)">{{ row.status.replace('_', ' ') }}</span>
              <span class="gantt-title">{{ row.title }}</span>
            </div>
            <div class="gantt-track">
              <span
                v-for="tick in ticks"
                :key="tick.key"
                class="gantt-gridline"
                :style="{ left: tick.left + '%' }"
              ></span>
              <span v-if="showNow" class="gantt-now" :style="{ left: nowPct + '%' }"></span>
              <span
                class="gantt-bar"
                :class="`st-${row.status}`"
                :style="{ left: pct(row.created_at) + '%', width: barWidth(row) }"
              ></span>
              <span
                v-for="marker in row.markers"
                :key="marker.id"
                class="gantt-marker"
                :class="`mk-${markerKind(marker.type)}`"
                :style="{ left: pct(marker.created_at) + '%' }"
                :title="markerTitle(marker)"
              ></span>
            </div>
          </router-link>
        </div>
      </div>

      <div v-if="rows.length" class="gantt-legend">
        <span v-for="item in legend" :key="item.type" class="legend-item">
          <span class="legend-dot" :class="`mk-${item.kind}`"></span>{{ item.label }}
        </span>
        <span v-if="showNow" class="legend-item"><span class="legend-line"></span>now</span>
      </div>
    </section>
  </div>
</template>
