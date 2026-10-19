<script setup>
import { computed } from 'vue'
import { ganttTicks, markerKind, markerLabel, spanPct } from '../gantt'
import StatusSelect from './StatusSelect.vue'

const props = defineProps({
  // Rows: span (created_at, updated_at), status, and one marker per event.
  rows: { type: Array, default: () => [] },
  // Visible window in milliseconds: { lo, hi }.
  domain: { type: Object, required: true },
  // Link each row to its task detail (the Gantt view); the task page does not.
  linkRows: { type: Boolean, default: false },
  // Drop the label column, leaving the track, for the single-row task chart.
  compact: { type: Boolean, default: false },
  // Make markers clickable, emitting their event (the task timeline).
  clickMarkers: { type: Boolean, default: false },
  showLegend: { type: Boolean, default: true }
})

const emit = defineEmits(['marker-click', 'change-status'])

function onMarkerClick(marker) {
  if (props.clickMarkers) emit('marker-click', marker)
}

function pct(t) {
  return spanPct(t, props.domain.lo, props.domain.hi)
}

const ticks = computed(() => ganttTicks(props.domain.lo, props.domain.hi, { compact: props.compact }))
const nowPct = computed(() => pct(Date.now()))
// "now" may sit outside a range the user picked, so only draw the line when the
// current time falls inside the visible window.
const showNow = computed(() => nowPct.value >= 0 && nowPct.value <= 100)

function barWidth(row) {
  return `${Math.max(pct(row.updated_at) - pct(row.created_at), 0.6)}%`
}

function markerTitle(marker) {
  return `${markerLabel(marker.type)} · ${new Date(marker.created_at).toLocaleString()}\n${marker.message}`
}

const legend = computed(() => {
  const seen = new Set()
  const out = []
  for (const row of props.rows) {
    for (const marker of row.markers) {
      if (seen.has(marker.type)) continue
      seen.add(marker.type)
      out.push({ type: marker.type, kind: markerKind(marker.type), label: markerLabel(marker.type) })
    }
  }
  return out
})
</script>

<template>
  <div class="gantt-scroll">
    <div class="gantt" :class="{ compact }">
      <div class="gantt-row gantt-axis">
        <div v-if="!compact" class="gantt-label"></div>
        <div class="gantt-track">
          <span
            v-for="tick in ticks"
            :key="tick.key"
            class="gantt-tick"
            :class="tick.align"
            :style="{ left: tick.left + '%' }"
            >{{ tick.label }}</span
          >
        </div>
      </div>

      <component
        :is="linkRows ? 'router-link' : 'div'"
        v-for="row in rows"
        :key="row.id"
        v-bind="linkRows ? { to: `/task/${row.id}` } : {}"
        class="gantt-row"
        :class="{ 'gantt-link': linkRows }"
        :title="row.title"
      >
        <div v-if="!compact" class="gantt-label">
          <!-- Stop the click from reaching the row's task link, so changing the
               status does not also open the task. -->
          <span class="gantt-status" @click.stop.prevent>
            <StatusSelect
              :model-value="row.status"
              @update:model-value="(value) => emit('change-status', row, value)"
            />
          </span>
          <span class="gantt-title">{{ row.title }}</span>
        </div>
        <div class="gantt-track">
          <span v-for="tick in ticks" :key="tick.key" class="gantt-gridline" :style="{ left: tick.left + '%' }"></span>
          <span v-if="showNow" class="gantt-now" :style="{ left: nowPct + '%' }"></span>
          <span
            class="gantt-bar"
            :class="`st-${row.status}`"
            :style="{ left: pct(row.created_at) + '%', width: barWidth(row) }"
          ></span>
          <component
            :is="clickMarkers ? 'button' : 'span'"
            v-for="marker in row.markers"
            :key="marker.id"
            v-bind="clickMarkers ? { type: 'button' } : {}"
            class="gantt-marker"
            :class="`mk-${markerKind(marker.type)}`"
            :style="{ left: pct(marker.created_at) + '%' }"
            :title="markerTitle(marker)"
            @click="onMarkerClick(marker)"
          ></component>
        </div>
      </component>
    </div>
  </div>

  <div v-if="showLegend && legend.length" class="gantt-legend">
    <span v-for="item in legend" :key="item.type" class="legend-item">
      <span class="legend-dot" :class="`mk-${item.kind}`"></span>{{ item.label }}
    </span>
    <span v-if="showNow" class="legend-item"><span class="legend-line"></span>now</span>
  </div>
</template>
