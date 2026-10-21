<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { store, timeAgo } from '../store'

// The "Diagnostics" settings section: which external commands the app runs,
// whether each is on PATH, and what version it reports, followed by what the
// ghx and slackx local caches hold. Read-only; the probes run on the server, so
// opening the section is what refreshes them.
const props = defineProps({
  active: { type: Boolean, default: false }
})

const GROUPS = [
  { category: 'runtime', label: 'Runtime' },
  { category: 'tool', label: 'Helper tools' },
  { category: 'harness', label: 'Agent harnesses' }
]

const EMPTY_GHX_CACHE = { available: false, error: null, repositories: [] }
const EMPTY_SLACKX_CACHE = {
  available: false,
  error: null,
  workspace: null,
  db_path: null,
  channel_count: 0,
  user_count: 0,
  thread_count: 0,
  message_count: 0,
  read_marker_count: 0,
  channels_updated_at: null,
  users_updated_at: null,
  threads_updated_at: null
}

const dependencies = ref([])
const ghxCache = ref({ ...EMPTY_GHX_CACHE })
const slackxCache = ref({ ...EMPTY_SLACKX_CACHE })
const checkedAt = ref(null)
const loading = ref(false)
const loaded = ref(false)

const grouped = computed(() =>
  GROUPS.map((group) => ({
    ...group,
    items: dependencies.value.filter((dependency) => dependency.category === group.category)
  })).filter((group) => group.items.length > 0)
)

const installed = computed(() => dependencies.value.filter((dependency) => dependency.present))
const missing = computed(() => dependencies.value.filter((dependency) => !dependency.present))

const cachedRepositories = computed(() => ghxCache.value.repositories || [])
const staleRepositories = computed(() => cachedRepositories.value.filter((repository) => repository.status === 'stale'))
const cachedItemCount = computed(() =>
  cachedRepositories.value.reduce((total, repository) => total + repository.issues + repository.pull_requests, 0)
)

// A cache table row's "last updated": when the entity was refreshed, or a dash
// when slackx records no timestamp for it.
function updatedLabel(iso) {
  return iso ? timeAgo(iso) : '—'
}

// A ghx hit rate, rendered the way the CLI prints it: the percentage followed
// by the number of retrievals it is computed over, or a dash when ghx recorded
// a retrieval of that kind.
function hitRateLabel(rate) {
  if (!rate || rate.percent === null || rate.percent === undefined) return '—'
  return `${rate.percent}% (${rate.retrievals})`
}

async function load() {
  loading.value = true
  try {
    const report = await api.settings.diagnostics()
    dependencies.value = report.dependencies || []
    ghxCache.value = report.ghx_cache || { ...EMPTY_GHX_CACHE }
    slackxCache.value = report.slackx_cache || { ...EMPTY_SLACKX_CACHE }
    checkedAt.value = report.checked_at || null
    loaded.value = true
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

// Only probe when the section is opened: version checks spawn each command, so
// visiting another Settings section should not pay for them.
watch(
  () => props.active,
  (active) => {
    if (active) load()
  },
  { immediate: true }
)
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Diagnostics</h2>
      <button class="btn sm" :disabled="loading" @click="load">
        <span v-if="loading" class="spinner" aria-hidden="true"></span>
        Recheck
      </button>
    </div>
    <p class="faint" style="margin-top: 0">
      External commands Agentic runs and the version each one reports, then what the ghx and slackx caches hold. A
      missing optional tool only disables its integration; a missing required tool breaks the feature named beside it.
    </p>
    <p v-if="checkedAt" class="faint">
      Checked {{ timeAgo(checkedAt) }} · {{ installed.length }} of {{ dependencies.length }} available
      <span v-if="missing.length"> · {{ missing.length }} missing</span>
    </p>

    <div v-for="group in grouped" :key="group.category" style="margin-bottom: 16px">
      <h3>{{ group.label }}</h3>
      <div v-for="dependency in group.items" :key="dependency.id" class="item">
        <div class="item-top">
          <span class="title">{{ dependency.name }}</span>
          <span class="badge" :class="dependency.present ? 'ok' : 'danger'">
            {{ dependency.present ? 'installed' : 'missing' }}
          </span>
          <span v-if="dependency.required" class="badge">required</span>
        </div>
        <div class="item-top" style="margin-top: 6px">
          <span class="faint grow">{{ dependency.purpose }}</span>
          <span v-if="dependency.version" class="mono">{{ dependency.version }}</span>
          <span v-else-if="dependency.present" class="faint">no version reported</span>
        </div>
        <div v-if="dependency.path" class="faint mono" style="font-size: 11px">{{ dependency.path }}</div>
        <div v-if="dependency.error" style="color: var(--danger); font-size: 12px">{{ dependency.error }}</div>
      </div>
    </div>

    <div style="margin-bottom: 16px">
      <h3 style="margin-bottom: 6px">ghx cache</h3>
      <p v-if="!ghxCache.available" class="faint" style="margin-top: 0">
        ghx is not installed, so there is no cache to read.
      </p>
      <p v-else-if="ghxCache.error" class="faint" style="margin-top: 0; color: var(--danger)">
        {{ ghxCache.error }}
      </p>
      <template v-else>
        <p class="faint" style="margin-top: 0">
          {{ cachedRepositories.length }} repositories · {{ cachedItemCount }} issues and PRs ·
          {{ staleRepositories.length }} stale
        </p>
        <p v-if="cachedRepositories.length" class="faint" style="margin-top: 0">
          Hit rates are per retrieval operation, with the number of retrievals in parentheses; a dash means none
          recorded.
        </p>
        <div v-if="cachedRepositories.length" class="diagnostics-table-wrap">
          <table class="diagnostics-table">
            <thead>
              <tr>
                <th>Repository</th>
                <th class="num">Issues</th>
                <th class="num">PRs</th>
                <th>Cached</th>
                <th>Status</th>
                <th class="num">Issue list</th>
                <th class="num">Issue view</th>
                <th class="num">PR list</th>
                <th class="num">PR view</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="repository in cachedRepositories" :key="repository.repository">
                <td class="mono">{{ repository.repository }}</td>
                <td class="num">{{ repository.issues }}</td>
                <td class="num">{{ repository.pull_requests }}</td>
                <td>{{ repository.cached_age || '—' }}</td>
                <td class="faint">{{ repository.status }}</td>
                <td class="num">{{ hitRateLabel(repository.issue_list) }}</td>
                <td class="num">{{ hitRateLabel(repository.issue_view) }}</td>
                <td class="num">{{ hitRateLabel(repository.pr_list) }}</td>
                <td class="num">{{ hitRateLabel(repository.pr_view) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="faint">No repositories cached.</p>
      </template>
    </div>

    <div style="margin-bottom: 16px">
      <h3 style="margin-bottom: 6px">slackx cache</h3>
      <p v-if="!slackxCache.available" class="faint" style="margin-top: 0">
        slackx is not installed, so there is no cache to read.
      </p>
      <p v-else-if="slackxCache.error" class="faint" style="margin-top: 0; color: var(--danger)">
        {{ slackxCache.error }}
      </p>
      <template v-else>
        <p v-if="slackxCache.workspace || slackxCache.db_path" class="faint mono" style="margin-top: 0">
          <span v-if="slackxCache.workspace">workspace {{ slackxCache.workspace }}</span>
          <span v-if="slackxCache.workspace && slackxCache.db_path"> · </span>
          <span v-if="slackxCache.db_path">{{ slackxCache.db_path }}</span>
        </p>
        <div class="diagnostics-table-wrap">
          <table class="diagnostics-table">
            <thead>
              <tr>
                <th>Entity</th>
                <th class="num">Count</th>
                <th>Last updated</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Channels</td>
                <td class="num">{{ slackxCache.channel_count }}</td>
                <td class="faint">{{ updatedLabel(slackxCache.channels_updated_at) }}</td>
              </tr>
              <tr>
                <td>Users</td>
                <td class="num">{{ slackxCache.user_count }}</td>
                <td class="faint">{{ updatedLabel(slackxCache.users_updated_at) }}</td>
              </tr>
              <tr>
                <td>Threads</td>
                <td class="num">{{ slackxCache.thread_count }}</td>
                <td class="faint">{{ updatedLabel(slackxCache.threads_updated_at) }}</td>
              </tr>
              <tr>
                <td>Messages</td>
                <td class="num">{{ slackxCache.message_count }}</td>
                <td class="faint">—</td>
              </tr>
              <tr>
                <td>Read markers</td>
                <td class="num">{{ slackxCache.read_marker_count }}</td>
                <td class="faint">—</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

    <p v-if="loaded && dependencies.length === 0" class="faint">No dependencies reported.</p>
  </section>
</template>
