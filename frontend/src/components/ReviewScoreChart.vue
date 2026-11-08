<script setup>
import { computed } from 'vue'
import { dayLabel, formatScore, scoreTone } from '../reviewScores'

const props = defineProps({
  // One rubric's daily series: label, points ({date, mean, count}), count, mean.
  series: { type: Object, required: true }
})

// The chart is drawn in a fixed viewBox and scaled by its container, so it
// needs no measurement and stays legible down to a phone's width.
const WIDTH = 320
const HEIGHT = 128
const PAD = { top: 10, right: 10, bottom: 22, left: 26 }
const plotWidth = WIDTH - PAD.left - PAD.right
const plotHeight = HEIGHT - PAD.top - PAD.bottom

const points = computed(() => props.series.points || [])

// The day range, so the horizontal position is real time: a gap between
// reviews stays a gap instead of collapsing to two adjacent points.
const range = computed(() => {
  if (!points.value.length) return { start: 0, end: 0 }
  const days = points.value.map((point) => dayMillis(point.date))
  return { start: Math.min(...days), end: Math.max(...days) }
})

function dayMillis(day) {
  return Date.parse(`${day}T00:00:00Z`)
}

function x(day) {
  const millis = dayMillis(day)
  if (range.value.end === range.value.start) return PAD.left + plotWidth / 2
  return PAD.left + ((millis - range.value.start) / (range.value.end - range.value.start)) * plotWidth
}

function y(score) {
  return PAD.top + (1 - Math.max(0, Math.min(1, Number(score)))) * plotHeight
}

const linePath = computed(() =>
  points.value
    .map((point, index) => `${index ? 'L' : 'M'}${x(point.date).toFixed(1)} ${y(point.mean).toFixed(1)}`)
    .join(' ')
)

// A faint area under the line gives the series a body without hiding the gaps.
const areaPath = computed(() => {
  if (!points.value.length) return ''
  const first = points.value[0]
  const last = points.value[points.value.length - 1]
  return `${linePath.value} L${x(last.date).toFixed(1)} ${y(0).toFixed(1)} L${x(first.date).toFixed(1)} ${y(0).toFixed(1)} Z`
})

const gridlines = [0, 0.25, 0.5, 0.75, 1]

// At most three date labels: the first, the middle, and the last day with a
// run. Labels too close together are dropped rather than drawn over each other.
const dateLabels = computed(() => {
  if (!points.value.length) return []
  const unique = [...new Set(points.value.map((point) => point.date))]
  const picks =
    unique.length === 1
      ? [{ date: unique[0], anchor: 'middle' }]
      : [
          { date: unique[0], anchor: 'start' },
          ...(unique.length > 2 ? [{ date: unique[Math.floor((unique.length - 1) / 2)], anchor: 'middle' }] : []),
          { date: unique[unique.length - 1], anchor: 'end' }
        ]
  const labels = []
  for (const pick of picks) {
    const position = x(pick.date)
    if (labels.some((label) => Math.abs(label.x - position) < 52)) continue
    labels.push({ ...pick, x: position })
  }
  return labels
})

const crossesYear = computed(() => {
  if (points.value.length < 2) return false
  const first = points.value[0].date.slice(0, 4)
  const last = points.value[points.value.length - 1].date.slice(0, 4)
  return first !== last
})

function pointTitle(point) {
  const reviews = `${point.count} review${point.count === 1 ? '' : 's'}`
  return `${dayLabel(point.date, true)} · ${formatScore(point.mean)} · ${reviews}`
}
</script>

<template>
  <div class="score-chart" :aria-label="`${series.label} score over time`">
    <svg
      v-if="points.length"
      :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
      class="score-chart-svg"
      role="img"
      :aria-label="`${series.label}: ${points.length} day${points.length === 1 ? '' : 's'} of scores`"
    >
      <!-- Horizontal gridlines at quarter steps, with the axis labels for the
           three that matter: 0, 0.5, and 1. -->
      <g class="score-grid">
        <line
          v-for="value in gridlines"
          :key="value"
          :x1="PAD.left"
          :x2="WIDTH - PAD.right"
          :y1="y(value)"
          :y2="y(value)"
          :class="{ 'score-grid-mid': value === 0.5 }"
        />
        <text
          v-for="value in [0, 0.5, 1]"
          :key="`label-${value}`"
          :x="PAD.left - 6"
          :y="y(value) + 3"
          text-anchor="end"
        >
          {{ value === 0 ? '0' : value.toFixed(1) }}
        </text>
      </g>

      <path v-if="points.length > 1" :d="areaPath" class="score-area" />
      <path v-if="points.length > 1" :d="linePath" class="score-line" />

      <circle
        v-for="point in points"
        :key="point.date"
        :cx="x(point.date)"
        :cy="y(point.mean)"
        r="3.5"
        class="score-point"
        :class="`tone-${scoreTone(point.mean)}`"
      >
        <title>{{ pointTitle(point) }}</title>
      </circle>

      <text
        v-for="label in dateLabels"
        :key="label.date"
        :x="label.x"
        :y="HEIGHT - 6"
        :text-anchor="label.anchor"
        class="score-date"
      >
        {{ dayLabel(label.date, crossesYear) }}
      </text>
    </svg>
    <p v-else class="faint score-empty">No scored reviews.</p>
  </div>
</template>
