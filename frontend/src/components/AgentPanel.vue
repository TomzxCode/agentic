<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, openRunStream } from '../api'
import { parseAgentPrompts, taskPrompts } from '../prompts'
import { store, timeAgo } from '../store'
import EntityCard from './EntityCard.vue'
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

// User-defined prompts (Settings → Agent prompts) that apply here: each shows
// only when the task has exactly one associated GitHub item of its kind.
const promptButtons = computed(() => taskPrompts(props.task, parseAgentPrompts(store.settings.agent_prompts)))

// ACP names the tool in the update's title (opencode sends just `read` or
// `skill`) and puts the call's own argument in `rawInput`, which arrives with
// the first `tool_update`, not on the `tool_call` itself. The title alone says
// which tool ran and nothing about what it touched, so the row adds the one
// argument that tells two calls of the same tool apart: the file, the skill,
// the command.
const TOOL_DETAIL_LIMIT = 400

function toolName(block) {
  const title = (block.title || '').trim()
  // Some harnesses prefix the call with its description: "Assess PR 27 risk: read".
  const tail = title.includes(': ') ? title.slice(title.lastIndexOf(': ') + 2) : title
  return tail.toLowerCase()
}

// The run's working directory when it is known, so a file under it reads as a
// repo-relative path instead of an absolute one.
const runCwd = computed(() => activeRun.value?.cwd || liveCwd.value)

function displayPath(path, cwd) {
  const value = String(path || '').trim()
  if (!value) return ''
  const base = (cwd || '').replace(/\/+$/, '')
  if (base && value.startsWith(`${base}/`)) return value.slice(base.length + 1)
  const parts = value.split('/').filter(Boolean)
  return parts.length > 3 ? `…/${parts.slice(-3).join('/')}` : value
}

function toolDetail(block, cwd) {
  const raw = block.rawInput || {}
  const locations = block.locations || []
  const name = toolName(block)
  const kind = block.toolKind
  const path = raw.path || raw.filePath || raw.file_path
  const command = raw.command || raw.code || raw.script
  let detail
  if (name === 'shell' || name === 'bash' || name === 'execute' || kind === 'execute') {
    // opencode repeats the command as the call's title, so the detail only adds
    // something when the title says something else.
    const text = command ? command.trim() : ''
    detail = text && text !== (block.title || '').trim() ? `$ ${text}` : ''
  } else if (path) {
    detail = displayPath(path, cwd)
  } else if (locations.length > 1) {
    detail = `${locations.length} files`
  } else if (locations.length === 1) {
    detail = displayPath(locations[0].path, cwd)
  } else if (name === 'grep' || name === 'glob' || name === 'search' || kind === 'search') {
    detail = raw.pattern || raw.query || ''
  } else if (name === 'skill') {
    detail = raw.id || raw.name || ''
  } else if (name === 'subagent' || name === 'task' || kind === 'think') {
    detail = [raw.agent, raw.description].filter(Boolean).join(' · ')
  } else if (name === 'webfetch') {
    detail = raw.url || ''
  } else if (name === 'websearch') {
    detail = raw.query || ''
  } else {
    detail = raw.id || raw.name || raw.query || raw.url || ''
  }
  const text = String(detail).trim()
  return text.length > TOOL_DETAIL_LIMIT ? `${text.slice(0, TOOL_DETAIL_LIMIT - 1)}…` : text
}

// The model the run answers with. ACP reports it as the session's `model`
// config option, so the run reaches the page as a `model` event while it
// streams and as the run's own `model` field once it is stored.
const modelName = computed(() => {
  const stored = String(activeRun.value?.model || '').trim()
  if (stored) return stored
  const reported = events.value.find((ev) => ev.type === 'model')
  return String(reported?.text || '').trim()
})

// The agent streams tiny chunks; merge consecutive ones into readable blocks so
// a message reads as a message instead of one line per token.
const blocks = computed(() => {
  const out = []
  // Calls run in parallel, so their updates interleave: a `tool_update` belongs
  // to the row its `toolCallId` was created for, wherever that row sits.
  const tools = new Map()
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
      const data = ev.data || {}
      const toolId = data.toolCallId
      let block = toolId ? tools.get(toolId) : undefined
      if (block) {
        block.title = ev.text || block.title
        if (data.kind) block.toolKind = data.kind
        // `rawInput` and `locations` arrive with the call's first update; later
        // updates repeat `locations` and carry only the status.
        if (data.rawInput && Object.keys(data.rawInput).length) block.rawInput = data.rawInput
        if (data.locations?.length) block.locations = data.locations
        block.status = data.status || block.status
      } else {
        block = {
          id: `b${out.length}`,
          kind: 'tool',
          label: 'tool',
          toolId,
          title: ev.text,
          toolKind: data.kind,
          rawInput: data.rawInput,
          locations: data.locations,
          status: data.status
        }
        out.push(block)
        if (toolId) tools.set(toolId, block)
      }
      block.detail = toolDetail(block, runCwd.value)
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
    // 'info' and 'usage' are noise; the model is the header's, not a row; skip them.
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

async function start(text) {
  const value = (typeof text === 'string' ? text : prompt.value).trim()
  if (!value || running.value) return
  running.value = true
  events.value = []
  try {
    const body = { prompt: value }
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

    <div v-if="promptButtons.length" class="row" style="margin-bottom: 8px">
      <button
        v-for="p in promptButtons"
        :key="p.key"
        class="btn sm"
        :disabled="running"
        :title="p.text"
        @click="start(p.text)"
      >
        {{ p.label }}
      </button>
    </div>

    <textarea
      v-model="prompt"
      class="textarea"
      :disabled="running"
      placeholder="Ask the agent to work on this task…"
      @keydown.ctrl.enter="start()"
    ></textarea>
    <div class="row" style="margin-top: 8px">
      <button class="btn primary" :disabled="running || !prompt.trim()" @click="start()">
        <span v-if="running" class="spinner"></span> Run
      </button>
      <button v-if="running" class="btn danger" @click="cancel">Cancel</button>
      <span v-if="running" class="faint">streaming…</span>
      <span v-else class="faint kbd-hint">Ctrl+Enter to run</span>
    </div>

    <div v-if="activeRun" class="row transcript-head" style="margin-top: 12px; justify-content: space-between">
      <h3>{{ activeRun.kind === 'refresh_context' ? 'Context refresh' : 'Transcript' }}</h3>
      <span class="row">
        <span v-if="modelName" class="faint mono">{{ modelName }}</span>
        <span class="badge" :class="{ run: activeRun.status === 'running' }">{{ activeRun.status }}</span>
      </span>
    </div>
    <SessionLinks v-if="activeRun" :links="activeRun.links" />
    <div v-if="activeRun" class="transcript" style="margin-top: 6px">
      <div v-if="!blocks.length" class="faint">Waiting for the agent…</div>
      <div v-for="block in blocks" :key="block.id" class="ev" :class="block.kind">
        <span class="who">{{ block.label }}</span>
        <template v-if="block.kind === 'tool'">
          <span class="body"
            >{{ block.title }}<span v-if="block.status"> · {{ block.status }}</span
            ><span v-if="block.detail"> · {{ block.detail }}</span></span
          >
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
    <EntityCard v-for="run in runs" :key="run.id" style="cursor: pointer" @click="viewRun(run)">
      <template #lead>
        <span
          class="badge"
          :class="{ run: run.status === 'running', ok: run.status === 'succeeded', danger: run.status === 'failed' }"
        >
          {{ run.status }}
        </span>
      </template>
      <template #title>
        <span class="title">{{ run.prompt.slice(0, 90) }}</span>
      </template>
      <template #actions>
        <span v-if="run.model" class="faint mono">{{ run.model }}</span>
        <span class="faint">{{ timeAgo(run.created_at) }}</span>
      </template>
      <div v-if="run.links?.length" @click.stop>
        <SessionLinks :links="run.links" compact />
      </div>
    </EntityCard>
  </section>
</template>
