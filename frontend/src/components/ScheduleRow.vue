<script setup>
import { onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import { formatDateTime, formatDuration, store, timeAgo } from '../store'
import EntityCard from './EntityCard.vue'

// One scheduled task card: its command, next/last run, actions, and its run
// history. The row owns its run loading and polling (a run settles in seconds);
// it tells the page shell to reload the list once a run finishes.
const props = defineProps({
  task: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  expanded: { type: Boolean, default: false },
  browserTimezone: { type: String, default: 'UTC' }
})
const emit = defineEmits(['edit', 'delete', 'toggle-enabled', 'toggle', 'expand', 'changed'])

const runs = ref([])
const running = ref(false)
let loaded = false
let poller = null

async function fetchRuns() {
  try {
    runs.value = await api.schedules.runs(props.task.id)
  } catch (e) {
    store.notify(e.message, true)
  }
}

// Opening this row's history loads the runs once, then keeps them cached.
watch(
  () => props.expanded,
  (open) => {
    if (open && !loaded) {
      loaded = true
      fetchRuns()
    }
  }
)

// Poll while a run is still running, then reload the list so the next-run time
// and last status refresh too. Bounded so a stuck poller stops.
function poll() {
  clearTimeout(poller)
  poller = setTimeout(async () => {
    await fetchRuns()
    if (runs.value.some((run) => run.status === 'running')) {
      poll()
    } else {
      poller = null
      emit('changed')
    }
  }, 1500)
}

async function runNow() {
  running.value = true
  try {
    await api.schedules.run(props.task.id)
    emit('expand')
    if (!loaded) {
      loaded = true
      await fetchRuns()
    }
    poll()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    running.value = false
  }
}

function statusClass(status) {
  return { succeeded: 'ok', failed: 'danger', running: 'run' }[status] || ''
}

function runDuration(run) {
  if (!run.ended_at) return 'running'
  return formatDuration(new Date(run.ended_at) - new Date(run.started_at))
}

onUnmounted(() => clearTimeout(poller))
</script>

<template>
  <EntityCard>
    <template #lead>
      <span class="badge" :class="task.enabled ? 'ok' : 'warn'">{{ task.enabled ? 'enabled' : 'paused' }}</span>
    </template>
    <template #title>
      <span class="title">{{ task.name }}</span>
    </template>
    <template #actions>
      <div class="row" style="gap: 6px; align-items: center">
        <button class="btn sm" :disabled="busy || running" @click="runNow">Run now</button>
        <button class="btn sm ghost" :disabled="busy" @click="emit('toggle-enabled')">
          {{ task.enabled ? 'Pause' : 'Enable' }}
        </button>
        <button class="btn sm ghost" @click="emit('edit')">Edit</button>
        <button class="btn sm danger" :disabled="busy" @click="emit('delete')">Delete</button>
      </div>
    </template>

    <div class="row" style="gap: 8px; align-items: center; margin-top: 2px">
      <code>{{ task.schedule }}</code>
      <span class="faint">{{ task.timezone }}</span>
      <span v-if="task.cwd" class="faint">in {{ task.cwd }}</span>
    </div>
    <pre class="sched-command">{{ task.command }}</pre>

    <template #meta>
      <div class="row" style="justify-content: space-between; gap: 8px; margin-top: 6px">
        <span class="faint row" style="gap: 8px; align-items: center; flex-wrap: wrap">
          <span v-if="task.next_run_at">
            next {{ formatDateTime(task.next_run_at, task.timezone) }}
            <span v-if="task.timezone !== browserTimezone" class="faint">
              ({{ formatDateTime(task.next_run_at) }} your time)
            </span>
          </span>
          <span v-else>{{ task.enabled ? 'no next run' : 'paused' }}</span>
          <span class="faint">·</span>
          <span v-if="task.last_run_at">
            last
            <span v-if="task.last_status" class="badge" :class="statusClass(task.last_status)">
              {{ task.last_status }}
            </span>
            {{ timeAgo(task.last_run_at) }}
          </span>
          <span v-else>no runs yet</span>
        </span>
        <button class="btn sm ghost" @click="emit('toggle')">
          {{ expanded ? 'Hide runs' : 'Run history' }}
        </button>
      </div>

      <div v-if="expanded" class="sched-runs">
        <p v-if="!runs.length" class="faint" style="margin: 8px 0 0">No runs recorded yet.</p>
        <div v-for="run in runs" :key="run.id" class="sched-run">
          <div class="row" style="gap: 8px; align-items: center">
            <span class="badge" :class="statusClass(run.status)">{{ run.status }}</span>
            <span class="faint">
              {{ formatDateTime(run.started_at) }} · {{ runDuration(run) }}
              <span v-if="run.exit_code !== null && run.exit_code !== undefined"> · exit {{ run.exit_code }}</span>
            </span>
          </div>
          <pre v-if="run.output" class="sched-output">{{ run.output }}</pre>
        </div>
      </div>
    </template>
  </EntityCard>
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
.sched-runs {
  margin-top: 8px;
  border-top: 1px solid var(--border);
}
.sched-run {
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}
.sched-run:last-child {
  border-bottom: none;
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
