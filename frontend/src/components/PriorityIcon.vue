<script setup>
import { computed } from 'vue'

const props = defineProps({
  priority: { type: [Number, String], default: 2 },
  label: { type: String, default: '' }
})

// 0 = low, 1 = medium, 2 = high, 3 = urgent.
const NAMES = { 0: 'low', 1: 'medium', 2: 'high', 3: 'urgent' }
const level = computed(() => NAMES[Number(props.priority)] || 'medium')
const name = computed(() => props.label || level.value)
</script>

<template>
  <span class="task-priority" :class="`prio-${level}`" :title="name" :aria-label="name" role="img">
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="4" fill="currentColor" />
    </svg>
  </span>
</template>
