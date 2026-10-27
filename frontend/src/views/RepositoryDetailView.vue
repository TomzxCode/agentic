<script setup>
import { computed, onMounted, ref, resolveComponent, shallowRef } from 'vue'
import { api } from '../api'
import { changeCreateBody, changesForItem } from '../changes'
import { store, statusLabel, timeAgo } from '../store'
import {
  authoredByLogin,
  itemAuthor,
  itemState,
  itemStatus,
  parseRemote,
  personForHandle,
  personLink
} from '../repositories/parse'
import { itemsForRepository, repositoryRows, sortItems } from '../repositories/rows'
import { ghxItemUrl, ghxRepoUrl } from '../toolLinks'
import GridColumnChooser from '../components/GridColumnChooser.vue'
import RepositoryItemsGrid from '../components/RepositoryItemsGrid.vue'

const props = defineProps({ id: { type: String, required: true } })

// The globally registered router-link, handed to the grid so its cells keep
// internal navigation inside the SPA (and so tests can stub it by name).
const routerLink = resolveComponent('RouterLink')

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
// Every change record, so a PR row can show the changes that reference it.
const changes = ref([])
// The PR whose change is being recorded, so its button shows a spinner.
const recordingId = ref('')
// The row whose task is being created, so its button shows a spinner.
const creatingId = ref('')
// The grid's api, once it reports ready, so the column chooser can read the
// columns and show or hide them.
const gridApi = shallowRef(null)

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

// The repository's page in the ghx web UI, when one is configured in Settings.
const ghxRepositoryLink = computed(() => ghxRepoUrl(repository.value?.remote_url, store.settings?.ghx_url))

// Every issue and PR the repository has, newest number first. Filtering and
// sorting are done in the grid, at the column level.
const sortedRows = computed(() => sortItems(rows.value))

// The rows handed to the grid: the repository's items enriched with everything a
// cell needs (state badge, author link, task chips, change lines, actions), so
// the grid's cell renderers stay presentation-only.
const tableRows = computed(() =>
  sortedRows.value.map((row) => {
    const status = itemStatus(row)
    const author = itemAuthor(row)
    const person = personForHandle(store.people, author)
    const authorLink = personLink(store.people, author)
    return {
      key: `${row.kind}:${row.number || row.id}`,
      kind: row.kind,
      number: row.number || '',
      title: row.title || '',
      url: row.url || '',
      stateLabel: status?.label || '',
      stateClass: status?.className || '',
      authorLabel: author ? `@${author}` : '',
      personId: person?.id || '',
      // Where the author links: the person, or the prefilled creation page.
      authorPath: authorLink?.path || '',
      tasks: tasksFor(row),
      // The distinct statuses of the row's linked tasks, in first-seen order,
      // for the Task status column.
      statuses: [...new Set(tasksFor(row).map((task) => task.status))].map((status) => ({
        status,
        label: statusLabel(status)
      })),
      // Change records are shown on pull request rows only, as the card layout
      // did: a change lands in a PR, so a change naming an issue is not shown.
      changes: row.kind === 'pr' ? changesFor(row) : [],
      canCreate: !row.linked && !!row.url,
      canRecord: canRecordChange(row),
      // The row's page in the ghx web UI, when one is configured in Settings.
      ghxUrl: ghxItemUrl(row, store.settings?.ghx_url) || '',
      busy: (!!row.url && creatingId.value === row.url) || (!!row.id && recordingId.value === row.id),
      fetched: row.fetched_at ? `fetched ${timeAgo(row.fetched_at)}` : '',
      raw: row
    }
  })
)

function tasksFor(row) {
  return (row.task_ids || []).map((id) => tasksById.value[id]).filter(Boolean)
}

// The change records that reference a PR, shown under its row. Changes belong
// to a task and name the PR they landed in via their external ref.
function changesFor(row) {
  return changesForItem(changes.value, row)
}

// Offer to record a change for a merged PR only when exactly one task uses it
// (so the change has an unambiguous owner), no change references it yet, and
// the viewer authored it (a PR someone else wrote is not the viewer's change).
function canRecordChange(row) {
  return (
    !!row.item &&
    itemState(row) === 'merged' &&
    tasksFor(row).length === 1 &&
    !changesFor(row).length &&
    authoredByMe(row)
  )
}

// A PR counts as the viewer's when its GitHub author matches the configured
// login (case-insensitive). With no login known (never set and `gh` could not
// detect one), authorship cannot be attributed, so nothing is filtered out.
function authoredByMe(row) {
  return authoredByLogin(row, store.settings?.github_login)
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
// all" button asks ghx for a delta fetch first. A failure leaves the stored
// items to render on their own.
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

// Button one: refresh the whole repository from GitHub (ghx's delta fetch, not
// a forced re-download). The backend writes the listing's state back onto the
// task-linked items, so
// reload the items too: the refresh covers the repository and its items.
async function refreshAll() {
  if (refreshingAll.value || !canListGithub.value) return
  refreshingAll.value = true
  await loadGithub({ refresh: true })
  refreshingAll.value = false
  if (ghxError.value) {
    store.notify(`Could not refresh from GitHub: ${ghxError.value}`, true)
    return
  }
  try {
    await store.loadItems()
  } catch (e) {
    store.notify(e.message, true)
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
  let firstError = ''
  const worker = async () => {
    while (queue.length) {
      const id = queue.shift()
      try {
        const refreshed = await api.items.refresh(id)
        // A 200 can still carry a fetch_error (ghx/slackx could not run).
        if (refreshed?.fetch_error) {
          failed += 1
          firstError = firstError || refreshed.fetch_error
        }
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
  if (failed)
    store.notify(
      `Refreshed ${done} of ${ids.length} linked items; ${failed} failed${firstError ? `: ${firstError}` : ''}`,
      true
    )
  else store.notify(`Refreshed ${done} linked item${done === 1 ? '' : 's'}`)
}

onMounted(load)
</script>

<template>
  <div class="page-fill">
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
          <a
            v-if="ghxRepositoryLink"
            class="btn sm ghost"
            :href="ghxRepositoryLink"
            target="_blank"
            rel="noopener"
            title="Open this repository in the local ghx web UI"
          >
            Open in ghx
          </a>
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
          <GridColumnChooser :api="gridApi" storage-key="repository-items" />
        </span>
      </div>

      <p v-if="ghxError" class="faint" style="margin: 8px 0 0">
        Could not list this repository from GitHub ({{ ghxError }}). Showing the items already associated to tasks.
      </p>
      <p v-else-if="ghxFailed.length" class="faint" style="margin: 8px 0 0">
        Could not load the {{ ghxFailed.join(' or the ') }} from GitHub. Showing the rest of the repository.
      </p>

      <!-- While the GitHub listing loads, the wait shows where the grid will
           land, instead of flashing a partial page. -->
      <div v-if="loading" class="empty"><span class="spinner" aria-hidden="true"></span></div>

      <template v-else>
        <div v-if="!rows.length" class="panel" style="margin-top: 14px">
          <p class="muted" style="margin-top: 0">No issues or pull requests to show for this repository.</p>
          <p class="muted" style="margin: 0">
            Paste a GitHub issue or PR link on a task, or import one when creating a task.
          </p>
        </div>

        <RepositoryItemsGrid
          v-else
          :rows="tableRows"
          :router-link="routerLink"
          @new-task="createTaskFrom"
          @record-change="recordChange"
          @ready="gridApi = $event"
        />
      </template>
    </template>
  </div>
</template>
