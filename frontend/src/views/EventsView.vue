<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import { formatDateTime, store, timeAgo } from '../store'

// The events page: every task's timeline in one stream, newest first. A row
// links back to its task, and the page pages backwards with the created_at/id
// cursor the API returns through the last row.

const PAGE_SIZE = 50

const events = ref([])
const loading = ref(true)
const loadingMore = ref(false)
const error = ref(false)
const hasMore = ref(false)
const search = ref('')
const actorFilter = ref('')
const clientFilter = ref('')

// The type prefix gives the row's dot a colour without one class per event
// type: an agent's work, a recorded change, and a person's involvement read
// differently at a glance.
function typeClass(type) {
  if (type.startsWith('change_')) return 'change'
  if (type.startsWith('person_') || type.startsWith('requester_')) return 'person'
  if (type.startsWith('run_') || type.startsWith('context_') || type.startsWith('summary_')) return 'agent'
  return ''
}

function typeLabel(type) {
  return (type || '').replace(/_/g, ' ')
}

function localDayKey(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

function dayLabel(key) {
  const today = new Date()
  if (key === localDayKey(today.toISOString())) return 'Today'
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (key === localDayKey(yesterday.toISOString())) return 'Yesterday'
  const [year, month, day] = key.split('-').map(Number)
  return new Date(year, month, day).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  })
}

// Events arrive newest first, so a new group starts whenever the local day
// changes.
const groups = computed(() => {
  const result = []
  for (const event of events.value) {
    const key = localDayKey(event.created_at)
    let group = result[result.length - 1]
    if (!group || group.key !== key) {
      group = { key, label: dayLabel(key), items: [] }
      result.push(group)
    }
    group.items.push(event)
  }
  return result
})

function filters() {
  return {
    actor: actorFilter.value || undefined,
    client: clientFilter.value || undefined,
    q: search.value.trim() || undefined
  }
}

async function load() {
  loading.value = true
  error.value = false
  try {
    const rows = await api.events.list({ ...filters(), limit: PAGE_SIZE })
    events.value = rows
    hasMore.value = rows.length === PAGE_SIZE
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  const last = events.value[events.value.length - 1]
  if (!last || loadingMore.value) return
  loadingMore.value = true
  try {
    const rows = await api.events.list({
      ...filters(),
      before: last.created_at,
      beforeId: last.id,
      limit: PAGE_SIZE
    })
    events.value = [...events.value, ...rows]
    hasMore.value = rows.length === PAGE_SIZE
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    loadingMore.value = false
  }
}

// Typing filters on the server after a pause, so the stream still covers the
// whole history rather than only the rows already loaded.
let searchTimer = null
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 250)
})
watch([actorFilter, clientFilter], load)

onMounted(load)
onUnmounted(() => clearTimeout(searchTimer))
</script>

<template>
  <div>
    <div class="events-head">
      <div>
        <h1>Events</h1>
        <span class="faint">Every task's activity, newest first</span>
      </div>
      <span class="faint">{{ events.length }}{{ hasMore ? '+' : '' }} shown</span>
    </div>

    <div class="row events-filters">
      <input v-model="search" class="input grow" placeholder="Search message or task…" />
      <select v-model="actorFilter" class="input events-select" aria-label="Filter by actor">
        <option value="">Any actor</option>
        <option value="human">Human</option>
        <option value="agent">Agent</option>
      </select>
      <select v-model="clientFilter" class="input events-select" aria-label="Filter by client">
        <option value="">Any client</option>
        <option value="web">Web</option>
        <option value="cli">CLI</option>
        <option value="api">API</option>
      </select>
      <button class="btn sm ghost" :disabled="loading" @click="load">
        <span v-if="loading" class="spinner" aria-hidden="true"></span>
        Refresh
      </button>
    </div>

    <div v-if="loading && !events.length" class="empty"><span class="spinner"></span></div>
    <div v-else-if="error && !events.length" class="empty">Could not load events.</div>
    <div v-else-if="!events.length" class="empty">No activity yet.</div>
    <template v-else>
      <div v-for="group in groups" :key="group.key" class="event-day">
        <h2 class="event-day-label">{{ group.label }}</h2>
        <ul class="events">
          <li v-for="event in group.items" :key="event.id">
            <span class="event-dot" :class="typeClass(event.type)"></span>
            <span class="grow">
              <span class="event-line">
                <router-link :to="`/task/${event.task_id}`" class="event-task">{{ event.task_title }}</router-link>
                <span class="badge event-type">{{ typeLabel(event.type) }}</span>
                <span class="badge" :title="`Recorded via ${event.client} by a ${event.actor}`"
                  >{{ event.client }} · {{ event.actor }}</span
                >
              </span>
              <span class="event-message">{{ event.message || typeLabel(event.type) }}</span>
            </span>
            <time class="event-when" :datetime="event.created_at" :title="formatDateTime(event.created_at)">{{
              timeAgo(event.created_at)
            }}</time>
          </li>
        </ul>
      </div>
      <div v-if="hasMore" class="row" style="justify-content: center; margin-top: 12px">
        <button class="btn" :disabled="loadingMore" @click="loadMore">
          <span v-if="loadingMore" class="spinner" aria-hidden="true"></span>
          Load older events
        </button>
      </div>
    </template>
  </div>
</template>
