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

const props = defineProps({ id: { type: String, required: true } })
const emit = defineEmits(['changed'])

const problem = ref(null)
const loading = ref(true)
const notFound = ref(false)
const editing = ref(false)
const draft = ref({ title: '', description: '', status: 'open', priority: 2 })
let closeStream = null

// Links from the most recent run that produced a session.
const latestLinks = computed(() => problem.value?.runs?.find((run) => run.links?.length)?.links || [])

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

function startEdit() {
  draft.value = {
    title: problem.value.title,
    description: problem.value.description,
    status: problem.value.status,
    priority: problem.value.priority,
  }
  editing.value = true
}

async function saveEdit() {
  await api.problems.update(props.id, draft.value)
  editing.value = false
  await load()
  emit('changed')
}

async function removeProblem() {
  if (!confirm('Delete this problem? This cannot be undone.')) return
  await api.problems.remove(props.id)
  emit('changed')
  location.hash = ''
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
watch(() => props.id, async (val) => {
  if (!val) return
  loading.value = true
  notFound.value = false
  await load()
  subscribe()
})
</script>

<template>
  <div v-if="loading" class="empty"><span class="spinner"></span></div>
  <div v-else-if="notFound" class="empty">Problem not found. <router-link to="/">Back</router-link></div>
  <div v-else>
    <div class="row page-head" style="margin-bottom: 16px">
      <div class="grow" style="min-width: 0">
        <h1 style="margin-bottom: 4px">{{ problem.title }}</h1>
        <div class="row">
          <span class="badge">{{ problem.status.replace('_', ' ') }}</span>
          <span class="badge">priority {{ problem.priority }}</span>
          <span v-if="problem.repository_id" class="badge">
            {{ store.repositories.find((r) => r.id === problem.repository_id)?.name || 'repo' }}
          </span>
        </div>
        <SessionLinks v-if="latestLinks.length" :links="latestLinks" compact />
      </div>
      <div class="row">
        <button class="btn sm" @click="startEdit">Edit</button>
        <button class="btn sm danger" @click="removeProblem">Delete</button>
      </div>
    </div>

    <p v-if="problem.description" class="muted" style="white-space: pre-wrap">{{ problem.description }}</p>

    <div class="grid-2">
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

    <div v-if="editing" class="modal-backdrop" @click.self="editing = false">
      <div class="modal">
        <h1 style="margin-bottom: 14px">Edit problem</h1>
        <div class="field"><label>Title</label><input v-model="draft.title" class="input" /></div>
        <div class="field"><label>Description</label><textarea v-model="draft.description" class="textarea"></textarea></div>
        <div class="row">
          <div class="field grow">
            <label>Status</label>
            <select v-model="draft.status" class="select">
              <option value="open">Open</option>
              <option value="in_progress">In progress</option>
              <option value="blocked">Blocked</option>
              <option value="done">Done</option>
              <option value="archived">Archived</option>
            </select>
          </div>
          <div class="field grow">
            <label>Priority</label>
            <select v-model.number="draft.priority" class="select">
              <option :value="0">Low</option><option :value="1">Medium</option>
              <option :value="2">High</option><option :value="3">Urgent</option>
            </select>
          </div>
        </div>
        <div class="row" style="justify-content: flex-end">
          <button class="btn ghost" @click="editing = false">Cancel</button>
          <button class="btn primary" @click="saveEdit">Save</button>
        </div>
      </div>
    </div>
  </div>
</template>
