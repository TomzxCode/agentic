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
  taskPullRequests,
  verdictLabel,
  verdictTone
} from '../reviews'
import { store, timeAgo, formatDateTime } from '../store'
import AgentPanel from './AgentPanel.vue'
import FindingsSelector from './FindingsSelector.vue'
import GithubItemPanel from './GithubItemPanel.vue'

// The task's pull-request mode: for each PR the task is linked to, the same
// detail panel the issue mode shows for an issue (state, author, labels,
// description, read from GitHub) with the review queue's row for that PR
// below it (readiness, reviewed commit, per-step verdicts) read from the
// user-global store the review skills write to. A PR the store has no reports
// for still shows its detail and link, with a note instead of steps. The agent
// panel below them works the pull requests through an agent.

const props = defineProps({
  task: { type: Object, required: true },
  harnesses: { type: Array, default: () => [] }
})
const emit = defineEmits(['changed'])

// The pull requests the task links, from its associated items.
const linked = computed(() => taskPullRequests(props.task))
// A signature of the linked PRs, so the panel refetches when the links change.
const signature = computed(() => linked.value.map((pr) => `${pr.owner}/${pr.repo}#${pr.number}`).join('|'))

const queue = ref({ prs: [] })
const loading = ref(true)
const error = ref(false)

// Each linked PR paired with its review-queue row, or null when the store has
// no reports for it. The template renders this rather than looking the row up
// again per field.
const items = computed(() => linked.value.map((pr) => ({ pr, row: queueRowFor(queue.value.prs, pr) })))

// The report open in the viewer: its PR row, its name, and content.
const openPr = ref(null)
const openName = ref('')
const reportContent = ref(null)
const reportLoading = ref(false)
const reportTruncated = ref(false)

const reportHtml = computed(() => renderMarkdown(stripReportMarker(reportContent.value)))

// The agent panel at the bottom of this view, so a run started by the findings
// selector below a PR shows up there right away.
const agentPanel = ref(null)

// FindingsSelector creates its own run; hand it to the agent panel so its
// transcript opens and the run joins the history.
function onFindingsShared({ run }) {
  agentPanel.value?.adopt(run)
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
    queue.value = await api.reviews.task(props.task.id, { refresh })
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

// A step cell's tooltip: its verdict, its reviewed commit, and whether it is
// stale (does not cover the newest reviewed commit).
function stepTitle(key, step) {
  const label = QUEUE_STEPS.find((entry) => entry.key === key)?.label || key
  const parts = [label]
  if (step.verdict) parts.push(step.verdict)
  if (step.commit) parts.push(step.stale ? `${shortCommit(step.commit)} (stale)` : shortCommit(step.commit))
  return parts.join(' · ')
}

// A running step's tooltip: when its marker was written.
function runningTitle(row, key) {
  const marker = runningStep(row, key)
  const label = QUEUE_STEPS.find((entry) => entry.key === key)?.label || key
  if (!marker) return label
  return marker.started_at ? `${label}: running since ${formatDateTime(marker.started_at)}` : `${label}: running`
}

async function openReport(row, step) {
  if (!step?.report || !row) return
  openPr.value = row
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
watch(signature, () => load())
</script>

<template>
  <div class="task-review">
    <GithubItemPanel
      v-for="{ pr, row } in items"
      :key="`${pr.owner}/${pr.repo}#${pr.number}`"
      :url="pr.url"
      :item="pr.item"
    >
      <template #head>
        <span v-if="row && READINESS_LIGHTS[row.readiness]" class="task-pr-readiness" :title="readinessTitle(row)">{{
          READINESS_LIGHTS[row.readiness]
        }}</span>
        <button class="btn sm ghost" :disabled="loading" title="Re-read the store and GitHub" @click="load(true)">
          Refresh
        </button>
      </template>

      <div v-if="loading && !queue.prs.length" class="empty"><span class="spinner" aria-hidden="true"></span></div>

      <div v-else-if="error">
        <p style="margin: 8px 0 0; color: var(--danger)">Could not load the review queue for this task.</p>
        <button class="btn" @click="load()">Retry</button>
      </div>

      <template v-else-if="row">
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
        </div>

        <FindingsSelector
          :repository="row.repository"
          :number="row.number"
          :url="row.url"
          :task-id="task.id"
          :task-label="task.title"
          @shared="onFindingsShared"
        />
      </template>

      <p v-else class="faint" style="margin: 8px 0 0">
        No review reports for this pull request yet. Run <code>/review-pr-full</code> on it to fill the queue.
      </p>
    </GithubItemPanel>

    <div v-if="!items.length" class="empty">This task is not linked to a pull request.</div>

    <AgentPanel
      ref="agentPanel"
      :task="task"
      :harnesses="harnesses"
      context-kind="pull_request"
      @changed="emit('changed')"
    />

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
