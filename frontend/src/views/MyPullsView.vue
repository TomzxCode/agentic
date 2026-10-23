<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import SearchSelect from '../components/SearchSelect.vue'
import {
  ciLabel,
  ciTone,
  CI_FILTERS,
  groupPulls,
  matchesCiFilter,
  matchesPullSearch,
  matchesReviewFilter,
  matchesThreadFilter,
  needsAttention,
  PULL_GROUPINGS,
  pullCounts,
  pullFilterCounts,
  reviewLabel,
  REVIEW_FILTERS,
  reviewTone,
  sortPulls,
  THREAD_FILTERS
} from '../myPulls'
import { parseRemote, personLink } from '../repositories/parse'
import { matchesRepositoryFilter, repositoriesWithCounts } from '../reviews'
import { formatDateTime, store, timeAgo } from '../store'

// My PRs: the open pull requests the GitHub login in Settings authored, read
// from one GraphQL search per load. Each row carries the four things that decide
// whether the pull request is moving: its check rollup, its review decision, who
// approved it, and how many review threads are still open.

const report = ref({ login: '', pulls: [], counts: {}, error: null })
const loading = ref(true)
const error = ref(false)
const search = ref('')

// The filters: one active value per facet, each an empty string for "Any", plus
// the repository multi-select (an empty list means every repository). They are
// per-visit like the search box, since they narrow what the loaded list shows
// rather than change how the page is laid out.
const ciFilter = ref('')
const reviewFilter = ref('')
const threadFilter = ref('')
const repositoryFilter = ref([])

// How the rows are split into sections. It is a per-device view preference,
// remembered in localStorage like the feedback page's grouping, so leaving the
// page and coming back keeps it.
const GROUP_KEY = 'agentic.myPullsGroupBy'

// The stored grouping, falling back to the flat list when nothing (or something
// no longer offered) is stored.
function readStoredGrouping() {
  try {
    const stored = localStorage.getItem(GROUP_KEY) || ''
    return PULL_GROUPINGS.some((option) => option.value === stored) ? stored : ''
  } catch {
    // Storage can be blocked (private mode); the flat list still applies.
    return ''
  }
}

const groupBy = ref(readStoredGrouping())

watch(groupBy, (value) => {
  try {
    localStorage.setItem(GROUP_KEY, value)
  } catch {
    // Not fatal: the grouping still applies for this session.
  }
})

// The list in display order, what the search and filters keep of it, and those
// rows split into the sections the grouping asks for.
const pulls = computed(() => sortPulls(report.value.pulls || []))
const filtered = computed(() =>
  pulls.value.filter(
    (pull) =>
      matchesPullSearch(pull, search.value) &&
      matchesRepositoryFilter(pull, repositoryFilter.value) &&
      matchesCiFilter(pull, ciFilter.value) &&
      matchesReviewFilter(pull, reviewFilter.value) &&
      matchesThreadFilter(pull, threadFilter.value)
  )
)
const groups = computed(() => groupPulls(filtered.value, groupBy.value))
// The header's totals, over the whole list rather than the search result.
const counts = computed(() => pullCounts(pulls.value))
// How many pull requests each filter option would show, over the whole list, so
// a chip states what it is worth rather than what the other filters left.
const filterCounts = computed(() => pullFilterCounts(pulls.value))
// The repositories to offer, with their row counts, over the whole list. This is
// the same multi-select the review queue uses, so it reads its options the same
// way.
const repositories = computed(() => repositoriesWithCounts(pulls.value))
const repositoryOptions = computed(() =>
  repositories.value.map((repository) => ({
    value: repository.value,
    label: `${repository.value} (${repository.count})`
  }))
)

function filterCount(facet, value) {
  if (!value) return pulls.value.length
  return filterCounts.value[facet]?.[value] || 0
}

// Whether anything narrows the list, so the empty state can offer one button
// that clears it all instead of naming each control.
const filtering = computed(() =>
  Boolean(search.value || repositoryFilter.value.length || ciFilter.value || reviewFilter.value || threadFilter.value)
)

function clearFilters() {
  search.value = ''
  repositoryFilter.value = []
  ciFilter.value = ''
  reviewFilter.value = ''
  threadFilter.value = ''
}

// What the empty state says: the search text, the repositories, the filters, or
// a combination of them.
const emptyMessage = computed(() => {
  const narrowed = Boolean(ciFilter.value || reviewFilter.value || threadFilter.value)
  if (search.value && (narrowed || repositoryFilter.value.length)) {
    return `No pull requests match “${search.value}” with the selected filters.`
  }
  if (search.value) return `No pull requests match “${search.value}”.`
  if (repositoryFilter.value.length) {
    return `No pull requests in ${repositoryFilter.value.join(', ')}.`
  }
  return 'No pull requests match the selected filters.'
})

// The three filter rows, built here because the template cannot carry a ref: the
// array holds the row's active value and the setter that picks another.
const filterRows = computed(() => [
  { key: 'ci', label: 'CI', options: CI_FILTERS, active: ciFilter.value, pick: (value) => (ciFilter.value = value) },
  {
    key: 'review',
    label: 'Review',
    options: REVIEW_FILTERS,
    active: reviewFilter.value,
    pick: (value) => (reviewFilter.value = value)
  },
  {
    key: 'threads',
    label: 'Threads',
    options: THREAD_FILTERS,
    active: threadFilter.value,
    pick: (value) => (threadFilter.value = value)
  }
])

// Registered repositories keyed by their lowercased "owner/name", so a pull
// request can link to its repository page when the app tracks it.
const repositoryIds = computed(() => {
  const map = new Map()
  for (const repository of store.repositories) {
    const remote = parseRemote(repository.remote_url)
    if (remote) map.set(`${remote.owner}/${remote.repo}`.toLowerCase(), repository.id)
  }
  return map
})

// The id of the registered repository matching a pull request's repository, or
// null when the app does not track it.
function repositoryLink(repository) {
  return repositoryIds.value.get(String(repository || '').toLowerCase()) || null
}

// Where a GitHub login links: the person carrying it as an alias, or the
// prefilled person-creation page when nobody does yet (rendered grey).
function personLinkFor(login) {
  return personLink(store.people, login)
}

// A thread cell's tooltip: how many of the pull request's threads are still
// open, which the cell shows as "open / total".
function threadTitle(pull) {
  const open = Number(pull.open_threads) || 0
  const total = Number(pull.threads_total) || 0
  if (!total) return 'No review threads'
  return `${open} of ${total} review thread${total === 1 ? '' : 's'} still open`
}

async function load(refresh = false) {
  loading.value = true
  error.value = false
  try {
    // The people directory resolves an approver to a person page, and the
    // repositories resolve a pull request's repository to its page.
    await store.loadPeople().catch(() => {})
    await store.loadRepositories().catch(() => {})
    report.value = await api.myPulls.list({ refresh })
    // Drop any selected repository the refreshed list no longer carries, so the
    // control never filters on something it cannot show as selected.
    const known = new Set(repositories.value.map((repository) => repository.value.toLowerCase()))
    repositoryFilter.value = repositoryFilter.value.filter((value) => known.has(String(value).toLowerCase()))
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="my-pulls">
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 4px">
      <h1>My PRs</h1>
      <span class="row" style="gap: 8px; align-items: center">
        <span v-if="!loading && !error && !report.error" class="faint">
          {{ counts.total }} open · {{ counts.attention }} need attention · {{ counts.approved }} approved ·
          {{ counts.openThreads }} open thread{{ counts.openThreads === 1 ? '' : 's' }}
        </span>
        <button
          class="btn sm ghost"
          :disabled="loading"
          title="Re-read your pull requests from GitHub"
          @click="load(true)"
        >
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          Refresh
        </button>
      </span>
    </div>
    <p v-if="report.login" class="faint my-pulls-root">
      Open pull requests authored by <code>{{ report.login }}</code
      >.
    </p>

    <div v-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load your pull requests.</p>
      <button class="btn" @click="load(true)">Retry</button>
    </div>

    <div v-else-if="report.error" class="panel">
      <p style="margin-top: 0">{{ report.error }}</p>
      <button class="btn sm ghost" @click="load(true)">Retry</button>
    </div>

    <div v-else-if="loading && !pulls.length" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="!pulls.length" class="empty">You have no open pull requests.</div>

    <template v-else>
      <div class="my-pulls-filters">
        <input
          v-model="search"
          class="input my-pulls-search"
          type="search"
          placeholder="Search repository, number, title, or approver…"
          aria-label="Search my pull requests"
        />
        <SearchSelect
          v-model="repositoryFilter"
          class="my-pulls-repository-select"
          multiple
          bulk-actions
          :sort="false"
          :options="repositoryOptions"
          placeholder="All repositories"
          title="Filter by one or more repositories"
        />
        <label class="faint my-pulls-group-by">
          Group by
          <select v-model="groupBy" class="select my-pulls-group-select" aria-label="Group my pull requests by">
            <option v-for="option in PULL_GROUPINGS" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
      </div>

      <div class="my-pulls-filter-groups">
        <div
          v-for="facet in filterRows"
          :key="facet.key"
          class="my-pulls-filter-row"
          role="group"
          :aria-label="`Filter by ${facet.label.toLowerCase()}`"
        >
          <span class="faint my-pulls-filter-label">{{ facet.label }}</span>
          <button
            v-for="option in facet.options"
            :key="option.value"
            class="my-pulls-chip"
            :class="{ active: facet.active === option.value }"
            :aria-pressed="facet.active === option.value"
            @click="facet.pick(option.value)"
          >
            {{ option.label }} <span class="count">{{ filterCount(facet.key, option.value) }}</span>
          </button>
        </div>
      </div>

      <div v-if="!filtered.length" class="empty">
        {{ emptyMessage }}
        <button v-if="filtering" class="btn sm ghost" @click="clearFilters">Clear filters</button>
      </div>

      <div v-else class="my-pulls-groups">
        <section v-for="group in groups" :key="group.key" class="my-pulls-group">
          <h2 v-if="group.label" class="group-head my-pulls-group-head">
            <span v-if="group.badge" class="badge" :class="group.tone">{{ group.label }}</span>
            <span v-else>{{ group.label }}</span>
            <span class="faint my-pulls-group-count">{{ group.pulls.length }}</span>
          </h2>
          <div class="my-pulls-table-wrap">
            <table class="my-pulls-table">
              <thead>
                <tr>
                  <th>PR</th>
                  <th>CI</th>
                  <th>Review</th>
                  <th>Approvers</th>
                  <th>Threads</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="pull in group.pulls"
                  :key="`${pull.repository}#${pull.number}`"
                  :class="{ 'needs-attention': needsAttention(pull) }"
                >
                  <td class="my-pulls-pr-cell">
                    <a
                      class="my-pulls-link"
                      :href="pull.url"
                      target="_blank"
                      rel="noopener"
                      :title="`Open #${pull.number} on GitHub`"
                      >#{{ pull.number }}</a
                    >
                    <span v-if="pull.draft" class="badge st-draft">draft</span>
                    <!-- The heading already names the repository when the list is
                         grouped by it, so the row does not repeat it. -->
                    <template v-if="groupBy !== 'repository'">
                      <router-link
                        v-if="repositoryLink(pull.repository)"
                        class="my-pulls-repository"
                        :to="`/repositories/${repositoryLink(pull.repository)}`"
                        :title="`Open ${pull.repository} in the app`"
                        >{{ pull.repository }}</router-link
                      >
                      <span v-else class="my-pulls-repository faint">{{ pull.repository }}</span>
                    </template>
                    <span class="my-pulls-title" :title="pull.title">{{ pull.title }}</span>
                  </td>
                  <td>
                    <span class="badge" :class="ciTone(pull)">{{ ciLabel(pull) }}</span>
                  </td>
                  <td>
                    <span class="badge" :class="reviewTone(pull)">{{ reviewLabel(pull) }}</span>
                  </td>
                  <td class="my-pulls-approvers">
                    <span v-if="pull.approvers.length" class="my-pulls-approvers-label faint">approved by </span>
                    <template v-if="pull.approvers.length">
                      <template v-for="(login, index) in pull.approvers" :key="login">
                        <span v-if="index" class="faint">, </span>
                        <router-link
                          v-if="personLinkFor(login)"
                          :to="personLinkFor(login).path"
                          :class="{ faint: personLinkFor(login).missing }"
                          >{{ login }}</router-link
                        >
                        <span v-else>{{ login }}</span>
                      </template>
                    </template>
                    <span v-else class="faint">—</span>
                  </td>
                  <td class="my-pulls-threads" :title="threadTitle(pull)">
                    <span :class="{ 'my-pulls-threads-open': pull.open_threads > 0 }"
                      >{{ pull.open_threads }} open</span
                    >
                  </td>
                  <td class="faint">
                    <span v-if="pull.updated_at" class="mono" :title="formatDateTime(pull.updated_at)">{{
                      timeAgo(pull.updated_at)
                    }}</span>
                    <span v-else>—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>
