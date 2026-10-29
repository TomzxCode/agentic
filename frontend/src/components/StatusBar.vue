<template>
  <div
    ref="statusBarEl"
    class="status-bar statusbar page-load-status performance-status-bar"
    :class="{ mobile: isMobile }"
    data-testid="status-bar"
    role="status"
    aria-live="polite"
    :style="isMobile ? { left: '0px' } : {}"
  >
    <div v-if="expanded" class="status-bar-resizer" data-testid="status-bar-resizer" @pointerdown="startResize"></div>
    <div class="status-bar-summary">
      <button class="status-bar-toggle" data-testid="status-bar-toggle" type="button" @click="expanded = !expanded">
        {{ expanded ? 'Hide' : 'Show' }} details
      </button>
      <template v-if="!isMobile">
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
          DB: {{ debugStats.dbRequests.reduce((s, r) => s + (r.db_queries || 0), 0) }} queries,
          {{ debugStats.dbRequests.reduce((s, r) => s + (r.db_time_ms || 0), 0).toFixed(2) }} ms
        </span>
      </template>
      <span v-if="lastRequest" class="status-bar-item" data-testid="last-api-call">
        Last: {{ Number(lastRequest.duration_ms || 0).toFixed(2) }} ms ({{ lastRequest.db_queries || 0 }} queries,
        {{ Number(lastRequest.db_time_ms || 0).toFixed(2) }} ms)
      </span>
    </div>
    <div
      v-if="expanded"
      class="status-bar-details"
      data-testid="status-bar-details"
      :style="{ height: detailsHeight + 'px' }"
    >
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
        <button
          type="button"
          class="status-bar-tab"
          :class="{ active: activeTab === 'cli' }"
          data-testid="tab-cli-calls"
          @click="activeTab = 'cli'"
        >
          CLI calls
        </button>
        <button
          type="button"
          class="status-bar-tab"
          :class="{ active: activeTab === 'rpc' }"
          data-testid="tab-rpc-calls"
          @click="activeTab = 'rpc'"
        >
          RPC calls
        </button>
        <button
          v-if="activeTab === 'api'"
          type="button"
          class="status-bar-tab"
          data-testid="clear-api-calls"
          @click="clearApiCalls"
        >
          Clear API calls
        </button>
        <button
          v-else-if="activeTab === 'db'"
          type="button"
          class="status-bar-tab"
          data-testid="clear-db-queries"
          @click="clearDbQueries"
        >
          Clear DB queries
        </button>
        <button
          v-else-if="activeTab === 'cli'"
          type="button"
          class="status-bar-tab"
          data-testid="clear-cli-calls"
          @click="clearCli"
        >
          Clear CLI calls
        </button>
        <button v-else type="button" class="status-bar-tab" data-testid="clear-rpc-calls" @click="clearRpc">
          Clear RPC calls
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
      <div v-else-if="activeTab === 'db'">
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
      <div v-else-if="activeTab === 'cli'">
        <div class="status-bar-sort">
          <label>Sort by</label>
          <select v-model="sortBy" class="status-bar-select">
            <option value="recent">Recent</option>
            <option value="duration">Duration</option>
          </select>
        </div>
        <div v-for="(req, i) in filteredRequests" :key="i" class="status-bar-call">
          <div class="status-bar-call-head" style="cursor: pointer" @click="toggleCall(i)">
            {{ collapsedCalls.has(i) ? '▸' : '▾' }} {{ Math.round(req.duration_ms) }} ms — {{ req.method }}
            {{ req.path }} ({{ (req.cli_calls || []).filter((c) => c.mode === 'cli' || !c.mode).length }} CLI calls,
            {{ Number(req.cli_time_ms || 0).toFixed(2) }} ms)
          </div>
          <ul
            v-if="(req.cli_calls || []).some((c) => c.mode === 'cli' || !c.mode) && !collapsedCalls.has(i)"
            class="status-bar-queries"
          >
            <li
              v-for="(c, j) in (req.cli_calls || []).filter((x) => x.mode === 'cli' || !x.mode)"
              :key="j"
              class="status-bar-query"
            >
              <span class="status-bar-query-time">{{ Number(c.duration_ms || 0).toFixed(2) }} ms</span>
              <code class="status-bar-query-sql">{{ (c.cmd || []).join(' ') }} ({{ c.mode }})</code>
            </li>
          </ul>
        </div>
        <p v-if="!filteredRequests.length" class="status-bar-empty">No CLI calls recorded yet.</p>
      </div>
      <div v-else>
        <div class="status-bar-sort">
          <label>Sort by</label>
          <select v-model="sortBy" class="status-bar-select">
            <option value="recent">Recent</option>
            <option value="duration">Duration</option>
          </select>
        </div>
        <div v-for="(req, i) in filteredRequests" :key="i" class="status-bar-call">
          <div class="status-bar-call-head" style="cursor: pointer" @click="toggleCall(i)">
            {{ collapsedCalls.has(i) ? '▸' : '▾' }} {{ Math.round(req.duration_ms) }} ms — {{ req.method }}
            {{ req.path }} ({{ (req.cli_calls || []).filter((c) => c.mode === 'rpc').length }} RPC calls,
            {{ Number(req.cli_time_ms || 0).toFixed(2) }} ms)
          </div>
          <ul
            v-if="(req.cli_calls || []).some((c) => c.mode === 'rpc') && !collapsedCalls.has(i)"
            class="status-bar-queries"
          >
            <li
              v-for="(c, j) in (req.cli_calls || []).filter((x) => x.mode === 'rpc')"
              :key="j"
              class="status-bar-query"
            >
              <span class="status-bar-query-time">{{ Number(c.duration_ms || 0).toFixed(2) }} ms</span>
              <code class="status-bar-query-sql">{{ (c.cmd || []).join(' ') }}</code>
            </li>
          </ul>
        </div>
        <p v-if="!filteredRequests.length" class="status-bar-empty">No RPC calls recorded yet.</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { usePageLoadPerformance } from '../composables/usePageLoadPerformance'
import {
  debugStats,
  refreshDebugRequests,
  clearApiCalls,
  clearDbQueries,
  clearCliCalls,
  clearCliRequests,
  clearCliQueries,
  clearRpcCalls,
  clearRpcRequests
} from '../debug.js'

const { metrics } = usePageLoadPerformance()
const route = useRoute()
const expanded = ref(localStorage.getItem('agentic.debugExpanded') === 'true')
const activeTab = ref(
  (() => {
    for (const key of ['agentic.debugTab', 'agentic.debugActiveTab', 'agentic.statusBarTab', 'agentic.activeTab']) {
      const value = localStorage.getItem(key)
      if (value) return value
    }
    return 'api'
  })()
)
const isMobile = ref(typeof window !== 'undefined' && window.innerWidth <= 760)
const collapsedCalls = ref(new Set())
const sortBy = ref('recent')
const filter = ref(localStorage.getItem('agentic.debugFilter') || '')
// Published as --status-bar-height so floating chrome (the tasks bulk bar) can
// sit above the status bar however tall it grows.
const statusBarEl = ref(null)
let statusBarObserver

watch(filter, (value) => {
  localStorage.setItem('agentic.debugFilter', value)
})

watch(expanded, (value) => {
  localStorage.setItem('agentic.debugExpanded', String(value))
})

watch(activeTab, (value) => {
  for (const key of ['agentic.debugTab', 'agentic.debugActiveTab', 'agentic.statusBarTab', 'agentic.activeTab']) {
    localStorage.setItem(key, value)
  }
})

const lastRequest = computed(() => (debugStats.requests && debugStats.requests.length ? debugStats.requests[0] : null))

const sortedRequests = computed(() => {
  const list = [
    ...(activeTab.value === 'api'
      ? debugStats.requests
      : activeTab.value === 'db'
        ? debugStats.dbRequests
        : (debugStats.cliRequests ??
          debugStats.cliCalls ??
          debugStats.cliQueries ??
          debugStats.rpcRequests ??
          debugStats.rpcCalls ??
          []))
  ]
  if (sortBy.value === 'duration') return list.sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0))
  if (sortBy.value === 'dbQueries') return list.sort((a, b) => (b.db_queries || 0) - (a.db_queries || 0))
  if (sortBy.value === 'dbTime') return list.sort((a, b) => (b.db_time_ms || 0) - (a.db_time_ms || 0))
  return list
})

function clearCli() {
  clearCliCalls?.()
  clearCliRequests?.()
  clearCliQueries?.()
}

function clearRpc() {
  clearRpcCalls?.()
  clearRpcRequests?.()
}

const filteredRequests = computed(() => {
  let list = sortedRequests.value
  if (activeTab.value === 'cli') {
    list = list.filter((req) => (req.cli_calls || []).some((c) => c.mode === 'cli' || !c.mode))
  }
  if (activeTab.value === 'rpc') {
    list = list.filter((req) => (req.cli_calls || []).some((c) => c.mode === 'rpc'))
  }
  const q = filter.value.trim().toLowerCase()
  if (!q) return list
  return list.filter((req) => `${req.method} ${req.path}`.toLowerCase().includes(q))
})

function toggleCall(index) {
  const next = new Set(collapsedCalls.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  collapsedCalls.value = next
}

const storedDetailsHeight = ref(240)
const detailsHeight = computed(() => {
  if (isMobile.value) {
    return Math.max(80, (typeof window !== 'undefined' ? window.innerHeight : 800) - 48)
  }
  return storedDetailsHeight.value
})
function updateMobile() {
  isMobile.value = window.innerWidth <= 760
}

onMounted(() => {
  const stored = Number(localStorage.getItem('agentic.statusBarHeight'))
  if (Number.isFinite(stored) && stored >= 80 && stored <= 600) storedDetailsHeight.value = stored
  updateMobile()
  window.addEventListener('resize', updateMobile)
  if (statusBarEl.value && typeof ResizeObserver !== 'undefined') {
    statusBarObserver = new ResizeObserver(() => {
      document.documentElement.style.setProperty('--status-bar-height', `${statusBarEl.value?.offsetHeight ?? 0}px`)
    })
    statusBarObserver.observe(statusBarEl.value)
  }
})

function startResize(event) {
  const startY = event.clientY
  const startHeight = storedDetailsHeight.value
  const onMove = (e) => {
    const next = Math.min(600, Math.max(80, startHeight + (startY - e.clientY)))
    storedDetailsHeight.value = next
  }
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    storedDetailsHeight.value = detailsHeight.value
    localStorage.setItem('agentic.statusBarHeight', String(storedDetailsHeight.value))
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

let refreshTimer

function scheduleRefresh() {
  clearTimeout(refreshTimer)
  refreshTimer = setTimeout(refreshDebugRequests, 100)
}

watch(() => route.fullPath, scheduleRefresh)
watch(() => debugStats.apiCalls, scheduleRefresh)
watch(expanded, (value) => {
  if (value) {
    clearTimeout(refreshTimer)
    refreshDebugRequests()
  }
})

onMounted(() => {
  refreshDebugRequests()
})

onUnmounted(() => {
  clearTimeout(refreshTimer)
  window.removeEventListener('resize', updateMobile)
  statusBarObserver?.disconnect()
  document.documentElement.style.removeProperty('--status-bar-height')
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
.status-bar-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  flex: 1 1 auto;
  min-width: 0;
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
  position: absolute;
  top: -3px;
  left: 0;
  right: 0;
  height: 6px;
  cursor: row-resize;
  touch-action: none;
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

@media (max-width: 760px) {
  :global(.sidebar-open) .status-bar {
    display: none;
  }
  .status-bar {
    left: 0;
    padding-bottom: max(4px, env(safe-area-inset-bottom));
  }
  .status-bar-summary {
    flex-wrap: nowrap;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  .status-bar-tabs {
    flex-wrap: wrap;
  }
  .status-bar-resizer {
    display: none;
  }
}
</style>
