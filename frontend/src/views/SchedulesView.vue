<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { store } from '../store'
import SchedulesList from '../components/SchedulesList.vue'
import SchedulesExecutions from '../components/SchedulesExecutions.vue'

// The scheduled shell tasks: user-defined commands the app runs on a cron
// schedule, with their run history. This shell owns the header, the tab switch,
// and the executions tab; the Schedules tab lives in its own component.
const tab = ref('schedules')
// Reported by the Schedules tab, for the header count and Refresh button.
const taskCount = ref(0)
const schedulesLoading = ref(true)
// Bumped to ask the Schedules tab to reload.
const refreshToken = ref(0)

const executions = ref([])
const executionsLoading = ref(false)
const executionsError = ref(false)
// The executions whose output is open, keyed by run id.
const openedExecutions = ref({})
let executionsPoller = null
// A background refresh of the executions tab, so scheduled runs that fire on
// their own show up without a manual Refresh.
let tabPoller = null
const REFRESH_MS = 15000

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
}

function refresh() {
  if (tab.value === 'executions') loadExecutions()
  else refreshToken.value += 1
}

// Refresh the executions tab on a slow timer, so a run the scheduler starts on
// its own (and the next-run time it advances) appears without a manual Refresh.
function scheduleTabRefresh() {
  clearTimeout(tabPoller)
  tabPoller = setTimeout(async () => {
    if (tab.value === 'executions' && document.visibilityState === 'visible') await loadExecutions({ silent: true })
    scheduleTabRefresh()
  }, REFRESH_MS)
}

// Coming back to the tab should show current state at once, not wait a tick.
function onVisibility() {
  if (tab.value === 'executions' && document.visibilityState === 'visible') loadExecutions({ silent: true })
}

function toggleExecution(id) {
  openedExecutions.value = { ...openedExecutions.value, [id]: !openedExecutions.value[id] }
}

onMounted(() => {
  scheduleTabRefresh()
  document.addEventListener('visibilitychange', onVisibility)
})
onUnmounted(() => {
  clearTimeout(executionsPoller)
  clearTimeout(tabPoller)
  document.removeEventListener('visibilitychange', onVisibility)
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
              ? `${taskCount} task${taskCount === 1 ? '' : 's'}`
              : `${executions.length} execution${executions.length === 1 ? '' : 's'}`
          }}
        </span>
        <button
          class="btn sm ghost"
          :disabled="tab === 'schedules' ? schedulesLoading : executionsLoading"
          @click="refresh"
        >
          <span
            v-if="tab === 'schedules' ? schedulesLoading : executionsLoading"
            class="spinner"
            aria-hidden="true"
          ></span>
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

    <SchedulesList
      v-show="tab === 'schedules'"
      :active="tab === 'schedules'"
      :refresh-token="refreshToken"
      @count="taskCount = $event"
      @loading="schedulesLoading = $event"
    />

    <SchedulesExecutions
      v-if="tab === 'executions'"
      :executions="executions"
      :loading="executionsLoading"
      :error="executionsError"
      :opened="openedExecutions"
      @toggle-output="toggleExecution"
      @retry="loadExecutions()"
    />
  </div>
</template>

<style scoped>
.sched-tabs {
  gap: 6px;
  margin-bottom: 12px;
}
</style>
