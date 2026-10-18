<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { store, formatDateTime, timeAgo, formatDuration } from '../store'
import EntityCard from '../components/EntityCard.vue'
import ScheduleForm from '../components/ScheduleForm.vue'

// The scheduled shell tasks: user-defined commands the app runs on a cron
// schedule, with their run history. The scheduler lives in the API process, so
// this view only reads state and asks it to run a task now.
const loading = ref(true)
const error = ref(false)
const tasks = ref([])
// The id of the row whose action is in flight, so its buttons disable.
const busy = ref('')
// The task whose run history is open ("" when none).
const expanded = ref('')
// Run history by task id, loaded on demand.
const runs = ref({})
// Pollers by task id, so a running task refreshes until it finishes.
const pollers = {}

// Two views of the same feature: the schedules, and every run across all of
// them, newest first.
const tab = ref('schedules')
const executions = ref([])
const executionsLoading = ref(false)
const executionsError = ref(false)
// The executions whose output is open, keyed by run id.
const openedExecutions = ref({})
let executionsPoller = null
// A background refresh of the active tab, so scheduled runs that fire on their
// own show up (with the advancing next-run time) without a manual Refresh.
let tabPoller = null
const REFRESH_MS = 15000

// The browser's timezone is the sensible default for a new schedule.
const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
// Zone names for the selector: everything the browser knows, plus the browser
// zone and UTC so the default is always offered.
const timezones = (() => {
  const known = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : []
  return [...new Set([...known, browserTimezone, 'UTC'])].sort()
})()

// A fresh draft for a new task.
function blankDraft() {
  return { name: '', command: '', schedule: '0 9 * * *', cwd: '', timezone: browserTimezone, enabled: true }
}

// The new-task draft, held here rather than inside the form so the form can be
// closed and reopened without losing it, and so it is its own object: opening a
// row's edit form never touches this one.
const newDraft = ref(blankDraft())
// The new-task form is hidden until asked for, so the list is what you see first.
const formOpen = ref(false)
// The open edit forms, keyed by task id, each holding its own draft. A row's
// form and draft survive while another form opens, so nothing typed is lost.
const editing = ref({})

async function load({ silent = false } = {}) {
  if (!silent) loading.value = true
  error.value = false
  try {
    tasks.value = await api.schedules.list()
  } catch (e) {
    // A background refresh that fails keeps the last good list rather than
    // replacing it with an error, so a blip does not wipe what you are reading.
    if (!silent) {
      error.value = true
      store.notify(e.message, true)
    }
  } finally {
    if (!silent) loading.value = false
  }
}

function openForm() {
  formOpen.value = true
}

// Closing the new-task form discards its draft, so reopening starts clean.
function closeForm() {
  formOpen.value = false
  newDraft.value = blankDraft()
}

// A draft seeded from a task, for its edit form.
function draftFromTask(task) {
  return {
    name: task.name,
    command: task.command,
    schedule: task.schedule,
    cwd: task.cwd || '',
    timezone: task.timezone || browserTimezone,
    enabled: task.enabled
  }
}

// Open a row's edit form. An already open form keeps the draft it has, so a row
// you come back to still shows what you typed.
function startEdit(task) {
  if (!editing.value[task.id]) editing.value[task.id] = draftFromTask(task)
}

function closeEdit(task) {
  delete editing.value[task.id]
}

function isValid(draft) {
  return Boolean(draft.name.trim() && draft.command.trim() && draft.schedule.trim())
}

function draftBody(draft) {
  return {
    name: draft.name.trim(),
    command: draft.command,
    schedule: draft.schedule.trim(),
    cwd: draft.cwd.trim() || null,
    timezone: draft.timezone.trim() || null,
    enabled: draft.enabled
  }
}

async function saveNew() {
  if (!isValid(newDraft.value)) {
    store.notify('Name, command, and schedule are required', true)
    return
  }
  busy.value = 'new'
  try {
    await api.schedules.create(draftBody(newDraft.value))
    store.notify('Scheduled task created')
    closeForm()
    await load()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function saveEdit(task) {
  const draft = editing.value[task.id]
  if (!isValid(draft)) {
    store.notify('Name, command, and schedule are required', true)
    return
  }
  busy.value = task.id
  try {
    await api.schedules.update(task.id, draftBody(draft))
    store.notify('Scheduled task updated')
    closeEdit(task)
    await load()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function toggleEnabled(task) {
  busy.value = task.id
  try {
    await api.schedules.update(task.id, { enabled: !task.enabled })
    await load()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function remove(task) {
  if (!confirm(`Delete scheduled task "${task.name}" and its run history?`)) return
  busy.value = task.id
  try {
    await api.schedules.remove(task.id)
    if (expanded.value === task.id) expanded.value = ''
    delete runs.value[task.id]
    delete editing.value[task.id]
    await load()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function runNow(task) {
  busy.value = task.id
  try {
    await api.schedules.run(task.id)
    expanded.value = task.id
    await loadRuns(task.id)
    poll(task.id)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function loadRuns(taskId) {
  try {
    runs.value[taskId] = await api.schedules.runs(taskId)
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function loadExecutions({ silent = false } = {}) {
  clearTimeout(executionsPoller)
  executionsPoller = null
  if (!silent) executionsLoading.value = true
  executionsError.value = false
  try {
    executions.value = await api.schedules.executions(100)
  } catch (e) {
    if (!silent) {
      executionsError.value = true
      store.notify(e.message, true)
    }
    return
  } finally {
    if (!silent) executionsLoading.value = false
  }
  // A run in progress settles in seconds, so poll it fast; the slow baseline
  // that catches a newly scheduled run comes from the tab poller.
  if (executions.value.some((run) => run.status === 'running')) {
    executionsPoller = setTimeout(() => {
      if (tab.value === 'executions' && document.visibilityState === 'visible') loadExecutions({ silent: true })
    }, 2000)
  }
}

function selectTab(name) {
  tab.value = name
  if (name === 'executions') loadExecutions()
  else load({ silent: true })
}

function refresh({ silent = false } = {}) {
  if (tab.value === 'executions') loadExecutions({ silent })
  else load({ silent })
}

// Refresh the active tab on a slow timer, so a run the scheduler starts on its
// own (and the next-run time it advances) appears without a manual Refresh.
function scheduleTabRefresh() {
  clearTimeout(tabPoller)
  tabPoller = setTimeout(async () => {
    if (document.visibilityState === 'visible') await refresh({ silent: true })
    scheduleTabRefresh()
  }, REFRESH_MS)
}

// Coming back to the tab should show current state at once, not wait a tick.
function onVisibility() {
  if (document.visibilityState === 'visible') refresh({ silent: true })
}

function toggleExecution(id) {
  openedExecutions.value = { ...openedExecutions.value, [id]: !openedExecutions.value[id] }
}

// Poll a task's runs while one is still running, then reload the list so the
// next-run time and last status refresh too. Bounded so a stuck poller stops.
function poll(taskId) {
  clearTimeout(pollers[taskId])
  pollers[taskId] = setTimeout(async () => {
    await loadRuns(taskId)
    if ((runs.value[taskId] || []).some((run) => run.status === 'running')) {
      poll(taskId)
    } else {
      delete pollers[taskId]
      await load()
    }
  }, 1500)
}

async function toggleRuns(task) {
  if (expanded.value === task.id) {
    expanded.value = ''
    return
  }
  expanded.value = task.id
  if (!runs.value[task.id]) await loadRuns(task.id)
}

function statusClass(status) {
  return { succeeded: 'ok', failed: 'danger', running: 'run' }[status] || ''
}

function runDuration(run) {
  if (!run.ended_at) return 'running'
  return formatDuration(new Date(run.ended_at) - new Date(run.started_at))
}

onMounted(() => {
  load()
  scheduleTabRefresh()
  document.addEventListener('visibilitychange', onVisibility)
})
onUnmounted(() => {
  clearTimeout(executionsPoller)
  clearTimeout(tabPoller)
  document.removeEventListener('visibilitychange', onVisibility)
  for (const id of Object.keys(pollers)) clearTimeout(pollers[id])
})
</script>

<template>
  <div>
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 12px">
      <h1>Scheduled tasks</h1>
      <span class="row" style="gap: 8px; align-items: center">
        <span class="faint">
          {{
            tab === 'schedules'
              ? `${tasks.length} task${tasks.length === 1 ? '' : 's'}`
              : `${executions.length} execution${executions.length === 1 ? '' : 's'}`
          }}
        </span>
        <button class="btn sm ghost" :disabled="tab === 'schedules' ? loading : executionsLoading" @click="refresh()">
          <span v-if="tab === 'schedules' ? loading : executionsLoading" class="spinner" aria-hidden="true"></span>
          Refresh
        </button>
      </span>
    </div>

    <div class="row sched-tabs" role="tablist" aria-label="Scheduled tasks views">
      <button
        class="btn sm"
        :class="{ ghost: tab !== 'schedules' }"
        role="tab"
        :aria-selected="tab === 'schedules'"
        @click="selectTab('schedules')"
      >
        Schedules
      </button>
      <button
        class="btn sm"
        :class="{ ghost: tab !== 'executions' }"
        role="tab"
        :aria-selected="tab === 'executions'"
        @click="selectTab('executions')"
      >
        Executions
      </button>
    </div>

    <template v-if="tab === 'schedules'">
      <div v-if="!formOpen" class="row" style="justify-content: flex-end; margin-bottom: 12px">
        <button class="btn primary" @click="openForm">New scheduled task</button>
      </div>

      <ScheduleForm
        v-if="formOpen"
        v-model="newDraft"
        heading="New scheduled task"
        submit-label="Create scheduled task"
        :saving="busy === 'new'"
        :zones="timezones"
        :browser-timezone="browserTimezone"
        id-prefix="sched"
        @cancel="closeForm"
        @save="saveNew"
      />

      <div v-if="loading" class="empty"><span class="spinner" aria-hidden="true"></span></div>

      <div v-else-if="error" class="panel">
        <p style="margin-top: 0; color: var(--danger)">Could not load scheduled tasks.</p>
        <button class="btn" @click="load">Retry</button>
      </div>

      <div v-else-if="!tasks.length" class="panel">
        <p class="muted" style="margin: 0">
          No scheduled tasks yet. Click New scheduled task to have the app run a shell command on a cron schedule.
        </p>
      </div>

      <div v-else>
        <template v-for="task in tasks" :key="task.id">
          <ScheduleForm
            v-if="editing[task.id]"
            v-model="editing[task.id]"
            :heading="`Edit ${task.name}`"
            submit-label="Save changes"
            :saving="busy === task.id"
            :zones="timezones"
            :browser-timezone="browserTimezone"
            :id-prefix="`sched-${task.id}`"
            @cancel="closeEdit(task)"
            @save="saveEdit(task)"
          />
          <EntityCard v-else>
            <template #lead>
              <span class="badge" :class="task.enabled ? 'ok' : 'warn'">{{ task.enabled ? 'enabled' : 'paused' }}</span>
            </template>
            <template #title>
              <span class="title">{{ task.name }}</span>
            </template>
            <template #actions>
              <div class="row" style="gap: 6px; align-items: center">
                <button class="btn sm" :disabled="busy === task.id" @click="runNow(task)">Run now</button>
                <button class="btn sm ghost" :disabled="busy === task.id" @click="toggleEnabled(task)">
                  {{ task.enabled ? 'Pause' : 'Enable' }}
                </button>
                <button class="btn sm ghost" @click="startEdit(task)">Edit</button>
                <button class="btn sm danger" :disabled="busy === task.id" @click="remove(task)">Delete</button>
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
                <button class="btn sm ghost" @click="toggleRuns(task)">
                  {{ expanded === task.id ? 'Hide runs' : 'Run history' }}
                </button>
              </div>

              <div v-if="expanded === task.id" class="sched-runs">
                <p v-if="!runs[task.id] || !runs[task.id].length" class="faint" style="margin: 8px 0 0">
                  No runs recorded yet.
                </p>
                <div v-for="run in runs[task.id] || []" :key="run.id" class="sched-run">
                  <div class="row" style="gap: 8px; align-items: center">
                    <span class="badge" :class="statusClass(run.status)">{{ run.status }}</span>
                    <span class="faint">
                      {{ formatDateTime(run.started_at) }} · {{ runDuration(run) }}
                      <span v-if="run.exit_code !== null && run.exit_code !== undefined">
                        · exit {{ run.exit_code }}</span
                      >
                    </span>
                  </div>
                  <pre v-if="run.output" class="sched-output">{{ run.output }}</pre>
                </div>
              </div>
            </template>
          </EntityCard>
        </template>
      </div>
    </template>

    <template v-else>
      <div v-if="executionsLoading" class="empty"><span class="spinner" aria-hidden="true"></span></div>

      <div v-else-if="executionsError" class="panel">
        <p style="margin-top: 0; color: var(--danger)">Could not load executions.</p>
        <button class="btn" @click="loadExecutions()">Retry</button>
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
            <button v-if="run.output" class="btn sm ghost" @click="toggleExecution(run.id)">
              {{ openedExecutions[run.id] ? 'Hide output' : 'Show output' }}
            </button>
            <span v-else class="faint" style="font-size: 12px">no output</span>
          </div>
          <pre v-if="openedExecutions[run.id] && run.output" class="sched-output">{{ run.output }}</pre>
        </EntityCard>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sched-tabs {
  gap: 6px;
  margin-bottom: 12px;
}
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
