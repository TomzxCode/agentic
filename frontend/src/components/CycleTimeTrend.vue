<script setup>
import { computed } from 'vue'
import { bucketLabel } from '../cycleTime'

const props = defineProps({
  // A CycleTimeSeries: label, median_hours, count, and its buckets.
  series: { type: Object, required: true }
})

const buckets = computed(() => props.series.buckets || [])
// Bars are drawn against the largest bucket median, so the shape shows relative
// movement rather than an absolute scale shared with other metrics.
const max = computed(() =>
  Math.max(1, ...buckets.value.map((bucket) => bucket.median_hours ?? 0).filter((value) => value > 0))
)

function barHeight(bucket) {
  if (bucket.median_hours == null) return 0
  return Math.max(3, (bucket.median_hours / max.value) * 100)
}
</script>

<template>
  <div class="cycle-trend" :aria-label="`${series.label} trend`">
    <div class="cycle-bars" role="img" :aria-label="`${series.label}: ${series.count} observations`">
      <span
        v-for="bucket in buckets"
        :key="bucket.start"
        class="cycle-bar"
        :class="{ 'cycle-bar-empty': bucket.median_hours == null }"
        :style="{ height: `${barHeight(bucket)}%` }"
        :title="bucketLabel(bucket)"
      ></span>
    </div>
    <p class="faint cycle-span">{{ buckets.length }} periods</p>
  </div>
</template>
