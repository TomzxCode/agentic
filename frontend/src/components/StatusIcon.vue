<script setup>
defineProps({
  status: { type: String, default: 'open' },
  label: { type: String, default: '' }
})
</script>

<template>
  <span class="task-status" :class="`st-${status}`" :title="label || status" :aria-label="label || status" role="img">
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path
        v-if="status === 'done'"
        d="M3.5 8.5l3 3 6-7"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
      <path
        v-else-if="status === 'blocked'"
        d="M4.5 4.5l7 7M11.5 4.5l-7 7"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
      />
      <path v-else-if="status === 'in_progress'" d="M5.5 4l6 4-6 4z" fill="currentColor" />
      <g v-else-if="status === 'in_review'">
        <path
          d="M1.5 8s2.4-4 6.5-4 6.5 4 6.5 4-2.4 4-6.5 4S1.5 8 1.5 8z"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linejoin="round"
        />
        <circle cx="8" cy="8" r="2" fill="currentColor" />
      </g>
      <path
        v-else-if="status === 'archived'"
        d="M4 8h8"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
      />
      <circle v-else cx="8" cy="8" r="5" fill="none" stroke="currentColor" stroke-width="2" />
    </svg>
  </span>
</template>
