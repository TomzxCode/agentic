<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api, openProblemStream } from '../api'
import { store } from '../store'
import ContextPanel from '../components/ContextPanel.vue'
import ItemsPanel from '../components/ItemsPanel.vue'
import WorktreesPanel from '../components/WorktreesPanel.vue'
import AgentPanel from '../components/AgentPanel.vue'
import TimelinePanel from '../components/TimelinePanel.vue'
import SessionLinks from '../components/SessionLinks.vue'
import EditableText from '../components/EditableText.vue'
import InlineSelect from '../components/InlineSelect.vue'

const props = defineProps({ id: { type: String, required: true } })
const emit = defineEmits(['changed'])

const problem = ref(null)
const loading = ref(true)
const notFound = ref(false)
let closeStream = null

// Links from the most recent run that produced a session.
const latestLinks = computed(() => problem.value?.runs?.find((run) => run.links?.length)?.links || [])

const STATUS_OPTIONS = [
  { value: 'open', label: 'open' },
  { value: 'in_progress', label: 'in progress' },
  { value: 'blocked', label: 'blocked' },
  { value: 'done', label: 'done' },
  { value: 'archived', label: 'archived' },
]
const PRIORITY_OPTIONS = [
  { value: 0, label: 'priority: low' },
  { value: 1, label: 'priority: medium' },
  { value: 2, label: 'priority: high' },
  { value: 3, label: 'priority: urgent' },
]
const repositoryOptions = computed(() => [
  { value: '', label: 'no repository' },
  ...store.repositories.map((r) => ({ value: r.id, label: r.name })),
])

async function load() {
  try {
    problem.value = await api.problems.get(props.id)
  } catch (e) {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

function subscribe() {
  closeStream?.()
  closeStream = openProblemStream(props.id, (ev) => {
    if (ev.kind === 'problem') load()
  })
}

// Inline "edit online": each property saves on change, no form.
async function update(field, value) {
  if (field === 'title' && !String(value).trim()) {
    store.notify('Title cannot be empty', true)
    await load()
    return
  }
  if (field === 'repository_id' && value === '') value = null
  try {
    await api.problems.update(props.id, { [field]: value })
    await load()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
    await load()
  }
}

async function removeProblem() {
  if (!confirm('Delete this problem? This cannot be undone.')) return
  await api.problems.remove(props.id)
  emit('changed')
  window.history.pushState({}, '', '/')
  location.reload()
}

function onChanged() {
  load()
  emit('changed')
}

onMounted(async () => {
  await store.loadHarnesses().catch(() => {})
  await store.loadRepositories().catch(() => {})
  await load()
  subscribe()
})
onUnmounted(() => closeStream?.())
watch(
  () => props.id,
  async (val) => {
    if (!val) return
    loading.value = true
    notFound.value = false
    await load()
    subscribe()
  },
)
</script>

<template>
  <div v-if="loading" class="empty"><span class="spinner"></span></div>
  <div v-else-if="notFound" class="empty">Problem not found. <router-link to="/">Back</router-link></div>
  <div v-else>
    <div class="row page-head" style="margin-bottom: 16px">
      <div class="grow" style="min-width: 0">
        <EditableText
          as="h1"
          style="margin-bottom: 4px"
          :value="problem.title"
          placeholder="Untitled problem"
          @save="(value) => update('title', value)"
        />
        <div class="row">
          <InlineSelect
            :value="problem.status"
            :options="STATUS_OPTIONS"
            title="Status"
            @save="(value) => update('status', value)"
          />
          <InlineSelect
            :value="problem.priority"
            :options="PRIORITY_OPTIONS"
            title="Priority"
            @save="(value) => update('priority', Number(value))"
          />
          <InlineSelect
            :value="problem.repository_id || ''"
            :options="repositoryOptions"
            title="Repository"
            @save="(value) => update('repository_id', value)"
          />
        </div>
        <SessionLinks v-if="latestLinks.length" :links="latestLinks" compact />
      </div>
      <div class="row">
        <button class="btn sm danger" @click="removeProblem">Delete</button>
      </div>
    </div>

    <EditableText
      class="muted"
      as="p"
      multiline
      :value="problem.description"
      placeholder="Add a description…"
      @save="(value) => update('description', value)"
    />

    <div class="grid-2" style="margin-top: 16px">
      <div>
        <ContextPanel :problem="problem" @changed="onChanged" />
        <AgentPanel :problem="problem" :harnesses="store.harnesses" @changed="onChanged" />
        <ItemsPanel :problem="problem" @changed="onChanged" />
      </div>
      <div>
        <WorktreesPanel :problem="problem" :repositories="store.repositories" @changed="onChanged" />
        <TimelinePanel :events="problem.timeline" />
      </div>
    </div>
  </div>
</template>
