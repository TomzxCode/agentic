<script setup>
import { computed, onMounted, ref, nextTick } from 'vue'
import { api } from '../api'
import { store, statusClass, statusLabel } from '../store'

// Ask the shell to reload tasks/tags so the sidebar stays in sync (a push adds
// a task, a pop marks one done).
const emit = defineEmits(['changed'])

const entries = ref([])
const history = ref([])
const showHistory = ref(false)
const loading = ref(false)
const error = ref('')

// The input doubles as the add field and the filter/edit field, like the
// desktop stack window: with nothing selected it filters and adds; with a row
// selected it edits that row's title.
const draft = ref('')
const mode = ref('add') // add | edit
const editingId = ref(null)
const filter = ref('')

const selectedId = ref(null)
const descriptionDraft = ref('')
const showHelp = ref(false)
const titleInput = ref(null)

// Two units of precision, matching the desktop app: 0m 45s, 2h 05m, 3d 04h.
function formatDuration(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0))
  const minutes = Math.floor(total / 60)
  const secs = total % 60
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  const days = Math.floor(hours / 24)
  const hrs = hours % 24
  if (days > 0) return `${days}d ${String(hrs).padStart(2, '0')}h`
  if (hours > 0) return `${hours}h ${String(mins).padStart(2, '0')}m`
  return `${minutes}m ${String(secs).padStart(2, '0')}s`
}

function formatTime(iso) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  return date.toLocaleString(undefined, {
    month: sameDay ? undefined : 'short',
    day: sameDay ? undefined : 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  })
}

const visible = computed(() => {
  const needle = filter.value.trim().toLowerCase()
  if (!needle) return entries.value
  return entries.value.filter((entry) => (entry.task?.title || '').toLowerCase().includes(needle))
})

const current = computed(() => entries.value[0] || null)
const selected = computed(() => entries.value.find((entry) => entry.id === selectedId.value) || null)

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    entries.value = await api.stack.list()
    if (selectedId.value && !entries.value.some((entry) => entry.id === selectedId.value)) {
      selectedId.value = null
    }
    syncDescription()
  } catch (e) {
    error.value = e.message
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  try {
    history.value = await api.stack.history()
  } catch (e) {
    store.notify(e.message, true)
  }
}

function select(entry) {
  if (selectedId.value === entry.id) return
  selectedId.value = entry.id
  syncDescription()
  focusTitle()
}

function syncDescription() {
  descriptionDraft.value = selected.value?.task?.description || ''
}

function focusTitle() {
  nextTick(() => titleInput.value?.focus())
}

function clearSelection() {
  selectedId.value = null
  editingId.value = null
  mode.value = 'add'
  draft.value = ''
  filter.value = ''
  syncDescription()
}

async function submit() {
  const text = draft.value.trim()
  if (mode.value === 'edit' && editingId.value) {
    if (text) await saveTitle(editingId.value, text)
    editingId.value = null
    mode.value = 'add'
    draft.value = ''
    return
  }
  if (!text) return
  await push(text, 'top')
}

async function push(title, position) {
  try {
    entries.value = await api.stack.push({ title, position })
    draft.value = ''
    filter.value = ''
    selectedId.value = null
    mode.value = 'add'
    emit('changed')
    store.notify(positionMessage(position))
  } catch (e) {
    store.notify(e.message, true)
  }
}

function positionMessage(position) {
  if (position === 'next') return 'Added after the current task'
  if (position === 'last') return 'Added to the bottom'
  return 'Added to the top'
}

async function pop() {
  try {
    entries.value = await api.stack.pop()
    selectedId.value = null
    syncDescription()
    emit('changed')
    store.notify('Popped the current task')
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function promote(entry) {
  try {
    entries.value = await api.stack.promote(entry.id)
    selectedId.value = entry.id
    syncDescription()
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function removeEntry(entry) {
  try {
    await api.stack.remove(entry.id)
    if (selectedId.value === entry.id) selectedId.value = null
    await refresh()
    if (showHistory.value) await loadHistory()
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function reorder(entry, target) {
  const from = entries.value.findIndex((item) => item.id === entry.id)
  const to = from + target
  if (from < 0 || to < 0 || to >= entries.value.length) return
  try {
    entries.value = await api.stack.reorder(entry.id, to)
    selectedId.value = entry.id
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function saveTitle(entryId, title) {
  try {
    entries.value = await api.stack.update(entryId, { title })
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function saveDescription() {
  const entry = selected.value
  if (!entry) return
  const next = descriptionDraft.value
  if (next === (entry.task?.description || '')) return
  try {
    entries.value = await api.stack.update(entry.id, { description: next })
    syncDescription()
  } catch (e) {
    store.notify(e.message, true)
  }
}

function beginEdit(entry) {
  mode.value = 'edit'
  editingId.value = entry.id
  draft.value = entry.task?.title || ''
  focusTitle()
}

function onTitleKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  } else if (event.key === 'Enter' && event.shiftKey && mode.value === 'add') {
    event.preventDefault()
    const text = draft.value.trim()
    if (text) push(text, 'next')
  } else if (event.key === 'Escape') {
    event.preventDefault()
    clearSelection()
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    move(event.key === 'ArrowDown' ? 1 : -1)
  }
}

function onTitleInput() {
  if (mode.value === 'add') filter.value = draft.value
}

function move(delta) {
  const list = visible.value
  if (!list.length) return
  const index = list.findIndex((entry) => entry.id === selectedId.value)
  const next = index < 0 ? (delta > 0 ? 0 : list.length - 1) : Math.max(0, Math.min(list.length - 1, index + delta))
  select(list[next])
}

// Keys on the list itself (the input handles its own).
function onKeydown(event) {
  const target = event.target
  if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
  if (event.metaKey || event.ctrlKey || event.altKey) return

  if (event.key === 'Escape') {
    clearSelection()
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    move(event.key === 'ArrowDown' ? 1 : -1)
    return
  }
  if (!selected.value) return
  if (event.key === 'Enter') {
    event.preventDefault()
    beginEdit(selected.value)
  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault()
    reorder(selected.value, event.key === 'ArrowLeft' ? -1 : 1)
  } else if (event.key === 'Home' || event.key === '/') {
    event.preventDefault()
    promote(selected.value)
  } else if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault()
    removeEntry(selected.value)
  } else if (/^[0-9]$/.test(event.key)) {
    const entry = visible.value[Number(event.key)]
    if (entry) select(entry)
  }
}

onMounted(refresh)
</script>

<template>
  <div class="stack-page" @keydown="onKeydown">
    <div class="row page-head" style="margin-bottom: 14px">
      <h1 class="grow">Stack</h1>
      <button
        class="btn sm ghost"
        :class="{ active: showHistory }"
        @click="((showHistory = !showHistory), showHistory && loadHistory())"
      >
        History
      </button>
      <button class="btn sm ghost" title="Keyboard shortcuts (?)" @click="showHelp = !showHelp">?</button>
      <button class="btn sm ghost" @click="refresh"><span v-if="loading" class="spinner"></span> Refresh</button>
    </div>

    <section class="panel stack-panel">
      <div class="stack-add row">
        <input
          ref="titleInput"
          v-model="draft"
          class="input grow"
          :placeholder="mode === 'edit' ? 'Edit title…' : 'Add a task (Enter: top · Shift+Enter: next)'"
          aria-label="Add or filter tasks"
          @keydown="onTitleKeydown"
          @input="onTitleInput"
        />
        <button v-if="mode === 'edit'" class="btn" @click="submit">Save</button>
        <button v-else class="btn primary" @click="submit">Add</button>
      </div>
      <p v-if="filter" class="faint stack-filter-note">
        Filtering by “{{ filter }}” · <button class="link-btn" @click="((filter = ''), (draft = ''))">clear</button>
      </p>

      <div v-if="error" class="empty">
        Couldn't load the stack: {{ error }}.
        <div style="margin-top: 10px"><button class="btn sm ghost" @click="refresh">Retry</button></div>
      </div>
      <div v-else-if="!entries.length" class="empty">
        The stack is empty. Type above and press <span class="mono">Enter</span> to make something current.
      </div>
      <div v-else-if="!visible.length" class="empty">No tasks match “{{ filter }}”.</div>

      <ol v-else class="stack-list" aria-label="Task stack">
        <li
          v-for="entry in visible"
          :key="entry.id"
          class="stack-row"
          :class="{ current: entry.is_current, selected: entry.id === selectedId }"
          @click="select(entry)"
          @dblclick="beginEdit(entry)"
        >
          <span class="stack-index mono">{{ entry.position }}</span>
          <span class="stack-indicator" :title="entry.is_current ? 'Current task' : 'Queued'">
            {{ entry.is_current ? '🔥' : '💤' }}
          </span>
          <span
            :class="statusClass(entry.task?.status)"
            class="stack-status"
            :title="`Status: ${statusLabel(entry.task?.status)}`"
          >
            {{ statusLabel(entry.task?.status) }}
          </span>
          <router-link :to="`/task/${entry.task_id}`" class="stack-title grow" :title="entry.task?.title">
            <span v-if="entry.task?.description" class="stack-note" title="Has a description">📝</span>
            {{ entry.task?.title || entry.task_id }}
          </router-link>
          <span class="stack-col mono faint" title="Times it became current">×{{ entry.execution_count }}</span>
          <span class="stack-col mono faint" title="Started">{{ formatTime(entry.started_at) }}</span>
          <span class="stack-col mono faint" title="Last current">{{ formatTime(entry.last_current) }}</span>
          <span class="stack-col mono" title="Time as current">{{ formatDuration(entry.duration) }}</span>
          <span class="stack-actions">
            <button
              v-if="!entry.is_current"
              class="btn sm ghost"
              title="Promote to current (Home)"
              @click.stop="promote(entry)"
            >
              ↑
            </button>
            <button class="btn sm ghost danger" title="Remove from the stack (Delete)" @click.stop="removeEntry(entry)">
              ✕
            </button>
          </span>
        </li>
      </ol>

      <div v-if="current" class="stack-footer row">
        <span class="faint grow">Current: {{ current.task?.title }}</span>
        <button class="btn sm" @click="pop">Mark done (pop)</button>
      </div>
    </section>

    <section v-if="selected" class="panel stack-desc">
      <div class="panel-head">
        <h2>{{ selected.task?.title }}</h2>
        <router-link class="faint" :to="`/task/${selected.task_id}`">Open task →</router-link>
      </div>
      <textarea
        v-model="descriptionDraft"
        class="textarea"
        placeholder="Add a description…"
        @blur="saveDescription"
        @keydown.escape="saveDescription"
      ></textarea>
    </section>

    <section v-if="showHistory" class="panel" style="margin-top: 16px">
      <div class="panel-head">
        <h2>History</h2>
        <span class="faint">Removed and completed tasks</span>
      </div>
      <div v-if="!history.length" class="empty">Nothing removed yet.</div>
      <div v-for="entry in history" :key="entry.id" class="stack-row history">
        <span class="stack-indicator">✅</span>
        <router-link :to="`/task/${entry.task_id}`" class="stack-title grow">{{ entry.task?.title }}</router-link>
        <span class="stack-col mono faint">{{ formatDuration(entry.duration) }}</span>
        <span class="stack-col mono faint">{{ formatTime(entry.deleted_at) }}</span>
      </div>
    </section>

    <section v-if="showHelp" class="panel stack-help" style="margin-top: 16px">
      <div class="panel-head"><h2>Keyboard shortcuts</h2></div>
      <dl class="stack-help-grid">
        <dt>Enter</dt>
        <dd>Add to top (becomes current) / save an edit</dd>
        <dt>Shift+Enter</dt>
        <dd>Insert after the current task</dd>
        <dt>↑ / ↓</dt>
        <dd>Move the selection</dd>
        <dt>← / →</dt>
        <dd>Move the selected task up or down one</dd>
        <dt>Home or /</dt>
        <dd>Promote the selected task to current</dd>
        <dt>Delete / Backspace</dt>
        <dd>Remove the selected task</dd>
        <dt>0–9</dt>
        <dd>Select a task by position</dd>
        <dt>Esc</dt>
        <dd>Clear the selection and filter</dd>
      </dl>
    </section>
  </div>
</template>
