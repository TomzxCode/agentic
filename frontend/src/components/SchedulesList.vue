<script setup>
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'
import ScheduleForm from './ScheduleForm.vue'
import ScheduleRow from './ScheduleRow.vue'

// The "Schedules" tab: the create form, the list of scheduled tasks, and each
// row's edit form. Self-contained: it owns its list, drafts, and the slow
// background refresh, and reports its task count to the page shell header.
const props = defineProps({
  // Whether this tab is showing, so the background refresh only runs for it.
  active: { type: Boolean, default: false },
  // Bumped by the shell's Refresh button to force a reload.
  refreshToken: { type: Number, default: 0 }
})
const emit = defineEmits(['count', 'loading'])

const loading = ref(true)
const error = ref(false)
const tasks = ref([])
// The id of the row whose action is in flight, so its buttons disable.
const busy = ref('')
// The task whose run history is open ("" when none).
const expanded = ref('')

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

const REFRESH_MS = 15000
let tabPoller = null

watch(tasks, () => emit('count', tasks.value.length), { immediate: true })
watch(loading, () => emit('loading', loading.value), { immediate: true })

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
    delete editing.value[task.id]
    await load()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

// Only one row's history is open at a time; the row loads its own runs when it
// opens.
function toggleRuns(task) {
  expanded.value = expanded.value === task.id ? '' : task.id
}

// Refresh on a slow timer while this tab shows, so a run the scheduler starts on
// its own (and the next-run time it advances) appears without a manual Refresh.
function scheduleRefresh() {
  clearTimeout(tabPoller)
  tabPoller = setTimeout(async () => {
    if (props.active && document.visibilityState === 'visible') await load({ silent: true })
    scheduleRefresh()
  }, REFRESH_MS)
}

// Coming back to the tab should show current state at once, not wait a tick.
function onVisibility() {
  if (props.active && document.visibilityState === 'visible') load({ silent: true })
}

// Opening the tab reloads silently, matching the shell's old tab switch.
watch(
  () => props.active,
  (active) => {
    if (active) load({ silent: true })
  }
)
watch(
  () => props.refreshToken,
  () => load({ silent: true })
)

onMounted(() => {
  load()
  scheduleRefresh()
  document.addEventListener('visibilitychange', onVisibility)
})
onUnmounted(() => {
  clearTimeout(tabPoller)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<template>
  <div>
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
        <ScheduleRow
          v-else
          :task="task"
          :busy="busy === task.id"
          :expanded="expanded === task.id"
          :browser-timezone="browserTimezone"
          @edit="startEdit(task)"
          @delete="remove(task)"
          @toggle-enabled="toggleEnabled(task)"
          @toggle="toggleRuns(task)"
          @expand="expanded = task.id"
          @changed="load()"
        />
      </template>
    </div>
  </div>
</template>
