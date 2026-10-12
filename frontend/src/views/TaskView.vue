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
import RepositorySelect from '../components/RepositorySelect.vue'
import TagInput from '../components/TagInput.vue'
import StatusIcon from '../components/StatusIcon.vue'
import PriorityIcon from '../components/PriorityIcon.vue'

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
const repositoryRef = ref(null)
const tagRef = ref(null)

// Links from the most recent run that produced a session.
const latestLinks = computed(() => task.value?.runs?.find((run) => run.links?.length)?.links || [])

const STATUS_OPTIONS = [
  { value: 'open', label: 'open', icon: StatusIcon, iconProps: { status: 'open', label: 'open' } },
  {
    value: 'in_progress',
    label: 'in progress',
    icon: StatusIcon,
    iconProps: { status: 'in_progress', label: 'in progress' }
  },
  { value: 'blocked', label: 'blocked', icon: StatusIcon, iconProps: { status: 'blocked', label: 'blocked' } },
  { value: 'done', label: 'done', icon: StatusIcon, iconProps: { status: 'done', label: 'done' } },
  { value: 'archived', label: 'archived', icon: StatusIcon, iconProps: { status: 'archived', label: 'archived' } }
]
const PRIORITY_OPTIONS = [
  { value: 0, label: 'low', icon: PriorityIcon, iconProps: { priority: 0, label: 'low' } },
  { value: 1, label: 'medium', icon: PriorityIcon, iconProps: { priority: 1, label: 'medium' } },
  { value: 2, label: 'high', icon: PriorityIcon, iconProps: { priority: 2, label: 'high' } },
  { value: 3, label: 'urgent', icon: PriorityIcon, iconProps: { priority: 3, label: 'urgent' } }
]
async function load() {
  try {
    task.value = await api.tasks.get(props.id)
  } catch {
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
  try {
    await api.tasks.update(props.id, { [field]: value })
    await load()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
    await load()
  }
}

async function setRepositories(ids) {
  await update('repository_ids', ids)
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
      repository: repositoryRef,
      tags: tagRef
    }[field]
    target?.value?.activate?.()
  }
  // Focus-hint mode uses the DOM scan in App; nothing to register here.
  await store.loadHarnesses().catch(() => {})
  await store.loadRepositories().catch(() => {})
  await load()
  subscribe()
})
onUnmounted(() => {
  store.focusField = null
  store.hintMode = false
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
  }
)
</script>

<template>
  <div v-if="loading" class="empty"><span class="spinner"></span></div>
  <div v-else-if="notFound" class="empty">Task not found. <router-link to="/">Back</router-link></div>
  <div v-else>
    <div class="row page-head task-head">
      <div class="grow">
        <EditableText
          ref="titleRef"
          as="h1"
          class="task-title"
          :value="task.title"
          placeholder="Untitled task"
          @save="(value) => update('title', value)"
        />
        <div class="task-meta">
          <SearchSelect
            ref="statusRef"
            variant="inline"
            :model-value="task.status"
            :options="STATUS_OPTIONS"
            :sort="false"
            title="Status"
            @update:model-value="(value) => update('status', value)"
          />
          <span class="meta-sep" aria-hidden="true"></span>
          <SearchSelect
            ref="priorityRef"
            variant="inline"
            :model-value="task.priority"
            :options="PRIORITY_OPTIONS"
            :sort="false"
            title="Priority"
            @update:model-value="(value) => update('priority', Number(value))"
          />
          <span class="meta-sep" aria-hidden="true"></span>
          <RepositorySelect
            ref="repositoryRef"
            :model-value="task.repository_ids"
            :repositories="store.repositories"
            @update:model-value="setRepositories"
          />
          <span class="meta-sep" aria-hidden="true"></span>
          <TagInput
            ref="tagRef"
            class="task-meta-tags"
            :model-value="task.tags || []"
            :suggestions="store.tags"
            placeholder="Add tags…"
            @update:model-value="(value) => update('tags', value)"
          />
        </div>
      </div>
      <div class="row task-actions">
        <SessionLinks v-if="latestLinks.length" :links="latestLinks" compact />
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
        <TimelinePanel :events="task.timeline" :task="task" />
      </div>
    </div>
  </div>
</template>
