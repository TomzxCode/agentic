<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import { formatTimestamp, moveItem, targetIndexAt } from '../stack'
import { deadlineInfo, formatDeadline, priorityLabel as priorityName, store } from '../store'
import EditableText from './EditableText.vue'
import MentionTextarea from './MentionTextarea.vue'
import PriorityIcon from './PriorityIcon.vue'
import SearchSelect from './SearchSelect.vue'
import StatusSelect from './StatusSelect.vue'

// The stack table: one row per entry plus the selected row's description, with
// drag-to-reorder. The page shell owns the entries, the selection, and the
// shortcuts; this component renders them, owns the row-level edits and drag,
// and emits the shell-level changes up.
const props = defineProps({
  entries: { type: Array, default: () => [] },
  filter: { type: String, default: '' },
  selectedId: { type: String, default: null },
  description: { type: String, default: '' },
  now: { type: Number, required: true },
  loadedAt: { type: Number, required: true },
  // Registers a row's title editor with the shell, so its shortcuts can drive it.
  registerEditor: { type: Function, default: () => {} }
})
const emit = defineEmits([
  'update:entries',
  'set-entries',
  'select',
  'promote',
  'remove',
  'changed',
  'refresh',
  'resync-description',
  'update:description'
])

// The stack table's columns, used by the description row's colspan.
const COLUMN_COUNT = 13

// 0 = low, 1 = medium, 2 = high, 3 = urgent. The icon-only picker reuses the
// priority icon, so the level can be changed in place from the stack row.
const priorityOptions = [0, 1, 2, 3].map((value) => {
  const name = priorityName(value)
  return {
    value,
    label: name.charAt(0).toUpperCase() + name.slice(1),
    icon: PriorityIcon,
    iconProps: { priority: value, label: `Priority: ${name}` }
  }
})

// A local copy of the rows so a drag can reorder live and read its own result on
// release, before the shell's prop round-trips back.
const rows = ref([])
let dragCandidate = null // { id, startY }
let dragId = null
let dragging = false
watch(
  () => props.entries,
  (list) => {
    if (!dragging) rows.value = list
  },
  { immediate: true }
)

// A non-current task's duration is fixed; the current task's keeps counting.
function displayDuration(entry) {
  if (!entry.is_current) return entry.duration
  return (entry.duration || 0) + (props.now - props.loadedAt) / 1000
}

// The deadline state (overdue / due soon / later) for a row, or null.
function deadlineFor(entry) {
  return deadlineInfo(entry.task?.deadline, props.now)
}

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

const nowDate = computed(() => new Date(props.now))

// Change a task's status from its stack row. A status outside the in-flight set
// takes the task off the stack, so the shell reloads afterwards.
async function changeStatus(entry, status) {
  if (!entry.task || status === entry.task.status) return
  const previous = entry.task.status
  entry.task.status = status
  try {
    await api.tasks.update(entry.task_id, { status })
    emit('changed')
    emit('refresh')
  } catch (e) {
    entry.task.status = previous
    store.notify(e.message, true)
  }
}

// Change a task's priority from its stack row; it stays on the stack.
async function changePriority(entry, priority) {
  if (!entry.task || priority === entry.task.priority) return
  const previous = entry.task.priority
  entry.task.priority = priority
  try {
    await api.tasks.update(entry.task_id, { priority })
    emit('changed')
  } catch (e) {
    entry.task.priority = previous
    store.notify(e.message, true)
  }
}

async function saveTitle(entry, title) {
  const next = title.trim()
  if (!next || next === entry.task?.title) return
  try {
    emit('set-entries', await api.stack.update(entry.id, { title: next }))
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function saveDescription() {
  const entry = rows.value.find((item) => item.id === props.selectedId)
  if (!entry) return
  const next = props.description
  if (next === (entry.task?.description || '')) return
  try {
    emit('set-entries', await api.stack.update(entry.id, { description: next }))
    emit('resync-description')
  } catch (e) {
    store.notify(e.message, true)
  }
}

// --- Drag and drop ---------------------------------------------------------
// Rows can be dragged to reorder (mouse anywhere on a row, touch from the
// handle). The list reorders live under the pointer; the move is persisted on
// release. Dragging is disabled while filtering, since reordering a filtered
// subset is ambiguous.
const listEl = ref(null)

function onRowPointerDown(event, entry) {
  if (props.filter) return
  const target = event.target
  const fromHandle = !!(target.closest && target.closest('.stack-handle'))
  if (!fromHandle) {
    // Touch/pen only drags from the handle (so the list can still scroll);
    // the mouse can drag anywhere on the row except its controls.
    if (event.pointerType !== 'mouse') return
    if (target.closest && target.closest('button, input, textarea, select')) return
  }
  dragCandidate = { id: entry.id, startY: event.clientY }
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragEnd)
  window.addEventListener('pointercancel', onDragEnd)
}

function onDragMove(event) {
  if (!dragCandidate) return
  if (!dragging) {
    if (Math.abs(event.clientY - dragCandidate.startY) < 6) return
    dragging = true
    dragId = dragCandidate.id
    document.body.classList.add('row-dragging')
  }
  const rowEls = listEl.value ? Array.from(listEl.value.querySelectorAll('.stack-row')) : []
  const midpoints = rowEls.map((row) => {
    const rect = row.getBoundingClientRect()
    return rect.top + rect.height / 2
  })
  const index = targetIndexAt(midpoints, event.clientY)
  const current = rows.value.findIndex((item) => item.id === dragId)
  if (current === -1 || index === current) return
  rows.value = moveItem(rows.value, current, index)
  emit('update:entries', rows.value)
}

async function onDragEnd() {
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
  window.removeEventListener('pointercancel', onDragEnd)
  const wasDragging = dragging
  const id = dragId
  dragCandidate = null
  dragging = false
  dragId = null
  document.body.classList.remove('row-dragging')
  if (!wasDragging || !id) return

  // Swallow the click that follows the drag so it does not just select the row.
  const swallow = (event) => {
    event.stopPropagation()
    event.preventDefault()
  }
  window.addEventListener('click', swallow, { capture: true, once: true })
  setTimeout(() => window.removeEventListener('click', swallow, { capture: true }), 300)

  const index = rows.value.findIndex((item) => item.id === id)
  if (index === -1) return
  try {
    emit('set-entries', await api.stack.reorder(id, index))
  } catch (e) {
    store.notify(e.message, true)
    emit('refresh')
  }
}

onUnmounted(() => {
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
  window.removeEventListener('pointercancel', onDragEnd)
  document.body.classList.remove('row-dragging')
})
</script>

<template>
  <div v-if="!rows.length" class="empty">
    <template v-if="filter">No tasks match “{{ filter }}”.</template>
    <template v-else>
      The stack is empty. Type above and press <span class="mono">Enter</span> to make something current.
    </template>
  </div>
  <table v-else ref="listEl" class="stack-table" aria-label="Task stack">
    <tbody>
      <template v-for="entry in rows" :key="entry.id">
        <tr
          class="stack-row"
          :class="{ current: entry.is_current, selected: entry.id === selectedId, dragging: entry.id === dragId }"
          @click="emit('select', entry)"
          @pointerdown="onRowPointerDown($event, entry)"
        >
          <td class="stack-handle-cell">
            <span class="stack-handle" title="Drag to reorder" aria-hidden="true">⠿</span>
          </td>
          <td class="stack-index mono">{{ entry.position }}</td>
          <td class="stack-indicator" :title="entry.is_current ? 'Current task' : 'Queued'">
            {{ entry.is_current ? '🔥' : '💤' }}
          </td>
          <td class="stack-status-cell" @click.stop @keydown.stop>
            <StatusSelect
              :model-value="entry.task?.status"
              @update:model-value="(value) => changeStatus(entry, value)"
            />
          </td>
          <td class="stack-priority-cell" @click.stop @keydown.stop>
            <SearchSelect
              class="task-priority-select"
              variant="icon"
              :model-value="entry.task?.priority ?? 2"
              :options="priorityOptions"
              :sort="false"
              title="Change priority"
              @update:model-value="(value) => changePriority(entry, Number(value))"
            />
          </td>
          <td class="stack-open-cell">
            <router-link class="btn sm ghost" :to="`/task/${entry.task_id}`" title="Open the task" @click.stop>
              ↗
            </router-link>
          </td>
          <td class="stack-title-cell" :title="entry.task?.title">
            <EditableText
              :ref="(el) => registerEditor(entry.id, el)"
              class="stack-title"
              :value="entry.task?.title || ''"
              placeholder="Untitled task"
              @save="(title) => saveTitle(entry, title)"
            />
          </td>
          <td class="stack-deadline-cell">
            <span
              v-if="deadlineFor(entry)"
              class="badge"
              :class="deadlineFor(entry).tone"
              :title="`Deadline: ${formatDeadline(entry.task?.deadline)}`"
            >
              {{ deadlineFor(entry).label }}
            </span>
            <span
              v-if="entry.task?.waiting_on_name"
              class="badge warn"
              :title="
                entry.task.follow_up_at
                  ? `Waiting on ${entry.task.waiting_on_name}, check back ${formatDeadline(entry.task.follow_up_at)}`
                  : `Waiting on ${entry.task.waiting_on_name}`
              "
            >
              Waiting on {{ entry.task.waiting_on_name }}
            </span>
          </td>
          <td class="stack-col mono faint" title="Times it became current">×{{ entry.execution_count }}</td>
          <td class="stack-col mono faint" title="Started">
            {{ formatTimestamp(entry.started_at, nowDate) }}
          </td>
          <td class="stack-col mono faint" title="Last current">
            {{ formatTimestamp(entry.last_current, nowDate) }}
          </td>
          <td class="stack-col stack-duration mono" title="Time as current">
            {{ formatDuration(displayDuration(entry)) }}
          </td>
          <td class="stack-actions-cell">
            <span class="stack-actions">
              <button
                v-if="!entry.is_current"
                class="btn sm ghost"
                title="Promote to current (Home)"
                @click.stop="emit('promote', entry)"
              >
                ↑
              </button>
              <button
                class="btn sm ghost danger"
                title="Remove from the stack (Delete)"
                @click.stop="emit('remove', entry)"
              >
                ✕
              </button>
            </span>
          </td>
        </tr>
        <tr v-if="entry.id === selectedId" class="stack-desc-row">
          <td :colspan="COLUMN_COUNT">
            <div class="stack-desc">
              <div class="stack-desc-head">
                <span class="faint">Description</span>
                <router-link class="faint" :to="`/task/${entry.task_id}`">Open task →</router-link>
              </div>
              <MentionTextarea
                :model-value="description"
                class="textarea"
                placeholder="Add a description… Use @ to mention a person or an item."
                @update:model-value="emit('update:description', $event)"
                @blur="saveDescription"
                @keydown.escape="saveDescription"
              />
            </div>
          </td>
        </tr>
      </template>
    </tbody>
  </table>
</template>
