<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { changeCreateBody, changeStatusBadge, changesForItem } from '../changes'
import { store, statusLabel, timeAgo } from '../store'
import {
  itemAuthor,
  itemState,
  itemStatus,
  itemsForRepository,
  parseRemote,
  personForHandle,
  repositoryRows,
  sortItems,
  stateBreakdown
} from '../repositories'
import ItemCard from '../components/ItemCard.vue'
import TaskLink from '../components/TaskLink.vue'

const props = defineProps({ id: { type: String, required: true } })

const TASK_STATUS_ORDER = ['open', 'in_progress', 'blocked', 'done', 'archived']

const loading = ref(true)
const error = ref(false)
// The live listing of the repository's issues and PRs, fetched from ghx.
const ghxItems = ref([])
// Kinds ghx could not list ("issues", "pull requests"); empty on success.
const ghxFailed = ref([])
// A failed ghx listing; the stored items still render below it.
const ghxError = ref('')
const refreshingAll = ref(false)
const refreshingLinked = ref(false)
const query = ref('')
// Every change record, so a PR row can show the changes that reference it.
const changes = ref([])
// The PR whose change is being recorded, so its button shows a spinner.
const recordingId = ref('')
// The row whose task is being created, so its button shows a spinner.
const creatingId = ref('')
// Kind filter: '' shows both sections, otherwise 'issue' or 'pr'.
const kindFilter = ref('')
// State filter: '' shows every state, otherwise a value from STATE_ORDER.
const stateFilter = ref('')
// Task status filter: '' shows every item, otherwise a task status. An item
// matches when any of the tasks it is linked to has that status.
const statusFilter = ref('')

const repository = computed(() => store.repositories.find((r) => r.id === props.id) || null)
const tasksById = computed(() => Object.fromEntries(store.tasks.map((task) => [task.id, task])))

// The items already associated to a task, which the second refresh button
// re-fetches and the record-change action works on.
const linkedItems = computed(() => (repository.value ? itemsForRepository(repository.value, store.items) : []))

// Every issue and PR of the repository: the live ghx listing overlaid with the
// stored, task-associated items.
const rows = computed(() => repositoryRows(ghxItems.value, linkedItems.value))

// The repository has a GitHub remote worth listing.
const canListGithub = computed(() => !!parseRemote(repository.value?.remote_url))

// Filter-control counts cover the whole repository (like the Items page), so a
// button's number does not move while the search or the other filter narrows
// the list.
const kindCounts = computed(() => {
  const counts = { issue: 0, pr: 0 }
  for (const row of rows.value) if (counts[row.kind] !== undefined) counts[row.kind] += 1
  return counts
})

// The states present among the repository's rows, in a stable order.
const stateOptions = computed(() => stateBreakdown(rows.value))

// The kind toggle only earns its place when both kinds are present.
const showKindFilter = computed(() => kindCounts.value.issue > 0 && kindCounts.value.pr > 0)

// The task statuses present among the rows' tasks, in a stable order. Each
// count is the number of rows carrying at least one task in that status, so a
// row with two tasks of the same status counts once.
const statusOptions = computed(() => {
  const counts = {}
  for (const row of rows.value) {
    const seen = new Set()
    for (const task of tasksFor(row)) {
      if (seen.has(task.status)) continue
      seen.add(task.status)
      counts[task.status] = (counts[task.status] || 0) + 1
    }
  }
  return TASK_STATUS_ORDER.filter((status) => counts[status]).map((status) => ({
    value: status,
    label: statusLabel(status),
    count: counts[status]
  }))
})

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return sortItems(rows.value).filter((row) => {
    if (kindFilter.value && row.kind !== kindFilter.value) return false
    if (stateFilter.value && itemState(row) !== stateFilter.value) return false
    if (statusFilter.value && !tasksFor(row).some((task) => task.status === statusFilter.value)) return false
    if (!q) return true
    return (
      String(row.title || '')
        .toLowerCase()
        .includes(q) || String(row.number || '').includes(q)
    )
  })
})
const issues = computed(() => filtered.value.filter((row) => row.kind === 'issue'))
const pulls = computed(() => filtered.value.filter((row) => row.kind === 'pr'))

function tasksFor(row) {
  return (row.task_ids || []).map((id) => tasksById.value[id]).filter(Boolean)
}

// The change records that reference a PR, shown under its row. Changes belong
// to a task and name the PR they landed in via their external ref.
function changesFor(row) {
  return changesForItem(changes.value, row)
}

// Offer to record a change for a merged PR only when exactly one task uses it
// (so the change has an unambiguous owner) and no change references it yet.
function canRecordChange(row) {
  return !!row.item && itemState(row) === 'merged' && tasksFor(row).length === 1 && !changesFor(row).length
}

// Swap a refreshed stored item back into the store so its row reflects the new
// metadata (a merge time picked up from GitHub).
function replaceItem(updated) {
  const index = store.items.findIndex((entry) => entry.id === updated.id)
  if (index !== -1) store.items[index] = updated
}

async function recordChange(row) {
  const task = tasksFor(row)[0]
  if (!task || recordingId.value) return
  recordingId.value = row.id
  try {
    // The change dates to the merge. An item fetched before merge times were
    // stored carries none, so refresh it from GitHub once to pick the time up.
    let mergedAt = row.metadata_json?.merged_at
    if (!mergedAt) {
      const refreshed = await api.items.refresh(row.id)
      if (refreshed) {
        mergedAt = refreshed.metadata_json?.merged_at
        replaceItem(refreshed)
      }
    }
    // The button only shows on a merged PR, so the change opens accepted; with
    // no merge time to use, it is accepted as of now.
    const change = await api.changes.create(changeCreateBody(task.id, row, mergedAt || new Date().toISOString()))
    if (change) changes.value = [change, ...changes.value]
    store.notify('Change recorded')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    recordingId.value = ''
  }
}

// The directory person behind a row's GitHub author, when one carries the
// login as an alias; null leaves the author unlinked.
function authorPerson(row) {
  return personForHandle(store.people, itemAuthor(row))
}

// Turn an issue or PR the repository has into a task. The backend imports the
// URL (fetching it, filling title and description, linking the item), so after
// the reload the row renders as a linked one with its task chip. The view stays
// put: the row's new chip is the confirmation.
async function createTaskFrom(row) {
  if (!row.url || creatingId.value) return
  creatingId.value = row.url
  try {
    await api.tasks.create({ github_url: row.url })
    await Promise.all([store.loadItems(), store.loadTasks()])
    store.notify('Task created')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    creatingId.value = ''
  }
}

async function load() {
  loading.value = true
  error.value = false
  try {
    // People and changes are supplementary: a failed load leaves an author
    // unlinked and a PR without its change rows rather than blanking the view.
    await Promise.all([
      store.loadRepositories(),
      store.loadItems(),
      store.loadTasks(),
      store.loadPeople().catch(() => {}),
      api.changes
        .list()
        .then((rows) => (changes.value = rows || []))
        .catch(() => {})
    ])
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
    loading.value = false
    return
  }
  // The GitHub listing is the slow part (ghx subprocesses), so the spinner
  // covers it too rather than flashing a partial page first.
  await loadGithub()
  loading.value = false
}

// Fetch the repository's whole issue and PR listing from GitHub (ghx). Because
// ghx serves a cached listing, the first load reads the cache and the "refresh
// all" button asks ghx to re-fetch first. A failure leaves the stored items to
// render on their own.
async function loadGithub({ refresh = false } = {}) {
  ghxError.value = ''
  if (!canListGithub.value) {
    ghxItems.value = []
    ghxFailed.value = []
    return
  }
  try {
    const listing = await api.github.repository({ repository_id: props.id, state: 'all', limit: 1000, refresh })
    // Swap only once the response arrives, so a slow ghx call does not blank
    // the rows that are already on screen.
    ghxItems.value = listing?.items || []
    ghxFailed.value = listing?.failed || []
  } catch (e) {
    ghxError.value = e.message
    ghxItems.value = []
    ghxFailed.value = []
  }
}

// Button one: re-fetch the whole repository from GitHub (forcing ghx's cache).
async function refreshAll() {
  if (refreshingAll.value || !canListGithub.value) return
  refreshingAll.value = true
  await loadGithub({ refresh: true })
  refreshingAll.value = false
  if (ghxError.value) {
    store.notify(`Could not refresh from GitHub: ${ghxError.value}`, true)
    return
  }
  const issues = ghxItems.value.filter((item) => item.kind === 'issue').length
  const pulls = ghxItems.value.filter((item) => item.kind === 'pr').length
  store.notify(`Refreshed ${issues} issue${issues === 1 ? '' : 's'} and ${pulls} pull request${pulls === 1 ? '' : 's'}`)
}

// Button two: re-fetch the stored items already associated to tasks, a few at a
// time so a large repository does not spawn a burst of ghx processes. A failed
// item keeps its stored data: the rows are reloaded from the API afterwards.
async function refreshLinked() {
  if (refreshingLinked.value || !linkedItems.value.length) return
  refreshingLinked.value = true
  const ids = linkedItems.value.map((item) => item.id)
  const queue = [...ids]
  let failed = 0
  const worker = async () => {
    while (queue.length) {
      const id = queue.shift()
      try {
        await api.items.refresh(id)
      } catch {
        failed += 1
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(4, queue.length) }, worker))
  try {
    await store.loadItems()
  } catch (e) {
    store.notify(e.message, true)
  }
  refreshingLinked.value = false
  const done = ids.length - failed
  if (failed) store.notify(`Refreshed ${done} of ${ids.length} linked items; ${failed} failed`, true)
  else store.notify(`Refreshed ${done} linked item${done === 1 ? '' : 's'}`)
}

onMounted(load)
</script>

<template>
  <div>
    <div v-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load this repository's items.</p>
      <button class="btn" @click="load">Retry</button>
    </div>

    <!-- Brief: only until the stores resolve; the listing's wait is shown in
         the section spinners below instead of hiding the page. -->
    <div v-else-if="loading && !repository" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="!repository" class="panel">
      <p class="muted" style="margin-top: 0">No repository with that id.</p>
      <router-link to="/repositories">← Back to Repositories</router-link>
    </div>

    <template v-else>
      <div class="faint"><router-link to="/repositories">Repositories</router-link> / {{ repository.name }}</div>
      <div class="row" style="justify-content: space-between; margin-top: 6px; align-items: flex-start">
        <h1>{{ repository.name }}</h1>
        <span class="row" style="gap: 6px; flex-wrap: wrap; justify-content: flex-end">
          <span v-if="repository.default_branch" class="badge">{{ repository.default_branch }}</span>
          <span v-if="repository.remote_url" class="faint">{{ repository.remote_url }}</span>
          <button
            class="btn sm"
            :disabled="refreshingAll || loading || !canListGithub"
            aria-label="Refresh all issues and pull requests"
            title="Fetch the repository's issues and pull requests from GitHub"
            @click="refreshAll"
          >
            <span v-if="refreshingAll" class="spinner" aria-hidden="true"></span>
            <span v-else>↻</span>
            {{ refreshingAll ? 'Refreshing…' : 'Refresh all' }}
          </button>
          <button
            class="btn sm"
            :disabled="refreshingLinked || !linkedItems.length"
            aria-label="Refresh issues and pull requests associated to tasks"
            title="Re-fetch the items already associated to tasks"
            @click="refreshLinked"
          >
            <span v-if="refreshingLinked" class="spinner" aria-hidden="true"></span>
            <span v-else>↻</span>
            {{ refreshingLinked ? 'Refreshing…' : 'Refresh linked' }}
          </button>
        </span>
      </div>

      <p v-if="ghxError" class="faint" style="margin: 8px 0 0">
        Could not list this repository from GitHub ({{ ghxError }}). Showing the items already associated to tasks.
      </p>
      <p v-else-if="ghxFailed.length" class="faint" style="margin: 8px 0 0">
        Could not load the {{ ghxFailed.join(' or the ') }} from GitHub. Showing the rest of the repository.
      </p>

      <!-- While the GitHub listing loads, the wait shows where the rows will
           land: one spinner under each section heading. -->
      <template v-if="loading">
        <h2 class="group-head">Issues</h2>
        <div class="empty"><span class="spinner" aria-hidden="true"></span></div>
        <h2 class="group-head">Pull requests</h2>
        <div class="empty"><span class="spinner" aria-hidden="true"></span></div>
      </template>

      <template v-else>
        <div v-if="!rows.length" class="panel" style="margin-top: 14px">
          <p class="muted" style="margin-top: 0">No issues or pull requests to show for this repository.</p>
          <p class="muted" style="margin: 0">
            Paste a GitHub issue or PR link on a task, or import one when creating a task.
          </p>
        </div>

        <template v-else>
          <div class="panel" style="margin-top: 14px">
            <input v-model="query" class="input" placeholder="Filter by title or number…" aria-label="Filter items" />

            <div v-if="showKindFilter" class="row" style="gap: 6px; margin-top: 12px">
              <span class="filter-label">Kind</span>
              <div class="row" style="gap: 6px" role="group" aria-label="Filter by kind">
                <button
                  class="btn sm"
                  :class="{ primary: !kindFilter }"
                  :aria-pressed="!kindFilter"
                  @click="kindFilter = ''"
                >
                  All {{ rows.length }}
                </button>
                <button
                  class="btn sm"
                  :class="{ primary: kindFilter === 'issue' }"
                  :aria-pressed="kindFilter === 'issue'"
                  @click="kindFilter = 'issue'"
                >
                  Issues {{ kindCounts.issue }}
                </button>
                <button
                  class="btn sm"
                  :class="{ primary: kindFilter === 'pr' }"
                  :aria-pressed="kindFilter === 'pr'"
                  @click="kindFilter = 'pr'"
                >
                  Pull requests {{ kindCounts.pr }}
                </button>
              </div>
            </div>

            <div v-if="stateOptions.length" class="row" style="gap: 6px; margin-top: 12px">
              <span class="filter-label">State</span>
              <div class="row" style="gap: 6px" role="group" aria-label="Filter by state">
                <button
                  class="btn sm"
                  :class="{ primary: !stateFilter }"
                  :aria-pressed="!stateFilter"
                  @click="stateFilter = ''"
                >
                  Any state
                </button>
                <button
                  v-for="state in stateOptions"
                  :key="state.value"
                  class="btn sm"
                  :class="{ primary: stateFilter === state.value }"
                  :aria-pressed="stateFilter === state.value"
                  @click="stateFilter = state.value"
                >
                  {{ state.label }} {{ state.count }}
                </button>
              </div>
            </div>

            <div v-if="statusOptions.length" class="row" style="gap: 6px; margin-top: 12px">
              <span class="filter-label">Task status</span>
              <div class="row" style="gap: 6px" role="group" aria-label="Filter by task status">
                <button
                  class="btn sm"
                  :class="{ primary: !statusFilter }"
                  :aria-pressed="!statusFilter"
                  @click="statusFilter = ''"
                >
                  Any task status
                </button>
                <button
                  v-for="status in statusOptions"
                  :key="status.value"
                  class="btn sm"
                  :class="{ primary: statusFilter === status.value }"
                  :aria-pressed="statusFilter === status.value"
                  @click="statusFilter = status.value"
                >
                  {{ status.label }} {{ status.count }}
                </button>
              </div>
            </div>
          </div>

          <template v-if="!filtered.length">
            <p class="muted">No issues or PRs match the filters.</p>
          </template>

          <template v-else>
            <template v-if="issues.length">
              <h2 class="group-head">
                Issues <span class="faint">{{ issues.length }}</span>
              </h2>
              <ItemCard
                v-for="row in issues"
                :key="`issue-${row.number || row.id}`"
                :item="row"
                :show-source="false"
                :show-status="false"
                :show-content="false"
                :show-times="false"
              >
                <template #lead>
                  <span class="badge">issue</span>
                  <span v-if="itemStatus(row)" class="badge" :class="itemStatus(row).className">
                    {{ itemStatus(row).label }}
                  </span>
                  <span v-if="row.number" class="faint">#{{ row.number }}</span>
                </template>
                <template #actions>
                  <span v-if="itemAuthor(row)" class="faint">
                    <router-link v-if="authorPerson(row)" :to="`/person/${authorPerson(row).id}`">
                      @{{ itemAuthor(row) }}
                    </router-link>
                    <span v-else>@{{ itemAuthor(row) }}</span>
                  </span>
                  <button
                    v-if="!row.linked && row.url"
                    class="btn sm"
                    :disabled="creatingId === row.url"
                    title="Create a task from this issue"
                    @click="createTaskFrom(row)"
                  >
                    <span v-if="creatingId === row.url" class="spinner" aria-hidden="true"></span>
                    New task
                  </button>
                </template>
                <div v-if="tasksFor(row).length" class="row" style="margin-top: 8px; gap: 6px">
                  <TaskLink v-for="task in tasksFor(row)" :key="task.id" :task="task" />
                </div>
                <template #meta>
                  <div v-if="row.fetched_at" class="faint" style="margin-top: 6px">
                    fetched {{ timeAgo(row.fetched_at) }}
                  </div>
                </template>
              </ItemCard>
            </template>

            <template v-if="pulls.length">
              <h2 class="group-head">
                Pull requests <span class="faint">{{ pulls.length }}</span>
              </h2>
              <ItemCard
                v-for="row in pulls"
                :key="`pr-${row.number || row.id}`"
                :item="row"
                :show-source="false"
                :show-status="false"
                :show-content="false"
                :show-times="false"
              >
                <template #lead>
                  <span class="badge">PR</span>
                  <span v-if="itemStatus(row)" class="badge" :class="itemStatus(row).className">
                    {{ itemStatus(row).label }}
                  </span>
                  <span v-if="row.number" class="faint">#{{ row.number }}</span>
                </template>
                <template #actions>
                  <span v-if="itemAuthor(row)" class="faint">
                    <router-link v-if="authorPerson(row)" :to="`/person/${authorPerson(row).id}`">
                      @{{ itemAuthor(row) }}
                    </router-link>
                    <span v-else>@{{ itemAuthor(row) }}</span>
                  </span>
                  <button
                    v-if="!row.linked && row.url"
                    class="btn sm"
                    :disabled="creatingId === row.url"
                    title="Create a task from this pull request"
                    @click="createTaskFrom(row)"
                  >
                    <span v-if="creatingId === row.url" class="spinner" aria-hidden="true"></span>
                    New task
                  </button>
                  <button
                    v-if="canRecordChange(row)"
                    class="btn sm"
                    :disabled="recordingId === row.id"
                    title="Record a change for this PR"
                    @click="recordChange(row)"
                  >
                    <span v-if="recordingId === row.id" class="spinner" aria-hidden="true"></span>
                    Record change
                  </button>
                </template>
                <div v-if="tasksFor(row).length" class="row" style="margin-top: 8px; gap: 6px">
                  <TaskLink v-for="task in tasksFor(row)" :key="task.id" :task="task" />
                </div>
                <div v-if="changesFor(row).length" class="change-lines">
                  <div v-for="change in changesFor(row)" :key="change.id" class="change-line">
                    <span :class="changeStatusBadge(change.status)">{{ change.status }}</span>
                    <router-link :to="`/task/${change.task_id}`">{{ change.title || change.id }}</router-link>
                    <span class="faint">{{ change.change_class }}</span>
                    <span class="faint">· {{ timeAgo(change.opened_at) }}</span>
                  </div>
                </div>
                <template #meta>
                  <div v-if="row.fetched_at" class="faint" style="margin-top: 6px">
                    fetched {{ timeAgo(row.fetched_at) }}
                  </div>
                </template>
              </ItemCard>
            </template>
          </template>
        </template>
      </template>
    </template>
  </div>
</template>
