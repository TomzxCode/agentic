<script setup>
// Inline deadline editor: shows the deadline (with how soon it is) and opens a
// datetime picker in place. Emits the new value as a UTC ISO string, or null to
// clear it.
import { computed, nextTick, ref } from 'vue'
import { deadlineInfo, formatDeadline } from '../store'

const props = defineProps({
  modelValue: { type: String, default: null },
  placeholder: { type: String, default: 'Set deadline' },
  title: { type: String, default: 'Deadline' },
  // A deadline-like field that is not a due date (a snooze, a follow-up check)
  // hides the due-state badge, whose wording would be misleading.
  showState: { type: Boolean, default: true }
})
const emit = defineEmits(['update:modelValue'])

// A new deadline defaults to this time so only the date needs choosing.
const DEFAULT_TIME = '17:00'

const editing = ref(false)
const draft = ref('')
const initialDraft = ref('')
const input = ref(null)

const info = computed(() => deadlineInfo(props.modelValue))
const display = computed(() => (props.modelValue ? formatDeadline(props.modelValue) : props.placeholder))

// ISO (UTC) to the local wall-clock string a datetime-local input expects. With
// no deadline yet, prefill today at the default time.
function toInputValue(iso) {
  const pad = (n) => String(n).padStart(2, '0')
  const date = iso ? new Date(iso) : null
  if (date && !Number.isNaN(date.getTime())) {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
  }
  const now = new Date()
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${DEFAULT_TIME}`
}

function start() {
  draft.value = toInputValue(props.modelValue)
  initialDraft.value = draft.value
  editing.value = true
  nextTick(() => input.value?.focus())
}

// Enter confirms the shown value; clicking away without changing it cancels, so
// opening the picker by mistake never sets a deadline.
function commit(confirm = false) {
  if (!editing.value) return
  editing.value = false
  const current = props.modelValue
  if (!draft.value) {
    if (current) emit('update:modelValue', null)
    return
  }
  if (!confirm && draft.value === initialDraft.value) return
  const iso = new Date(draft.value).toISOString()
  if (iso !== current) emit('update:modelValue', iso)
}

function clear() {
  draft.value = ''
  editing.value = false
  if (props.modelValue) emit('update:modelValue', null)
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    editing.value = false
  } else if (event.key === 'Enter') {
    event.preventDefault()
    commit(true)
  }
}

// Let a parent (e.g. the command palette) jump straight into editing.
defineExpose({ activate: start })
</script>

<template>
  <span class="deadline">
    <input
      v-if="editing"
      ref="input"
      v-model="draft"
      type="datetime-local"
      class="inline-input deadline-input"
      @keydown="onKeydown"
      @blur="() => commit()"
    />
    <template v-else>
      <button
        type="button"
        class="deadline-btn"
        :class="{ 'is-empty': !modelValue }"
        :title="modelValue ? `${title}: ${display}` : placeholder"
        @click="start"
      >
        {{ display }}
      </button>
      <span v-if="showState && info" class="badge" :class="info.tone">{{ info.label }}</span>
      <button
        v-if="modelValue"
        type="button"
        class="chip-x"
        aria-label="Clear deadline"
        title="Clear deadline"
        @click="clear"
      >
        ×
      </button>
    </template>
  </span>
</template>
