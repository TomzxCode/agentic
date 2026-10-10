<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, openRunStream } from '../api'
import { store, timeAgo } from '../store'
import SessionLinks from './SessionLinks.vue'

const props = defineProps({ task: { type: Object, required: true }, harnesses: { type: Array, default: () => [] } })
const emit = defineEmits(['changed'])

const prompt = ref('')
const harnessId = ref('')
const worktreeId = ref('')
const activeRunId = ref('')
const activeRun = ref(null)
const events = ref([])
const running = ref(false)
const runs = ref([])
let closeStream = null

const liveCwd = computed(() => {
  const w = props.task.worktrees?.find((x) => x.id === worktreeId.value)
  if (w) return w.path
  const active = props.task.worktrees?.find((x) => x.status === 'active')
  return active?.path || '(task repository)'
})

async function loadRuns() {
  runs.value = await api.runs.list(props.task.id)
}

function handleEvent(ev) {
  if (ev.type === 'run_finished') {
    running.value = false
    activeRunId.value = ''
    // Session id (and therefore its links) is recorded when the run ends.
    if (activeRun.value) api.runs.get(activeRun.value.id).then((fresh) => (activeRun.value = fresh))
    loadRuns()
    emit('changed')
    return
  }
  // Merge streaming tool updates into the existing tool_call entry.
  events.value.push(ev)
}

async function start() {
  if (!prompt.value.trim()) return
  running.value = true
  events.value = []
  try {
    const body = { prompt: prompt.value }
    if (harnessId.value) body.harness_id = harnessId.value
    if (worktreeId.value) body.worktree_id = worktreeId.value
    const run = await api.runs.create(props.task.id, body)
    activeRun.value = run
    activeRunId.value = run.id
    prompt.value = ''
    closeStream?.()
    closeStream = openRunStream(run.id, handleEvent, () => {
      running.value = false
      activeRunId.value = ''
      loadRuns()
      emit('changed')
    })
    loadRuns()
  } catch (e) {
    running.value = false
    store.notify(e.message, true)
  }
}

async function cancel() {
  if (activeRunId.value) await api.runs.cancel(activeRunId.value)
}

async function viewRun(run) {
  activeRun.value = await api.runs.get(run.id)
  activeRunId.value = run.id
  events.value = await api.runs.events(run.id)
  if (run.status === 'running') {
    closeStream?.()
    closeStream = openRunStream(run.id, handleEvent)
  }
}

onMounted(loadRuns)
</script>

<template>
  <section class="panel">
    <div class="panel-head"><h2>Agent</h2></div>

    <div class="row">
      <select v-model="harnessId" class="select w-170">
        <option value="">Default harness</option>
        <option v-for="h in harnesses" :key="h.id" :value="h.id" :disabled="!h.available">
          {{ h.name }}{{ h.available ? '' : ' (unavailable)' }}
        </option>
      </select>
      <select v-model="worktreeId" class="select grow">
        <option value="">Auto working directory</option>
        <option v-for="w in (task.worktrees || []).filter((x) => x.status === 'active')" :key="w.id" :value="w.id">
          {{ w.branch }}
        </option>
      </select>
    </div>
    <div class="faint mono" style="margin: 6px 0 8px">cwd: {{ liveCwd }}</div>

    <textarea
      v-model="prompt"
      class="textarea"
      :disabled="running"
      placeholder="Ask the agent to work on this task…"
      @keydown.ctrl.enter="start"
    ></textarea>
    <div class="row" style="margin-top: 8px">
      <button class="btn primary" :disabled="running || !prompt.trim()" @click="start">
        <span v-if="running" class="spinner"></span> Run
      </button>
      <button v-if="running" class="btn danger" @click="cancel">Cancel</button>
      <span v-if="running" class="faint">streaming…</span>
      <span v-else class="faint kbd-hint">Ctrl+Enter to run</span>
    </div>

    <div v-if="activeRun" class="row" style="margin-top: 12px; justify-content: space-between">
      <h3>{{ activeRun.kind === 'refresh_context' ? 'Context refresh' : 'Transcript' }}</h3>
      <span class="badge" :class="{ run: activeRun.status === 'running' }">{{ activeRun.status }}</span>
    </div>
    <SessionLinks v-if="activeRun" :links="activeRun.links" />
    <div v-if="activeRun" class="transcript" style="margin-top: 6px">
      <div v-if="!events.length" class="faint">Waiting for the agent…</div>
      <div v-for="(ev, i) in events" :key="i" class="ev" :class="ev.type">
        <span class="who">{{ ev.type }}</span>
        <span class="body">{{ ev.text }}</span>
        <template v-if="ev.type === 'tool_call' || ev.type === 'tool_update'">
          <span v-if="ev.data?.rawInput?.command" class="body"> $ {{ ev.data.rawInput.command }}</span>
        </template>
      </div>
    </div>

    <h3 v-if="runs.length" style="margin-top: 16px">History</h3>
    <div v-for="run in runs" :key="run.id" class="item" style="cursor: pointer" @click="viewRun(run)">
      <div class="item-top">
        <span class="badge" :class="{ run: run.status === 'running', ok: run.status === 'succeeded', danger: run.status === 'failed' }">
          {{ run.status }}
        </span>
        <span class="grow" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
          {{ run.prompt.slice(0, 90) }}
        </span>
        <span class="faint">{{ timeAgo(run.created_at) }}</span>
      </div>
      <div v-if="run.links?.length" @click.stop>
        <SessionLinks :links="run.links" compact />
      </div>
    </div>
  </section>
</template>
