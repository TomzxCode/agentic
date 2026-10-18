<script setup>
import { computed, nextTick, ref } from 'vue'
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
  // How the field is edited: 'content' (click or Enter on the rendered value),
  // 'field' (an explicit button under the value), or 'external' (same protection
  // as 'field', but the parent renders the action and opens the field through
  // activate()). Both button modes stop treating the content as the edit
  // trigger: a body whose Markdown carries its own controls (a `<details>`
  // section, a link) needs that, otherwise a click meant for the control opens
  // the editor instead. An empty field has no content to interact with, so its
  // placeholder still opens the editor on click.
  editTrigger: { type: String, default: 'content' }
})
const emit = defineEmits(['save', 'editing'])

// Whether the content keeps its own clicks (so the edit action is elsewhere).
const protectsContent = computed(() => props.editTrigger !== 'content')

const editing = ref(false)
const draft = ref('')
const input = ref(null)
const displayEl = ref(null)
// The height the value occupied on screen, applied to the multiline editor so
// opening it does not collapse the section it sits in.
const editorHeight = ref(null)
let skipCommit = false

// Open the editor with the raw value; what both the click target and the edit
// button do once a click is theirs to handle.
function open() {
  draft.value = props.value || ''
  // Measure the displayed value before the editor replaces it.
  const displayed = props.multiline ? displayEl.value?.offsetHeight || 0 : 0
  editorHeight.value = null
  editing.value = true
  emit('editing', true)
  nextTick(() => {
    input.value?.focus()
    if (!props.multiline) return
    // The textarea's default rows are the floor, so a short value keeps a
    // usable field. A value taller than that opens at the height it had on
    // screen, and the raw Markdown scrolls inside it when it needs more room.
    editorHeight.value = Math.max(displayed, input.value?.offsetHeight || 0) || null
    if (input.value?.setSelectionRange) {
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

// The rendered Markdown is the edit trigger only when the field edits its own
// content; with an edit action elsewhere, the content keeps its own clicks.
function onDisplayClick(event) {
  if (!protectsContent.value) start(event)
}

function commit() {
  if (skipCommit) {
    skipCommit = false
    return
  }
  const value = draft.value
  editing.value = false
  emit('editing', false)
  if (value !== (props.value || '')) emit('save', value)
}

function cancel() {
  skipCommit = true
  editing.value = false
  emit('editing', false)
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
// Not when the content is protected: there the edit action is the way in (and
// it carries the Enter key itself).
function onDisplayKeydown(event) {
  if (protectsContent.value) return
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
    :style="editorHeight ? { height: editorHeight + 'px' } : undefined"
    @keydown="onKeydown"
    @blur="commit"
  ></textarea>
  <!-- Displayed as Markdown; the editor still opens the raw value. When the
       content is protected, a control inside it (a <details> to expand, a link)
       gets the click instead of the editor. -->
  <component
    :is="as"
    v-else-if="markdown && value"
    ref="displayEl"
    class="inline-edit"
    :class="{ 'with-edit-btn': protectsContent }"
    :tabindex="protectsContent ? undefined : 0"
    :title="protectsContent ? undefined : 'Click or press Enter to edit'"
    @click="onDisplayClick"
    @keydown="onDisplayKeydown"
  >
    <MarkdownView :source="value" :task-lists="taskLists" />
    <button v-if="editTrigger === 'field'" type="button" class="btn sm ghost inline-edit-btn" @click.stop="open">
      ✎ Edit
    </button>
  </component>
  <component
    :is="as"
    v-else
    ref="displayEl"
    class="inline-edit"
    :class="{ 'inline-empty': !value, multiline }"
    tabindex="0"
    title="Click or press Enter to edit"
    @click="start"
    @keydown="onDisplayKeydown"
    >{{ value || placeholder }}</component
  >
</template>
