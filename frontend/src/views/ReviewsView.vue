<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import {
  approvedFilterCount,
  commitUrl,
  draftFilterCount,
  groupQueueByRepository,
  isApproved,
  isReviewedByMe,
  KIND_FILTER_LABELS,
  KIND_FILTER_STATES,
  matchesApprovedFilter,
  matchesAuthorFilter,
  matchesDraftFilter,
  matchesQueueSearch,
  matchesRepositoryFilter,
  matchesReviewedFilter,
  matchesStateFilter,
  nextKindFilter,
  PR_STATE_FILTERS,
  QUEUE_STEPS,
  queueAuthors,
  repositoriesWithCounts,
  READINESS_LIGHTS,
  READINESS_TITLES,
  REQUEST_SOURCE_BADGES,
  reviewedFilterCount,
  riskTone,
  runningStep,
  shortCommit,
  stateFilterCounts,
  stripReportMarker,
  verdictLabel,
  verdictTone
} from '../reviews'
import { store, timeAgo, formatDateTime } from '../store'
import { ghxItemUrl } from '../toolLinks'
import { parseRemote, personLink } from '../repositories/parse'
import SearchSelect from '../components/SearchSelect.vue'

// The review queue: every pull request with review reports in the user-global
// store the review skills write to, one row per PR with a column per review
// step. This is what the review_requested_prs orchestrator prints, read from the
// store and the PRs the app tracks instead of a live GitHub discovery.

const queue = ref({ root: null, prs: [], counts: {} })
const loading = ref(true)
const error = ref(false)
// The PR whose task is being created, so its button shows a spinner.
const creatingKey = ref('')

// The filters: a PR's status (open by default, so the queue shows the pull
// requests still awaiting a review), one or more repositories, one or more
// authors, the state of the draft filter ("hidden" by default, since a draft
// is not ready for review), the same three states for approved pull requests
// (also hidden by default, since they no longer await a review) and for ones
// the user already reviewed (kept by default, since they may still need a
// follow-up), and a text search over the row's fields.
//
// They are per-device view preferences, remembered in localStorage like the
// feedback page's grouping, so leaving the page and coming back keeps them.
const FILTERS_KEY = 'agentic.reviewQueueFilters'

// A stored kind filter's state. Values stored before the filter had three
// states carry a boolean instead, where true meant "show them alongside the
// rest", so they migrate to "all". Anything else falls back to *fallback*.
function readKindFilter(stored, legacyInclude, fallback = 'hide') {
  if (KIND_FILTER_STATES.includes(stored)) return stored
  return legacyInclude === true ? 'all' : fallback
}

// The stored filters, with anything malformed or no longer offered falling back
// to its default rather than breaking the page.
function readStoredFilters() {
  const defaults = {
    state: 'open',
    repositories: [],
    authors: [],
    draftsFilter: 'hide',
    approvedFilter: 'hide',
    reviewedFilter: 'all',
    search: ''
  }
  try {
    const stored = JSON.parse(localStorage.getItem(FILTERS_KEY) || 'null')
    if (!stored || typeof stored !== 'object') return defaults
    return {
      state: PR_STATE_FILTERS.some((option) => option.value === stored.state) ? stored.state : defaults.state,
      repositories: Array.isArray(stored.repositories) ? stored.repositories.map(String) : [],
      authors: Array.isArray(stored.authors) ? stored.authors.map(String) : [],
      draftsFilter: readKindFilter(stored.draftsFilter, stored.includeDrafts, defaults.draftsFilter),
      approvedFilter: readKindFilter(stored.approvedFilter, stored.includeApproved, defaults.approvedFilter),
      reviewedFilter: readKindFilter(stored.reviewedFilter, undefined, defaults.reviewedFilter),
      search: typeof stored.search === 'string' ? stored.search : ''
    }
  } catch {
    // Storage can be blocked (private mode), and a stored value can be corrupt;
    // the defaults still apply for this session.
    return defaults
  }
}

const storedFilters = readStoredFilters()

const stateFilter = ref(storedFilters.state)
const repositoryFilter = ref(storedFilters.repositories)
const authorFilter = ref(storedFilters.authors)
const draftsFilter = ref(storedFilters.draftsFilter)
const approvedFilter = ref(storedFilters.approvedFilter)
const reviewedFilter = ref(storedFilters.reviewedFilter)
const search = ref(storedFilters.search)

// Write the filters back as they change: a choice, a clear from the empty
// state, or a value the refreshed queue dropped all land here.
watch(
  [stateFilter, repositoryFilter, authorFilter, draftsFilter, approvedFilter, reviewedFilter, search],
  () => {
    try {
      localStorage.setItem(
        FILTERS_KEY,
        JSON.stringify({
          state: stateFilter.value,
          repositories: repositoryFilter.value,
          authors: authorFilter.value,
          draftsFilter: draftsFilter.value,
          approvedFilter: approvedFilter.value,
          reviewedFilter: reviewedFilter.value,
          search: search.value
        })
      )
    } catch {
      // Not fatal: the filters still apply for this session.
    }
  },
  { deep: true }
)

// Each kind filter cycles hidden -> only -> all on click, so one button carries
// its three states.
function cycleDraftsFilter() {
  draftsFilter.value = nextKindFilter(draftsFilter.value)
}

function cycleApprovedFilter() {
  approvedFilter.value = nextKindFilter(approvedFilter.value)
}

function cycleReviewedFilter() {
  reviewedFilter.value = nextKindFilter(reviewedFilter.value)
}

// Show every pull request from the empty state: every kind filter goes to
// "all", which is the state that keeps every row.
function showEveryPullRequest() {
  draftsFilter.value = 'all'
  approvedFilter.value = 'all'
  reviewedFilter.value = 'all'
}

// What clicking a kind filter's button will do, for its tooltip.
function kindFilterTitle(label, state) {
  if (state === 'hide') return `${label} are hidden; click to show only ${label.toLowerCase()}`
  if (state === 'only') return `Only ${label.toLowerCase()} are shown; click to show everything`
  return `Everything is shown; click to hide ${label.toLowerCase()}`
}

// The report open in the viewer: its PR, its relative store path, and content.
const openPr = ref(null)
const openName = ref('')
const reportContent = ref(null)
const reportLoading = ref(false)
const reportTruncated = ref(false)

const reportHtml = computed(() => renderMarkdown(stripReportMarker(reportContent.value)))
// The rows the filters keep: status, then repository, then author, then drafts,
// then approved pull requests, then the ones the user reviewed, then the search
// text.
const filteredPrs = computed(() =>
  queue.value.prs.filter(
    (pr) =>
      matchesStateFilter(pr, stateFilter.value) &&
      matchesRepositoryFilter(pr, repositoryFilter.value) &&
      matchesAuthorFilter(pr, authorFilter.value) &&
      matchesDraftFilter(pr, draftsFilter.value) &&
      matchesApprovedFilter(pr, approvedFilter.value) &&
      matchesReviewedFilter(pr, reviewedFilter.value) &&
      matchesQueueSearch(pr, search.value)
  )
)
const groups = computed(() => groupQueueByRepository(filteredPrs.value))
// Per-status counts for the filter chips, over the whole queue.
const stateCounts = computed(() => stateFilterCounts(queue.value.prs))
// How many drafts the queue holds, for the drafts toggle.
const draftCount = computed(() => draftFilterCount(queue.value.prs))
// How many approved pull requests the queue holds, for the approved toggle.
const approvedCount = computed(() => approvedFilterCount(queue.value.prs))
// How many pull requests the user already reviewed, for the reviewed toggle.
const reviewedCount = computed(() => reviewedFilterCount(queue.value.prs))
// The drafts the other filters would keep while drafts are hidden, so the empty
// state can name them and offer to show them instead of blaming the status or
// the search. The approved and reviewed filters still apply: a row they hide is
// not one this offers.
const hiddenDrafts = computed(() =>
  draftsFilter.value !== 'hide'
    ? []
    : queue.value.prs.filter(
        (pr) =>
          pr.draft &&
          matchesStateFilter(pr, stateFilter.value) &&
          matchesRepositoryFilter(pr, repositoryFilter.value) &&
          matchesAuthorFilter(pr, authorFilter.value) &&
          matchesApprovedFilter(pr, approvedFilter.value) &&
          matchesReviewedFilter(pr, reviewedFilter.value) &&
          matchesQueueSearch(pr, search.value)
      )
)
// The approved pull requests the other filters would keep while approved ones
// are hidden, so the empty state can offer to show them instead of blaming the
// search or the repository. The draft and reviewed filters still apply.
const hiddenApproved = computed(() =>
  approvedFilter.value !== 'hide'
    ? []
    : queue.value.prs.filter(
        (pr) =>
          isApproved(pr) &&
          matchesStateFilter(pr, stateFilter.value) &&
          matchesRepositoryFilter(pr, repositoryFilter.value) &&
          matchesAuthorFilter(pr, authorFilter.value) &&
          matchesDraftFilter(pr, draftsFilter.value) &&
          matchesReviewedFilter(pr, reviewedFilter.value) &&
          matchesQueueSearch(pr, search.value)
      )
)
// The pull requests the user already reviewed that the other filters would keep
// while reviewed ones are hidden. The draft and approved filters still apply.
const hiddenReviewed = computed(() =>
  reviewedFilter.value !== 'hide'
    ? []
    : queue.value.prs.filter(
        (pr) =>
          isReviewedByMe(pr) &&
          matchesStateFilter(pr, stateFilter.value) &&
          matchesRepositoryFilter(pr, repositoryFilter.value) &&
          matchesAuthorFilter(pr, authorFilter.value) &&
          matchesDraftFilter(pr, draftsFilter.value) &&
          matchesApprovedFilter(pr, approvedFilter.value) &&
          matchesQueueSearch(pr, search.value)
      )
)
// The repositories to offer, with their row counts, over the whole queue.
const repositories = computed(() => repositoriesWithCounts(queue.value.prs))
// The repository dropdown's options, each carrying its row count.
const repositoryOptions = computed(() =>
  repositories.value.map((repository) => ({
    value: repository.value,
    label: `${repository.value} (${repository.count})`
  }))
)
// The authors to offer, with their row counts, over the whole queue.
const authors = computed(() => queueAuthors(queue.value.prs))
// The author dropdown's options, each carrying its row count.
const authorOptions = computed(() =>
  authors.value.map((author) => ({ value: author.value, label: `${author.value} (${author.count})` }))
)
// The header's totals, over what the filters show, so they match the table.
const counts = computed(() => ({
  total: filteredPrs.value.length,
  ready: filteredPrs.value.filter((pr) => pr.readiness === 'green').length,
  blocked: filteredPrs.value.filter((pr) => pr.readiness === 'red').length
}))

async function load(refresh = false) {
  loading.value = true
  error.value = false
  try {
    // The people directory resolves a GitHub login to a person page, the
    // registered repositories resolve a store repository to its page, and the
    // tasks resolve a PR's association to its task link.
    await store.loadPeople().catch(() => {})
    await store.loadRepositories().catch(() => {})
    await store.loadTasks().catch(() => {})
    queue.value = await api.reviews.queue({ refresh })
    // Drop any selected repository or author the refreshed queue no longer
    // carries, so a control never filters on something it cannot show as
    // selected.
    const knownRepositories = new Set(repositories.value.map((repository) => repository.value.toLowerCase()))
    repositoryFilter.value = repositoryFilter.value.filter((value) =>
      knownRepositories.has(String(value).toLowerCase())
    )
    const known = new Set(authors.value.map((author) => author.value.toLowerCase()))
    authorFilter.value = authorFilter.value.filter((value) => known.has(String(value).toLowerCase()))
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

// A PR's row key, used to mark which row is creating a task.
function prKey(pr) {
  return `${pr.repository}#${pr.number}`
}

const tasksById = computed(() => Object.fromEntries(store.tasks.map((task) => [task.id, task])))

// The task a PR's tracked item is associated to, or null when there is none.
// The queue carries the task ids; the task itself comes from the store, like
// the repository view resolves its item chips.
function taskFor(pr) {
  const id = (pr.task_ids || [])[0]
  if (!id) return null
  return tasksById.value[id] || { id, title: 'Linked task', status: 'open' }
}

// Turn a PR into a task by importing it, the same way the repository view's
// "New task" does: the backend fetches the PR, fills the task, and links it as
// an item. The row then shows its task link in place of the button.
async function createTaskFrom(pr) {
  if (!pr.url || creatingKey.value) return
  creatingKey.value = prKey(pr)
  try {
    const task = await api.tasks.create({ github_url: pr.url })
    await store.loadTasks()
    await store.loadItems().catch(() => {})
    pr.task_ids = [task.id]
    store.notify('Task created')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    creatingKey.value = ''
  }
}

// Where a GitHub login links: the person carrying it as an alias, or the
// prefilled person-creation page when nobody does yet (rendered grey).
function personLinkFor(login) {
  return personLink(store.people, login)
}

// Registered repositories keyed by their lowercased "owner/name", so a store
// repository can be linked to its page in the app. The store keys by canonical
// casing, which can differ from the remote's.
const repositoryIds = computed(() => {
  const map = new Map()
  for (const repository of store.repositories) {
    const remote = parseRemote(repository.remote_url)
    if (remote) map.set(`${remote.owner}/${remote.repo}`, repository.id)
  }
  return map
})

// The id of the registered repository matching a store repository, or null when
// the app does not track it (there is then nothing in the app to link to).
function repositoryLink(repository) {
  return repositoryIds.value.get(String(repository || '').toLowerCase()) || null
}

// The app's own page for the PR, the row's primary link. It is deliberately not
// GitHub: the queue is where the review work happens, and the app's PR view is
// what runs it.
function pullPath(pr) {
  return `/pr/${pr.repository}/${pr.number}`
}

// The PR's page in the local ghx web UI, when one is configured.
function ghxLink(pr) {
  return ghxItemUrl(pr, store.settings?.ghx_url)
}

// The step state for a column, or null when the step has no report.
function stepFor(pr, key) {
  return pr.steps?.[key] || null
}

function readinessTitle(pr) {
  return READINESS_TITLES[pr.readiness] || ''
}

// Why the review scan put a PR in the queue, when it did. The report store alone
// says nothing about that: a PR can be here only because a review has run.
const SOURCE_TITLES = {
  requested: 'A review is requested from you',
  reviewed: 'You reviewed this pull request and it is still open'
}

function sourceTitle(pr) {
  return SOURCE_TITLES[pr.request_source] || 'Awaiting your review'
}

// The emoji a source reads as, or the raw source when it is one this build does
// not know, so the row still says something.
function sourceBadge(pr) {
  return REQUEST_SOURCE_BADGES[pr.request_source] || pr.request_source
}

// A step cell's tooltip: its verdict, its reviewed commit, and whether it is
// stale (does not cover the newest reviewed commit).
function stepTitle(pr, key, step) {
  const label = QUEUE_STEPS.find((entry) => entry.key === key)?.label || key
  const parts = [label]
  if (step.verdict) parts.push(step.verdict)
  if (step.commit) parts.push(step.stale ? `${shortCommit(step.commit)} (stale)` : shortCommit(step.commit))
  return parts.join(' · ')
}

// A running step's tooltip: when its marker was written.
function runningTitle(pr, key) {
  const marker = runningStep(pr, key)
  const label = QUEUE_STEPS.find((entry) => entry.key === key)?.label || key
  if (!marker) return label
  return marker.started_at ? `${label}: running since ${formatDateTime(marker.started_at)}` : `${label}: running`
}

async function openReport(pr, step) {
  if (!step?.report) return
  openPr.value = pr
  openName.value = step.report
  reportContent.value = null
  reportTruncated.value = false
  reportLoading.value = true
  try {
    const data = await api.reviews.report(pr.repository, pr.number, step.report)
    reportContent.value = data.content
    reportTruncated.value = !!data.truncated
  } catch (e) {
    store.notify(e.message, true)
    openPr.value = null
  } finally {
    reportLoading.value = false
  }
}

function closeReport() {
  openPr.value = null
  openName.value = ''
  reportContent.value = null
}

onMounted(load)
</script>

<template>
  <div class="review-queue">
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 4px">
      <h1>Review queue</h1>
      <span class="row" style="gap: 8px; align-items: center">
        <span v-if="!loading && !error" class="faint">
          {{ counts.total }} PR{{ counts.total === 1 ? '' : 's' }} · {{ counts.ready }} ready ·
          {{ counts.blocked }} blocked
        </span>
        <button class="btn sm ghost" :disabled="loading" title="Re-read the store and GitHub" @click="load(true)">
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          Refresh
        </button>
      </span>
    </div>
    <p v-if="queue.root" class="faint review-root">Reports read from {{ queue.root }}</p>

    <div v-if="!loading && !error && queue.prs.length" class="review-filters">
      <div class="review-state-filters" role="group" aria-label="Filter by pull request status">
        <button
          v-for="option in PR_STATE_FILTERS"
          :key="option.value"
          class="review-state-filter"
          :class="{ active: stateFilter === option.value }"
          :aria-pressed="stateFilter === option.value"
          @click="stateFilter = option.value"
        >
          {{ option.label }} <span class="count">{{ stateCounts[option.value] }}</span>
        </button>
      </div>
      <div class="review-toggle-filters" role="group" aria-label="Filter drafts, approved, and reviewed pull requests">
        <button
          class="review-toggle-filter review-draft-filter"
          :class="{ active: draftsFilter !== 'hide' }"
          :title="kindFilterTitle('Drafts', draftsFilter)"
          :aria-label="`Drafts: ${KIND_FILTER_LABELS[draftsFilter]}, ${draftCount} in the queue`"
          @click="cycleDraftsFilter"
        >
          Drafts <span class="count">{{ draftCount }}</span>
          <span class="state"> {{ KIND_FILTER_LABELS[draftsFilter] }}</span>
        </button>
        <button
          class="review-toggle-filter review-approved-filter"
          :class="{ active: approvedFilter !== 'hide' }"
          :title="kindFilterTitle('Approved pull requests', approvedFilter)"
          :aria-label="`Approved pull requests: ${KIND_FILTER_LABELS[approvedFilter]}, ${approvedCount} in the queue`"
          @click="cycleApprovedFilter"
        >
          Approved <span class="count">{{ approvedCount }}</span>
          <span class="state"> {{ KIND_FILTER_LABELS[approvedFilter] }}</span>
        </button>
        <button
          class="review-toggle-filter review-reviewed-filter"
          :class="{ active: reviewedFilter !== 'hide' }"
          :title="kindFilterTitle('Reviewed pull requests', reviewedFilter)"
          :aria-label="`Reviewed pull requests: ${KIND_FILTER_LABELS[reviewedFilter]}, ${reviewedCount} in the queue`"
          @click="cycleReviewedFilter"
        >
          Reviewed <span class="count">{{ reviewedCount }}</span>
          <span class="state"> {{ KIND_FILTER_LABELS[reviewedFilter] }}</span>
        </button>
      </div>
      <SearchSelect
        v-model="repositoryFilter"
        class="review-repository-select"
        multiple
        bulk-actions
        :sort="false"
        :options="repositoryOptions"
        placeholder="All repositories"
        title="Filter by one or more repositories"
      />
      <SearchSelect
        v-model="authorFilter"
        class="review-author-select"
        multiple
        bulk-actions
        :sort="false"
        :options="authorOptions"
        placeholder="All authors"
        title="Filter by one or more authors"
      />
      <input
        v-model="search"
        class="input review-search"
        type="search"
        placeholder="Search repository, number, title, or author…"
        aria-label="Search the review queue"
      />
    </div>

    <div v-if="loading && !queue.prs.length" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load the review queue.</p>
      <button class="btn" @click="load()">Retry</button>
    </div>

    <div v-else-if="!queue.prs.length" class="empty">
      No pull requests have review reports in the store yet. Run <code>/review-pr-full</code> on a PR to fill it.
    </div>

    <div v-else-if="!filteredPrs.length" class="empty">
      <p v-if="hiddenDrafts.length">
        {{ hiddenDrafts.length }} draft pull request{{ hiddenDrafts.length === 1 ? ' is' : 's are' }} hidden.
      </p>
      <p v-else-if="hiddenApproved.length">
        {{ hiddenApproved.length }} approved pull request{{ hiddenApproved.length === 1 ? ' is' : 's are' }} hidden.
      </p>
      <p v-else-if="hiddenReviewed.length">
        {{ hiddenReviewed.length }} reviewed pull request{{ hiddenReviewed.length === 1 ? ' is' : 's are' }} hidden.
      </p>
      <p v-else-if="draftsFilter === 'only'">No drafts match.</p>
      <p v-else-if="approvedFilter === 'only'">No approved pull requests match.</p>
      <p v-else-if="reviewedFilter === 'only'">No pull requests you reviewed match.</p>
      <p v-else-if="search">No pull requests match “{{ search }}”.</p>
      <p v-else-if="repositoryFilter.length">No pull requests in {{ repositoryFilter.join(', ') }}.</p>
      <p v-else-if="authorFilter.length">No pull requests by {{ authorFilter.join(', ') }}.</p>
      <p v-else>No {{ stateFilter === 'all' ? '' : `${stateFilter} ` }}pull requests.</p>
      <button v-if="hiddenDrafts.length" class="btn sm ghost" @click="draftsFilter = 'all'">Include drafts</button>
      <button v-if="hiddenApproved.length" class="btn sm ghost" @click="approvedFilter = 'all'">
        Include approved
      </button>
      <button v-if="hiddenReviewed.length" class="btn sm ghost" @click="reviewedFilter = 'all'">
        Include reviewed
      </button>
      <button
        v-if="draftsFilter === 'only' || approvedFilter === 'only' || reviewedFilter === 'only'"
        class="btn sm ghost"
        @click="showEveryPullRequest"
      >
        Show every pull request
      </button>
      <button v-if="search" class="btn sm ghost" @click="search = ''">Clear search</button>
      <button v-if="repositoryFilter.length" class="btn sm ghost" @click="repositoryFilter = []">
        Clear repositories
      </button>
      <button v-if="authorFilter.length" class="btn sm ghost" @click="authorFilter = []">Clear author</button>
      <button v-if="stateFilter !== 'all'" class="btn sm ghost" @click="stateFilter = 'all'">Show all</button>
    </div>

    <template v-else>
      <section v-for="group in groups" :key="group.repository">
        <h2 class="group-head">
          <router-link
            v-if="repositoryLink(group.repository)"
            :to="`/repositories/${repositoryLink(group.repository)}`"
            >{{ group.repository }}</router-link
          >
          <template v-else>{{ group.repository }}</template>
          <span class="faint review-count">{{ group.prs.length }}</span>
        </h2>
        <div class="review-table-wrap">
          <table class="review-table">
            <thead>
              <tr>
                <th>PR</th>
                <th>Author</th>
                <th>Age</th>
                <th>Last comment</th>
                <th>Reviewed</th>
                <th>Last review</th>
                <th v-for="column in QUEUE_STEPS" :key="column.key" class="review-col-step">
                  {{ column.label }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="pr in group.prs" :key="`${pr.repository}#${pr.number}`">
                <td class="review-pr-cell">
                  <router-link
                    v-if="taskFor(pr)"
                    class="review-task-link"
                    :to="`/task/${taskFor(pr).id}?view=pr`"
                    :title="`Task: ${taskFor(pr).title} · opens in PR view`"
                    :aria-label="`Task: ${taskFor(pr).title} (opens in PR view)`"
                    >📝</router-link
                  >
                  <button
                    v-else
                    class="review-task-new"
                    :disabled="creatingKey === prKey(pr)"
                    :title="`Create a task from PR #${pr.number}`"
                    :aria-label="`Create a task from PR #${pr.number}`"
                    @click="createTaskFrom(pr)"
                  >
                    <span v-if="creatingKey === prKey(pr)" class="spinner" aria-hidden="true"></span>
                    <span v-else aria-hidden="true">➕</span>
                  </button>
                  <a
                    v-if="ghxLink(pr)"
                    class="review-tool-link"
                    :href="ghxLink(pr)"
                    target="_blank"
                    rel="noopener"
                    title="Open in ghx"
                    >ghx</a
                  >
                  <a
                    v-if="pr.url"
                    class="review-tool-link"
                    :href="pr.url"
                    target="_blank"
                    rel="noopener"
                    title="Open on GitHub"
                    >gh</a
                  >
                  <span
                    class="review-readiness"
                    role="img"
                    :title="readinessTitle(pr)"
                    :aria-label="readinessTitle(pr)"
                    >{{ READINESS_LIGHTS[pr.readiness] }}</span
                  >
                  <span class="review-number">#{{ pr.number }}</span>
                  <span
                    v-if="isApproved(pr)"
                    class="review-approved"
                    role="img"
                    title="Approved on GitHub"
                    aria-label="Approved on GitHub"
                    >✅</span
                  >
                  <span v-if="pr.draft" class="badge st-draft">draft</span>
                  <span
                    v-if="pr.request_source"
                    class="review-source"
                    role="img"
                    :title="sourceTitle(pr)"
                    :aria-label="sourceTitle(pr)"
                    >{{ sourceBadge(pr) }}</span
                  >
                  <router-link
                    class="review-pr-link"
                    :to="pullPath(pr)"
                    :title="pr.title"
                    :aria-label="
                      pr.title ? `Open PR #${pr.number} in the app: ${pr.title}` : `Open PR #${pr.number} in the app`
                    "
                    >{{ pr.title || `#${pr.number}` }}</router-link
                  >
                </td>
                <td class="faint">
                  <router-link
                    v-if="personLinkFor(pr.author)"
                    :to="personLinkFor(pr.author).path"
                    :class="{ faint: personLinkFor(pr.author).missing }"
                    >{{ pr.author }}</router-link
                  >
                  <template v-else>{{ pr.author || '—' }}</template>
                </td>
                <td>
                  <span v-if="pr.created_at" class="mono">{{ timeAgo(pr.created_at) }}</span>
                  <span v-else class="faint">—</span>
                </td>
                <td>
                  <template v-if="pr.last_comment_at">
                    <span class="mono">{{ timeAgo(pr.last_comment_at) }}</span>
                    <span v-if="pr.last_comment_by" class="faint review-by">
                      by
                      <router-link
                        v-if="personLinkFor(pr.last_comment_by)"
                        :to="personLinkFor(pr.last_comment_by).path"
                        :class="{ faint: personLinkFor(pr.last_comment_by).missing }"
                        >{{ pr.last_comment_by }}</router-link
                      >
                      <template v-else>{{ pr.last_comment_by }}</template>
                    </span>
                  </template>
                  <span v-else class="faint">—</span>
                </td>
                <td>
                  <a
                    v-if="commitUrl(pr)"
                    class="mono"
                    :href="commitUrl(pr)"
                    target="_blank"
                    rel="noopener"
                    :title="`Reviewed commit ${pr.head_commit}`"
                    >{{ shortCommit(pr.head_commit) }}</a
                  >
                  <code v-else-if="pr.head_commit">{{ shortCommit(pr.head_commit) }}</code>
                  <span v-else class="faint">—</span>
                </td>
                <td class="review-reviewed-at">
                  <span v-if="pr.reviewed_at" class="mono">{{ formatDateTime(pr.reviewed_at) }}</span>
                  <span v-else class="faint">—</span>
                </td>

                <td v-for="column in QUEUE_STEPS" :key="column.key" class="review-col-step">
                  <span
                    v-if="runningStep(pr, column.key)"
                    class="review-step-running"
                    role="status"
                    :title="runningTitle(pr, column.key)"
                    :aria-label="runningTitle(pr, column.key)"
                    ><span class="spinner" aria-hidden="true"></span
                  ></span>
                  <template v-else-if="stepFor(pr, column.key)">
                    <button
                      v-if="column.key === 'assess-pr-risk'"
                      class="review-step"
                      :title="stepTitle(pr, column.key, stepFor(pr, column.key))"
                      @click="openReport(pr, stepFor(pr, column.key))"
                    >
                      <span
                        v-if="stepFor(pr, column.key).risk"
                        class="review-risk"
                        :class="`tone-${riskTone(stepFor(pr, column.key).risk)}`"
                        >{{ stepFor(pr, column.key).risk[0].toUpperCase() }}</span
                      ><span class="faint"
                        >/{{
                          stepFor(pr, column.key).confidence ? stepFor(pr, column.key).confidence[0].toUpperCase() : '—'
                        }}</span
                      >
                      <span
                        v-if="stepFor(pr, column.key).verdict"
                        :class="`tone-${verdictTone(stepFor(pr, column.key).verdict)}`"
                        >{{ stepFor(pr, column.key).verdict }}</span
                      >
                      <span
                        v-if="stepFor(pr, column.key).stale && stepFor(pr, column.key).commit"
                        class="review-stale"
                        >{{ shortCommit(stepFor(pr, column.key).commit) }}</span
                      >
                    </button>
                    <button
                      v-else
                      class="review-step"
                      :title="stepTitle(pr, column.key, stepFor(pr, column.key))"
                      @click="openReport(pr, stepFor(pr, column.key))"
                    >
                      <span
                        v-if="stepFor(pr, column.key).verdict"
                        class="review-verdict"
                        :class="`tone-${verdictTone(stepFor(pr, column.key).verdict)}`"
                        >{{ verdictLabel(stepFor(pr, column.key).verdict) }}</span
                      >
                      <span v-else class="faint">local</span>
                      <span
                        v-if="stepFor(pr, column.key).stale && stepFor(pr, column.key).commit"
                        class="review-stale"
                        >{{ shortCommit(stepFor(pr, column.key).commit) }}</span
                      >
                    </button>
                  </template>
                  <span v-else class="faint">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <div v-if="openPr" class="modal-backdrop" @click.self="closeReport">
      <div class="modal review-modal">
        <div class="row" style="justify-content: space-between; align-items: baseline">
          <h2 style="margin: 0">
            {{ openPr.repository }}#{{ openPr.number }} <span class="faint review-modal-path">{{ openName }}</span>
          </h2>
          <button class="btn sm ghost" aria-label="Close report" @click="closeReport">Close</button>
        </div>
        <div v-if="reportLoading" class="empty"><span class="spinner" aria-hidden="true"></span></div>
        <!-- The report's marker comment is stripped and its HTML sanitized by
             the renderer before it reaches v-html. -->
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div v-else-if="reportContent !== null" class="review-content md" v-html="reportHtml"></div>
        <p v-if="reportTruncated" class="faint">Showing the first part of a large report.</p>
      </div>
    </div>
  </div>
</template>
