<script setup>
import { priorityLabel } from '../store'
import PriorityIcon from './PriorityIcon.vue'
import SearchSelect from './SearchSelect.vue'

// The editable priority picker: the icon-only SearchSelect preset with the
// task priorities, so every place a task's priority can be changed in place
// (task rows, the stack table, the bulk bar) looks and behaves the same.
const PRIORITY_VALUES = [0, 1, 2, 3]
const priorityOptions = PRIORITY_VALUES.map((value) => {
  const name = priorityLabel(value)
  return {
    value,
    label: name.charAt(0).toUpperCase() + name.slice(1),
    icon: PriorityIcon,
    iconProps: { priority: value, label: `Priority: ${name}` }
  }
})

defineProps({
  modelValue: { type: [String, Number], default: null },
  title: { type: String, default: 'Change priority' },
  disabled: { type: Boolean, default: false },
  // `icon` for a row's circle, `field` or `inline` for a labeled picker.
  variant: { type: String, default: 'icon' },
  placeholder: { type: String, default: 'Priority' }
})

defineEmits(['update:modelValue'])
</script>

<template>
  <SearchSelect
    class="task-priority-select"
    :variant="variant"
    :model-value="modelValue"
    :options="priorityOptions"
    :sort="false"
    :title="title"
    :placeholder="placeholder"
    :disabled="disabled"
    @update:model-value="$emit('update:modelValue', $event)"
  />
</template>
