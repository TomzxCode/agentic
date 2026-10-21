<template>
  <div
    class="status-bar statusbar page-load-status performance-status-bar"
    data-testid="status-bar"
    role="status"
    aria-live="polite"
  >
    <button class="status-bar-toggle" data-testid="status-bar-toggle" type="button" @click="expanded = !expanded">
      {{ expanded ? 'Hide' : 'Show' }} details
    </button>
    <span class="status-bar-item" data-testid="page-load-time"> Page loaded in {{ metrics.loadTime }} ms </span>
    <span class="status-bar-item" data-testid="dom-content-loaded">
      DOMContentLoaded: {{ metrics.domContentLoaded }} ms
    </span>
    <span class="status-bar-item" data-testid="ttfb"> TTFB: {{ metrics.ttfb }} ms </span>
    <span v-if="metrics.firstPaint !== null" class="status-bar-item" data-testid="first-paint">
      First paint: {{ metrics.firstPaint }} ms
    </span>
    <span class="status-bar-item" data-testid="api-calls">
      API: {{ debugStats.requests.length }} calls,
      {{ debugStats.requests.reduce((s, r) => s + (r.duration_ms || 0), 0).toFixed(2) }} ms
    </span>
    <span class="status-bar-item" data-testid="db-queries">
      DB: {{ debugStats.requests.reduce((s, r) => s + (r.db_queries || 0), 0) }} queries,
      {{ debugStats.requests.reduce((s, r) => s + (r.db_time_ms || 0), 0).toFixed(2) }} ms
    </span>
    <span v-if="lastRequest" class="status-bar-item" data-testid="last-api-call">
      Last: {{ Number(lastRequest.duration_ms || 0).toFixed(2) }} ms ({{ lastRequest.db_queries || 0 }} queries,
      {{ Number(lastRequest.db_time_ms || 0).toFixed(2) }} ms)
    </span>
    <div
      v-if="expanded"
      class="status-bar-details"
      data-testid="status-bar-details"
      :style="{ maxHeight: detailsHeight + 'px' }"
    >
      <div class="status-bar-resizer" data-testid="status-bar-resizer" @pointerdown="startResize"></div>
      <input v-model="filter" class="status-bar-filter" data-testid="debug-filter" type="text" placeholder="Filter…" />
      <div class="status-bar-tabs">
        <button
          type="button"
          class="status-bar-tab"
          :class="{ active: activeTab === 'api' }"
          data-testid="tab-api-calls"
          @click="activeTab = 'api'"
        >
          API calls
        </button>
        <button
          type="button"
          class="status-bar-tab"
          :class="{ active: activeTab === 'db' }"
          data-testid="tab-db-queries"
          @click="activeTab = 'db'"
        >
          DB queries
        </button>
      </div>
      <div v-if="activeTab === 'api'">
        <div class="status-bar-sort">
          <label>Sort by</label>
          <select v-model="sortBy" class="status-bar-select">
            <option value="recent">Recent</option>
            <option value="duration">Duration</option>
            <option value="dbQueries">DB calls</option>
            <option value="dbTime">DB time</option>
          </select>
        </div>
        <div v-for="(req, i) in filteredRequests" :key="i" class="status-bar-call">
          <div class="status-bar-call-head">
            {{ Math.round(req.duration_ms) }} ms — {{ req.method }} {{ req.path }} (DB: {{ req.db_queries }} queries,
            {{ Math.round(req.db_time_ms) }} ms)
          </div>
        </div>
        <p v-if="!filteredRequests.length" class="status-bar-empty">No API calls recorded yet.</p>
      </div>
      <div v-else>
        <div class="status-bar-sort">
          <label>Sort by</label>
          <select v-model="sortBy" class="status-bar-select">
            <option value="recent">Recent</option>
            <option value="duration">Duration</option>
            <option value="dbQueries">DB calls</option>
            <option value="dbTime">DB time</option>
          </select>
        </div>
        <div v-for="(req, i) in filteredRequests" :key="i" class="status-bar-call">
          <div class="status-bar-call-head" style="cursor: pointer" @click="toggleCall(i)">
            {{ collapsedCalls.has(i) ? '▸' : '▾' }} {{ Math.round(req.duration_ms) }} ms — {{ req.method }}
            {{ req.path }} ({{ (req.queries || []).length }} queries, {{ Number(req.db_time_ms || 0).toFixed(2) }} ms)
          </div>
          <ul v-if="req.queries && req.queries.length && !collapsedCalls.has(i)" class="status-bar-queries">
            <li v-for="(q, j) in req.queries" :key="j" class="status-bar-query">
              <span class="status-bar-query-time">{{ Number(q.duration_ms || 0).toFixed(2) }} ms</span>
              <code class="status-bar-query-sql">{{ q.sql }}</code>
            </li>
          </ul>
        </div>
        <p v-if="!filteredRequests.some((r) => (r.queries || []).length)" class="status-bar-empty">
          No DB queries recorded yet.
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { usePageLoadPerformance } from '../composables/usePageLoadPerformance'
import { debugStats, refreshDebugRequests } from '../debug.js'

const { metrics } = usePageLoadPerformance()
const expanded = ref(false)
const activeTab = ref('api')
const collapsedCalls = ref(new Set())
const sortBy = ref('recent')
const filter = ref(localStorage.getItem('agentic.debugFilter') || '')

watch(filter, (value) => {
  localStorage.setItem('agentic.debugFilter', value)
})

const lastRequest = computed(() => (debugStats.requests && debugStats.requests.length ? debugStats.requests[0] : null))

const sortedRequests = computed(() => {
  const list = [...debugStats.requests]
  if (sortBy.value === 'duration') return list.sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0))
  if (sortBy.value === 'dbQueries') return list.sort((a, b) => (b.db_queries || 0) - (a.db_queries || 0))
  if (sortBy.value === 'dbTime') return list.sort((a, b) => (b.db_time_ms || 0) - (a.db_time_ms || 0))
  return list
})

const filteredRequests = computed(() => {
  const q = filter.value.trim().toLowerCase()
  if (!q) return sortedRequests.value
  return sortedRequests.value.filter((req) => `${req.method} ${req.path}`.toLowerCase().includes(q))
})

function toggleCall(index) {
  const next = new Set(collapsedCalls.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  collapsedCalls.value = next
}

const detailsHeight = ref(240)
onMounted(() => {
  const stored = Number(localStorage.getItem('agentic.statusBarHeight'))
  if (Number.isFinite(stored) && stored >= 80 && stored <= 600) detailsHeight.value = stored
})

function startResize(event) {
  const startY = event.clientY
  const startHeight = detailsHeight.value
  const onMove = (e) => {
    const next = Math.min(600, Math.max(80, startHeight + (startY - e.clientY)))
    detailsHeight.value = next
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    localStorage.setItem('agentic.statusBarHeight', String(detailsHeight.value))
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

watch(expanded, (value) => {
  if (value) refreshDebugRequests()
})

onMounted(() => {
  refreshDebugRequests()
  const timer = setInterval(refreshDebugRequests, 2000)
  // store timer on component instance for cleanup
  onUnmounted(() => clearInterval(timer))
})
</script>

<style scoped>
.status-bar {
  position: fixed;
  left: var(--sidebar-width, 300px);
  right: 0;
  bottom: 0;
  z-index: 60;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  padding: 4px 12px;
  border-top: 1px solid var(--border, #2a2a2a);
  background: var(--bg-1, #111);
  color: var(--muted, #999);
  font-size: 12px;
  font-family: var(--mono, monospace);
}
.status-bar-item {
  white-space: nowrap;
}
.status-bar-toggle {
  background: transparent;
  border: 1px solid var(--border, #2a2a2a);
  color: inherit;
  font: inherit;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
}
.status-bar-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 6px;
}
.status-bar-sort {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}
.status-bar-select {
  background: var(--bg-2, #1a1a1a);
  color: inherit;
  border: 1px solid var(--border, #2a2a2a);
  border-radius: 4px;
  font: inherit;
  padding: 2px 4px;
}
.status-bar-filter {
  width: 100%;
  background: var(--bg-2, #1a1a1a);
  color: inherit;
  border: 1px solid var(--border, #2a2a2a);
  border-radius: 4px;
  font: inherit;
  padding: 2px 6px;
  margin-bottom: 6px;
}
.status-bar-tab {
  background: transparent;
  border: 1px solid var(--border, #2a2a2a);
  color: inherit;
  font: inherit;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 4px;
}
.status-bar-tab.active {
  background: var(--bg-3, #222);
  color: var(--text, #eee);
}
.status-bar-details {
  flex-basis: 100%;
  width: 100%;
  overflow: auto;
  border-top: 1px solid var(--border, #2a2a2a);
  padding-top: 6px;
}
.status-bar-resizer {
  height: 6px;
  cursor: row-resize;
  background: var(--border, #2a2a2a);
  border-radius: 3px;
  margin-bottom: 6px;
}
.status-bar-call {
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border, #2a2a2a);
}
.status-bar-call:last-child {
  border-bottom: none;
}
.status-bar-call-head {
  font-weight: 600;
}
.status-bar-queries {
  list-style: none;
  padding-left: 12px;
  margin: 4px 0 0;
}
.status-bar-query {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border, #2a2a2a);
}
.status-bar-query:last-child {
  border-bottom: none;
}
.status-bar-query-time {
  flex: none;
  color: var(--faint, #666);
}
.status-bar-query-sql {
  white-space: pre-wrap;
  word-break: break-all;
}

.status-bar-empty {
  margin: 4px 0 0;
  color: var(--faint, #666);
}
</style>
