<script setup>
import { nextTick, ref } from 'vue'

const props = defineProps({
  value: { type: String, default: '' },
  placeholder: { type: String, default: 'Click to edit' },
  multiline: { type: Boolean, default: false },
  as: { type: String, default: 'span' },
})
const emit = defineEmits(['save'])

const editing = ref(false)
const draft = ref('')
const input = ref(null)
let skipCommit = false

function start() {
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
function onDisplayKeydown(event) {
  if (event.key === 'Enter' || event.key === 'F2') {
    event.preventDefault()
    start()
  }
}
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
  <component
    :is="as"
    v-else
    class="inline-edit"
    :class="{ 'inline-empty': !value, multiline }"
    tabindex="0"
    title="Click or press Enter to edit"
    @click="start"
    @keydown="onDisplayKeydown"
  >{{ value || placeholder }}</component>
</template>
