<script setup>
import { timeAgo } from '../store'

defineProps({ events: { type: Array, default: () => [] } })

function display(value) {
  if (value === null || value === undefined || value === '') return '(empty)'
  const text = Array.isArray(value) ? value.join(', ') : String(value)
  return text.length > 140 ? `${text.slice(0, 137)}…` : text
}

function changes(event) {
  const raw = event.data_json?.changes
  if (!raw || typeof raw !== 'object') return []
  return Object.entries(raw).map(([field, delta]) => ({
    field,
    from: display(delta?.from),
    to: display(delta?.to),
  }))
}
</script>

<template>
  <section class="panel">
    <div class="panel-head"><h2>Timeline</h2></div>
    <div v-if="!events.length" class="faint">Nothing yet.</div>
    <ul class="timeline">
      <li v-for="event in events" :key="event.id">
        <span class="dot"></span>
        <span class="grow">
          <span>{{ event.message || event.type }} <span class="faint">· {{ event.type }}</span></span>
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
  </section>
</template>
