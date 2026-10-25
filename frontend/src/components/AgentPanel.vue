<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { api, openRunStream } from '../api'
import {
  LINKED_ITEM_VARIABLES,
  PROMPT_VARIABLE_GROUPS,
  buildPromptContext,
  isCommandPrompt,
  linkedItemVariables,
  linkedPromptItems,
  parseAgentPrompts,
  resolvePromptTemplate,
  taskPrompts,
  taskVariables
} from '../prompts'
import { store, timeAgo } from '../store'
import EntityCard from './EntityCard.vue'
import SessionLinks from './SessionLinks.vue'
import SearchSelect from './SearchSelect.vue'

const props = defineProps({
  task: { type: Object, default: null },
  // The GitHub issue/PR URL this panel works on, used to create a task lazily
  // when an agent run is submitted before any task is linked.
  githubUrl: { type: String, default: '' },
  harnesses: { type: Array, default: () => [] },
  // The linked items the panel's view is about: "issue" in the issue view,
  // "pull_request" in the PR view. Empty means the task's own view, where every
  // linked issue and pull request is relevant.
  contextKind: { type: String, default: '' }
})
const emit = defineEmits(['changed', 'task-created'])

const prompt = ref('')
const promptEl = ref(null)
const harnessId = ref('')
const modelId = ref('')
const modelChoices = ref([])
const modelsLoading = ref(false)
const modelsError = ref('')
const worktreeId = ref('')
const activeRunId = ref('')
const activeRun = ref(null)
const events = ref([])
const running = ref(false)
const runs = ref([])
// Whether to attach the task and view context to a submitted message.
const attachContext = ref(true)
let closeStream = null

// The linked items the panel is about, and the single one that fills the item
// variables when the task names exactly one of them. Empty when there is no task
// yet (the panel creates one on the first run).
const contextItems = computed(() => (props.task ? linkedPromptItems(props.task, props.contextKind || null) : []))
const contextItem = computed(() => (contextItems.value.length === 1 ? contextItems.value[0].item : null))
// Each linked item gets a short identifier (li.a, li.b, ...), so a prompt can
// name a specific one when the task links several.
const linked = computed(() => linkedItemVariables(contextItems.value))

// Where the task lives in the app, so a variable can link straight to it.
const taskUrl = computed(() => {
  const id = props.task?.id
  if (!id) return ''
  const origin = typeof location !== 'undefined' ? location.origin : ''
  return `${origin}/task/${id}`
})

// The values the prompt's variables resolve to. Filled once and reused for the
// prompt buttons and for a message typed into the box.
const variables = computed(() => {
  const base = props.task
    ? taskVariables(props.task, contextItem.value, {
        repositories: store.repositories,
        taskUrl: taskUrl.value
      })
    : {}
  return {
    ...base,
    ...linked.value.variables
  }
})

// The variable palette: the fixed groups, plus one group per linked item when
// the task links several. With a single linked item the unprefixed fields
// already name it, so that group is replaced by the per-item ones only when
// there is more than one.
const paletteGroups = computed(() => {
  const multiple = contextItems.value.length > 1
  const groups = PROMPT_VARIABLE_GROUPS.filter((group) => !(multiple && group.label === 'Linked item'))
  if (!multiple) return groups
  return [
    ...groups,
    ...linked.value.labels.map(({ prefix, item, coords }) => ({
      label: prefix,
      note: `${coords.owner}/${coords.repository}#${coords.number}${item?.title ? ` · ${item.title}` : ''}`,
      variables: LINKED_ITEM_VARIABLES.map((variable) => ({ ...variable, token: `${prefix}.${variable.token}` }))
    }))
  ]
})

// What the submitted message will carry beyond its own text.
const contextSummary = computed(() => {
  const parts = ['task']
  const count = contextItems.value.length
  if (count) {
    const label =
      props.contextKind === 'pull_request' ? 'pull request' : props.contextKind === 'issue' ? 'issue' : 'item'
    parts.push(`${count} linked ${label}${count === 1 ? '' : 's'}`)
  }
  return `Attaches ${parts.join(' + ')}`
})

const liveCwd = computed(() => {
  if (!props.task) return '(repository)'
  const w = (props.task.worktrees || []).find((x) => x.id === worktreeId.value)
  if (w) return w.path
  const active = (props.task.worktrees || []).find((x) => x.status === 'active')
  return active?.path || '(task repository)'
})

// The model a harness answers with when a run selects none: the model set on
// the harness, else the default its own config file names.
function harnessModel(harness) {
  return harness?.model || harness?.default_model || ''
}

// The harness a run uses when the picker keeps its default option.
const effectiveHarness = computed(
  () => props.harnesses.find((h) => h.id === harnessId.value) || props.harnesses.find((h) => h.is_default) || null
)
const effectiveHarnessId = computed(() => effectiveHarness.value?.id || '')

const defaultHarnessLabel = computed(() => {
  const harness = props.harnesses.find((h) => h.is_default)
  if (!harness) return 'Default harness'
  return `Default harness (${harness.name}${harness.available === false ? ', unavailable' : ''})`
})
// The harness picker names harnesses; the model is its own picker, so it never
// repeats the model here.
const harnessOptions = computed(() => [
  { value: '', label: defaultHarnessLabel.value },
  ...props.harnesses.map((h) => ({ value: h.id, label: `${h.name}${h.available ? '' : ' (unavailable)'}` }))
])
const worktreeOptions = computed(() => [
  { value: '', label: 'Auto working directory' },
  ...(props.task?.worktrees || []).filter((w) => w.status === 'active').map((w) => ({ value: w.id, label: w.branch }))
])

// The models the selected harness offers. They live on its ACP session and are
// read by the API (the default harness answers from the session the server holds
// open), so the picker is filled in one request rather than by spawning one.
const modelOptions = computed(() => [
  {
    value: '',
    label: `Harness default${harnessModel(effectiveHarness.value) ? ` · ${harnessModel(effectiveHarness.value)}` : ''}`
  },
  ...modelChoices.value.map((m) => ({ value: m.value, label: m.name }))
])

async function loadModels() {
  // The model is chosen per run, so switching harnesses starts over from the
  // harness's own default.
  modelId.value = ''
  modelChoices.value = []
  modelsError.value = ''
  const harness = effectiveHarness.value
  if (!harness) return
  modelsLoading.value = true
  try {
    const result = await api.harnesses.models(harness.id)
    modelChoices.value = result.models || []
    modelsError.value = result.error || ''
  } catch (e) {
    modelsError.value = e.message
  } finally {
    modelsLoading.value = false
  }
}

// The list belongs to the harness a run would use, so it follows the picker and
// also fills in when the harness list arrives after the panel mounts.
watch(effectiveHarnessId, () => loadModels(), { immediate: true })

// User-defined prompts (Settings → Agent prompts) that apply here: each shows
// only when the task has exactly one associated GitHub item of its kind.
const promptButtons = computed(() =>
  props.task ? taskPrompts(props.task, parseAgentPrompts(store.settings.agent_prompts), variables.value) : []
)

// Insert a variable's token at the cursor, so a click adds it without losing
// what is already typed.
function insertVariable(token) {
  const text = `{${token}}`
  const el = promptEl.value
  if (!el) {
    prompt.value += text
    return
  }
  const start = el.selectionStart ?? prompt.value.length
  const end = el.selectionEnd ?? start
  prompt.value = `${prompt.value.slice(0, start)}${text}${prompt.value.slice(end)}`
  nextTick(() => {
    el.focus()
    el.setSelectionRange(start + text.length, start + text.length)
  })
}

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

// The model a run answers with, named the way the harness names it. A stored run
// carries the label (`model_name`) beside the id it selects with; a live one
// arrives as a `model` event whose text is already that label.
const modelName = computed(() => {
  const stored = String(activeRun.value?.model_name || '').trim()
  if (stored) return stored
  const reported = events.value.find((ev) => ev.type === 'model')
  return String(reported?.text || activeRun.value?.model || '').trim()
})

// What to show for a stored run: the harness's name for the model, with the id
// hovering when the two differ.
function runModel(run) {
  return run.model_name || run.model || ''
}

function runModelTitle(run) {
  return run.model_name && run.model_name !== run.model ? run.model : ''
}

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
  if (!props.task?.id) {
    runs.value = []
    return
  }
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

// The message a run receives: the prompt with its variables filled, plus the
// task and view context unless the message is a command that carries its own
// arguments.
function composePrompt(text) {
  const resolved = resolvePromptTemplate(text, variables.value)
  if (!attachContext.value || isCommandPrompt(resolved)) return resolved
  const context = props.task
    ? buildPromptContext(props.task, contextItems.value, { repositories: store.repositories })
    : ''
  return context ? `${resolved}\n\n---\n${context}` : resolved
}

async function start(text) {
  const raw = (typeof text === 'string' ? text : prompt.value).trim()
  if (!raw || running.value) return
  // When no task is linked yet, create one from the GitHub URL first, so the
  // run (and its worktree, context, and history) has a home.
  let task = props.task
  if (!task?.id) {
    if (!props.githubUrl) {
      store.notify('No task is linked to this item', true)
      return
    }
    try {
      const created = await api.tasks.create({ github_url: props.githubUrl })
      await store.loadTasks().catch(() => {})
      await store.loadItems().catch(() => {})
      task = (store.tasks || []).find((item) => item.id === created.id) || created
      emit('task-created', task)
    } catch (e) {
      store.notify(e.message, true)
      return
    }
  }
  const value = composePrompt(raw)
  running.value = true
  events.value = []
  try {
    const body = { prompt: value }
    if (harnessId.value) body.harness_id = harnessId.value
    if (worktreeId.value) body.worktree_id = worktreeId.value
    if (modelId.value) body.model = modelId.value
    const run = await api.runs.create(task.id, body)
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
  // A queued run has not started yet; follow it so its first event arrives.
  if (run.status === 'running' || run.status === 'queued') {
    closeStream?.()
    closeStream = openRunStream(run.id, handleEvent)
  }
}

// Show a run started outside this panel (the PR view's findings selector) the
// way a run started here appears: its transcript streams and its row joins the
// history without waiting for a reload.
function adopt(run) {
  if (!run?.id) return
  activeRun.value = run
  activeRunId.value = run.id
  events.value = []
  closeStream?.()
  closeStream = openRunStream(run.id, handleEvent)
  loadRuns()
}

defineExpose({ adopt })

watch(
  () => props.task?.id,
  () => {
    loadRuns()
  }
)
onMounted(() => {
  loadRuns()
})
</script>

<template>
  <section class="panel">
    <div class="panel-head"><h2>Agent</h2></div>

    <div class="row">
      <SearchSelect v-model="harnessId" class="w-170" :options="harnessOptions" placeholder="Default harness" />
      <SearchSelect
        v-model="modelId"
        class="grow model-select"
        :options="modelOptions"
        :disabled="modelsLoading"
        placeholder="Harness default"
      />
      <SearchSelect v-model="worktreeId" class="grow" :options="worktreeOptions" placeholder="Auto working directory" />
    </div>
    <div v-if="modelsError" class="faint" style="margin-bottom: 8px">Model list: {{ modelsError }}</div>
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
      ref="promptEl"
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

    <div class="prompt-context row">
      <label class="row" style="gap: 6px; cursor: pointer">
        <input v-model="attachContext" type="checkbox" :disabled="running" />
        <span class="faint">Attach context</span>
      </label>
      <span class="faint">{{ contextSummary }}</span>
    </div>

    <div class="prompt-vars">
      <span class="faint prompt-vars-title">Variables</span>
      <div v-for="group in paletteGroups" :key="group.label" class="prompt-vars-row">
        <span class="prompt-vars-group faint">{{ group.label }}</span>
        <span v-if="group.note" class="faint prompt-vars-note">{{ group.note }}</span>
        <button
          v-for="variable in group.variables"
          :key="variable.token"
          type="button"
          class="chip prompt-var"
          :title="variable.description"
          :disabled="running"
          @click="insertVariable(variable.token)"
        >
          {{ variable.token }}
        </button>
      </div>
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
        <span v-if="runModel(run)" class="faint mono" :title="runModelTitle(run)">{{ runModel(run) }}</span>
        <span class="faint">{{ timeAgo(run.created_at) }}</span>
      </template>
      <div v-if="run.links?.length" @click.stop>
        <SessionLinks :links="run.links" compact />
      </div>
    </EntityCard>
  </section>
</template>
