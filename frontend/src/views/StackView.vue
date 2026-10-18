<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api'
import { store } from '../store'
import StackHeader from '../components/StackHeader.vue'
import StackList from '../components/StackList.vue'
import StackHistory from '../components/StackHistory.vue'
import StackHelp from '../components/StackHelp.vue'

// Ask the shell to reload tasks/tags so the sidebar stays in sync (a push adds
// a task, a pop marks one done).
const emit = defineEmits(['changed'])

const entries = ref([])
const history = ref([])
const showHistory = ref(false)
const loading = ref(false)
const error = ref('')

// The current task's duration grows in real time. The server returns a
// snapshot; `loadedAt` is when it arrived and `now` ticks every second, so the
// live value is the snapshot plus the time since it was loaded. The list
// component renders the values; this shell owns the clock.
const now = ref(Date.now())
const loadedAt = ref(Date.now())
let tickId = null

function setEntries(list) {
  entries.value = list
  loadedAt.value = Date.now()
  now.value = loadedAt.value
}

// The field at the top adds a task (Enter) and filters the list as you type.
const draft = ref('')
const filter = ref('')

const selectedId = ref(null)
const descriptionDraft = ref('')
const showHelp = ref(false)
const pageEl = ref(null)

// One EditableText per row, so Enter can start editing the selected title.
const editors = new Map()
function setEditorRef(id, el) {
  if (el) editors.set(id, el)
  else editors.delete(id)
}

// Move focus to the page so the row shortcuts (arrows, Home, Delete) work; the
// title field only takes focus when you edit a row.
function focusPage() {
  nextTick(() => pageEl.value?.focus())
}

const visible = computed(() => {
  const needle = filter.value.trim().toLowerCase()
  if (!needle) return entries.value
  return entries.value.filter((entry) => (entry.task?.title || '').toLowerCase().includes(needle))
})

const selected = computed(() => entries.value.find((entry) => entry.id === selectedId.value) || null)

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    setEntries(await api.stack.list())
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

// Show the history panel, loading it the first time it opens.
function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value) loadHistory()
}

function select(entry) {
  if (selectedId.value === entry.id) return
  selectedId.value = entry.id
  syncDescription()
}

// A row click selects it (and keeps the keyboard shortcuts working); the task
// page is reached through the row's open button or the description panel.
function onRowClick(entry) {
  select(entry)
  // A click on the title starts an inline edit that takes focus; don't steal it
  // back to the page.
  if (editors.get(entry.id)?.isEditing?.()) return
  focusPage()
}

function syncDescription() {
  descriptionDraft.value = selected.value?.task?.description || ''
}

function clearSelection() {
  selectedId.value = null
  draft.value = ''
  filter.value = ''
  syncDescription()
}

async function submit() {
  const text = draft.value.trim()
  if (!text) return
  await push(text, 'top')
}

async function push(title, position) {
  try {
    setEntries(await api.stack.push({ title, position }))
    draft.value = ''
    filter.value = ''
    selectedId.value = null
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

async function promote(entry) {
  try {
    setEntries(await api.stack.promote(entry.id))
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

// Reorder the selected task one step up or down from the keyboard.
async function reorder(entry, target) {
  const from = entries.value.findIndex((item) => item.id === entry.id)
  const to = from + target
  if (from < 0 || to < 0 || to >= entries.value.length) return
  try {
    setEntries(await api.stack.reorder(entry.id, to))
    selectedId.value = entry.id
  } catch (e) {
    store.notify(e.message, true)
  }
}

function onTitleKeydown(event) {
  if (event.key === 'Enter' && event.shiftKey) {
    event.preventDefault()
    const text = draft.value.trim()
    if (text) push(text, 'next')
  } else if (event.key === 'Enter') {
    event.preventDefault()
    submit()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    clearSelection()
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    move(event.key === 'ArrowDown' ? 1 : -1)
  }
}

function onTitleInput() {
  filter.value = draft.value
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
    editors.get(selectedId.value)?.activate?.()
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

onMounted(() => {
  refresh()
  focusPage()
  // Tick so the current task's duration counts up every second.
  tickId = setInterval(() => (now.value = Date.now()), 1000)
})

onUnmounted(() => {
  if (tickId !== null) clearInterval(tickId)
})
</script>

<template>
  <div ref="pageEl" class="stack-page" tabindex="-1" @keydown="onKeydown">
    <StackHeader
      :show-history="showHistory"
      :loading="loading"
      @toggle-history="toggleHistory"
      @toggle-help="showHelp = !showHelp"
      @refresh="refresh"
    />

    <section class="panel stack-panel">
      <div class="stack-add row">
        <input
          v-model="draft"
          class="input grow"
          placeholder="Add a task (Enter: top · Shift+Enter: next)"
          aria-label="Add or filter tasks"
          @keydown="onTitleKeydown"
          @input="onTitleInput"
        />
        <button class="btn primary" @click="submit">Add</button>
      </div>
      <p v-if="filter" class="faint stack-filter-note">
        Filtering by “{{ filter }}” · <button class="link-btn" @click="((filter = ''), (draft = ''))">clear</button>
      </p>

      <div v-if="error" class="empty">
        Couldn't load the stack: {{ error }}.
        <div style="margin-top: 10px"><button class="btn sm ghost" @click="refresh">Retry</button></div>
      </div>

      <StackList
        v-else
        v-model:description="descriptionDraft"
        :entries="visible"
        :filter="filter"
        :selected-id="selectedId"
        :now="now"
        :loaded-at="loadedAt"
        :register-editor="setEditorRef"
        @update:entries="entries = $event"
        @set-entries="setEntries"
        @select="onRowClick"
        @promote="promote"
        @remove="removeEntry"
        @changed="emit('changed')"
        @refresh="refresh"
        @resync-description="syncDescription"
      />
    </section>

    <StackHistory v-if="showHistory" :history="history" :now="now" />

    <StackHelp v-if="showHelp" />
  </div>
</template>
