<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { remoteLabel } from '../repositories/parse'
import { store, timeAgo } from '../store'

// The "Review requests" settings section: the background scan that asks GitHub
// which pull requests await a review, how often it runs, and which repositories
// it considers. The page shell supplies the raw overrides/defaults and whether
// this section is showing, so the status loads when it is opened.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) },
  active: { type: Boolean, default: false }
})

// A repository's own opinion, or "default" to follow the app-wide choice below.
const POLICIES = [
  { value: 'default', label: 'Default' },
  { value: 'include', label: 'Include' },
  { value: 'exclude', label: 'Exclude' }
]

const form = reactive({ review_scan_interval: '', review_scan_default: 'include' })
const status = ref(null)
const loading = ref(false)
const saving = ref('')
const saved = ref('')
const scanning = ref(false)
const savingRepository = ref('')
let savedTimer

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

async function load() {
  loading.value = true
  try {
    await store.loadRepositories().catch(() => {})
    // Best effort: a backend without the endpoint simply shows no status.
    if (typeof api.reviews?.scan === 'function') status.value = await api.reviews.scan()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function save(key) {
  saving.value = key
  try {
    await api.settings.update({ [key]: form[key] })
    saved.value = key
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = ''), 1500)
    status.value = await api.reviews.scan().catch(() => status.value)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    saving.value = ''
  }
}

// The scan runs in the request, so a big result set can take a moment.
async function scanNow() {
  if (scanning.value || typeof api.reviews?.runScan !== 'function') return
  scanning.value = true
  try {
    status.value = await api.reviews.runScan()
    if (status.value.error) store.notify(status.value.error, true)
    else store.notify(`Scan found ${status.value.found}, kept ${status.value.kept}`)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    scanning.value = false
  }
}

// A repository saves its policy on change. The select edits the store's own row,
// so a failure puts the previous value back.
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
    form.review_scan_interval = overrides.review_scan_interval ?? ''
    form.review_scan_default = overrides.review_scan_default ?? 'include'
  },
  { immediate: true }
)

watch(
  () => props.active,
  (active) => {
    if (active) load()
  }
)

onMounted(load)
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Review requests</h2>
      <button class="btn sm" :disabled="scanning" @click="scanNow">
        <span v-if="scanning" class="spinner" aria-hidden="true"></span>
        Scan now
      </button>
    </div>
    <p class="faint" style="margin-top: 0">
      A background scan asks GitHub which pull requests await your review: those with a review requested from you, and
      the open ones you have already reviewed. They join the
      <router-link to="/reviews">review queue</router-link> even before a review report exists for them. Discovery runs
      through <code>gh</code>, so the GitHub CLI must be installed and authenticated.
    </p>

    <div class="field">
      <label>
        How often to scan
        <span v-if="saving === 'review_scan_interval'" class="faint">saving…</span>
        <span v-else-if="saved === 'review_scan_interval'" class="faint">saved</span>
      </label>
      <input
        v-model="form.review_scan_interval"
        class="input mono"
        :placeholder="defaults.review_scan_interval || '1h'"
        @blur="save('review_scan_interval')"
      />
      <p class="faint" style="margin: 4px 0 0">
        A duration such as <code>30m</code>, <code>1h</code> or <code>1d</code>. Leave it blank to stop scanning.
      </p>
      <p class="faint" style="margin: 4px 0 0">
        Last scan:
        <template v-if="status?.last_run_at">
          {{ timeAgo(status.last_run_at) }} · {{ status.found }} found, {{ status.kept }} kept
          <span v-if="status.origin === 'manual'"> · run by hand</span>
        </template>
        <template v-else>never</template>
        <span v-if="status && !status.enabled"> · scanning is off</span>
        <span v-else-if="status?.stored"> · {{ status.stored }} in the queue</span>
      </p>
      <p v-if="status?.error" style="margin: 4px 0 0; color: var(--danger)">{{ status.error }}</p>
    </div>

    <div class="field">
      <label>Repositories with no policy of their own</label>
      <select v-model="form.review_scan_default" class="select" @change="save('review_scan_default')">
        <option value="include">Include: scan every repository except the excluded ones</option>
        <option value="exclude">Exclude: scan only the repositories marked include</option>
      </select>
    </div>

    <div class="field">
      <label>Repositories</label>
      <p class="faint" style="margin: 0 0 8px">
        Leave a repository on <strong>Default</strong> to follow the choice above. <strong>Include</strong> and
        <strong>Exclude</strong> override it for that repository.
      </p>
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
      <p v-if="loading" class="faint" style="margin: 0"><span class="spinner" aria-hidden="true"></span></p>
      <p v-else-if="!repositories.length" class="faint" style="margin: 0">
        No repositories are registered yet. Add one under <router-link to="/repositories">Repositories</router-link>.
      </p>
    </div>
  </section>
</template>
