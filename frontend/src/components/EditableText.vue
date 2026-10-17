<script setup>
import { nextTick, ref } from 'vue'
import MarkdownView from './MarkdownView.vue'

const props = defineProps({
  value: { type: String, default: '' },
  placeholder: { type: String, default: 'Click to edit' },
  multiline: { type: Boolean, default: false },
  as: { type: String, default: 'span' },
  // Render the display value as Markdown. The editor still opens the raw value.
  markdown: { type: Boolean, default: false },
  // Leave task-list checkboxes in the rendered Markdown clickable.
  taskLists: { type: Boolean, default: false },
  // Show an explicit edit button and stop treating the rendered Markdown as the
  // edit trigger. A field whose content carries its own controls (a `<details>`
  // section, a link) needs this: otherwise a click meant for the control opens
  // the editor instead. An empty field has no content to interact with, so its
  // placeholder still opens the editor on click.
  editButton: { type: Boolean, default: false }
})
const emit = defineEmits(['save'])

const editing = ref(false)
const draft = ref('')
const input = ref(null)
let skipCommit = false

// Open the editor with the raw value; what both the click target and the edit
// button do once a click is theirs to handle.
function open() {
  draft.value = props.value || ''
  editing.value = true
  nextTick(() => {
    input.value?.focus()
    if (props.multiline && input.value?.setSelectionRange) {
      const end = draft.value.length
      input.value.setSelectionRange(end, end)
    }
  })
}

function start(event) {
  // A click on a control inside the rendered Markdown (a link or a task-list
  // checkbox) belongs to that control, not to opening the editor.
  if (event?.target?.closest?.('a, input, button, label, select, textarea')) return
  open()
}

// The rendered Markdown is the edit trigger only when the field has no edit
// button; with one, the content keeps its own clicks.
function onDisplayClick(event) {
  if (!props.editButton) start(event)
}

function commit() {
  if (skipCommit) {
    skipCommit = false
    return
  }
  const value = draft.value
  editing.value = false
  if (value !== (props.value || '')) emit('save', value)
}

function cancel() {
  skipCommit = true
  editing.value = false
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    cancel()
  } else if (event.key === 'Enter' && (!props.multiline || event.metaKey || event.ctrlKey)) {
    event.preventDefault()
    commit()
  }
}

// Activate editing from the keyboard (Enter or F2) when not already editing.
// Not on a field with an edit button: there the button is the way in (and it
// carries the Enter key itself).
function onDisplayKeydown(event) {
  if (props.editButton) return
  if (event.key === 'Enter' || event.key === 'F2') {
    event.preventDefault()
    start()
  }
}

// Let a parent (e.g. the command palette) jump straight into editing, and ask
// whether this editor is currently open.
defineExpose({ activate: open, isEditing: () => editing.value })
</script>

<template>
  <input
    v-if="editing && !multiline"
    ref="input"
    v-model="draft"
    class="inline-input"
    @keydown="onKeydown"
    @blur="commit"
  />
  <textarea
    v-else-if="editing"
    ref="input"
    v-model="draft"
    class="inline-input"
    rows="3"
    @keydown="onKeydown"
    @blur="commit"
  ></textarea>
  <!-- Displayed as Markdown; the editor still opens the raw value. With an
       edit button the content is not a click target, so a control inside it
       (a <details> to expand, a link) gets the click. -->
  <component
    :is="as"
    v-else-if="markdown && value"
    class="inline-edit"
    :class="{ 'with-edit-btn': editButton }"
    :tabindex="editButton ? undefined : 0"
    :title="editButton ? undefined : 'Click or press Enter to edit'"
    @click="onDisplayClick"
    @keydown="onDisplayKeydown"
  >
    <MarkdownView :source="value" :task-lists="taskLists" />
    <button v-if="editButton" type="button" class="btn sm ghost inline-edit-btn" @click.stop="open">✎ Edit</button>
  </component>
  <component
    :is="as"
    v-else
    class="inline-edit"
    :class="{ 'inline-empty': !value, multiline }"
    tabindex="0"
    title="Click or press Enter to edit"
    @click="start"
    @keydown="onDisplayKeydown"
    >{{ value || placeholder }}</component
  >
</template>
