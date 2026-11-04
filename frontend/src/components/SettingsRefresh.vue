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
// The ghx cache job's cadence. Every page reads that cache, so this is how
// fresh its GitHub reads are; the button runs the same pass by hand.
const CACHE_INTERVAL_KEY = 'ghx_cache_refresh_interval'
const cache = reactive({ interval: '' })
const status = ref({})
const cacheStatus = ref({})
const saving = ref('')
const saved = ref('')
// Per source, so refreshing one does not block the other.
const forcing = reactive({ slack: false, github: false, cache: false })
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
    const payload = await api.settings.refreshStatus()
    status.value = payload.sources || {}
    cacheStatus.value = payload.ghx_cache || {}
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

// Run the ghx cache pass now, ignoring its cadence and a failed repository's
// backoff. The server waits for the pass, so a repository ghx has never fully
// cached can make this take a while.
async function forceRefreshCache() {
  if (forcing.cache || typeof api.settings.refreshGhxCache !== 'function') return
  forcing.cache = true
  try {
    cacheStatus.value = await api.settings.refreshGhxCache()
    const summary = `${cacheStatus.value.refreshed} refreshed${
      cacheStatus.value.failed ? `, ${cacheStatus.value.failed} failed` : ''
    }`
    store.notify(`GitHub cache: ${summary}`, cacheStatus.value.failed > 0 || Boolean(cacheStatus.value.error))
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    forcing.cache = false
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

// Save the cache job's cadence. A malformed duration is rejected by the server
// and reported, leaving the stored value alone.
async function saveCacheInterval() {
  saving.value = CACHE_INTERVAL_KEY
  try {
    await api.settings.update({ [CACHE_INTERVAL_KEY]: cache.interval })
    saved.value = CACHE_INTERVAL_KEY
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = ''), 1500)
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
    cache.interval = overrides.ghx_cache_refresh_interval ?? ''
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
      refresh interval. Each field saves when you leave it; leave one blank to stop refreshing that source. The ghx
      cache every GitHub page reads is refreshed separately by one background job, which also serves the
      <code>Force refresh</code> button below.
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
          · {{ status[field.source].refreshed_24h || 0 }} refreshed in the last 24h
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
    <div class="field">
      <label>
        GitHub cache refresh
        <span v-if="saving === CACHE_INTERVAL_KEY" class="faint">saving…</span>
        <span v-else-if="saved === CACHE_INTERVAL_KEY" class="faint">saved</span>
      </label>
      <div class="row">
        <input
          v-model="cache.interval"
          class="input mono grow"
          :placeholder="defaults.ghx_cache_refresh_interval || '15m'"
          @blur="saveCacheInterval"
        />
        <button class="btn sm" :disabled="forcing.cache" @click="forceRefreshCache">
          <span v-if="forcing.cache" class="spinner" aria-hidden="true"></span>
          Force refresh
        </button>
      </div>
      <p class="faint" style="margin: 4px 0 0">
        How often the background job runs <code>ghx cache</code> over the registered GitHub repositories. Every page
        reads the cache, so this is how fresh the GitHub pages are. A duration such as <code>15m</code>,
        <code>1h</code> or <code>1d</code>; leave it blank to stop the scheduled pass. The button runs one pass now,
        including a repository whose last refresh failed.
      </p>
      <p class="faint" style="margin: 4px 0 0">
        Last cache refresh:
        <template v-if="cacheStatus.last_run_at">
          {{ timeAgo(cacheStatus.last_run_at) }} · {{ cacheStatus.refreshed }} refreshed
          <span v-if="cacheStatus.failed" style="color: var(--danger)"> · {{ cacheStatus.failed }} failed </span>
          <span v-if="cacheStatus.skipped"> · {{ cacheStatus.skipped }} skipped</span>
          <span v-if="cacheStatus.origin === 'manual'"> · forced</span>
        </template>
        <template v-else>never</template>
      </p>
      <p v-if="cacheStatus.error" style="margin: 4px 0 0; color: var(--danger)">{{ cacheStatus.error }}</p>
    </div>
  </section>
</template>
