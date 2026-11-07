<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { remoteLabel } from '../repositories/parse'
import { store } from '../store'
import RefreshPolicyField from './RefreshPolicyField.vue'

// The "GitHub" settings section: the GitHub login that counts as "you", how
// often GitHub issues/PRs re-fetch, the cadence of the one background job that
// keeps the ghx cache every GitHub page reads, and which repositories the review
// scan considers. The page shell supplies the raw overrides/defaults, the
// effective (detected) login, and whether this section is showing.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) },
  effective: { type: Object, default: () => ({}) },
  active: { type: Boolean, default: false }
})

const form = reactive({ github_login: '', review_scan_default: 'include' })
const detectedLogin = ref('')
const savingLogin = ref(false)
const savedLogin = ref(false)
let loginSavedTimer

const CACHE_INTERVAL_KEY = 'ghx_cache_refresh_interval'
const cache = reactive({ interval: '' })
const savingCache = ref(false)
const savedCache = ref(false)
let cacheSavedTimer

const savingDefault = ref(false)
const savedDefault = ref(false)
let defaultSavedTimer

// A repository's own opinion, or "default" to follow the app-wide choice.
const POLICIES = [
  { value: 'default', label: 'Default' },
  { value: 'include', label: 'Include' },
  { value: 'exclude', label: 'Exclude' }
]

const loadingRepositories = ref(false)
const savingRepository = ref('')

// The list identifies a repository by its GitHub "owner/repo" when the remote
// names one, so a checkout is recognisable even when its registered name is a
// directory name; a repository with no GitHub remote keeps its name. Sorted
// alphabetically, and each row carries whatever the identifier does not say.
function identifier(repository) {
  return remoteLabel(repository.remote_url) || repository.name || repository.path
}

function secondaryLabel(repository) {
  const label = identifier(repository)
  if (repository.name && repository.name !== label) return repository.name
  if (!remoteLabel(repository.remote_url) && repository.path && repository.path !== label) return repository.path
  return ''
}

const repositories = computed(() =>
  [...store.repositories].sort((a, b) => identifier(a).localeCompare(identifier(b), undefined, { sensitivity: 'base' }))
)

async function loadRepositories() {
  loadingRepositories.value = true
  try {
    await store.loadRepositories()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    loadingRepositories.value = false
  }
}

// The select edits the store's own row, so a failure puts the previous value
// back.
async function setPolicy(repository, previous) {
  if (typeof api.repositories?.update !== 'function') return
  savingRepository.value = repository.id
  try {
    const updated = await api.repositories.update(repository.id, { review_scan: repository.review_scan })
    repository.review_scan = updated.review_scan
  } catch (e) {
    repository.review_scan = previous
    store.notify(e.message, true)
  } finally {
    savingRepository.value = ''
  }
}

watch(
  () => props.overrides,
  (overrides) => {
    form.github_login = overrides.github_login ?? ''
    // Only show a detected value when the user has not overridden it.
    detectedLogin.value = overrides.github_login ? '' : props.effective?.github_login || ''
    form.review_scan_default = overrides.review_scan_default ?? 'include'
    cache.interval = overrides[CACHE_INTERVAL_KEY] ?? ''
  },
  { immediate: true }
)

watch(
  () => props.active,
  (active) => {
    if (active) loadRepositories()
  }
)

onMounted(loadRepositories)

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

async function saveDefault() {
  savingDefault.value = true
  try {
    await api.settings.update({ review_scan_default: form.review_scan_default })
    savedDefault.value = true
    clearTimeout(defaultSavedTimer)
    defaultSavedTimer = setTimeout(() => (savedDefault.value = false), 1500)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    savingDefault.value = false
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
        caller: every page reads the cache, so this is how fresh the GitHub pages are. The review scan runs after each
        pass that refreshed a repository. A duration such as <code>15m</code>, <code>1h</code> or <code>1d</code>; leave
        it blank to stop refreshing the cache.
      </p>
    </div>

    <div class="field">
      <label>
        Repositories with no policy of their own
        <span v-if="savingDefault" class="faint">saving…</span>
        <span v-else-if="savedDefault" class="faint">saved</span>
      </label>
      <select v-model="form.review_scan_default" class="select" @change="saveDefault">
        <option value="include">Include: scan every repository except the excluded ones</option>
        <option value="exclude">Exclude: scan only the repositories marked include</option>
      </select>
      <p class="faint" style="margin: 4px 0 0">
        Which repositories the review scan considers. Leave a repository on <strong>Default</strong> to follow this
        choice; <strong>Include</strong> and <strong>Exclude</strong> override it for that repository.
      </p>
    </div>

    <div class="field">
      <label>Repositories</label>
      <div
        v-for="repository in repositories"
        :key="repository.id"
        class="row"
        style="justify-content: space-between; align-items: center; margin-bottom: 6px"
      >
        <span>
          {{ identifier(repository) }}
          <span v-if="secondaryLabel(repository)" class="faint"> · {{ secondaryLabel(repository) }}</span>
        </span>
        <span class="row" style="gap: 8px; align-items: center">
          <span v-if="savingRepository === repository.id" class="spinner" aria-hidden="true"></span>
          <select
            v-model="repository.review_scan"
            class="select"
            style="width: auto"
            :aria-label="`Review scan for ${identifier(repository)}`"
            @change="setPolicy(repository, $event.target.dataset.previous)"
            @focus="$event.target.dataset.previous = repository.review_scan"
          >
            <option v-for="policy in POLICIES" :key="policy.value" :value="policy.value">
              {{ policy.label }}
            </option>
          </select>
        </span>
      </div>
      <p v-if="loadingRepositories" class="faint" style="margin: 0">
        <span class="spinner" aria-hidden="true"></span>
      </p>
      <p v-else-if="!repositories.length" class="faint" style="margin: 0">
        No repositories are registered yet. Add one under <router-link to="/repositories">Repositories</router-link>.
      </p>
    </div>
  </section>
</template>
