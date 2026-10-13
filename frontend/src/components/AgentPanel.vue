<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, openRunStream } from '../api'
import { store, timeAgo } from '../store'
import SessionLinks from './SessionLinks.vue'
import SearchSelect from './SearchSelect.vue'

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

const defaultHarnessLabel = computed(() => {
  const harness = props.harnesses.find((h) => h.is_default)
  if (!harness) return 'Default harness'
  const model = harness.model ? ` · ${harness.model}` : ''
  return `Default harness (${harness.name}${model}${harness.available === false ? ', unavailable' : ''})`
})
const harnessOptions = computed(() => [
  { value: '', label: defaultHarnessLabel.value },
  ...props.harnesses.map((h) => ({
    value: h.id,
    label: `${h.name}${h.model ? ` · ${h.model}` : ''}${h.available ? '' : ' (unavailable)'}`
  }))
])
const worktreeOptions = computed(() => [
  { value: '', label: 'Auto working directory' },
  ...(props.task.worktrees || []).filter((w) => w.status === 'active').map((w) => ({ value: w.id, label: w.branch }))
])

// The agent streams tiny chunks; merge consecutive ones into readable blocks so
// a message reads as a message instead of one line per token.
const blocks = computed(() => {
  const out = []
  for (const ev of events.value) {
    const kind = ev.type
    if (kind === 'message' || kind === 'thought') {
      const last = out[out.length - 1]
      if (last && last.kind === kind) {
        last.text += ev.text
      } else {
        out.push({
          id: `b${out.length}`,
          kind,
          text: ev.text,
          label: kind === 'message' ? 'assistant' : 'thinking'
        })
      }
    } else if (kind === 'tool_call' || kind === 'tool_update') {
      const toolId = ev.data?.toolCallId
      const last = out[out.length - 1]
      if (last && last.kind === 'tool' && toolId && last.toolId === toolId) {
        last.title = ev.text || last.title
        last.command = ev.data?.rawInput?.command || last.command
        last.status = ev.data?.status || last.status
      } else {
        out.push({
          id: `b${out.length}`,
          kind: 'tool',
          label: 'tool',
          toolId,
          title: ev.text,
          command: ev.data?.rawInput?.command,
          status: ev.data?.status
        })
      }
    } else if (kind === 'plan') {
      out.push({
        id: `b${out.length}`,
        kind: 'plan',
        label: 'plan',
        entries: (ev.data?.entries || []).map((entry) => entry.content)
      })
    } else if (kind === 'permission') {
      out.push({ id: `b${out.length}`, kind: 'permission', label: 'permission', text: ev.text })
    } else if (kind === 'error') {
      out.push({ id: `b${out.length}`, kind: 'error', label: 'error', text: ev.text })
    } else if (kind === 'warning') {
      out.push({ id: `b${out.length}`, kind: 'warning', label: 'warning', text: ev.text })
    }
    // 'info' and 'usage' are noise; skip them.
  }
  return out
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
  // The first streamed event means a worker has picked the run up.
  if (activeRun.value && activeRun.value.status !== 'running') activeRun.value.status = 'running'
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
      <SearchSelect v-model="harnessId" class="w-170" :options="harnessOptions" placeholder="Default harness" />
      <SearchSelect v-model="worktreeId" class="grow" :options="worktreeOptions" placeholder="Auto working directory" />
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
      <div v-if="!blocks.length" class="faint">Waiting for the agent…</div>
      <div v-for="block in blocks" :key="block.id" class="ev" :class="block.kind">
        <span class="who">{{ block.label }}</span>
        <template v-if="block.kind === 'tool'">
          <span class="body"
            >{{ block.title }}<span v-if="block.status"> · {{ block.status }}</span></span
          >
          <span v-if="block.command" class="body"> $ {{ block.command }}</span>
        </template>
        <template v-else-if="block.kind === 'plan'">
          <span class="body">{{ block.entries.join(' · ') }}</span>
        </template>
        <template v-else>
          <span class="body">{{ block.text }}</span>
        </template>
      </div>
    </div>

    <h3 v-if="runs.length" style="margin-top: 16px">History</h3>
    <div v-for="run in runs" :key="run.id" class="item" style="cursor: pointer" @click="viewRun(run)">
      <div class="item-top">
        <span
          class="badge"
          :class="{ run: run.status === 'running', ok: run.status === 'succeeded', danger: run.status === 'failed' }"
        >
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
