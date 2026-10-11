<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { store } from '../store'
import GanttChart from '../components/GanttChart.vue'
import { resolveDomain, toField } from '../gantt'

const rows = ref([])
const loading = ref(false)
const error = ref('')
const includeDone = ref(false)
// The visible window is edited through two datetime fields. Until the user edits
// one, refreshes refit the window to the data.
const rangeStart = ref('')
const rangeEnd = ref('')
const rangePinned = ref(false)

// The window comes from the fitted domain and any range the user set; the chart
// gets the resolved lo/hi.
const resolved = computed(() => resolveDomain(rows.value, rangeStart.value, rangeEnd.value))
const domain = computed(() => ({ lo: resolved.value.lo, hi: resolved.value.hi }))
const rangeInvalid = computed(() => resolved.value.invalid)

async function load() {
  loading.value = true
  error.value = ''
  try {
    rows.value = await api.gantt.get({ includeDone: includeDone.value })
    if (!rangePinned.value) fitRange()
  } catch (e) {
    error.value = e.message
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}
onMounted(load)

function onRangeInput() {
  rangePinned.value = !!(rangeStart.value || rangeEnd.value)
}

function fitRange() {
  const { lo, hi } = resolveDomain(rows.value).fit
  rangePinned.value = false
  rangeStart.value = toField(lo)
  rangeEnd.value = toField(hi)
}
</script>

<template>
  <div>
    <div class="row page-head" style="margin-bottom: 16px">
      <h1 class="grow">Gantt</h1>
      <div class="gantt-range">
        <label class="gantt-range-field">
          <span>From</span>
          <input v-model="rangeStart" type="datetime-local" step="1" class="input" @input="onRangeInput" />
        </label>
        <label class="gantt-range-field">
          <span>To</span>
          <input v-model="rangeEnd" type="datetime-local" step="1" class="input" @input="onRangeInput" />
        </label>
        <button class="btn sm ghost" title="Fit the range to the data" @click="fitRange">Fit</button>
      </div>
      <label class="gantt-toggle">
        <input v-model="includeDone" type="checkbox" @change="load" />
        Include done
      </label>
      <button class="btn sm ghost" @click="load"><span v-if="loading" class="spinner"></span> Refresh</button>
    </div>

    <p v-if="rangeInvalid" class="gantt-range-error">End must be after start. Showing the fitted range.</p>

    <section class="panel">
      <div v-if="error" class="empty">
        Couldn't load the gantt: {{ error }}.
        <div style="margin-top: 10px"><button class="btn sm ghost" @click="load">Retry</button></div>
      </div>
      <div v-else-if="loading && !rows.length" class="empty"><span class="spinner"></span></div>
      <div v-else-if="!rows.length" class="empty">No tasks in flight. Create one to see it here.</div>

      <GanttChart v-else :rows="rows" :domain="domain" link-rows />
    </section>
  </div>
</template>
