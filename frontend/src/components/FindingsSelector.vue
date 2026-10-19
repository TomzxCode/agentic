<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { buildFindingsPrompt, defaultSelectedFindings, findingKey, findingsBySeverity } from '../reviewFindings'
import { store } from '../store'

// The must/should/may findings recorded for one pull request, with a checkbox
// per finding and a send action that hands the selection to an agent run on the
// task. The agent's skills post them to the PR; this app posts nothing itself.
//
// Rendered inline in the task view's PR mode and inside the share modal the
// review queue opens, so both surfaces share one selection.

const props = defineProps({
  repository: { type: String, required: true },
  number: { type: Number, required: true },
  // The PR's URL, so a task can be imported when none is linked.
  url: { type: String, default: '' },
  // The task the agent runs on, when the PR is already linked to one.
  taskId: { type: String, default: null },
  taskLabel: { type: String, default: '' }
})
const emit = defineEmits(['shared', 'imported'])

const findings = ref([])
const loading = ref(true)
const error = ref(false)
const selected = ref([])
const taskId = ref(props.taskId || '')
const importing = ref(false)
const sending = ref(false)

const groups = computed(() => findingsBySeverity(findings.value))
// The findings chosen for sharing, in the order they are listed.
const chosen = computed(() => findings.value.filter((finding) => selected.value.includes(findingKey(finding))))
const canSend = computed(() => Boolean(taskId.value) && chosen.value.length > 0 && !sending.value)
const prompt = computed(() => buildFindingsPrompt({ repository: props.repository, number: props.number }, chosen.value))

function isSelected(finding) {
  return selected.value.includes(findingKey(finding))
}

// Record the reviewer's choice on the finding's own state file, so it survives a
// reload and the review skills can read it. The list is updated optimistically
// and rolled back when the write fails.
async function record(changes) {
  const before = changes.map(({ finding }) => ({ finding, decision: finding.decision || '' }))
  for (const { finding, decision } of changes) finding.decision = decision
  try {
    findings.value = await api.reviews.decide(
      props.repository,
      props.number,
      changes.map(({ finding, decision }) => ({ step: finding.step, title: finding.title, decision }))
    )
  } catch (e) {
    for (const { finding, decision } of before) finding.decision = decision
    store.notify(e.message, true)
  }
}

function toggle(finding) {
  const key = findingKey(finding)
  const include = !selected.value.includes(key)
  selected.value = include ? [...selected.value, key] : selected.value.filter((item) => item !== key)
  record([{ finding, decision: include ? 'include' : 'skip' }])
}

function selectAll() {
  selected.value = findings.value.map(findingKey)
  if (findings.value.length) {
    record(findings.value.map((finding) => ({ finding, decision: 'include' })))
  }
}

function clearSelection() {
  selected.value = []
  if (findings.value.length) {
    record(findings.value.map((finding) => ({ finding, decision: 'skip' })))
  }
}

async function load() {
  loading.value = true
  error.value = false
  try {
    findings.value = await api.reviews.findings(props.repository, props.number)
    selected.value = defaultSelectedFindings(findings.value)
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

// When the PR has no task, import it as one, the same way the review queue's
// "New task" does, so the agent has somewhere to run.
async function importTask() {
  if (!props.url || importing.value) return
  importing.value = true
  try {
    const task = await api.tasks.create({ github_url: props.url })
    taskId.value = task.id
    store.notify('Task created')
    emit('imported', task)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    importing.value = false
  }
}

async function send() {
  if (!canSend.value) return
  sending.value = true
  try {
    const run = await api.runs.create(taskId.value, { prompt: prompt.value })
    store.notify('Sent the findings to an agent')
    emit('shared', { run, taskId: taskId.value })
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    sending.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="findings-selector">
    <div v-if="loading" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not read this pull request's findings.</p>
      <button class="btn" @click="load()">Retry</button>
    </div>

    <p v-else-if="!findings.length" class="faint" style="margin: 0">
      No must/should/may findings were recorded for this pull request.
    </p>

    <template v-else>
      <div class="row share-tools">
        <span class="faint">{{ chosen.length }} of {{ findings.length }} selected</span>
        <button class="btn sm ghost" @click="selectAll">Select all</button>
        <button class="btn sm ghost" @click="clearSelection">Clear</button>
      </div>

      <div v-for="group in groups" :key="group.value" class="share-group">
        <h3 :class="`tone-${group.tone}`">
          {{ group.label }} <span class="faint">{{ group.findings.length }}</span>
        </h3>
        <label v-for="finding in group.findings" :key="findingKey(finding)" class="share-finding">
          <input type="checkbox" :checked="isSelected(finding)" @change="toggle(finding)" />
          <span class="share-finding-body">
            <span class="share-finding-title">{{ finding.title }}</span>
            <span class="faint share-finding-meta">{{ finding.step }} · {{ finding.status }}</span>
            <span v-if="finding.description" class="share-finding-desc">{{ finding.description }}</span>
          </span>
        </label>
      </div>

      <details v-if="chosen.length" class="share-prompt">
        <summary class="faint">Prompt preview</summary>
        <pre class="share-prompt-text">{{ prompt }}</pre>
      </details>
    </template>

    <div class="row share-footer" style="justify-content: flex-end">
      <template v-if="!taskId">
        <span class="faint">No task is linked to this pull request.</span>
        <button v-if="url" class="btn" :disabled="importing" @click="importTask">
          <span v-if="importing" class="spinner" aria-hidden="true"></span>
          Import into a task
        </button>
      </template>
      <template v-else>
        <span class="faint">Runs on {{ taskLabel || 'the linked task' }}</span>
        <button class="btn primary" :disabled="!canSend" @click="send">
          <span v-if="sending" class="spinner" aria-hidden="true"></span>
          Send to agent
        </button>
      </template>
    </div>
  </div>
</template>
