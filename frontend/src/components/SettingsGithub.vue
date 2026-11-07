<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'
import RefreshPolicyField from './RefreshPolicyField.vue'

// The "GitHub" settings section: the GitHub login that counts as "you", how
// often GitHub issues/PRs re-fetch, and the cadence of the one background job
// that keeps the ghx cache every GitHub page reads. The page shell supplies the
// raw overrides/defaults, the effective (detected) login, and whether this
// section is showing.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) },
  effective: { type: Object, default: () => ({}) },
  active: { type: Boolean, default: false }
})

const form = reactive({ github_login: '' })
const detectedLogin = ref('')
const savingLogin = ref(false)
const savedLogin = ref(false)
let loginSavedTimer

const CACHE_INTERVAL_KEY = 'ghx_cache_refresh_interval'
const cache = reactive({ interval: '' })
const savingCache = ref(false)
const savedCache = ref(false)
let cacheSavedTimer

watch(
  () => props.overrides,
  (overrides) => {
    form.github_login = overrides.github_login ?? ''
    // Only show a detected value when the user has not overridden it.
    detectedLogin.value = overrides.github_login ? '' : props.effective?.github_login || ''
    cache.interval = overrides[CACHE_INTERVAL_KEY] ?? ''
  },
  { immediate: true }
)

// Saving the login reloads the shared settings so the inbox and repository
// views see the new identity without a page reload.
async function saveLogin() {
  savingLogin.value = true
  try {
    await api.settings.update({ github_login: form.github_login.trim() })
    savedLogin.value = true
    clearTimeout(loginSavedTimer)
    loginSavedTimer = setTimeout(() => (savedLogin.value = false), 1500)
    await store.loadSettings().catch(() => {})
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    savingLogin.value = false
  }
}

// A malformed duration is rejected by the server and reported, leaving the
// stored value alone.
async function saveCacheInterval() {
  savingCache.value = true
  try {
    await api.settings.update({ [CACHE_INTERVAL_KEY]: cache.interval })
    savedCache.value = true
    clearTimeout(cacheSavedTimer)
    cacheSavedTimer = setTimeout(() => (savedCache.value = false), 1500)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    savingCache.value = false
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>GitHub</h2>
    </div>
    <p class="faint" style="margin-top: 0">
      The GitHub account that counts as you. The inbox, a repository's pull requests, and the metrics page only offer to
      record a change for a pull request this account authored.
    </p>

    <div class="field">
      <label>
        Your GitHub login
        <span v-if="savingLogin" class="faint">saving…</span>
        <span v-else-if="savedLogin" class="faint">saved</span>
      </label>
      <input
        v-model="form.github_login"
        class="input"
        :placeholder="detectedLogin || 'detected from gh when blank'"
        @blur="saveLogin"
      />
      <p class="faint" style="margin: 4px 0 0">
        <template v-if="detectedLogin">
          Detected from <code>gh</code>: <code>{{ detectedLogin }}</code
          >.
        </template>
        Leave blank to use that, or set a login to override it.
      </p>
    </div>

    <p class="faint">
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
        <span v-if="savingCache" class="faint">saving…</span>
        <span v-else-if="savedCache" class="faint">saved</span>
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
