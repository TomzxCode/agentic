<script setup>
import { computed } from 'vue'
import { formatDayLabel, formatVisitDuration, localDayKey } from '../pageTiming'

// One column per day of the window, with the tallest day as the full height so
// the movement reads. Clicking a column selects that day for the timeline.
const props = defineProps({
  // DayTotal rows from the report: date (YYYY-MM-DD), duration_ms, visits.
  days: { type: Array, default: () => [] },
  // The days the timeline range covers, highlighted in the chart.
  selectedDays: { type: Array, default: () => [] }
})

defineEmits(['select'])

const max = computed(() => Math.max(1, ...props.days.map((day) => day.duration_ms || 0)))
const dense = computed(() => props.days.length > 14)

function height(day) {
  if (!day.duration_ms) return 0
  return Math.max(2, (day.duration_ms / max.value) * 100)
}

// A 30- or 90-day window cannot label every column, so only every fifth day
// carries its number; the tooltip holds the full date.
function label(day) {
  const date = new Date(`${day.date}T00:00:00`)
  if (Number.isNaN(date.getTime())) return ''
  if (!dense.value) return date.toLocaleDateString(undefined, { weekday: 'short' })
  return date.getDate() === 1 || date.getDate() % 5 === 0 ? String(date.getDate()) : ''
}

function tooltip(day) {
  const visits = day.visits === 1 ? '1 visit' : `${day.visits} visits`
  return `${formatDayLabel(day.date)} · ${formatVisitDuration(day.duration_ms)} · ${visits}`
}

const today = localDayKey()
</script>

<template>
  <div class="time-trend" role="img" :aria-label="`Daily time in the app over ${days.length} days`">
    <div class="time-trend-bars">
      <button
        v-for="day in days"
        :key="day.date"
        type="button"
        class="time-trend-col"
        :class="{
          'time-trend-selected': selectedDays.includes(day.date),
          'time-trend-today': day.date === today
        }"
        :title="tooltip(day)"
        :aria-pressed="selectedDays.includes(day.date)"
        @click="$emit('select', day.date)"
      >
        <span class="time-trend-bar-wrap">
          <span class="time-trend-bar" :style="{ height: `${height(day)}%` }"></span>
        </span>
        <span class="time-trend-label">{{ label(day) }}</span>
      </button>
    </div>
    <p v-if="!days.length" class="faint">No days in the window.</p>
  </div>
</template>
