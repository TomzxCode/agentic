<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import {
  commitUrl,
  queueRowFor,
  QUEUE_STEPS,
  READINESS_LIGHTS,
  READINESS_TITLES,
  riskTone,
  runningStep,
  shortCommit,
  stripReportMarker,
  SURFACE_STEPS,
  surfaceSteps,
  taskPullRequests,
  verdictLabel,
  verdictTone
} from '../reviews'
import { store, timeAgo, formatDateTime } from '../store'
import { parseGithubUrl } from '../repositories/parse'
import AgentPanel from './AgentPanel.vue'
import FindingsSelector from './FindingsSelector.vue'
import GithubItemPanel from './GithubItemPanel.vue'

// The task's pull-request mode: for each PR the task is linked to (or a single
// PR given by `url`), the same detail panel the issue mode shows for an issue
// (state, author, labels, description, read from GitHub) with the review queue's
// row for that PR below it (readiness, reviewed commit, per-step verdicts) read
// from the user-global store the review skills write to. A PR the store has no
// reports for still shows its detail and link, with a note instead of steps. The
// agent panel below them works the pull requests through an agent. `task` is
// optional: a standalone PR view has no task, and offers to create one so the
// agent can run.

const props = defineProps({
  task: { type: Object, default: null },
  harnesses: { type: Array, default: () => [] },
  // A single pull request URL to render on its own, without a task association.
  url: { type: String, default: '' }
})
const emit = defineEmits(['changed'])

const resolvedTask = ref(props.task)
watch(
  () => props.task,
  (value) => {
    resolvedTask.value = value
  }
)

// Even without a linked task, the agent panel can offer its prompt buttons and
// build context from the pull request's coordinates, creating a task on the
// first run.
const agentTask = computed(() => {
  if (resolvedTask.value) return resolvedTask.value
  const tracked = (store.items || []).find((item) => item.url === props.url)
  const parsed = parseGithubUrl(props.url)
  let item = tracked
  if (!item) {
    item = { source: 'github', kind: 'pull_request', url: props.url, title: '', metadata_json: {} }
  }
  const meta = { ...(item.metadata_json || {}) }
  if (parsed && !meta.owner) {
    meta.owner = parsed.owner
    meta.repo = parsed.repo
    meta.number = Number(parsed.number)
    meta.kind = parsed.kind
  }
  item = { ...item, metadata_json: meta }
  return { id: '', title: '', associations: [{ item }] }
})

// A standalone view may open a pull request that is already linked to a task:
// adopt that task so the agent panel and task-scoped review rows work. The full
// task detail (with its associations) is fetched so the agent's prompt buttons
// and context resolve, the way they do in the task view.
async function resolveLinkedTask() {
  if (resolvedTask.value || !props.url) return
  const tracked = (store.items || []).find((item) => item.url === props.url)
  const taskId = tracked?.task_ids?.[0]
  if (!taskId) return
  try {
    resolvedTask.value = await api.tasks.get(taskId)
  } catch {
    resolvedTask.value = (store.tasks || []).find((item) => item.id === taskId) || null
  }
}
watch(
  () => [props.url, store.items, store.tasks],
  () => {
    resolveLinkedTask()
  },
  { immediate: true, deep: true }
)

async function adoptTask(task) {
  if (!task?.id) return
  try {
    resolvedTask.value = await api.tasks.get(task.id)
  } catch {
    resolvedTask.value = task
  }
}

// The pull requests to render: the task's linked PRs, or the single PR named by
// `url` when this panel is used as a standalone view.
const linked = computed(() => {
  if (props.url) {
    const parsed = parseGithubUrl(props.url)
    if (!parsed || parsed.kind !== 'pr') return []
    const tracked = (store.items || []).find((item) => item.url === props.url)
    return [
      {
        owner: parsed.owner,
        repo: parsed.repo,
        number: Number(parsed.number),
        url: props.url,
        item: tracked || null,
        item_id: tracked?.id
      }
    ]
  }
  return props.task ? taskPullRequests(props.task) : []
})

// A signature of the linked PRs, so the panel refetches when the links change.
const signature = computed(() => linked.value.map((pr) => `${pr.owner}/${pr.repo}#${pr.number}`).join('|'))

const queue = ref({ prs: [] })
const loading = ref(true)
const error = ref(false)

// Each linked PR paired with its review-queue row, or null when the store has no
// reports for it. The template renders this rather than looking the row up again
// per field.
const items = computed(() => linked.value.map((pr) => ({ pr, row: queueRowFor(queue.value.prs, pr) })))

// Which pane each PR panel shows: "review" (the step row and the findings
// selector) or "reports" (the reports the steps wrote, one tab per step). A
// task may link several pull requests, so the choice is kept per PR.
const activeTabs = ref({})

function rowKey(row) {
  return `${row.repository}#${row.number}`
}

function tabFor(row) {
  return activeTabs.value[rowKey(row)] || 'review'
}

// The reports a row's steps wrote, in the queue's step order, with the
// conditional surface reviews after the chain. One tab per step that has a
// report, carrying its verdict and the commit it covers.
function stepReports(row) {
  const reports = []
  for (const column of [...QUEUE_STEPS, ...SURFACE_STEPS]) {
    const step = row.steps?.[column.key]
    if (step?.report) reports.push({ ...step, key: column.key, label: column.label })
  }
  return reports
}

// The report open in the viewer: the PR it belongs to, its name, and content.
const openKey = ref('')
const openName = ref('')
const reportContent = ref(null)
const reportLoading = ref(false)
const reportTruncated = ref(false)

const reportHtml = computed(() => renderMarkdown(stripReportMarker(reportContent.value)))

// Switch panes, opening the newest report so the reports pane is never blank
// when it has something to show.
function showTab(row, tab) {
  activeTabs.value = { ...activeTabs.value, [rowKey(row)]: tab }
  if (tab !== 'reports') return
  const first = stepReports(row)[0]
  if (first && (openKey.value !== rowKey(row) || !openName.value)) openReport(row, first)
}

// A report tab's tooltip: its step, its verdict, and the commit it covers.
function reportTabTitle(entry) {
  const parts = [entry.label]
  if (entry.verdict) parts.push(entry.verdict)
  if (entry.commit) parts.push(entry.stale ? `${shortCommit(entry.commit)} (stale)` : shortCommit(entry.commit))
  return parts.join(' · ')
}

// The agent panel at the bottom of this view, so a run started by the findings
// selector below a PR shows up there right away.
const agentPanel = ref(null)

// FindingsSelector creates its own run; hand it to the agent panel so its
// transcript opens and the run joins the history.
function onFindingsShared({ run }) {
  agentPanel.value?.adopt(run)
}

// After a findings import creates a task, adopt it so the agent panel appears.
function onImported(task) {
  if (task) {
    store.loadTasks().catch(() => {})
    adoptTask(task)
  }
}

async function load(refresh = false) {
  loading.value = true
  error.value = false
  // Nothing to read when the task links no pull request.
  if (!linked.value.length) {
    queue.value = { prs: [] }
    loading.value = false
    return
  }
  try {
    // The people directory resolves a GitHub login to a person page.
    await store.loadPeople().catch(() => {})
    if (resolvedTask.value?.id) {
      queue.value = await api.reviews.task(resolvedTask.value.id, { refresh })
    } else {
      queue.value = await api.reviews.queue({ refresh })
    }
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

function readinessTitle(row) {
  return READINESS_TITLES[row?.readiness] || ''
}

// A step's column label, for a tooltip. The surface reviews live in their own
// list because the review pane folds them into one row.
function stepLabel(key) {
  const step = QUEUE_STEPS.find((entry) => entry.key === key) || SURFACE_STEPS.find((entry) => entry.key === key)
  return step?.label || key
}

// A step cell's tooltip: its verdict, its reviewed commit, and whether it is
// stale (does not cover the newest reviewed commit). The adversarial review
// also names what it reproduced.
function stepTitle(key, step) {
  const parts = [stepLabel(key)]
  if (step.verdict) parts.push(step.verdict)
  if (key === 'adversarial-pr-review' && step.reproduced_count) parts.push(`${step.reproduced_count} reproduced`)
  if (step.commit) parts.push(step.stale ? `${shortCommit(step.commit)} (stale)` : shortCommit(step.commit))
  return parts.join(' · ')
}

// A running step's tooltip: when its marker was written.
function runningTitle(row, key) {
  const marker = runningStep(row, key)
  const label = stepLabel(key)
  if (!marker) return label
  return marker.started_at ? `${label}: running since ${formatDateTime(marker.started_at)}` : `${label}: running`
}

// Read a report and show it in the PR's reports pane. A step cell in the review
// pane calls this too, so clicking a verdict reads its report in place.
async function openReport(row, step) {
  if (!step?.report || !row) return
  activeTabs.value = { ...activeTabs.value, [rowKey(row)]: 'reports' }
  openKey.value = rowKey(row)
  openName.value = step.report
  reportContent.value = null
  reportTruncated.value = false
  reportLoading.value = true
  try {
    const data = await api.reviews.report(row.repository, row.number, step.report)
    reportContent.value = data.content
    reportTruncated.value = !!data.truncated
  } catch (e) {
    store.notify(e.message, true)
    openKey.value = ''
  } finally {
    reportLoading.value = false
  }
}

onMounted(load)
watch(signature, () => load())
</script>

<template>
  <div class="task-review">
    <GithubItemPanel
      v-for="{ pr, row } in items"
      :key="`${pr.owner}/${pr.repo}#${pr.number}`"
      :url="pr.url"
      :item="pr.item"
      :show-body="!row || tabFor(row) === 'description'"
      :show-reviewers="row ? tabFor(row) === 'description' : !loading"
    >
      <template #head>
        <span v-if="row && READINESS_LIGHTS[row.readiness]" class="task-pr-readiness" :title="readinessTitle(row)">{{
          READINESS_LIGHTS[row.readiness]
        }}</span>
        <button class="btn sm ghost" :disabled="loading" title="Re-read the store and GitHub" @click="load(true)">
          Refresh
        </button>
      </template>

      <!-- The panes sit at the top of the pull request, right under its title,
           so the description, the step verdicts, and the reports are one click
           apart instead of stacked. -->
      <template #tabs>
        <div v-if="row" class="row review-tabs pr-panel-tabs" role="tablist" aria-label="Pull request view">
          <button
            class="btn sm"
            role="tab"
            :class="{ ghost: tabFor(row) !== 'description' }"
            :aria-selected="tabFor(row) === 'description'"
            @click="showTab(row, 'description')"
          >
            Description
          </button>
          <button
            class="btn sm"
            role="tab"
            :class="{ ghost: tabFor(row) !== 'review' }"
            :aria-selected="tabFor(row) === 'review'"
            @click="showTab(row, 'review')"
          >
            Review
          </button>
          <button
            v-if="stepReports(row).length"
            class="btn sm"
            role="tab"
            :class="{ ghost: tabFor(row) !== 'reports' }"
            :aria-selected="tabFor(row) === 'reports'"
            @click="showTab(row, 'reports')"
          >
            Reports <span class="faint">{{ stepReports(row).length }}</span>
          </button>
        </div>
      </template>

      <div v-if="loading && !queue.prs.length" class="empty"><span class="spinner" aria-hidden="true"></span></div>

      <div v-else-if="error">
        <p style="margin: 8px 0 0; color: var(--danger)">Could not load the review queue for this task.</p>
        <button class="btn" @click="load()">Retry</button>
      </div>

      <template v-else-if="row">
        <!-- The review pane: when the pull request was last discussed and
             reviewed, its verdict per step, and the findings selector. -->
        <template v-if="tabFor(row) === 'review'">
          <div class="task-item-meta">
            <span v-if="row.last_comment_at">
              last comment <span class="mono">{{ timeAgo(row.last_comment_at) }}</span>
            </span>
            <span v-if="row.head_commit" class="task-pr-reviewed">
              reviewed
              <a
                v-if="commitUrl(row)"
                class="mono"
                :href="commitUrl(row)"
                target="_blank"
                rel="noopener"
                :title="`Reviewed commit ${row.head_commit}`"
                >{{ shortCommit(row.head_commit) }}</a
              >
              <code v-else>{{ shortCommit(row.head_commit) }}</code>
            </span>
          </div>

          <div class="task-pr-steps">
            <div v-for="column in QUEUE_STEPS" :key="column.key" class="task-pr-step">
              <span class="task-pr-step-label">{{ column.label }}</span>
              <span
                v-if="runningStep(row, column.key)"
                class="review-step-running"
                role="status"
                :title="runningTitle(row, column.key)"
                :aria-label="runningTitle(row, column.key)"
                ><span class="spinner" aria-hidden="true"></span
              ></span>
              <template v-else-if="row.steps?.[column.key]">
                <button
                  class="review-step"
                  :title="stepTitle(column.key, row.steps[column.key])"
                  @click="openReport(row, row.steps[column.key])"
                >
                  <template v-if="column.key === 'assess-pr-risk'">
                    <span
                      v-if="row.steps[column.key].risk"
                      class="review-risk"
                      :class="`tone-${riskTone(row.steps[column.key].risk)}`"
                      >{{ row.steps[column.key].risk[0].toUpperCase() }}</span
                    ><span class="faint"
                      >/{{
                        row.steps[column.key].confidence ? row.steps[column.key].confidence[0].toUpperCase() : '—'
                      }}</span
                    >
                  </template>
                  <span
                    v-if="row.steps[column.key].verdict"
                    :class="
                      column.key === 'assess-pr-risk'
                        ? `tone-${verdictTone(row.steps[column.key].verdict)}`
                        : 'review-verdict'
                    "
                    >{{
                      column.key === 'assess-pr-risk'
                        ? row.steps[column.key].verdict
                        : verdictLabel(row.steps[column.key].verdict)
                    }}</span
                  >
                  <span v-else-if="column.key !== 'assess-pr-risk'" class="faint">local</span>
                  <span v-if="row.steps[column.key].stale && row.steps[column.key].commit" class="review-stale">{{
                    shortCommit(row.steps[column.key].commit)
                  }}</span>
                </button>
              </template>
              <span v-else class="faint task-pr-step-empty">—</span>
            </div>
            <div class="task-pr-step">
              <span class="task-pr-step-label">Surfaces</span>
              <span v-if="surfaceSteps(row).length" class="review-surface-badges">
                <template v-for="entry in surfaceSteps(row)" :key="entry.key">
                  <span
                    v-if="runningStep(row, entry.key)"
                    class="review-step-running"
                    role="status"
                    :title="runningTitle(row, entry.key)"
                    :aria-label="runningTitle(row, entry.key)"
                    ><span class="spinner" aria-hidden="true"></span
                  ></span>
                  <button
                    v-else
                    class="review-step"
                    :title="stepTitle(entry.key, entry.step)"
                    @click="openReport(row, entry.step)"
                  >
                    <span class="review-surface-label">{{ entry.label }}</span>
                    <span
                      v-if="entry.step.verdict"
                      class="review-verdict"
                      :class="`tone-${verdictTone(entry.step.verdict)}`"
                      >{{ verdictLabel(entry.step.verdict) }}</span
                    >
                    <span v-else class="faint">·</span>
                    <span v-if="entry.step.stale && entry.step.commit" class="review-stale">{{
                      shortCommit(entry.step.commit)
                    }}</span>
                  </button>
                </template>
              </span>
              <span v-else class="faint task-pr-step-empty">—</span>
            </div>
          </div>

          <FindingsSelector
            :repository="row.repository"
            :number="row.number"
            :url="pr.url"
            :task-id="resolvedTask?.id || null"
            :task-label="resolvedTask?.title || ''"
            @shared="onFindingsShared"
            @imported="onImported"
          />
        </template>

        <!-- The reports pane: one tab per step that wrote a report, read in
             place instead of a modal. -->
        <template v-else-if="tabFor(row) === 'reports'">
          <div class="row review-tabs pr-report-tabs">
            <button
              v-for="entry in stepReports(row)"
              :key="entry.report"
              class="btn sm"
              :class="{ ghost: !(openKey === rowKey(row) && openName === entry.report) }"
              :title="reportTabTitle(entry)"
              @click="openReport(row, entry)"
            >
              {{ entry.label }}
            </button>
          </div>
          <p v-if="openKey === rowKey(row) && openName" class="faint review-path">{{ openName }}</p>
          <div v-if="openKey === rowKey(row) && reportLoading" class="empty">
            <span class="spinner" aria-hidden="true"></span>
          </div>
          <!-- The report's marker comment is stripped and its HTML sanitized by
               the renderer before it reaches v-html. -->
          <!-- eslint-disable vue/no-v-html -->
          <div
            v-else-if="openKey === rowKey(row) && reportContent !== null"
            class="review-content md"
            v-html="reportHtml"
          ></div>
          <!-- eslint-enable vue/no-v-html -->
          <p v-if="openKey === rowKey(row) && reportTruncated" class="faint">
            Showing the first part of a large report.
          </p>
        </template>
      </template>

      <p v-else class="faint" style="margin: 8px 0 0">
        No review reports for this pull request yet. Run <code>/review-pr-full</code> on it to fill the queue.
      </p>
    </GithubItemPanel>

    <div v-if="!items.length" class="empty">This task is not linked to a pull request.</div>

    <AgentPanel
      ref="agentPanel"
      :task="agentTask"
      :github-url="props.url"
      :harnesses="harnesses"
      context-kind="pull_request"
      @changed="emit('changed')"
      @task-created="adoptTask"
    />
  </div>
</template>
