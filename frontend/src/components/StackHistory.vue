<script setup>
import { computed } from 'vue'
import { formatTimestamp } from '../stack'

// The stack's history panel: the tasks that were removed or completed.
const props = defineProps({
  history: { type: Array, default: () => [] },
  now: { type: Number, required: true }
})

const nowDate = computed(() => new Date(props.now))

// Two units of precision, matching the stack rows.
function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0))
  const minutes = Math.floor(total / 60)
  const secs = total % 60
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  const days = Math.floor(hours / 24)
  const hrs = hours % 24
  if (days > 0) return `${days}d ${String(hrs).padStart(2, '0')}h`
  if (hours > 0) return `${hours}h ${String(mins).padStart(2, '0')}m`
  return `${minutes}m ${String(secs).padStart(2, '0')}s`
}
</script>

<template>
  <section class="panel" style="margin-top: 16px">
    <div class="panel-head">
      <h2>History</h2>
      <span class="faint">Removed and completed tasks</span>
    </div>
    <div v-if="!history.length" class="empty">Nothing removed yet.</div>
    <table v-else class="stack-table history-table">
      <tbody>
        <tr v-for="entry in history" :key="entry.id" class="stack-row history">
          <td class="stack-indicator">✅</td>
          <td class="stack-title-cell">
            <router-link :to="`/task/${entry.task_id}`" class="stack-title">{{ entry.task?.title }}</router-link>
          </td>
          <td class="stack-col mono faint">{{ formatDuration(entry.duration) }}</td>
          <td class="stack-col mono faint">{{ formatTimestamp(entry.deleted_at, nowDate) }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>
