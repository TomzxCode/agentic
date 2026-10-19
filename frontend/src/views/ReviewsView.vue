<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import {
  commitUrl,
  groupQueueByRepository,
  matchesAuthorFilter,
  matchesQueueSearch,
  matchesRepositoryFilter,
  matchesStateFilter,
  PR_STATE_FILTERS,
  QUEUE_STEPS,
  queueAuthors,
  queueRepositories,
  READINESS_LIGHTS,
  READINESS_TITLES,
  riskTone,
  shortCommit,
  stateFilterCounts,
  stripReportMarker,
  verdictLabel,
  verdictTone
} from '../reviews'
import { store, timeAgo, formatDateTime } from '../store'
import { parseRemote, personLink } from '../repositories/parse'
import SearchSelect from '../components/SearchSelect.vue'
import ShareFindingsModal from '../components/ShareFindingsModal.vue'

// The review queue: every pull request with review reports in the user-global
// store the review skills write to, one row per PR with a column per review
// step. This is what the review_requested_prs orchestrator prints, read from the
// store and the PRs the app tracks instead of a live GitHub discovery.

const queue = ref({ root: null, prs: [], counts: {} })
const loading = ref(true)
const error = ref(false)
// The PR whose task is being created, so its button shows a spinner.
const creatingKey = ref('')
// The PR whose review findings are being shared.
const sharing = ref(null)

// The filters: a PR's status (open by default, so the queue shows the pull
// requests still awaiting a review), one or more repositories, one or more
// authors, and a text search over the row's fields.
//
// They are per-device view preferences, remembered in localStorage like the
// feedback page's grouping, so leaving the page and coming back keeps them.
const FILTERS_KEY = 'agentic.reviewQueueFilters'

// The stored filters, with anything malformed or no longer offered falling back
// to its default rather than breaking the page.
function readStoredFilters() {
  const defaults = { state: 'open', repositories: [], authors: [], search: '' }
  try {
    const stored = JSON.parse(localStorage.getItem(FILTERS_KEY) || 'null')
    if (!stored || typeof stored !== 'object') return defaults
    return {
      state: PR_STATE_FILTERS.some((option) => option.value === stored.state) ? stored.state : defaults.state,
      repositories: Array.isArray(stored.repositories) ? stored.repositories.map(String) : [],
      authors: Array.isArray(stored.authors) ? stored.authors.map(String) : [],
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
const search = ref(storedFilters.search)

// Write the filters back as they change: a choice, a clear from the empty
// state, or a value the refreshed queue dropped all land here.
watch(
  [stateFilter, repositoryFilter, authorFilter, search],
  () => {
    try {
      localStorage.setItem(
        FILTERS_KEY,
        JSON.stringify({
          state: stateFilter.value,
          repositories: repositoryFilter.value,
          authors: authorFilter.value,
          search: search.value
        })
      )
    } catch {
      // Not fatal: the filters still apply for this session.
    }
  },
  { deep: true }
)

// The report open in the viewer: its PR, its relative store path, and content.
const openPr = ref(null)
const openName = ref('')
const reportContent = ref(null)
const reportLoading = ref(false)
const reportTruncated = ref(false)

const reportHtml = computed(() => renderMarkdown(stripReportMarker(reportContent.value)))
// The rows the filters keep: status, then repository, then author, then the
// search text.
const filteredPrs = computed(() =>
  queue.value.prs.filter(
    (pr) =>
      matchesStateFilter(pr, stateFilter.value) &&
      matchesRepositoryFilter(pr, repositoryFilter.value) &&
      matchesAuthorFilter(pr, authorFilter.value) &&
      matchesQueueSearch(pr, search.value)
  )
)
const groups = computed(() => groupQueueByRepository(filteredPrs.value))
// Per-status counts for the filter chips, over the whole queue.
const stateCounts = computed(() => stateFilterCounts(queue.value.prs))
// The repositories to offer, with their row counts, over the whole queue.
const repositories = computed(() => queueRepositories(queue.value.prs))
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

// After the share modal imports a task for a PR, reflect it on the row so it
// reads as linked, like the import button does.
function onImported(task) {
  if (sharing.value) sharing.value.task_ids = [task.id]
  store.loadTasks().catch(() => {})
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

// A step cell's tooltip: its verdict, its reviewed commit, and whether it is
// stale (does not cover the newest reviewed commit).
function stepTitle(pr, key, step) {
  const label = QUEUE_STEPS.find((entry) => entry.key === key)?.label || key
  const parts = [label]
  if (step.verdict) parts.push(step.verdict)
  if (step.commit) parts.push(step.stale ? `${shortCommit(step.commit)} (stale)` : shortCommit(step.commit))
  return parts.join(' · ')
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
      <p v-if="search">No pull requests match “{{ search }}”.</p>
      <p v-else-if="repositoryFilter.length">No pull requests in {{ repositoryFilter.join(', ') }}.</p>
      <p v-else-if="authorFilter.length">No pull requests by {{ authorFilter.join(', ') }}.</p>
      <p v-else>No {{ stateFilter === 'all' ? '' : `${stateFilter} ` }}pull requests.</p>
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
                    class="review-pr-link"
                    :href="pr.url"
                    target="_blank"
                    rel="noopener"
                    :title="[pr.title, readinessTitle(pr)].filter(Boolean).join(' — ')"
                  >
                    <span aria-hidden="true">{{ READINESS_LIGHTS[pr.readiness] }}</span>
                    #{{ pr.number }}
                  </a>
                  <span v-if="pr.draft" class="badge st-draft">draft</span>
                  <span v-if="pr.request_source" class="badge review-source" :title="sourceTitle(pr)">{{
                    pr.request_source
                  }}</span>
                  <span v-if="pr.title" class="review-title" :title="pr.title">{{ pr.title }}</span>
                  <button
                    class="btn sm ghost review-share"
                    :title="`Share PR #${pr.number}'s review findings with its author`"
                    @click="sharing = pr"
                  >
                    Share
                  </button>
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
                  <template v-if="stepFor(pr, column.key)">
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

    <ShareFindingsModal
      v-if="sharing"
      :repository="sharing.repository"
      :number="sharing.number"
      :url="sharing.url"
      :task-id="taskFor(sharing)?.id || null"
      :task-label="taskFor(sharing)?.title || ''"
      @close="sharing = null"
      @imported="onImported"
    />
  </div>
</template>
