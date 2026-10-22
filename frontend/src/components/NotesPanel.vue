<script setup>
import { computed, ref } from 'vue'
import { api } from '../api'
import { store, formatDateTime } from '../store'
import EditableText from './EditableText.vue'
import EntityCard from './EntityCard.vue'
import MentionTextarea from './MentionTextarea.vue'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const busy = ref(false)

// Notes are the items whose source is 'note' (plain text kept with the task).
// They live in their own section under Context rather than in the Items panel,
// which groups the external sources (Slack, GitHub, Drive, URLs, …).
const notes = computed(() => (props.task.associations || []).filter((a) => a.item?.source === 'note'))

const draft = ref('')

async function addNote() {
  const content = draft.value.trim()
  if (!content) return
  busy.value = true
  try {
    // No URL: the backend infers a note from the bare content, and the content
    // is the note's only value (its title falls back to it).
    await api.tasks.associate(props.task.id, { item: { title: '', content, fetch: false } })
    draft.value = ''
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

// A newline is a newline; Ctrl/Cmd+Enter submits the note (the same shortcut a
// multiline inline editor uses).
function onAddKeydown(event) {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
    event.preventDefault()
    addNote()
  }
}

async function saveContent(itemId, value) {
  try {
    await api.items.update(itemId, { content: value })
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function remove(itemId) {
  await api.tasks.unassociate(props.task.id, itemId)
  emit('changed')
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>
        Notes <span class="faint">{{ notes.length }}</span>
      </h2>
    </div>

    <div style="border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 12px">
      <!-- The Add button is overlaid in the field's bottom band (see .note-add)
           so the typed text keeps the full width. -->
      <div class="note-add">
        <MentionTextarea
          v-model="draft"
          class="textarea"
          rows="2"
          placeholder="Add a note… Use @ to mention a person or an item."
          @keydown="onAddKeydown"
        />
        <button class="btn primary sm" :disabled="busy || !draft.trim()" @click="addNote">
          <span v-if="busy" class="spinner"></span> Add note
        </button>
      </div>
    </div>

    <div v-if="!notes.length" class="faint">No notes yet.</div>

    <!-- A note reads as a comment: one value, the text itself, edited in place.
         The remove button sits beside the text so the text starts at the top of
         the card rather than below a header row. -->
    <EntityCard v-for="assoc in notes" :key="assoc.id">
      <div class="row" style="align-items: flex-start; gap: 8px">
        <EditableText
          class="grow"
          multiline
          markdown
          as="div"
          :value="assoc.item.content"
          placeholder="Empty note. Click to write."
          @save="(value) => saveContent(assoc.item.id, value)"
        />
        <button class="btn sm danger" title="Remove" @click="remove(assoc.item.id)">✕</button>
      </div>
      <template #meta>
        <div class="faint" style="margin-top: 4px">added {{ formatDateTime(assoc.created_at) }}</div>
      </template>
    </EntityCard>
  </section>
</template>
