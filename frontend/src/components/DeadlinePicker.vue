<script setup>
// Inline deadline editor: shows the deadline (with how soon it is) and opens a
// datetime picker in place. Emits the new value as a UTC ISO string, or null to
// clear it.
import { computed, nextTick, ref } from 'vue'
import { deadlineInfo, formatDeadline } from '../store'

const props = defineProps({
  modelValue: { type: String, default: null },
  placeholder: { type: String, default: 'Set deadline' },
  title: { type: String, default: 'Deadline' }
})
const emit = defineEmits(['update:modelValue'])

const editing = ref(false)
const draft = ref('')
const input = ref(null)

const info = computed(() => deadlineInfo(props.modelValue))
const display = computed(() => (props.modelValue ? formatDeadline(props.modelValue) : props.placeholder))

// ISO (UTC) to the local wall-clock string a datetime-local input expects.
function toInputValue(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function start() {
  draft.value = toInputValue(props.modelValue)
  editing.value = true
  nextTick(() => input.value?.focus())
}

function commit() {
  const current = props.modelValue
  editing.value = false
  if (!draft.value) {
    if (current) emit('update:modelValue', null)
    return
  }
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
    commit()
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
      @blur="commit"
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
      <span v-if="info" class="badge" :class="info.tone">{{ info.label }}</span>
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
