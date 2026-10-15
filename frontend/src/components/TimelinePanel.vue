<script setup>
import { computed, nextTick, onUnmounted, ref } from 'vue'
import { formatDuration, priorityLabel, statusDurations, statusLabel, store, timeAgo } from '../store'
import GanttChart from './GanttChart.vue'
import StatusIcon from './StatusIcon.vue'
import { resolveDomain } from '../gantt'

const props = defineProps({
  events: { type: Array, default: () => [] },
  // The owning task supplies the span (created to last update) and status for
  // the chart; the events alone define the markers.
  task: { type: Object, default: null }
})

// The timeline chart is a single row: the task's span with one marker per event.
const row = computed(() => {
  const events = props.events
  return {
    id: props.task?.id || 'task',
    title: props.task?.title || '',
    status: props.task?.status || 'open',
    created_at: props.task?.created_at || events[0]?.created_at,
    updated_at: props.task?.updated_at || events[events.length - 1]?.created_at,
    markers: events
  }
})

// Fit to the task's own span rather than to now, so an old task does not get
// squeezed against the left edge.
const domain = computed(() => resolveDomain([row.value], '', '', { includeNow: false }))

// Total time spent in each status, in the order the statuses were first entered,
// each with its share of the task's total elapsed time.
const statusSpans = computed(() => {
  const spans = statusDurations(props.task, props.events)
  const total = spans.reduce((sum, span) => sum + span.ms, 0)
  return spans.map((span) => ({ ...span, pct: total ? Math.round((span.ms / total) * 100) : 0 }))
})

// Clicking a marker jumps to its row in the event list and highlights it.
const eventEls = new Map()
const highlightId = ref(null)
let highlightTimer = null

function setEventRef(id) {
  return (el) => {
    if (el) eventEls.set(id, el)
    else eventEls.delete(id)
  }
}

async function focusEvent(marker) {
  highlightId.value = marker.id
  await nextTick()
  eventEls.get(marker.id)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => (highlightId.value = null), 2000)
}

onUnmounted(() => clearTimeout(highlightTimer))

// An item event (item_added / item_removed) links to the item's view when the
// item still exists, so the row resolves the recorded id against the store.
// A deleted item has no view to open, so its row keeps the recorded message as
// plain text.
const ITEM_EVENT_TYPES = new Set(['item_added', 'item_removed'])

function itemId(event) {
  if (!ITEM_EVENT_TYPES.has(event?.type)) return null
  const id = event?.data_json?.item_id
  if (!id) return null
  return store.items.some((entry) => entry.id === id) ? id : null
}

// Relationship fields show a name instead of an id. Prefer the label recorded
// in the event; fall back to the current store (and then the raw id).
function resolveValue(field, value, label) {
  if (label) return label
  if (value === null || value === undefined || value === '') return value
  if (field === 'priority') return priorityLabel(value)
  if (field === 'repository_id') return store.repositories.find((r) => r.id === value)?.name || value
  if (field === 'group_id') return store.groups.find((g) => g.id === value)?.name || value
  if (field === 'harness_id') return store.harnesses.find((h) => h.id === value)?.name || value
  return value
}

function fieldLabel(field) {
  return field.replace(/_id$/, '').replace(/_/g, ' ')
}

function display(field, value, label) {
  if (value === null || value === undefined || value === '') return '(empty)'
  const resolved = resolveValue(field, value, label)
  const text = Array.isArray(resolved) ? resolved.join(', ') : String(resolved)
  return text.length > 140 ? `${text.slice(0, 137)}…` : text
}

function changes(event) {
  const raw = event.data_json?.changes
  if (!raw || typeof raw !== 'object') return []
  return Object.entries(raw).map(([field, delta]) => ({
    field: fieldLabel(field),
    from: display(field, delta?.from, delta?.from_label),
    to: display(field, delta?.to, delta?.to_label)
  }))
}
</script>

<template>
  <section class="panel">
    <div class="panel-head"><h2>Timeline</h2></div>
    <div v-if="!events.length" class="faint">Nothing yet.</div>
    <template v-else>
      <div v-if="statusSpans.length" class="status-spans">
        <span class="status-spans-label faint">Time in status</span>
        <span v-for="span in statusSpans" :key="span.status" class="status-span">
          <StatusIcon :status="span.status" :label="statusLabel(span.status)" />
          <span class="status-span-time">{{ formatDuration(span.ms) }} · {{ span.pct }}%</span>
        </span>
      </div>
      <div class="timeline-gantt">
        <GanttChart :rows="[row]" :domain="domain" compact click-markers @marker-click="focusEvent" />
      </div>
      <ul class="timeline">
        <li
          v-for="event in events"
          :key="event.id"
          :ref="setEventRef(event.id)"
          :class="{ highlight: highlightId === event.id }"
        >
          <span class="dot"></span>
          <span class="grow">
            <span
              ><router-link v-if="itemId(event)" :to="`/items/${itemId(event)}`">{{
                event.message || event.type
              }}</router-link
              ><span v-else>{{ event.message || event.type }}</span>
              <span class="faint"> · {{ event.type }}</span>
              <span class="badge" :title="`Recorded via ${event.client} by a ${event.actor}`"
                >{{ event.client }} · {{ event.actor }}</span
              ></span
            >
            <span v-if="changes(event).length" class="changes">
              <span v-for="change in changes(event)" :key="change.field" class="change">
                <span class="field">{{ change.field }}</span>
                <span class="from">{{ change.from }}</span>
                <span class="arrow">→</span>
                <span class="to">{{ change.to }}</span>
              </span>
            </span>
          </span>
          <span class="when">{{ timeAgo(event.created_at) }}</span>
        </li>
      </ul>
    </template>
  </section>
</template>
