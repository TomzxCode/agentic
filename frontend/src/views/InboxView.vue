<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { changeCreateBody } from '../changes'
import { store } from '../store'
import TaskLink from '../components/TaskLink.vue'

// Ask the shell to reload tasks/tags so the sidebar reflects an action.
const emit = defineEmits(['changed'])

const loading = ref(true)
const error = ref(false)
// The id of the action in flight, so its button shows a spinner and the rest
// of the inbox is not clicked twice.
const busy = ref('')

// The section each suggestion kind belongs to, in the order they are shown. The
// API returns them already ordered by kind, so a stable grouping keeps that.
const SECTIONS = {
  close_task_merged_pr: 'Close finished tasks',
  record_change_merged_pr: 'Record changes',
  remove_worktree_done_task: 'Clean up worktrees'
}
const SECTION_ORDER = ['close_task_merged_pr', 'record_change_merged_pr', 'remove_worktree_done_task']

const suggestions = computed(() => store.inbox)

const sections = computed(() =>
  SECTION_ORDER.map((kind) => ({
    kind,
    label: SECTIONS[kind],
    items: suggestions.value.filter((suggestion) => suggestion.kind === kind)
  })).filter((section) => section.items.length)
)

// The task a suggestion is about, falling back to the copy the API returned
// when the task is not in the store.
function taskFor(suggestion) {
  return (
    store.tasks.find((task) => task.id === suggestion.task_id) || {
      id: suggestion.task_id,
      title: suggestion.task_title,
      status: suggestion.task_status,
      tags: []
    }
  )
}

async function load() {
  loading.value = true
  error.value = false
  try {
    await store.loadTasks()
    // Recording a change reads the item's merge time, so the items are needed.
    await store.loadItems().catch(() => {})
    await store.loadInbox()
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function runAction(suggestion, action) {
  if (busy.value) return
  busy.value = action.id
  try {
    if (action.kind === 'set_task_status') {
      await api.tasks.update(action.task_id, { status: action.status })
      const task = store.tasks.find((entry) => entry.id === action.task_id)
      if (task) task.status = action.status
      store.notify('Task closed')
    } else if (action.kind === 'create_change') {
      await recordChange(suggestion, action)
      store.notify('Change recorded')
    } else if (action.kind === 'remove_worktree') {
      await api.worktrees.remove(action.task_id, action.worktree_id)
      store.notify('Worktree removed')
    }
    emit('changed')
    await store.loadInbox()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

// Record a change for a merged PR, the same way the repository page does: a
// merge time fetched before the PR merged is refreshed once so the change dates
// to the merge, falling back to now when GitHub still reports none.
async function recordChange(suggestion, action) {
  const item = store.items.find((entry) => entry.id === action.item_id)
  if (!item) {
    store.notify('That pull request is no longer in the resources list.', true)
    return
  }
  let mergedAt = item.metadata_json?.merged_at
  if (!mergedAt) {
    const refreshed = await api.items.refresh(item.id)
    if (refreshed) {
      mergedAt = refreshed.metadata_json?.merged_at
      Object.assign(item, refreshed)
    }
  }
  await api.changes.create(changeCreateBody(action.task_id, item, mergedAt || new Date().toISOString()))
}

onMounted(load)
</script>

<template>
  <div>
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 12px">
      <h1>Inbox</h1>
      <span class="row" style="gap: 8px; align-items: center">
        <span class="faint"> {{ suggestions.length }} suggestion{{ suggestions.length === 1 ? '' : 's' }} </span>
        <button class="btn sm ghost" :disabled="loading" @click="load">
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          Refresh
        </button>
      </span>
    </div>

    <div v-if="loading && !suggestions.length" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load the inbox.</p>
      <button class="btn" @click="load">Retry</button>
    </div>

    <div v-else-if="!suggestions.length" class="empty">Inbox zero. Nothing needs a decision right now.</div>

    <template v-else>
      <section v-for="section in sections" :key="section.kind">
        <h2 class="group-head">
          {{ section.label }} <span class="faint">{{ section.items.length }}</span>
        </h2>
        <div v-for="suggestion in section.items" :key="suggestion.id" class="panel inbox-item">
          <div class="row" style="justify-content: space-between; gap: 10px; align-items: flex-start; flex-wrap: wrap">
            <div style="min-width: 0; flex: 1 1 220px">
              <TaskLink :task="taskFor(suggestion)" />
              <p class="faint" style="margin: 6px 0 0">{{ suggestion.reason }}</p>
            </div>
            <span class="row" style="gap: 6px; flex-wrap: wrap">
              <button
                v-for="action in suggestion.actions"
                :key="action.id"
                class="btn sm primary"
                :disabled="!!busy"
                @click="runAction(suggestion, action)"
              >
                <span v-if="busy === action.id" class="spinner" aria-hidden="true"></span>
                {{ action.label }}
              </button>
            </span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
