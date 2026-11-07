<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'
import RefreshPolicyField from './RefreshPolicyField.vue'

// The "GitHub" settings section: how often GitHub issues/PRs re-fetch, and the
// cadence of the one background job that keeps the ghx cache every GitHub page
// reads. The page shell supplies the raw overrides/defaults and whether this
// section is showing.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) },
  active: { type: Boolean, default: false }
})

const CACHE_INTERVAL_KEY = 'ghx_cache_refresh_interval'
const cache = reactive({ interval: '' })
const saving = ref(false)
const saved = ref(false)
let savedTimer

watch(
  () => props.overrides,
  (overrides) => {
    cache.interval = overrides[CACHE_INTERVAL_KEY] ?? ''
  },
  { immediate: true }
)

// A malformed duration is rejected by the server and reported, leaving the
// stored value alone.
async function saveCacheInterval() {
  saving.value = true
  try {
    await api.settings.update({ [CACHE_INTERVAL_KEY]: cache.interval })
    saved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = false), 1500)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>GitHub</h2>
    </div>
    <p class="faint" style="margin-top: 0">
      How often to re-fetch GitHub issues/PRs (ghx). Age bands pair an upper age with a refresh interval, and the field
      saves when you leave it; leave it blank to stop refreshing. The ghx cache every GitHub page reads is separate: one
      background job keeps it, and this is the only caller of <code>ghx cache</code>.
    </p>

    <RefreshPolicyField
      policy-key="github_refresh_policy"
      label="GitHub issues/PRs"
      source="github"
      :overrides="overrides"
      :defaults="defaults"
      :active="active"
    />

    <div class="field">
      <label>
        GitHub cache refresh
        <span v-if="saving" class="faint">saving…</span>
        <span v-else-if="saved" class="faint">saved</span>
      </label>
      <div class="row">
        <input
          v-model="cache.interval"
          class="input mono grow"
          :placeholder="defaults[CACHE_INTERVAL_KEY] || '15m'"
          @blur="saveCacheInterval"
        />
      </div>
      <p class="faint" style="margin: 4px 0 0">
        How often the background job runs <code>ghx cache</code> over the registered GitHub repositories. It is the only
        caller: every page reads the cache, so this is how fresh the GitHub pages are. A duration such as
        <code>15m</code>, <code>1h</code> or <code>1d</code>; leave it blank to stop refreshing the cache.
      </p>
    </div>
  </section>
</template>
