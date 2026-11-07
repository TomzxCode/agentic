<script setup>
import { onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store, timeAgo } from '../store'

// One source's refresh policy, rendered in that source's own section. The
// editable bands, the server's preview, the last-run status, and the force
// refresh stay identical in the Slack and GitHub sections.
const props = defineProps({
  policyKey: { type: String, required: true },
  label: { type: String, required: true },
  source: { type: String, required: true },
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) },
  active: { type: Boolean, default: false }
})

const value = ref('')
const preview = ref(null)
const status = ref(null)
const saving = ref(false)
const saved = ref(false)
const forcing = ref(false)
let savedTimer
let previewTimer

function formatDuration(seconds) {
  if (seconds == null) return 'never'
  for (const [label, size] of [
    ['w', 604800],
    ['d', 86400],
    ['h', 3600],
    ['m', 60],
    ['s', 1]
  ]) {
    if (seconds >= size && seconds % size === 0) return `${seconds / size}${label}`
  }
  return `${seconds}s`
}

// Explain a policy as age bands, using the server's parser so the preview and
// the saved behavior never disagree. Best effort: a backend without the
// endpoint simply shows no preview.
async function loadPreview() {
  if (typeof api.settings.previewRefreshPolicy !== 'function') return
  try {
    preview.value = await api.settings.previewRefreshPolicy(value.value)
  } catch (e) {
    preview.value = { valid: false, error: e.message }
  }
}

// When the background job last ran for this source. Best effort: a backend
// without the endpoint simply shows no status.
async function loadStatus() {
  if (typeof api.settings.refreshStatus !== 'function') return
  try {
    const sources = (await api.settings.refreshStatus()).sources || {}
    status.value = sources[props.source] || null
  } catch {
    // Leave the last known status; a failed read should not block the settings.
  }
}

// Re-fetch every item of this source now, ignoring its policy.
async function refreshNow() {
  if (forcing.value) return
  forcing.value = true
  try {
    const report = await api.items.refreshSource(props.source)
    const summary = `${report.refreshed} refreshed${report.failed ? `, ${report.failed} failed` : ''}`
    store.notify(`${props.label}: ${summary}`, report.failed > 0)
    await loadStatus()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    forcing.value = false
  }
}

function onInput() {
  clearTimeout(previewTimer)
  previewTimer = setTimeout(loadPreview, 300)
}

async function save() {
  saving.value = true
  try {
    await api.settings.update({ [props.policyKey]: value.value })
    saved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = false), 1500)
    await loadPreview()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    saving.value = false
  }
}

watch(
  () => props.overrides,
  (overrides) => {
    value.value = overrides[props.policyKey] ?? ''
    if (props.active) loadPreview()
  },
  { immediate: true }
)

// Opening the section re-reads the preview and the last-run status.
watch(
  () => props.active,
  (active) => {
    if (!active) return
    loadPreview()
    loadStatus()
  }
)

onMounted(loadStatus)
</script>

<template>
  <div class="field">
    <label>
      {{ label }}
      <span v-if="saving" class="faint">saving…</span>
      <span v-else-if="saved" class="faint">saved</span>
    </label>
    <div class="row">
      <input
        v-model="value"
        class="input mono grow"
        :placeholder="defaults[policyKey] || '1d=1h,7d=6h,30d=1d,*=7d'"
        @input="onInput"
        @blur="save"
      />
      <button class="btn sm" :disabled="forcing" @click="refreshNow">
        <span v-if="forcing" class="spinner" aria-hidden="true"></span>
        Force refresh
      </button>
    </div>
    <p class="faint" style="margin: 4px 0 0">
      <code>1d=1h,7d=6h,30d=1d,*=7d</code>: hourly while under a day old, every 6h under a week, daily under 30 days,
      weekly after. Omit the <code>*</code> band (or use <code>*=never</code>) to stop refreshing an item once it
      outgrows the last band.
    </p>
    <p class="faint" style="margin: 4px 0 0">
      Last run:
      <template v-if="status?.last_run_at">
        {{ timeAgo(status.last_run_at) }} · {{ status.refreshed }} refreshed
        <span v-if="status.failed" style="color: var(--danger)"> · {{ status.failed }} failed</span>
        <span v-if="status.origin === 'manual'"> · forced</span>
        · {{ status.refreshed_24h || 0 }} refreshed in the last 24h
      </template>
      <template v-else>never</template>
    </p>
    <p v-if="status?.error" style="margin: 4px 0 0; color: var(--danger)">{{ status.error }}</p>
    <div v-if="preview">
      <p v-if="!preview.valid" style="color: var(--danger); margin: 0">{{ preview.error }}</p>
      <template v-else-if="preview.enabled">
        <div v-for="(tier, index) in preview.tiers" :key="index" class="row" style="gap: 8px">
          <span class="faint" style="min-width: 140px">newer than {{ formatDuration(tier.max_age_seconds) }}</span>
          <span v-if="tier.interval_seconds != null">every {{ formatDuration(tier.interval_seconds) }}</span>
          <span v-else class="faint">never</span>
        </div>
        <div class="row" style="gap: 8px">
          <span class="faint" style="min-width: 140px">older than that</span>
          <span v-if="preview.fallback_seconds != null">every {{ formatDuration(preview.fallback_seconds) }}</span>
          <span v-else class="faint">never</span>
        </div>
      </template>
      <p v-else class="faint" style="margin: 0">No automatic refresh.</p>
    </div>
  </div>
</template>
