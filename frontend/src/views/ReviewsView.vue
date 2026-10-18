<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import {
  commitUrl,
  groupQueueByRepository,
  QUEUE_STEPS,
  READINESS_LIGHTS,
  READINESS_TITLES,
  riskTone,
  shortCommit,
  stripReportMarker,
  verdictLabel,
  verdictTone
} from '../reviews'
import { store, timeAgo } from '../store'
import { parseRemote, personForHandle } from '../repositories/parse'

// The review queue: every pull request with review reports in the user-global
// store the review skills write to, one row per PR with a column per review
// step. This is what the review_requested_prs orchestrator prints, read from the
// store and the PRs the app tracks instead of a live GitHub discovery.

const queue = ref({ root: null, prs: [], counts: {} })
const loading = ref(true)
const error = ref(false)
// The PR whose task is being created, so its button shows a spinner.
const creatingKey = ref('')

// The report open in the viewer: its PR, its relative store path, and content.
const openPr = ref(null)
const openName = ref('')
const reportContent = ref(null)
const reportLoading = ref(false)
const reportTruncated = ref(false)

const reportHtml = computed(() => renderMarkdown(stripReportMarker(reportContent.value)))
const groups = computed(() => groupQueueByRepository(queue.value.prs))

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

// The person carrying a GitHub login as an alias, or null when nobody does.
function personFor(login) {
  return personForHandle(store.people, login)
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
          {{ queue.counts.total }} PR{{ queue.counts.total === 1 ? '' : 's' }} · {{ queue.counts.ready }} ready ·
          {{ queue.counts.blocked }} blocked
        </span>
        <button class="btn sm ghost" :disabled="loading" title="Re-read the store and GitHub" @click="load(true)">
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          Refresh
        </button>
      </span>
    </div>
    <p v-if="queue.root" class="faint review-root">Reports read from {{ queue.root }}</p>

    <div v-if="loading && !queue.prs.length" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load the review queue.</p>
      <button class="btn" @click="load()">Retry</button>
    </div>

    <div v-else-if="!queue.prs.length" class="empty">
      No pull requests have review reports in the store yet. Run <code>/review-pr-full</code> on a PR to fill it.
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
                    :to="`/task/${taskFor(pr).id}`"
                    :title="`Task: ${taskFor(pr).title}`"
                    :aria-label="`Task: ${taskFor(pr).title}`"
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
                  <span v-if="pr.title" class="review-title" :title="pr.title">{{ pr.title }}</span>
                </td>
                <td class="faint">
                  <router-link v-if="personFor(pr.author)" :to="`/person/${personFor(pr.author).id}`">{{
                    pr.author
                  }}</router-link>
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
                        v-if="personFor(pr.last_comment_by)"
                        :to="`/person/${personFor(pr.last_comment_by).id}`"
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
  </div>
</template>
