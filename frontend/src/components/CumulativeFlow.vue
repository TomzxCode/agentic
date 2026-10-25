<script setup>
import { computed } from 'vue'

// The cumulative flow diagram: one stacked band per station's inventory over
// time, with everything completed stacked on top. A widening band is a queue
// forming at that station; the top edge is the line's total output to date.
const props = defineProps({
  // Daily flow samples: { at, backlog, in_progress, blocked, completed }.
  samples: { type: Array, required: true }
})

const W = 760
const H = 240
const BASE = 204
const TOP = 12

// Stacked bottom-up: the active queues first, everything finished on top, so
// the bands keep the stations' colors from the production-line drawing.
const BANDS = [
  { key: 'backlog', fill: 'band-backlog', label: 'Backlog' },
  { key: 'in_progress', fill: 'band-in_progress', label: 'In progress' },
  { key: 'blocked', fill: 'band-blocked', label: 'Blocked' },
  { key: 'completed', fill: 'band-completed', label: 'Completed' }
]

const count = computed(() => props.samples.length)
const maxTotal = computed(() =>
  Math.max(1, ...props.samples.map((sample) => sample.backlog + sample.in_progress + sample.blocked + sample.completed))
)
const scale = computed(() => (BASE - TOP) / maxTotal.value)

function x(index) {
  return count.value <= 1 ? 0 : (index / (count.value - 1)) * W
}

const bands = computed(() => {
  const below = props.samples.map(() => 0)
  return BANDS.map((band) => {
    const tops = props.samples.map((sample, index) => below[index] + sample[band.key])
    const points = props.samples.map((_, index) => `${x(index)},${BASE - tops[index] * scale.value}`)
    for (let index = count.value - 1; index >= 0; index--)
      points.push(`${x(index)},${BASE - below[index] * scale.value}`)
    for (let index = 0; index < count.value; index++) below[index] = tops[index]
    return { key: band.key, fill: band.fill, label: band.label, polygon: points.join(' ') }
  })
})

// Hover columns: one transparent rect per day, so every point of the chart
// answers "what did the line look like that day".
const step = computed(() => (count.value <= 1 ? W : W / (count.value - 1)))
const columns = computed(() =>
  props.samples.map((sample, index) => ({
    at: sample.at,
    x: x(index) - step.value / 2,
    label: sampleDate(sample.at),
    title: `${sampleDate(sample.at)}: ${sample.backlog} backlog, ${sample.in_progress} in progress, ${sample.blocked} blocked, ${sample.completed} completed`
  }))
)

function sampleDate(at) {
  const date = new Date(at)
  return Number.isNaN(date.getTime())
    ? String(at)
    : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// A handful of evenly spaced date labels under the chart.
const ticks = computed(() => {
  if (!count.value) return []
  const indexes = [...new Set([0, 1, 2, 3, 4].map((quarter) => Math.round((quarter * (count.value - 1)) / 4)))]
  return indexes.map((index) => ({ x: x(index), label: sampleDate(props.samples[index].at) }))
})
</script>

<template>
  <div class="cfd">
    <svg class="cfd-svg" :viewBox="`0 0 ${W} ${H}`" role="img" aria-label="Cumulative flow diagram">
      <polygon
        v-for="band in bands"
        :key="band.key"
        class="cfd-band"
        :class="band.fill"
        :points="band.polygon"
      ></polygon>
      <line class="cfd-baseline" :x1="0" :y1="BASE" :x2="W" :y2="BASE"></line>
      <rect
        v-for="column in columns"
        :key="column.at"
        class="cfd-column"
        :x="column.x"
        :y="0"
        :width="step"
        :height="BASE"
      >
        <title>{{ column.title }}</title>
      </rect>
    </svg>
    <div class="cfd-axis">
      <span v-for="tick in ticks" :key="tick.x" class="cfd-tick" :style="{ left: `${(tick.x / W) * 100}%` }">
        {{ tick.label }}
      </span>
    </div>
    <div class="cfd-legend">
      <span v-for="band in bands" :key="band.key" class="share-legend-item">
        <span class="share-dot" :class="`st-${band.key === 'completed' ? 'done' : band.key}`"></span>
        {{ band.label }}
      </span>
    </div>
  </div>
</template>
