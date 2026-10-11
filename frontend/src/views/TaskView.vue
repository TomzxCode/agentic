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
import SearchSelect from '../components/SearchSelect.vue'

const props = defineProps({ id: { type: String, required: true } })
const emit = defineEmits(['changed'])

const task = ref(null)
const loading = ref(true)
const notFound = ref(false)
let closeStream = null

// Template refs so the command palette can jump straight to a field.
const titleRef = ref(null)
const descriptionRef = ref(null)
const statusRef = ref(null)
const priorityRef = ref(null)
const groupRef = ref(null)
const repositoryRef = ref(null)

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
const groupOptions = computed(() => [
  { value: '', label: 'no group' },
  ...store.groups.map((g) => ({ value: g.id, label: `group: ${g.name}` })),
])

const taskRepositories = computed(() =>
  (task.value?.repository_ids || [])
    .map((id) => store.repositories.find((r) => r.id === id))
    .filter(Boolean)
    .sort((a, b) => a.name.localeCompare(b.name)),
)
const addRepositoryOptions = computed(() =>
  store.repositories
    .filter((r) => !(task.value?.repository_ids || []).includes(r.id))
    .map((r) => ({ value: r.id, label: r.name })),
)

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

async function addRepository(id) {
  if (!id) return
  await update('repository_ids', [...(task.value.repository_ids || []), id])
}

async function removeRepository(id) {
  await update('repository_ids', (task.value.repository_ids || []).filter((x) => x !== id))
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
  // The palette uses this to jump to a task field.
  store.focusField = (field) => {
    const target = {
      title: titleRef,
      description: descriptionRef,
      status: statusRef,
      priority: priorityRef,
      group: groupRef,
      repository: repositoryRef,
    }[field]
    target?.value?.activate?.()
  }
  await store.loadHarnesses().catch(() => {})
  await store.loadRepositories().catch(() => {})
  await store.loadGroups().catch(() => {})
  await load()
  subscribe()
})
onUnmounted(() => {
  store.focusField = null
  closeStream?.()
})
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
          ref="titleRef"
          as="h1"
          style="margin-bottom: 4px"
          :value="task.title"
          placeholder="Untitled task"
          @save="(value) => update('title', value)"
        />
        <div class="row">
          <SearchSelect
            ref="statusRef"
            variant="inline"
            :model-value="task.status"
            :options="STATUS_OPTIONS"
            :sort="false"
            title="Status"
            @update:model-value="(value) => update('status', value)"
          />
          <SearchSelect
            ref="priorityRef"
            variant="inline"
            :model-value="task.priority"
            :options="PRIORITY_OPTIONS"
            :sort="false"
            title="Priority"
            @update:model-value="(value) => update('priority', Number(value))"
          />
          <SearchSelect
            ref="groupRef"
            variant="inline"
            :model-value="task.group_id || ''"
            :options="groupOptions"
            title="Repository group"
            @update:model-value="(value) => update('group_id', value)"
          />
        </div>
        <div class="row" style="margin-top: 6px">
          <span class="faint">repositories:</span>
          <span v-for="repo in taskRepositories" :key="repo.id" class="chip">
            {{ repo.name }}
            <button class="chip-x" title="Remove" @click="removeRepository(repo.id)">×</button>
          </span>
          <SearchSelect
            v-if="addRepositoryOptions.length"
            ref="repositoryRef"
            variant="inline"
            :model-value="''"
            :options="addRepositoryOptions"
            placeholder="+ add repository"
            @update:model-value="addRepository"
          />
          <span v-if="!taskRepositories.length && !addRepositoryOptions.length" class="faint">none registered</span>
        </div>
        <SessionLinks v-if="latestLinks.length" :links="latestLinks" compact />
      </div>
      <div class="row">
        <button class="btn sm danger" @click="removeTask">Delete</button>
      </div>
    </div>

    <EditableText
      ref="descriptionRef"
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
