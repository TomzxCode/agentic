<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import CumulativeFlow from '../components/CumulativeFlow.vue'
import { formatCycleHours } from '../cycleTime'
import { store } from '../store'

// The Process page draws the SDLC pipeline the way a plant is read: stations
// with their queues, the moves between them, and the distributions that say
// how long an item takes to travel the line. The numbers come from
// GET /api/process, which reads task statuses and their recorded changes.
const report = ref(null)
const loading = ref(false)
const error = ref('')
const days = ref(90)

const WINDOW_OPTIONS = [30, 90, 180, 365]

async function load() {
  loading.value = true
  error.value = ''
  try {
    report.value = await api.process.get({ days: Number(days.value) || 90 })
  } catch (e) {
    error.value = e.message
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function stage(stage) {
  return (report.value?.stages || []).find((entry) => entry.stage === stage) || { stage, count: 0 }
}

function flowCount(fromStage, toStage) {
  const flow = (report.value?.flows || []).find((entry) => entry.from_stage === fromStage && entry.to_stage === toStage)
  return flow ? flow.count : 0
}

// The five boxes of the line. Positions are SVG coordinates inside the
// 760x350 viewBox; the diagram scrolls sideways on phones instead of scaling
// its text below readability.
const BOX_W = 155
const stations = computed(() => [
  { ...stage('backlog'), label: 'Backlog', x: 15, y: 50, h: 92 },
  { ...stage('in_progress'), label: 'In progress', x: 205, y: 50, h: 92 },
  { ...stage('done'), label: 'Done', x: 395, y: 50, h: 92 },
  { ...stage('archived'), label: 'Archived', x: 585, y: 50, h: 92 },
  { ...stage('blocked'), label: 'Blocked', x: 205, y: 235, h: 92 }
])

// The arrows of the line, with each end's move count for the window. An edge
// with no moves keeps its line but hides its label, so the drawing stays quiet.
const DRAWN_FLOWS = new Set([
  'backlog>in_progress',
  'in_progress>done',
  'done>archived',
  'in_progress>blocked',
  'blocked>in_progress'
])

const edges = computed(() => [
  { key: 'backlog>in_progress', x1: 170, y1: 96, x2: 205, y2: 96, lx: 187, ly: 84 },
  { key: 'in_progress>done', x1: 360, y1: 96, x2: 395, y2: 96, lx: 377, ly: 84 },
  { key: 'done>archived', x1: 550, y1: 96, x2: 585, y2: 96, lx: 567, ly: 84 },
  { key: 'in_progress>blocked', x1: 255, y1: 142, x2: 255, y2: 235, lx: 263, ly: 192, anchor: 'start' },
  { key: 'blocked>in_progress', x1: 310, y1: 235, x2: 310, y2: 142, lx: 302, ly: 192, anchor: 'end' }
])

function edgeCount(edge) {
  const [fromStage, toStage] = edge.key.split('>')
  return flowCount(fromStage, toStage)
}

// Moves the drawing does not show (a task sent back to the backlog from done,
// a skip to archived) still matter, so they are listed under the diagram.
const otherFlows = computed(() =>
  (report.value?.flows || []).filter((flow) => !DRAWN_FLOWS.has(`${flow.from_stage}>${flow.to_stage}`))
)

const stageLabel = (name) => (report.value?.stages || []).find((entry) => entry.stage === name)?.label || name

const cycle = computed(() => report.value?.cycle_time || {})

// Histogram bars are drawn against the busiest bucket, like the cycle-time
// trend on the Metrics page draws against its largest median.
const histogram = computed(() => report.value?.histogram || [])
const histogramMax = computed(() => Math.max(1, ...histogram.value.map((bucket) => bucket.count)))
function barHeight(count) {
  if (!count) return 0
  return Math.max(4, (count / histogramMax.value) * 100)
}

const littles = computed(() => report.value?.littles || {})

// Bottleneck ranking: each station's slice of the completed items' total cycle
// time, and whether each active station's queue grew over the window.
const waitShares = computed(() => (report.value?.wait_shares || []).filter((entry) => entry.share > 0))
const topShare = computed(() =>
  waitShares.value.reduce((top, entry) => (top == null || entry.share > top.share ? entry : top), null)
)
const sharePercent = (entry) => `${Math.round(entry.share * 100)}%`

const TREND_META = {
  filling: { label: 'Filling', badge: 'badge warn' },
  draining: { label: 'Draining', badge: 'badge ok' },
  steady: { label: 'Steady', badge: 'badge' }
}
const trendMeta = (trend) => TREND_META[trend] || TREND_META.steady
const pressure = computed(() => report.value?.queue_pressure || [])
function sparkHeights(row) {
  const max = Math.max(1, ...row.weekly_wip)
  return row.weekly_wip.map((value) => (value ? Math.max(15, (value / max) * 100) : 4))
}

// Cumulative flow: one snapshot a day of every station's inventory.
const flowSamples = computed(() => report.value?.flow_samples || [])

// Aging work in progress: what is on the line right now, longest wait first.
const wip = computed(() => report.value?.wip_items || [])
const wipMax = computed(() => Math.max(1, ...wip.value.map((item) => item.age_hours)))

// Flow efficiency: how much of a completed trip was touched work. Touch time
// comes from the focus-stack sessions the backend clips to each trip.
const touch = computed(() => report.value?.touch || {})

// Backlog forecast and outcome breakdown for the window's arrivals.
const forecast = computed(() => report.value?.forecast || {})
const outcomes = computed(() => report.value?.outcomes || { created: 0, done: 0, archived: 0, active: 0 })
const outcomeParts = computed(() =>
  [
    { key: 'done', label: 'Done', count: outcomes.value.done },
    { key: 'backlog', label: 'On the line', count: outcomes.value.active },
    { key: 'archived', label: 'Archived', count: outcomes.value.archived }
  ].filter((part) => part.count > 0)
)
function shortDate(iso) {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// Weekly arrivals vs completions: two bars per week against one shared scale.
const weekly = computed(() => report.value?.weekly || [])
const weeklyMax = computed(() => Math.max(1, ...weekly.value.flatMap((week) => [week.created, week.completed])))
function weekTitle(week) {
  const date = new Date(week.start)
  const label = Number.isNaN(date.getTime()) ? week.start : date.toLocaleDateString()
  return `${label}: ${week.created} arrived, ${week.completed} completed`
}

// Where completed items' time went: only stations something actually waited in.
const dwell = computed(() => (report.value?.dwell || []).filter((entry) => entry.count > 0))
const dwellMax = computed(() => Math.max(1, ...dwell.value.map((entry) => entry.median_hours || 0)))

function countLabel(n) {
  return n === 1 ? '1 item' : `${n} items`
}
</script>

<template>
  <div>
    <div class="row page-head" style="margin-bottom: 16px">
      <h1 class="grow">Process</h1>
      <label class="metric-window">
        <span>Window (days)</span>
        <select v-model.number="days" class="input" @change="load">
          <option v-for="option in WINDOW_OPTIONS" :key="option" :value="option">{{ option }}</option>
        </select>
      </label>
      <button class="btn sm ghost" @click="load"><span v-if="loading" class="spinner"></span> Refresh</button>
    </div>

    <div v-if="error" class="empty">
      Couldn't load the process report: {{ error }}.
      <div style="margin-top: 10px"><button class="btn sm ghost" @click="load">Retry</button></div>
    </div>
    <div v-else-if="!report" class="empty"><span class="spinner"></span></div>
    <template v-else>
      <section class="panel">
        <div class="panel-head">
          <h2>Production line</h2>
          <span class="faint"
            >{{ countLabel(report.arrivals) }} arrived in {{ report.window_days }} days ·
            {{ countLabel(report.completions) }} completed</span
          >
        </div>
        <p class="faint">
          Items wait in the backlog, get worked in progress, park when blocked, and ship to done. The number on an arrow
          is how many items took that move in the window; the number in a station is its current queue.
        </p>
        <div class="process-scroll">
          <svg class="process-svg" viewBox="0 0 760 350" role="img" aria-label="SDLC process graph">
            <defs>
              <marker
                id="process-arrow"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" class="arrow-fill"></path>
              </marker>
            </defs>
            <g v-for="edge in edges" :key="edge.key">
              <line
                class="flow-edge"
                :x1="edge.x1"
                :y1="edge.y1"
                :x2="edge.x2"
                :y2="edge.y2"
                marker-end="url(#process-arrow)"
              ></line>
              <text
                v-if="edgeCount(edge) > 0"
                class="flow-count"
                :x="edge.lx"
                :y="edge.ly"
                :text-anchor="edge.anchor || 'middle'"
              >
                {{ edgeCount(edge) }}
              </text>
            </g>
            <g v-for="station in stations" :key="station.stage">
              <rect
                class="station-rect"
                :class="`st-${station.stage}`"
                :x="station.x"
                :y="station.y"
                :width="BOX_W"
                :height="station.h"
                rx="10"
              ></rect>
              <text class="station-label" :x="station.x + 14" :y="station.y + 24">{{ station.label }}</text>
              <text class="station-count" :x="station.x + 14" :y="station.y + 58">{{ station.count }}</text>
              <text class="station-sub" :x="station.x + 14" :y="station.y + 78">
                {{ station.count ? `median wait ${formatCycleHours(station.median_age_hours)}` : 'empty' }}
              </text>
            </g>
          </svg>
        </div>
        <div v-if="otherFlows.length" class="other-flows">
          <span class="faint">Other moves in the window:</span>
          <span v-for="flow in otherFlows" :key="`${flow.from_stage}>${flow.to_stage}`" class="badge">
            {{ stageLabel(flow.from_stage) }} → {{ stageLabel(flow.to_stage) }} ×{{ flow.count }}
          </span>
        </div>
      </section>

      <section class="panel" style="margin-top: 16px">
        <div class="panel-head">
          <h2>Cumulative flow</h2>
          <span class="faint">inventory per day; a widening band is a queue forming</span>
        </div>
        <CumulativeFlow v-if="flowSamples.length" :samples="flowSamples" />
        <div v-else class="empty">No flow in this window.</div>
      </section>

      <section class="panel" style="margin-top: 16px">
        <div class="panel-head">
          <h2>Bottlenecks</h2>
          <span class="faint">where an average trip's time goes, and which queues grow</span>
        </div>
        <div v-if="!waitShares.length" class="empty">
          Nothing completed in this window, so the waits cannot be split yet. The queue pressure below still shows where
          work piles up.
        </div>
        <template v-else>
          <p class="bottleneck-takeaway">
            An average completed trip ({{ formatCycleHours(cycle.mean_hours) }}) spends
            <strong>{{ sharePercent(topShare) }}</strong> of its time in <strong>{{ topShare.label }}</strong
            >.
          </p>
          <div class="share-bar bottleneck-bar" role="img" aria-label="Share of cycle time per station">
            <span
              v-for="entry in waitShares"
              :key="entry.stage"
              class="share-segment"
              :class="`st-${entry.stage}`"
              :style="{ width: `${entry.share * 100}%` }"
              :title="`${entry.label}: ${sharePercent(entry)}`"
            ></span>
          </div>
          <div class="share-legend">
            <span v-for="entry in waitShares" :key="entry.stage" class="share-legend-item">
              <span class="share-dot" :class="`st-${entry.stage}`"></span>
              {{ entry.label }} {{ sharePercent(entry) }}
            </span>
          </div>
        </template>
        <div class="pressure-rows">
          <div v-for="row in pressure" :key="row.stage" class="pressure-row">
            <span class="dwell-label">{{ row.label }}</span>
            <span class="spark" role="img" :aria-label="`${row.label} inventory by week`">
              <span
                v-for="(height, index) in sparkHeights(row)"
                :key="index"
                class="spark-bar"
                :style="{ height: `${height}%` }"
              ></span>
            </span>
            <span class="faint pressure-nums"
              >{{ row.count }} in station · {{ row.arrived }} in · {{ row.departed }} out</span
            >
            <span :class="trendMeta(row.trend).badge">{{ trendMeta(row.trend).label }}</span>
          </div>
        </div>
      </section>

      <section class="panel" style="margin-top: 16px">
        <div class="panel-head">
          <h2>On the line now</h2>
          <span class="faint">{{ wip.length }} items, longest wait first</span>
        </div>
        <div v-if="!wip.length" class="empty">Nothing is on the line right now.</div>
        <div v-for="item in wip" :key="item.id" class="wip-row">
          <span class="share-dot" :class="`st-${item.stage}`"></span>
          <router-link :to="`/task/${item.id}`" class="wip-title grow">{{ item.title || item.id }}</router-link>
          <span class="wip-bar-track">
            <span
              class="wip-bar"
              :class="`st-${item.stage}`"
              :style="{ width: `${(item.age_hours / wipMax) * 100}%` }"
              :title="`In ${item.stage.replace('_', ' ')} since ${shortDate(item.entered_at)}`"
            ></span>
          </span>
          <span class="wip-age">{{ formatCycleHours(item.age_hours) }}</span>
        </div>
      </section>

      <section class="panel" style="margin-top: 16px">
        <div class="panel-head">
          <h2>Cycle time</h2>
          <span class="faint">creation → done, items completed in the window</span>
        </div>
        <div v-if="!cycle.count" class="empty">Nothing was completed in this window yet.</div>
        <template v-else>
          <div class="metric-grid">
            <article class="metric-card">
              <h2>Median</h2>
              <p class="metric-value">{{ formatCycleHours(cycle.median_hours) }}</p>
              <p class="faint">typical trip down the line</p>
            </article>
            <article class="metric-card">
              <h2>p90</h2>
              <p class="metric-value">{{ formatCycleHours(cycle.p90_hours) }}</p>
              <p class="faint">9 of 10 finish at least this fast</p>
            </article>
            <article class="metric-card">
              <h2>Mean</h2>
              <p class="metric-value">{{ formatCycleHours(cycle.mean_hours) }}</p>
              <p class="faint">
                fastest {{ formatCycleHours(cycle.fastest_hours) }} · slowest
                {{ formatCycleHours(cycle.slowest_hours) }}
              </p>
            </article>
            <article class="metric-card">
              <h2>Completed</h2>
              <p class="metric-value">{{ cycle.count }}</p>
              <p class="faint">{{ countLabel(report.completions) }} in {{ report.window_days }} days</p>
            </article>
            <article class="metric-card">
              <h2>Flow efficiency</h2>
              <p class="metric-value">
                {{ touch.efficiency == null ? 'n/a' : `${Math.round(touch.efficiency * 100)}%` }}
              </p>
              <p class="faint">
                of an average trip was touched work · {{ formatCycleHours(touch.mean_touch_hours) }} per item
              </p>
            </article>
          </div>
          <div class="process-bars" role="img" aria-label="Cycle time distribution">
            <span
              v-for="bucket in histogram"
              :key="bucket.label"
              class="process-bar"
              :class="{ 'process-bar-empty': !bucket.count }"
              :style="{ height: `${barHeight(bucket.count)}%` }"
              :title="`${bucket.label}: ${bucket.count} ${bucket.count === 1 ? 'item' : 'items'}`"
            ></span>
          </div>
          <div class="process-bar-labels">
            <span v-for="bucket in histogram" :key="bucket.label">{{ bucket.label }}</span>
          </div>
          <p class="faint process-span">
            How long completed items took, bucketed. Tall spikes on the right mean old work finally landing.
          </p>
        </template>
      </section>

      <section class="panel" style="margin-top: 16px">
        <div class="panel-head">
          <h2>Flow</h2>
          <span class="faint">arrivals and completions per week</span>
        </div>
        <div class="metric-grid">
          <article class="metric-card">
            <h2>Work in process</h2>
            <p class="metric-value">{{ littles.avg_wip == null ? 'n/a' : littles.avg_wip.toFixed(2) }}</p>
            <p class="faint">average items on the line</p>
          </article>
          <article class="metric-card">
            <h2>Throughput</h2>
            <p class="metric-value">
              {{ littles.throughput_per_day == null ? 'n/a' : `${littles.throughput_per_day.toFixed(2)}/day` }}
            </p>
            <p class="faint">completions per day over the window</p>
          </article>
          <article class="metric-card">
            <h2>Implied cycle time</h2>
            <p class="metric-value">{{ formatCycleHours(littles.projected_cycle_hours) }}</p>
            <p class="faint">Little's law: WIP ÷ throughput, vs {{ formatCycleHours(cycle.median_hours) }} observed</p>
          </article>
          <article class="metric-card">
            <h2>Backlog forecast</h2>
            <p class="metric-value">
              {{ forecast.p50_date == null ? 'n/a' : shortDate(forecast.p50_date) }}
            </p>
            <p class="faint">
              <template v-if="forecast.items === 0">the line is clear</template>
              <template v-else-if="forecast.p85_date != null">
                P85 {{ shortDate(forecast.p85_date) }} · clearing {{ forecast.items }} items from
                {{ forecast.weeks_observed }} weeks of history
              </template>
              <template v-else>no completion history in this window to forecast from</template>
            </p>
          </article>
        </div>
        <div v-if="!weekly.length" class="empty">No flow in this window.</div>
        <template v-else>
          <div class="flow-legend">
            <span><span class="flow-dot arrival"></span> arrived</span>
            <span><span class="flow-dot completed"></span> completed</span>
          </div>
          <div class="flow-chart" role="img" aria-label="Weekly arrivals and completions">
            <div v-for="week in weekly" :key="week.start" class="flow-week" :title="weekTitle(week)">
              <span class="flow-col">
                <span class="flow-bar arrival" :style="{ height: `${(week.created / weeklyMax) * 100}%` }"></span>
                <span class="flow-bar completed" :style="{ height: `${(week.completed / weeklyMax) * 100}%` }"></span>
              </span>
            </div>
          </div>
        </template>
        <div v-if="outcomes.created" class="outcome-block">
          <p class="faint outcome-label">Where the window's {{ outcomes.created }} arrivals stand now</p>
          <div class="share-bar">
            <span
              v-for="part in outcomeParts"
              :key="part.key"
              class="share-segment"
              :class="`st-${part.key}`"
              :style="{ width: `${(part.count / outcomes.created) * 100}%` }"
              :title="`${part.label}: ${part.count}`"
            ></span>
          </div>
          <div class="share-legend">
            <span v-for="part in outcomeParts" :key="part.key" class="share-legend-item">
              <span class="share-dot" :class="`st-${part.key}`"></span>
              {{ part.label }} {{ part.count }}
            </span>
          </div>
        </div>
      </section>

      <section class="panel" style="margin-top: 16px">
        <div class="panel-head">
          <h2>Where the time goes</h2>
          <span class="faint">station waits of completed items</span>
        </div>
        <div v-if="!dwell.length" class="empty">No completed items in this window to break down.</div>
        <div v-for="entry in dwell" :key="entry.stage" class="dwell-row">
          <span class="dwell-label">{{ entry.label }}</span>
          <span class="dwell-bar-track">
            <span class="dwell-bar" :style="{ width: `${((entry.median_hours || 0) / dwellMax) * 100}%` }"></span>
          </span>
          <span class="dwell-num">median {{ formatCycleHours(entry.median_hours) }}</span>
          <span class="dwell-num">mean {{ formatCycleHours(entry.mean_hours) }}</span>
          <span class="faint">{{ entry.count }} visited</span>
        </div>
      </section>
    </template>
  </div>
</template>
