<script setup>
import { statusLabel } from '../store'
import SearchSelect from './SearchSelect.vue'
import StatusIcon from './StatusIcon.vue'

// The editable status picker: the SearchSelect preset with the task statuses,
// so every place a task's status can be changed in place (task rows, the
// sidebar, the stack table, the gantt, the bulk bar) looks and behaves the same.
const STATUS_VALUES = ['open', 'in_progress', 'blocked', 'done', 'archived']
const statusOptions = STATUS_VALUES.map((value) => ({
  value,
  label: statusLabel(value),
  icon: StatusIcon,
  iconProps: { status: value, label: statusLabel(value) }
}))

defineProps({
  modelValue: { type: String, default: 'open' },
  title: { type: String, default: 'Change status' },
  disabled: { type: Boolean, default: false },
  // `icon` for a row's status icon, `field` or `inline` for a labeled picker.
  variant: { type: String, default: 'icon' },
  placeholder: { type: String, default: 'Status' }
})

defineEmits(['update:modelValue'])
</script>

<template>
  <SearchSelect
    class="task-status-select"
    :variant="variant"
    :model-value="modelValue"
    :options="statusOptions"
    :sort="false"
    :title="title"
    :placeholder="placeholder"
    :disabled="disabled"
    @update:model-value="$emit('update:modelValue', $event)"
  />
</template>
