<script setup>
defineProps({
  value: { type: [String, Number], default: '' },
  options: { type: Array, required: true }, // [{ value, label }]
  title: { type: String, default: 'Click to change' },
})
defineEmits(['save'])
</script>

<template>
  <select class="inline-select" :value="value" :title="title" @change="$emit('save', $event.target.value)">
    <option v-for="option in options" :key="String(option.value)" :value="option.value">
      {{ option.label }}
    </option>
  </select>
</template>
