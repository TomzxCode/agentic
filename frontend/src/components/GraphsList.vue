<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { formatDateTime, store } from '../store'
import GraphEditor from './GraphEditor.vue'
import GraphMetaForm from './GraphMetaForm.vue'

// The "Graphs" tab: the list of execution graphs with their settings forms,
// and the definition editor one graph opens at a time. Self-contained like the
// schedules tab: it owns its list and drafts, and reports its count upward.
const props = defineProps({
  active: { type: Boolean, default: false },
  refreshToken: { type: Number, default: 0 }
})
const emit = defineEmits(['count', 'loading', 'run-started'])

const loading = ref(true)
const graphs = ref([])
const busy = ref('')
// Which graph's definition editor is open ("" when none), and which graph's
// settings form is open.
const editing = ref('')
const settingsFor = ref('')
const editingDraft = ref({})
const harnesses = ref([])

const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
const newDraft = ref(blankDraft())
const creating = ref(false)

const editingGraph = computed(() => graphs.value.find((graph) => graph.id === editing.value) || null)

function blankDraft() {
  return { name: '', description: '', schedule: '0 9 * * *', timezone: browserTimezone, enabled: true }
}

function cancelCreate() {
  creating.value = false
  newDraft.value = blankDraft()
}

function cancelSettings() {
  settingsFor.value = ''
  editingDraft.value = {}
}

watch(graphs, () => emit('count', graphs.value.length), { immediate: true })
watch(loading, () => emit('loading', loading.value), { immediate: true })
watch(
  () => props.refreshToken,
  () => {
    if (props.active) load()
  }
)

async function load({ silent = false } = {}) {
  if (!silent) loading.value = true
  try {
    graphs.value = await api.graphs.list()
  } catch (e) {
    if (!silent) store.notify(e.message, true)
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadHarnesses() {
  try {
    harnesses.value = await api.harnesses.list()
  } catch {
    // The editor falls back to "Default harness" with an empty list.
  }
}

onMounted(() => {
  load()
  loadHarnesses()
})

function draftFromGraph(graph) {
  return {
    name: graph.name,
    description: graph.description || '',
    schedule: graph.schedule || '',
    timezone: graph.timezone || browserTimezone,
    enabled: graph.enabled
  }
}

function openSettings(graph) {
  creating.value = false
  settingsFor.value = graph.id
  editingDraft.value = draftFromGraph(graph)
}

function draftBody(draft) {
  return {
    name: draft.name.trim(),
    description: draft.description.trim(),
    schedule: draft.schedule.trim() || null,
    timezone: draft.timezone.trim() || null,
    enabled: draft.enabled
  }
}

async function saveNew() {
  busy.value = 'new'
  try {
    const graph = await api.graphs.create({ ...draftBody(newDraft.value), definition: { nodes: [], edges: [] } })
    creating.value = false
    newDraft.value = blankDraft()
    await load({ silent: true })
    // A new graph has no steps yet, so open the editor straight away.
    editing.value = graph.id
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function saveSettings(graph) {
  busy.value = graph.id
  try {
    await api.graphs.update(graph.id, draftBody(editingDraft.value))
    settingsFor.value = ''
    editingDraft.value = {}
    await load({ silent: true })
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function remove(graph) {
  if (!window.confirm(`Delete the graph '${graph.name}' and its execution history? Past runs stay on their tasks.`)) {
    return
  }
  busy.value = graph.id
  try {
    await api.graphs.remove(graph.id)
    if (editing.value === graph.id) editing.value = ''
    if (settingsFor.value === graph.id) {
      settingsFor.value = ''
      editingDraft.value = {}
    }
    await load({ silent: true })
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function run(graph) {
  busy.value = graph.id
  try {
    await api.graphs.run(graph.id)
    store.notify(`Started '${graph.name}'`)
    emit('run-started')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

async function saveDefinition(graph, definition) {
  try {
    await api.graphs.update(graph.id, { definition })
    await load({ silent: true })
    store.notify('Graph saved')
  } catch (e) {
    store.notify(e.message, true)
  }
}

// Run from the editor: persist the on-screen draft first, then start.
async function runFromEditor(graph, definition) {
  try {
    await api.graphs.update(graph.id, { definition })
    await load({ silent: true })
    await run(graph)
  } catch (e) {
    store.notify(e.message, true)
  }
}
</script>

<template>
  <div>
    <div v-if="editingGraph" style="margin-bottom: 12px">
      <GraphEditor
        :key="editingGraph.id"
        :graph="editingGraph"
        :harnesses="harnesses"
        @save="(definition) => saveDefinition(editingGraph, definition)"
        @close="editing = ''"
        @run="(definition) => runFromEditor(editingGraph, definition)"
      />
    </div>

    <template v-if="!editingGraph">
      <div v-if="creating" style="margin-bottom: 12px">
        <GraphMetaForm
          id-prefix="graph-new"
          heading="New execution graph"
          submit-label="Create graph"
          :model-value="newDraft"
          :saving="busy === 'new'"
          @update:model-value="newDraft = $event"
          @save="saveNew"
          @cancel="cancelCreate"
        />
      </div>

      <div v-if="!loading && !graphs.length && !creating" class="empty">
        <p class="faint">No execution graphs yet.</p>
        <button class="btn primary" @click="creating = true">New graph</button>
      </div>

      <div class="graphs-list">
        <div v-for="graph in graphs" :key="graph.id" class="item graph-row">
          <div class="grow" style="min-width: 0">
            <div class="row" style="gap: 8px; align-items: baseline">
              <strong>{{ graph.name }}</strong>
              <span v-if="graph.running_execution_id" class="badge graphs-running">running</span>
              <span v-if="!graph.enabled" class="faint" style="font-size: 12px">paused</span>
            </div>
            <p v-if="graph.description" class="faint" style="margin: 2px 0 0; font-size: 13px">
              {{ graph.description }}
            </p>
            <p class="faint" style="margin: 2px 0 0; font-size: 12px">
              <template v-if="graph.schedule">
                <code>{{ graph.schedule }}</code> · next {{ formatDateTime(graph.next_run_at) }} ·
                {{ graph.timezone }}
              </template>
              <template v-else>runs by hand only</template>
              ·
              {{ (graph.definition?.nodes || []).length }} step{{
                (graph.definition?.nodes || []).length === 1 ? '' : 's'
              }}
            </p>
          </div>
          <div class="row" style="gap: 6px; flex-shrink: 0">
            <button class="btn sm" :disabled="busy === graph.id" @click="run(graph)">Run</button>
            <button class="btn sm" @click="editing = graph.id">Edit graph</button>
            <button class="btn sm ghost" @click="openSettings(graph)">Settings</button>
            <button class="btn sm ghost" :disabled="busy === graph.id" @click="remove(graph)">Delete</button>
          </div>
        </div>

        <div v-if="!loading && graphs.length" class="row" style="margin-top: 10px">
          <button class="btn sm" @click="creating = true">New graph</button>
        </div>
      </div>

      <div v-for="graph in graphs" :key="`settings-${graph.id}`" style="margin-top: 12px">
        <GraphMetaForm
          v-if="settingsFor === graph.id"
          :id-prefix="`graph-${graph.id}`"
          :heading="`Settings: ${graph.name}`"
          submit-label="Save settings"
          :model-value="editingDraft"
          :saving="busy === graph.id"
          @update:model-value="editingDraft = $event"
          @save="saveSettings(graph)"
          @cancel="cancelSettings"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.graphs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.graph-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}
.graphs-running {
  color: var(--ok);
  border: 1px solid var(--ok);
}
.empty {
  text-align: center;
  padding: 32px 0;
}
@media (max-width: 760px) {
  .graph-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
