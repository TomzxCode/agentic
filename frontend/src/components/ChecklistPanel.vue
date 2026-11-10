<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'
import EditableText from './EditableText.vue'
import Icon from './Icon.vue'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const draft = ref('')
const busy = ref(false)
// The id of the item being converted, so only its button shows a spinner.
const converting = ref(null)

const items = computed(() => props.task.checklist || [])
// The items that count: a manual item, or one whose template still matches.
// Items from a template that no longer matches stay visible but disabled.
const applicable = computed(() => items.value.filter((item) => item.applicable))
const doneCount = computed(() => applicable.value.filter((item) => item.done).length)
const percent = computed(() =>
  applicable.value.length ? Math.round((doneCount.value / applicable.value.length) * 100) : 0
)

// Drag and drop reordering: while a drag is in progress `order` holds the ids
// in the order on screen, and the list renders from it instead of the server's
// positions. It is dropped once the reloaded task arrives.
const listEl = ref(null)
const dragId = ref(null)
const order = ref(null)
const moved = ref(false)

const displayItems = computed(() => {
  if (!order.value) return items.value
  const byId = new Map(items.value.map((item) => [item.id, item]))
  const listed = order.value.map((id) => byId.get(id)).filter(Boolean)
  // An item added while the drag was running still belongs in the list.
  return listed.concat(items.value.filter((item) => !order.value.includes(item.id)))
})

watch(items, () => {
  if (!dragId.value) {
    order.value = null
    moved.value = false
  }
})

async function saveOrder(ids) {
  try {
    await api.tasks.reorderChecklistItems(props.task.id, ids)
  } catch (e) {
    store.notify(e.message, true)
    order.value = null
  } finally {
    emit('changed')
  }
}

// The row under the pointer decides the new slot. Midpoint comparisons make
// the item swap as soon as it passes the middle of its neighbour.
function targetIndex(rows, y) {
  const raw = rows.findIndex((row) => {
    const rect = row.getBoundingClientRect()
    return y < rect.top + rect.height / 2
  })
  return raw === -1 ? rows.length : raw
}

function onDragMove(event) {
  if (!dragId.value || !listEl.value || !order.value) return
  const rows = [...listEl.value.querySelectorAll('[data-checklist-id]')]
  const current = order.value.indexOf(dragId.value)
  if (current === -1 || !rows.length) return
  const raw = targetIndex(rows, event.clientY)
  // Removing the dragged row first shifts every later slot down by one.
  const target = Math.max(0, Math.min(rows.length - 1, raw > current ? raw - 1 : raw))
  if (target === current) return
  const next = [...order.value]
  next.splice(current, 1)
  next.splice(target, 0, dragId.value)
  order.value = next
  moved.value = true
}

function endDrag() {
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', endDrag)
  window.removeEventListener('pointercancel', endDrag)
  const ids = order.value
  const changed = moved.value
  dragId.value = null
  moved.value = false
  if (!ids || !changed) {
    order.value = null
    return
  }
  saveOrder(ids)
}

function startDrag(item, event) {
  if (busy.value) return
  // Left mouse button, pen, or touch; right-click keeps the browser menu.
  if (event.button !== undefined && event.button !== 0) return
  event.preventDefault()
  dragId.value = item.id
  order.value = items.value.map((entry) => entry.id)
  moved.value = false
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', endDrag)
  window.addEventListener('pointercancel', endDrag)
}

// The keyboard path for the same move, so reordering works without a pointer.
function moveBy(item, delta) {
  if (busy.value) return
  const ids = items.value.map((entry) => entry.id)
  const current = ids.indexOf(item.id)
  const target = current + delta
  if (current === -1 || target < 0 || target >= ids.length) return
  ids.splice(current, 1)
  ids.splice(target, 0, item.id)
  saveOrder(ids)
}

async function add() {
  const text = draft.value.trim()
  if (!text || busy.value) return
  busy.value = true
  try {
    await api.tasks.addChecklistItem(props.task.id, { text })
    draft.value = ''
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function toggle(item) {
  if (!item.applicable) return
  try {
    await api.tasks.updateChecklistItem(props.task.id, item.id, { done: !item.done })
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
    // Put the checkbox back in step with the server after a failed save.
    emit('changed')
  }
}

// A converted item points at its task, so its field shows and edits the live
// task title. A normal item keeps editing its own text.
function itemText(item) {
  return item.converted_task_id ? item.converted_task_title || item.text : item.text
}

async function saveText(item, value) {
  const text = String(value || '').trim()
  // An empty edit is not a renaming; reload so the field shows the old text.
  if (!text) {
    emit('changed')
    return
  }
  try {
    if (item.converted_task_id) {
      await api.tasks.update(item.converted_task_id, { title: text })
    } else {
      await api.tasks.updateChecklistItem(props.task.id, item.id, { text })
    }
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
    emit('changed')
  }
}

// Turn the item into a child task. The item stays in the checklist, open and
// linked to the new task, so the step is not lost and its completion stays
// yours to record.
async function convert(item) {
  if (converting.value || item.converted_task_id) return
  converting.value = item.id
  try {
    const created = await api.tasks.convertChecklistItem(props.task.id, item.id)
    store.notify(`Created task: ${created.title}`)
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    converting.value = null
  }
}

async function remove(item) {
  try {
    await api.tasks.removeChecklistItem(props.task.id, item.id)
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
    emit('changed')
  }
}

function onAddKeydown(event) {
  if (event.key === 'Enter') {
    event.preventDefault()
    add()
  }
}
</script>

<template>
  <section class="panel checklist-panel">
    <div class="panel-head">
      <h2>
        Checklist
        <span v-if="applicable.length" class="faint">{{ doneCount }}/{{ applicable.length }}</span>
      </h2>
      <span v-if="items.length && !applicable.length" class="faint">Nothing applies right now</span>
    </div>

    <div
      v-if="applicable.length"
      class="checklist-progress"
      role="progressbar"
      :aria-valuenow="doneCount"
      aria-valuemin="0"
      :aria-valuemax="applicable.length"
      :aria-label="`${doneCount} of ${applicable.length} checklist items done`"
    >
      <span :style="{ width: percent + '%' }"></span>
    </div>

    <div v-if="!items.length" class="faint" style="margin-bottom: 10px">No checklist items yet.</div>

    <div ref="listEl" class="checklist-list" :class="{ dragging: dragId }">
      <div
        v-for="item in displayItems"
        :key="item.id"
        :data-checklist-id="item.id"
        class="checklist-item"
        :class="{ done: item.done, stale: !item.applicable, lifted: item.id === dragId }"
      >
        <button
          class="checklist-grip"
          type="button"
          :aria-label="`Reorder ${itemText(item)}`"
          :aria-pressed="item.id === dragId ? 'true' : undefined"
          title="Drag to reorder, or press ↑ / ↓"
          @pointerdown="startDrag(item, $event)"
          @keydown.up.prevent="moveBy(item, -1)"
          @keydown.down.prevent="moveBy(item, 1)"
        >
          ⠿
        </button>
        <input
          type="checkbox"
          :checked="item.done"
          :disabled="!item.applicable"
          :aria-label="item.text"
          @change="toggle(item)"
        />
        <div class="grow">
          <EditableText
            class="checklist-text"
            :value="itemText(item)"
            placeholder="Checklist item"
            @save="(v) => saveText(item, v)"
          />
          <div v-if="item.template_name" class="faint checklist-source">
            {{ item.template_name }}<span v-if="!item.applicable"> · no longer applies</span>
          </div>
        </div>
        <RouterLink
          v-if="item.converted_task_id"
          class="btn sm ghost checklist-action"
          :to="`/task/${item.converted_task_id}`"
          :title="`Open the task: ${item.converted_task_title || item.text}`"
          :aria-label="`Open the task: ${item.converted_task_title || item.text}`"
        >
          <Icon name="tasks" :size="14" />
        </RouterLink>
        <button
          v-else
          class="btn sm ghost checklist-action"
          :disabled="converting === item.id"
          title="Convert this item into a task"
          :aria-label="`Convert ${item.text} into a task`"
          @click="convert(item)"
        >
          <span v-if="converting === item.id" class="spinner"></span>
          <span v-else>+</span>
        </button>
        <button class="btn sm danger checklist-action" title="Remove this item" @click="remove(item)">✕</button>
      </div>
    </div>

    <div class="row" style="margin-top: 10px">
      <input
        v-model="draft"
        class="input grow"
        placeholder="Add a checklist item…"
        aria-label="New checklist item"
        @keydown="onAddKeydown"
      />
      <button class="btn primary sm" :disabled="busy || !draft.trim()" @click="add">
        <span v-if="busy" class="spinner"></span> Add
      </button>
    </div>
  </section>
</template>

<style scoped>
.checklist-progress {
  height: 4px;
  border-radius: 999px;
  background: var(--border);
  margin-bottom: 10px;
  overflow: hidden;
}
.checklist-progress span {
  display: block;
  height: 100%;
  background: var(--primary);
  transition: width 120ms ease;
}
.checklist-list.dragging {
  user-select: none;
}
.checklist-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
}
.checklist-item.lifted {
  opacity: 0.6;
}
.checklist-grip {
  flex-shrink: 0;
  margin-top: 1px;
  padding: 0 2px;
  border: none;
  background: none;
  color: var(--muted-foreground);
  font-size: 14px;
  line-height: 1.5;
  cursor: grab;
  /* A drag on the handle must not scroll the page on touch screens. */
  touch-action: none;
}
.checklist-grip:hover,
.checklist-grip:focus-visible {
  color: var(--foreground);
}
.checklist-item input[type='checkbox'] {
  margin-top: 4px;
  flex-shrink: 0;
}
.checklist-item.done .checklist-text {
  text-decoration: line-through;
  color: var(--muted-foreground);
}
/* Every row action is the same square, whatever glyph it carries. */
.checklist-item .checklist-action {
  width: 28px;
  min-width: 28px;
  padding-left: 0;
  padding-right: 0;
}
@media (max-width: 760px) {
  .checklist-item .checklist-action {
    width: 36px;
    min-width: 36px;
  }
}
.checklist-item.stale {
  opacity: 0.5;
}
.checklist-source {
  font-size: 11px;
  margin-top: 1px;
}
</style>
