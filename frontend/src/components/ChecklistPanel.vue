<script setup>
import { computed, ref } from 'vue'
import { api } from '../api'
import { store } from '../store'
import EditableText from './EditableText.vue'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const draft = ref('')
const busy = ref(false)

const items = computed(() => props.task.checklist || [])
// The items that count: a manual item, or one whose template still matches.
// Items from a template that no longer matches stay visible but disabled.
const applicable = computed(() => items.value.filter((item) => item.applicable))
const doneCount = computed(() => applicable.value.filter((item) => item.done).length)
const percent = computed(() =>
  applicable.value.length ? Math.round((doneCount.value / applicable.value.length) * 100) : 0
)

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

async function saveText(item, value) {
  const text = String(value || '').trim()
  // An empty edit is not a renaming; reload so the field shows the old text.
  if (!text) {
    emit('changed')
    return
  }
  try {
    await api.tasks.updateChecklistItem(props.task.id, item.id, { text })
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
    emit('changed')
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

    <div
      v-for="item in items"
      :key="item.id"
      class="checklist-item"
      :class="{ done: item.done, stale: !item.applicable }"
    >
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
          :value="item.text"
          placeholder="Checklist item"
          @save="(v) => saveText(item, v)"
        />
        <div v-if="item.template_name" class="faint checklist-source">
          {{ item.template_name }}<span v-if="!item.applicable"> · no longer applies</span>
        </div>
      </div>
      <button class="btn sm danger" title="Remove this item" @click="remove(item)">✕</button>
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
.checklist-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
}
.checklist-item input[type='checkbox'] {
  margin-top: 4px;
  flex-shrink: 0;
}
.checklist-item.done .checklist-text {
  text-decoration: line-through;
  color: var(--muted-foreground);
}
.checklist-item.stale {
  opacity: 0.5;
}
.checklist-source {
  font-size: 11px;
  margin-top: 1px;
}
</style>
