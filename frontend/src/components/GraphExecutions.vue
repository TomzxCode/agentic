<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import { formatDateTime, store } from '../store'

// The "Executions" tab: every execution across graphs, newest first, each one
// expandable into its nodes' statuses and outputs. A running execution waiting
// on a form shows the form here; answering it unblocks the walk. Polls while
// something is in flight, like the scheduled executions do.
const props = defineProps({
  active: { type: Boolean, default: false },
  refreshToken: { type: Number, default: 0 }
})
const emit = defineEmits(['count', 'loading'])

const loading = ref(true)
const executions = ref([])
// The execution id whose nodes are expanded, and its detail.
const opened = ref('')
const detail = ref(null)
const detailLoading = ref(false)
// The form being answered: values collected per field id.
const formValues = ref({})
// Which pending request the collected values belong to (execution, node, when
// it was asked), so a background refresh of the same request never wipes what
// has been typed so far.
let formKey = ''
const submitting = ref(false)

let fastPoller = null

const pendingForm = computed(() => detail.value?.pending_form || null)

watch(
  () => props.refreshToken,
  () => {
    if (props.active) load()
  }
)
watch(executions, (rows) => emit('count', rows.length), { immediate: true })
watch(loading, (value) => emit('loading', value), { immediate: true })

async function load({ silent = false } = {}) {
  clearTimeout(fastPoller)
  fastPoller = null
  if (!silent) loading.value = true
  try {
    executions.value = await api.graphs.executions(100)
  } catch (e) {
    if (!silent) store.notify(e.message, true)
  } finally {
    if (!silent) loading.value = false
  }
  // An execution in flight settles in seconds, so poll it fast.
  if (executions.value.some((row) => row.status === 'running')) {
    fastPoller = setTimeout(() => {
      if (props.active && document.visibilityState === 'visible') load({ silent: true })
    }, 2000)
  }
}

async function toggle(id) {
  if (opened.value === id) {
    opened.value = ''
    detail.value = null
    return
  }
  opened.value = id
  // A newly opened execution starts with fresh values, seeded from the
  // request's defaults.
  formKey = ''
  await openDetail(id)
}

async function openDetail(id) {
  detailLoading.value = true
  try {
    const fresh = await api.graphs.execution(id)
    const pending = fresh.pending_form
    if (pending) {
      const key = `${id}:${pending.node_id}:${pending.requested_at}`
      if (key !== formKey) {
        formKey = key
        // Pre-fill from the request's defaults, which already carry both the
        // injected values and the fields' own declared defaults. Only on the
        // first look at this request: a refresh must keep what was typed.
        const values = {}
        for (const [fieldId, value] of Object.entries(pending.defaults || {})) {
          values[fieldId] = value
        }
        for (const field of pending.fields || []) {
          if (values[field.id] === undefined) values[field.id] = field.defaultValue || ''
        }
        formValues.value = values
      }
    } else {
      formKey = ''
    }
    detail.value = fresh
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    detailLoading.value = false
  }
}

// Keep the detail current while its execution is in flight.
watch(executions, (rows) => {
  const current = rows.find((row) => row.id === opened.value)
  if (current && current.status === 'running' && !detailLoading.value) openDetail(opened.value)
})

async function submitForm(cancel = false) {
  if (!pendingForm.value) return
  submitting.value = true
  try {
    detail.value = await api.graphs.submitForm(opened.value, pendingForm.value.node_id, {
      values: formValues.value,
      cancel
    })
    formValues.value = {}
    formKey = ''
    await load({ silent: true })
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    submitting.value = false
  }
}

async function cancelExecution(id) {
  try {
    await api.graphs.cancelExecution(id)
    if (opened.value === id) await openDetail(id)
    await load({ silent: true })
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(() => load())
onUnmounted(() => clearTimeout(fastPoller))

function statusClass(status) {
  return (
    {
      done: 'ok',
      succeeded: 'ok',
      running: 'run',
      waiting: 'warn',
      failed: 'danger'
    }[status] || ''
  )
}
</script>

<template>
  <div>
    <div v-if="!loading && !executions.length" class="empty">
      <p class="faint">No executions yet. Run a graph to see it here.</p>
    </div>

    <div class="graphs-exec-list">
      <div v-for="execution in executions" :key="execution.id" class="item">
        <button class="graphs-exec-head" @click="toggle(execution.id)">
          <span class="badge" :class="statusClass(execution.status)">{{ execution.status }}</span>
          <strong>{{ execution.graph_name }}</strong>
          <span class="faint" style="font-size: 12px">
            {{ execution.trigger }} · {{ formatDateTime(execution.started_at) }}
          </span>
          <span v-if="execution.error" class="graphs-exec-error">{{ execution.error }}</span>
        </button>

        <div v-if="opened === execution.id" class="graphs-exec-detail">
          <p v-if="detailLoading && !detail" class="faint">Loading…</p>
          <template v-else-if="detail">
            <div v-for="node in detail.nodes" :key="node.node_id" class="graphs-node">
              <span class="badge" :class="statusClass(node.status)">{{ node.status }}</span>
              <span>{{ node.title }}</span>
              <span v-if="node.run_id" class="faint" style="font-size: 12px"> run {{ node.run_id.slice(0, 8) }} </span>
              <span v-if="node.error" class="graphs-exec-error">{{ node.error }}</span>
            </div>
            <details v-for="node in detail.nodes.filter((candidate) => candidate.output)" :key="`out-${node.node_id}`">
              <summary class="faint">{{ node.title }} output</summary>
              <pre class="graphs-output">{{ node.output }}</pre>
            </details>
            <div class="row" style="gap: 8px; margin-top: 8px">
              <router-link v-if="detail.task_id" class="btn sm ghost" :to="`/task/${detail.task_id}`">
                Open task
              </router-link>
              <button v-if="detail.status === 'running'" class="btn sm ghost" @click="cancelExecution(detail.id)">
                Cancel execution
              </button>
            </div>
          </template>
        </div>
      </div>
    </div>

    <div v-if="pendingForm" class="modal-backdrop" @click.self="submitForm(true)">
      <div class="modal">
        <div class="panel-head">
          <h2>{{ pendingForm.title }}</h2>
        </div>
        <p class="faint" style="margin-top: 0">The graph is waiting on this form to continue.</p>
        <div v-for="field in pendingForm.fields" :key="field.id" class="field">
          <label :for="`form-${field.id}`">{{ field.title }}<template v-if="field.required"> *</template></label>
          <textarea
            v-if="field.type === 'textarea'"
            :id="`form-${field.id}`"
            v-model="formValues[field.id]"
            class="textarea"
            rows="3"
            :placeholder="field.placeholder"
          ></textarea>
          <select
            v-else-if="field.type === 'select'"
            :id="`form-${field.id}`"
            v-model="formValues[field.id]"
            class="input"
          >
            <option v-for="option in field.options || []" :key="option" :value="option">{{ option }}</option>
          </select>
          <input
            v-else-if="field.type === 'checkbox'"
            :id="`form-${field.id}`"
            v-model="formValues[field.id]"
            type="checkbox"
            true-value="true"
            false-value="false"
          />
          <div v-else-if="field.type === 'slider' || field.type === 'number'" class="row" style="gap: 8px">
            <input
              :id="`form-${field.id}`"
              v-model="formValues[field.id]"
              class="grow"
              :type="field.type === 'number' ? 'number' : 'range'"
              :min="field.min ?? 0"
              :max="field.max ?? 100"
              :step="field.step ?? 1"
            />
            <span class="faint mono">{{ formValues[field.id] }}</span>
          </div>
          <input
            v-else
            :id="`form-${field.id}`"
            v-model="formValues[field.id]"
            class="input"
            :type="field.type"
            :placeholder="field.placeholder"
          />
        </div>
        <div class="row" style="justify-content: space-between">
          <button class="btn ghost" :disabled="submitting" @click="submitForm(true)">Cancel form</button>
          <button class="btn primary" :disabled="submitting" @click="submitForm(false)">Submit</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.graphs-exec-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.graphs-exec-head {
  display: flex;
  gap: 10px;
  align-items: baseline;
  flex-wrap: wrap;
  background: none;
  border: none;
  color: inherit;
  font: inherit;
  text-align: left;
  padding: 0;
  cursor: pointer;
  width: 100%;
}
.graphs-exec-error {
  color: var(--danger);
  font-size: 12px;
}
.graphs-exec-detail {
  margin-top: 8px;
  border-top: 1px solid var(--border);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.graphs-node {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.graphs-output {
  font-family: var(--mono);
  font-size: 12px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px;
  white-space: pre-wrap;
  max-height: 240px;
  overflow-y: auto;
}
.empty {
  text-align: center;
  padding: 32px 0;
}
</style>
