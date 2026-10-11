<script setup>
import { store, timeAgo } from '../store'

defineProps({ events: { type: Array, default: () => [] } })

// Relationship fields show a name instead of an id. Prefer the label recorded
// in the event; fall back to the current store (and then the raw id).
function resolveValue(field, value, label) {
  if (label) return label
  if (value === null || value === undefined || value === '') return value
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
    <ul class="timeline">
      <li v-for="event in events" :key="event.id">
        <span class="dot"></span>
        <span class="grow">
          <span
            >{{ event.message || event.type }} <span class="faint">· {{ event.type }}</span></span
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
  </section>
</template>
