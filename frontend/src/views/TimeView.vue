<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'
import TimeRangeTimeline from '../components/TimeRangeTimeline.vue'
import TimeTrendChart from '../components/TimeTrendChart.vue'
import {
  DAY_MS,
  dayStartMs,
  formatClockTime,
  formatDateTimeShort,
  formatVisitDuration,
  fromDateTimeLocal,
  localDayKey,
  pageColor,
  overlapMs,
  toDateTimeLocal,
  tzOffsetMinutes
} from '../pageTiming'

// The Time page: where the app's foreground time went, over a window and over a
// range the user picks. The client records the visits (see pageTiming.js); this
// page only reads them back.

const WINDOW_OPTIONS = [
  { value: 1, label: 'Today' },
  { value: 7, label: '7 days' },
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' }
]

const windowDays = ref(7)
const report = ref(null)
const loading = ref(false)
const error = ref('')

// The timeline range, held as local wall clock values because that is what the
// two <input type="datetime-local"> fields read and write. The API gets them as
// instants.
const todayStart = dayStartMs(localDayKey())
const rangeStart = ref(toDateTimeLocal(new Date(todayStart)))
const rangeEnd = ref(toDateTimeLocal(new Date(todayStart + DAY_MS)))
const timeline = ref(null)
const timelineLoading = ref(false)
const rangeError = computed(() => {
  const start = fromDateTimeLocal(rangeStart.value)
  const end = fromDateTimeLocal(rangeEnd.value)
  if (!start || !end) return 'Pick a start and an end.'
  if (end.getTime() <= start.getTime()) return 'The end must come after the start.'
  return ''
})
const rangeSpanMs = computed(() => {
  const start = fromDateTimeLocal(rangeStart.value)
  const end = fromDateTimeLocal(rangeEnd.value)
  return start && end ? Math.max(0, end.getTime() - start.getTime()) : 0
})
// The trend highlights every day the range touches, and a click on a column
// narrows the range to that day.
const selectedDays = computed(() => {
  const start = fromDateTimeLocal(rangeStart.value)
  const end = fromDateTimeLocal(rangeEnd.value)
  if (!start || !end || end.getTime() <= start.getTime()) return []
  const days = []
  const cursor = new Date(start.getTime())
  cursor.setHours(0, 0, 0, 0)
  for (let guard = 0; guard < 370 && cursor.getTime() < end.getTime(); guard += 1) {
    days.push(localDayKey(cursor))
    cursor.setDate(cursor.getDate() + 1)
  }
  return days
})
const pages = computed(() => report.value?.pages || [])
const topPage = computed(() => pages.value[0] || null)
const rangeVisits = computed(() => timeline.value?.visits || [])
// Newest first for the list; the API hands them back oldest first for the timeline.
const recentVisits = computed(() => [...rangeVisits.value].reverse())
// Only the part of each visit inside the range, so the header total matches the
// blocks rather than the full length of a visit that crosses a boundary.
const rangeTotalMs = computed(() => {
  const start = fromDateTimeLocal(rangeStart.value)
  const end = fromDateTimeLocal(rangeEnd.value)
  if (!start || !end) return 0
  return rangeVisits.value.reduce(
    (sum, visit) => sum + overlapMs(visit.started_at, visit.ended_at, start.getTime(), end.getTime()),
    0
  )
})

function percent(share) {
  return `${Math.round((share || 0) * 100)}%`
}

function whenLabel(iso) {
  return rangeSpanMs.value > DAY_MS ? formatDateTimeShort(iso) : formatClockTime(iso)
}

function setRange(start, end) {
  rangeStart.value = toDateTimeLocal(start)
  rangeEnd.value = toDateTimeLocal(end)
}

function showDay(key) {
  const start = dayStartMs(key)
  setRange(new Date(start), new Date(start + DAY_MS))
}

function showToday() {
  showDay(localDayKey())
}

function showLast24h() {
  const end = new Date()
  setRange(new Date(end.getTime() - DAY_MS), end)
}

// Only the latest request may replace what is on screen; changing the window
// quickly fires several.
let reportRequest = 0
async function loadReport() {
  const request = ++reportRequest
  loading.value = true
  error.value = ''
  try {
    const result = await api.pageVisits.report({ days: windowDays.value, tzOffset: tzOffsetMinutes() })
    if (request === reportRequest) report.value = result
  } catch (e) {
    if (request === reportRequest) {
      error.value = e.message
      store.notify(e.message, true)
    }
  } finally {
    if (request === reportRequest) loading.value = false
  }
}

let timelineRequest = 0
async function loadTimeline() {
  const start = fromDateTimeLocal(rangeStart.value)
  const end = fromDateTimeLocal(rangeEnd.value)
  if (rangeError.value || !start || !end) {
    timeline.value = null
    return
  }
  const request = ++timelineRequest
  timelineLoading.value = true
  try {
    const result = await api.pageVisits.visits({ start: start.toISOString(), end: end.toISOString() })
    if (request === timelineRequest) timeline.value = result
  } catch (e) {
    if (request === timelineRequest) {
      timeline.value = null
      store.notify(e.message, true)
    }
  } finally {
    if (request === timelineRequest) timelineLoading.value = false
  }
}

function refresh() {
  void loadReport()
  void loadTimeline()
}

watch(windowDays, loadReport)
watch([rangeStart, rangeEnd], loadTimeline)
onMounted(refresh)
</script>

<template>
  <div class="time-page">
    <div class="row page-head">
      <div class="grow">
        <h1>Time</h1>
        <span class="faint">Where the app's foreground time went</span>
      </div>
      <label class="time-window">
        <span>Window</span>
        <select v-model.number="windowDays" class="input">
          <option v-for="option in WINDOW_OPTIONS" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <button class="btn sm ghost" :disabled="loading" @click="refresh">
        <span v-if="loading" class="spinner" aria-hidden="true"></span>
        Refresh
      </button>
    </div>

    <div v-if="error && !report" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load the time report: {{ error }}</p>
      <button class="btn" @click="refresh">Retry</button>
    </div>
    <div v-else-if="!report" class="empty"><span class="spinner"></span></div>

    <template v-else>
      <div class="time-stats">
        <div class="stat">
          <span class="n">{{ formatVisitDuration(report.duration_ms) }}</span
          ><span class="l">tracked</span>
        </div>
        <div class="stat">
          <span class="n">{{ pages.length }}</span
          ><span class="l">pages</span>
        </div>
        <div class="stat">
          <span class="n">{{ report.visits }}</span
          ><span class="l">visits</span>
        </div>
        <div class="stat time-stat-top">
          <span class="n">{{ topPage ? topPage.label : '-' }}</span
          ><span class="l">top page</span>
        </div>
      </div>

      <section class="panel">
        <div class="panel-head">
          <h2>Timeline</h2>
          <span class="faint">
            <span v-if="timelineLoading" class="spinner" aria-hidden="true"></span>
            {{ rangeVisits.length }} {{ rangeVisits.length === 1 ? 'visit' : 'visits' }} ·
            {{ formatVisitDuration(rangeTotalMs) }} in range
          </span>
        </div>
        <div class="row time-range-tools">
          <label class="time-range-field">
            <span>From</span>
            <input v-model="rangeStart" class="input time-range-input" type="datetime-local" aria-label="Range start" />
          </label>
          <label class="time-range-field">
            <span>To</span>
            <input v-model="rangeEnd" class="input time-range-input" type="datetime-local" aria-label="Range end" />
          </label>
          <button class="btn sm ghost" @click="showToday">Today</button>
          <button class="btn sm ghost" @click="showLast24h">Last 24h</button>
        </div>
        <p v-if="rangeError" class="time-range-error">{{ rangeError }}</p>
        <p class="faint time-hint">
          Each row is a page and each block a visit. Time counts while the tab is visible and in use.
        </p>
        <TimeRangeTimeline v-if="timeline" :visits="timeline.visits" :start="timeline.start" :end="timeline.end" />
      </section>

      <div class="time-columns">
        <section class="panel">
          <div class="panel-head">
            <h2>Pages</h2>
            <span class="faint">Share of {{ formatVisitDuration(report.duration_ms) }}</span>
          </div>
          <p v-if="!pages.length" class="faint">No time recorded in this window yet.</p>
          <div v-for="page in pages" :key="page.key" class="time-page-row">
            <div class="time-page-name" :title="page.label">
              <span class="time-dot" :class="pageColor(page.key)" aria-hidden="true"></span>
              <span class="time-ellipsis">{{ page.label }}</span>
            </div>
            <div class="time-bar" role="img" :aria-label="`${page.label}: ${percent(page.share)}`">
              <span
                class="time-bar-fill"
                :class="pageColor(page.key)"
                :style="{ width: `${Math.max(2, Math.round((page.share || 0) * 100))}%` }"
              ></span>
            </div>
            <span class="time-amount">{{ formatVisitDuration(page.duration_ms) }}</span>
            <span class="time-share">{{ percent(page.share) }}</span>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <h2>Daily trend</h2>
            <span class="faint">Click a day to narrow the timeline</span>
          </div>
          <TimeTrendChart :days="report.days" :selected-days="selectedDays" @select="showDay" />
        </section>
      </div>

      <section class="panel">
        <div class="panel-head">
          <h2>Top places</h2>
          <span class="faint">The exact pages behind those totals</span>
        </div>
        <p v-if="!report.places.length" class="faint">No page visits recorded yet.</p>
        <div v-for="place in report.places" :key="place.path" class="time-place-row">
          <div class="time-place-main">
            <span class="time-place-title">{{ place.detail || place.label }}</span>
            <span class="faint">
              {{ place.detail ? place.label : 'page' }} · {{ place.visits }}
              {{ place.visits === 1 ? 'visit' : 'visits' }}
            </span>
          </div>
          <RouterLink class="time-place-path time-ellipsis" :to="place.path" :title="place.path">
            {{ place.path }}
          </RouterLink>
          <span class="time-amount">{{ formatVisitDuration(place.duration_ms) }}</span>
          <span class="time-share">{{ percent(place.share) }}</span>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Visits in range</h2>
          <span class="faint">{{ rangeVisits.length }} shown · {{ formatVisitDuration(rangeTotalMs) }} in range</span>
        </div>
        <p v-if="!recentVisits.length" class="faint">No visits in this range.</p>
        <div v-for="visit in recentVisits" :key="visit.id" class="time-visit-row">
          <span class="time-visit-when">
            <span>{{ whenLabel(visit.started_at) }}</span>
            <span>{{ whenLabel(visit.ended_at) }}</span>
          </span>
          <div class="time-visit-main">
            <RouterLink :to="visit.path">{{ visit.detail || visit.title }}</RouterLink>
            <span class="faint">{{ visit.detail ? visit.title : visit.path }}</span>
          </div>
          <span class="time-amount">{{ formatVisitDuration(visit.duration_ms) }}</span>
        </div>
      </section>
    </template>
  </div>
</template>
