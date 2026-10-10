<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api, openTaskStream } from '../api'
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

const task = ref(null)
const loading = ref(true)
const notFound = ref(false)
let closeStream = null

// Links from the most recent run that produced a session.
const latestLinks = computed(() => task.value?.runs?.find((run) => run.links?.length)?.links || [])

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
const groupOptions = computed(() => [
  { value: '', label: 'no group' },
  ...store.groups.map((g) => ({ value: g.id, label: `group: ${g.name}` })),
])

async function load() {
  try {
    task.value = await api.tasks.get(props.id)
  } catch (e) {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

function subscribe() {
  closeStream?.()
  closeStream = openTaskStream(props.id, (ev) => {
    if (ev.kind === 'task') load()
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
  if (field === 'group_id' && value === '') value = null
  try {
    await api.tasks.update(props.id, { [field]: value })
    await load()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
    await load()
  }
}

async function removeTask() {
  if (!confirm('Delete this task? This cannot be undone.')) return
  await api.tasks.remove(props.id)
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
  await store.loadGroups().catch(() => {})
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
  <div v-else-if="notFound" class="empty">Task not found. <router-link to="/">Back</router-link></div>
  <div v-else>
    <div class="row page-head" style="margin-bottom: 16px">
      <div class="grow" style="min-width: 0">
        <EditableText
          as="h1"
          style="margin-bottom: 4px"
          :value="task.title"
          placeholder="Untitled task"
          @save="(value) => update('title', value)"
        />
        <div class="row">
          <InlineSelect
            :value="task.status"
            :options="STATUS_OPTIONS"
            title="Status"
            @save="(value) => update('status', value)"
          />
          <InlineSelect
            :value="task.priority"
            :options="PRIORITY_OPTIONS"
            title="Priority"
            @save="(value) => update('priority', Number(value))"
          />
          <InlineSelect
            :value="task.repository_id || ''"
            :options="repositoryOptions"
            title="Repository"
            @save="(value) => update('repository_id', value)"
          />
          <InlineSelect
            :value="task.group_id || ''"
            :options="groupOptions"
            title="Repository group"
            @save="(value) => update('group_id', value)"
          />
        </div>
        <SessionLinks v-if="latestLinks.length" :links="latestLinks" compact />
      </div>
      <div class="row">
        <button class="btn sm danger" @click="removeTask">Delete</button>
      </div>
    </div>

    <EditableText
      class="muted"
      as="p"
      multiline
      :value="task.description"
      placeholder="Add a description…"
      @save="(value) => update('description', value)"
    />

    <div class="grid-2" style="margin-top: 16px">
      <div>
        <ContextPanel :task="task" @changed="onChanged" />
        <AgentPanel :task="task" :harnesses="store.harnesses" @changed="onChanged" />
        <ItemsPanel :task="task" @changed="onChanged" />
      </div>
      <div>
        <WorktreesPanel :task="task" :repositories="store.repositories" @changed="onChanged" />
        <TimelinePanel :events="task.timeline" />
      </div>
    </div>
  </div>
</template>
