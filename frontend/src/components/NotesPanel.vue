<script setup>
import { ref } from 'vue'
import { store, formatDateTime } from '../store'
import EditableText from './EditableText.vue'
import EntityCard from './EntityCard.vue'
import MentionTextarea from './MentionTextarea.vue'

// Notes are shown the same way wherever they live: one card per note, its own
// timestamp, edited in place. The owner (a task or a person) supplies the notes
// and the calls that add, save, and remove one.
const props = defineProps({
  notes: { type: Array, default: () => [] },
  add: { type: Function, required: true },
  save: { type: Function, required: true },
  remove: { type: Function, required: true }
})
const emit = defineEmits(['changed'])
const busy = ref(false)
const draft = ref('')

async function addNote() {
  const content = draft.value.trim()
  if (!content) return
  busy.value = true
  try {
    await props.add(content)
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

async function saveContent(noteId, value) {
  try {
    await props.save(noteId, value)
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function removeNote(noteId) {
  try {
    await props.remove(noteId)
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
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
          placeholder="Add a note… Use @ to mention a person, an item, a task, or a date."
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
    <EntityCard v-for="note in notes" :key="note.id">
      <div class="row" style="align-items: flex-start; gap: 8px">
        <EditableText
          class="grow"
          multiline
          markdown
          as="div"
          :value="note.content"
          placeholder="Empty note. Click to write."
          @save="(value) => saveContent(note.id, value)"
        />
        <button class="btn sm danger" title="Remove" @click="removeNote(note.id)">✕</button>
      </div>
      <template #meta>
        <div class="faint" style="margin-top: 4px">added {{ formatDateTime(note.created_at) }}</div>
      </template>
    </EntityCard>
  </section>
</template>
