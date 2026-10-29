<script setup>
import { computed } from 'vue'
import { blockInRange, formatClockTime, formatVisitDuration, overlapMs, pageColor, timelineTicks } from '../pageTiming'

// A range's visits as lanes: a page keeps a row, and each visit is a block where
// it happened. Lanes rather than one strip, so two tabs on different pages (or
// an overlapping visit) still read. Blocks are clipped to the range, so the
// timeline never runs past the boundaries the user picked.
const props = defineProps({
  // Visits from GET /api/page-visits/visits, oldest first.
  visits: { type: Array, default: () => [] },
  // The range's bounds, as ISO instants.
  start: { type: String, required: true },
  end: { type: String, required: true }
})

const rangeStart = computed(() => new Date(props.start).getTime())
const rangeEnd = computed(() => new Date(props.end).getTime())
const ticks = computed(() => timelineTicks(rangeStart.value, rangeEnd.value))

const lanes = computed(() => {
  const groups = new Map()
  for (const visit of props.visits) {
    const key = visit.route_name || visit.path
    let lane = groups.get(key)
    if (!lane) {
      lane = { key, label: visit.title || key, color: pageColor(key), visits: [], duration: 0 }
      groups.set(key, lane)
    }
    lane.visits.push(visit)
    lane.duration += overlapMs(visit.started_at, visit.ended_at, rangeStart.value, rangeEnd.value)
    // Visits arrive oldest first, so the newest title wins, matching the report.
    if (visit.title) lane.label = visit.title
  }
  return [...groups.values()]
    .map((lane) => ({
      ...lane,
      visits: [...lane.visits].sort((a, b) => new Date(a.started_at) - new Date(b.started_at))
    }))
    .sort((a, b) => b.duration - a.duration)
})

function block(visit) {
  return blockInRange(visit.started_at, visit.ended_at, rangeStart.value, rangeEnd.value)
}

// The first and last labels would run past the track; anchor them to its edges.
function tickAlign(tick) {
  if (tick.left < 4) return 'start'
  if (tick.left > 96) return 'end'
  return 'middle'
}

function tooltip(visit) {
  const when = `${formatClockTime(visit.started_at)}–${formatClockTime(visit.ended_at)}`
  const what = visit.detail ? `${visit.title} · ${visit.detail}` : visit.title || visit.path
  return `${when} · ${formatVisitDuration(visit.duration_ms)} · ${what}`
}
</script>

<template>
  <div class="time-timeline" :class="{ 'time-timeline-dense': ticks.length > 4 }">
    <div class="time-axis" aria-hidden="true">
      <span class="time-axis-label"></span>
      <div class="time-axis-track">
        <span
          v-for="tick in ticks"
          :key="tick.at"
          class="time-axis-tick"
          :class="`time-tick-${tickAlign(tick)}`"
          :style="{ left: `${tick.left}%` }"
          >{{ tick.label }}</span
        >
      </div>
    </div>
    <div
      v-for="lane in lanes"
      :key="lane.key"
      class="time-lane"
      role="img"
      :aria-label="`${lane.label}: ${lane.visits.length} visits, ${formatVisitDuration(lane.duration)}`"
    >
      <div class="time-lane-label" :title="lane.label">
        <span class="time-dot" :class="lane.color" aria-hidden="true"></span>
        <span class="time-lane-name">{{ lane.label }}</span>
      </div>
      <div class="time-lane-track">
        <span
          v-for="tick in ticks"
          :key="`grid-${tick.at}`"
          class="time-grid-line"
          :style="{ left: `${tick.left}%` }"
        ></span>
        <span
          v-for="visit in lane.visits"
          :key="visit.id"
          class="time-block"
          :class="lane.color"
          :style="{ left: `${block(visit).left}%`, width: `${block(visit).width}%` }"
          :title="tooltip(visit)"
        ></span>
      </div>
    </div>
    <p v-if="!lanes.length" class="faint time-timeline-empty">No visits in this range.</p>
  </div>
</template>
