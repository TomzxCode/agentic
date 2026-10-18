<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store, timeAgo } from '../store'

// The "Refresh" settings section: how often to re-fetch Slack and GitHub. The
// page shell supplies the raw overrides/defaults and whether this section is
// showing, so a preview runs when the section is opened and after settings load.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) },
  active: { type: Boolean, default: false }
})

// Slack threads and GitHub issues/PRs refresh on their own schedules.
const REFRESH_FIELDS = [
  { key: 'slack_refresh_policy', label: 'Slack threads', source: 'slack' },
  { key: 'github_refresh_policy', label: 'GitHub issues/PRs', source: 'github' }
]

const form = reactive({ slack_refresh_policy: '', github_refresh_policy: '' })
const previews = reactive({ slack_refresh_policy: null, github_refresh_policy: null })
const status = ref({})
const saving = ref('')
const saved = ref('')
// Per source, so refreshing one does not block the other.
const forcing = reactive({ slack: false, github: false })
let savedTimer
const previewTimers = {}

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
async function preview(key) {
  if (typeof api.settings.previewRefreshPolicy !== 'function') return
  try {
    previews[key] = await api.settings.previewRefreshPolicy(form[key])
  } catch (e) {
    previews[key] = { valid: false, error: e.message }
  }
}

function previewAll() {
  return Promise.all(REFRESH_FIELDS.map((field) => preview(field.key)))
}

// When the background job last ran for each source. Best effort: a backend
// without the endpoint simply shows no status.
async function loadStatus() {
  if (typeof api.settings.refreshStatus !== 'function') return
  try {
    status.value = (await api.settings.refreshStatus()).sources || {}
  } catch {
    // Leave the last known status; a failed read should not block the settings.
  }
}

// Re-fetch every item of one source now, ignoring its policy.
async function forceRefresh(source) {
  if (forcing[source]) return
  forcing[source] = true
  try {
    const report = await api.items.refreshSource(source)
    const label = REFRESH_FIELDS.find((field) => field.source === source)?.label || source
    const summary = `${report.refreshed} refreshed${report.failed ? `, ${report.failed} failed` : ''}`
    store.notify(`${label}: ${summary}`, report.failed > 0)
    await loadStatus()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    forcing[source] = false
  }
}

function onInput(key) {
  clearTimeout(previewTimers[key])
  previewTimers[key] = setTimeout(() => preview(key), 300)
}

async function save(key) {
  saving.value = key
  try {
    await api.settings.update({ [key]: form[key] })
    saved.value = key
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = ''), 1500)
    await preview(key)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    saving.value = ''
  }
}

watch(
  () => props.overrides,
  (overrides) => {
    form.slack_refresh_policy = overrides.slack_refresh_policy ?? ''
    form.github_refresh_policy = overrides.github_refresh_policy ?? ''
    if (props.active) previewAll()
  },
  { immediate: true }
)

// Opening the section re-reads the previews and the last-run status, matching
// the shell's old behavior when the section was selected.
watch(
  () => props.active,
  (active) => {
    if (!active) return
    previewAll()
    loadStatus()
  }
)

onMounted(loadStatus)
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Refresh</h2>
    </div>
    <p class="faint" style="margin-top: 0">
      How often to re-fetch Slack threads (slackx) and GitHub issues/PRs (ghx). Age bands pair an upper age with a
      refresh interval. Each field saves when you leave it; leave one blank to stop refreshing that source.
    </p>
    <div v-for="field in REFRESH_FIELDS" :key="field.key" class="field">
      <label>
        {{ field.label }}
        <span v-if="saving === field.key" class="faint">saving…</span>
        <span v-else-if="saved === field.key" class="faint">saved</span>
      </label>
      <div class="row">
        <input
          v-model="form[field.key]"
          class="input mono grow"
          :placeholder="defaults[field.key] || '1d=1h,7d=6h,30d=1d,*=7d'"
          @input="onInput(field.key)"
          @blur="save(field.key)"
        />
        <button class="btn sm" :disabled="forcing[field.source]" @click="forceRefresh(field.source)">
          <span v-if="forcing[field.source]" class="spinner" aria-hidden="true"></span>
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
        <template v-if="status[field.source]?.last_run_at">
          {{ timeAgo(status[field.source].last_run_at) }} · {{ status[field.source].refreshed }} refreshed
          <span v-if="status[field.source].failed" style="color: var(--danger)">
            · {{ status[field.source].failed }} failed
          </span>
          <span v-if="status[field.source].origin === 'manual'"> · forced</span>
        </template>
        <template v-else>never</template>
      </p>
      <p v-if="status[field.source]?.error" style="margin: 4px 0 0; color: var(--danger)">
        {{ status[field.source].error }}
      </p>
      <div v-if="previews[field.key]">
        <p v-if="!previews[field.key].valid" style="color: var(--danger); margin: 0">
          {{ previews[field.key].error }}
        </p>
        <template v-else-if="previews[field.key].enabled">
          <div v-for="(tier, index) in previews[field.key].tiers" :key="index" class="row" style="gap: 8px">
            <span class="faint" style="min-width: 140px">newer than {{ formatDuration(tier.max_age_seconds) }}</span>
            <span v-if="tier.interval_seconds != null">every {{ formatDuration(tier.interval_seconds) }}</span>
            <span v-else class="faint">never</span>
          </div>
          <div class="row" style="gap: 8px">
            <span class="faint" style="min-width: 140px">older than that</span>
            <span v-if="previews[field.key].fallback_seconds != null">
              every {{ formatDuration(previews[field.key].fallback_seconds) }}
            </span>
            <span v-else class="faint">never</span>
          </div>
        </template>
        <p v-else class="faint" style="margin: 0">No automatic refresh.</p>
      </div>
    </div>
  </section>
</template>
