<script setup>
import { formatDateTime, formatDuration } from '../store'
import EntityCard from './EntityCard.vue'

// The "Executions" tab: every run across all schedules, newest first, with its
// output toggle. Presentational: the page shell loads the runs and tracks which
// outputs are open.
defineProps({
  executions: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: Boolean, default: false },
  opened: { type: Object, default: () => ({}) }
})
const emit = defineEmits(['toggle-output', 'retry'])

function statusClass(status) {
  return { succeeded: 'ok', failed: 'danger', running: 'run' }[status] || ''
}

function runDuration(run) {
  if (!run.ended_at) return 'running'
  return formatDuration(new Date(run.ended_at) - new Date(run.started_at))
}
</script>

<template>
  <div v-if="loading" class="empty"><span class="spinner" aria-hidden="true"></span></div>

  <div v-else-if="error" class="panel">
    <p style="margin-top: 0; color: var(--danger)">Could not load executions.</p>
    <button class="btn" @click="emit('retry')">Retry</button>
  </div>

  <div v-else-if="!executions.length" class="panel">
    <p class="muted" style="margin: 0">
      No executions yet. Runs appear here as schedules fire or when you run one now.
    </p>
  </div>

  <div v-else>
    <EntityCard v-for="run in executions" :key="run.id">
      <template #lead>
        <span class="badge" :class="statusClass(run.status)">{{ run.status }}</span>
      </template>
      <template #title>
        <span class="title">{{ run.task_name }}</span>
      </template>
      <template #actions>
        <span class="faint" style="font-size: 12px">
          {{ formatDateTime(run.started_at) }} · {{ runDuration(run) }}
          <span v-if="run.exit_code !== null && run.exit_code !== undefined"> · exit {{ run.exit_code }}</span>
        </span>
      </template>

      <pre class="sched-command">{{ run.task_command }}</pre>
      <div class="row" style="gap: 8px; margin-top: 6px; align-items: center">
        <button v-if="run.output" class="btn sm ghost" @click="emit('toggle-output', run.id)">
          {{ opened[run.id] ? 'Hide output' : 'Show output' }}
        </button>
        <span v-else class="faint" style="font-size: 12px">no output</span>
      </div>
      <pre v-if="opened[run.id] && run.output" class="sched-output">{{ run.output }}</pre>
    </EntityCard>
  </div>
</template>

<style scoped>
.sched-command {
  margin: 6px 0 0;
  padding: 8px 10px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-family: var(--mono);
  font-size: 12.5px;
  white-space: pre-wrap;
  word-break: break-word;
}
.sched-output {
  margin: 6px 0 0;
  padding: 8px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-family: var(--mono);
  font-size: 12.5px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow: auto;
}
</style>
