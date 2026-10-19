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
  shortCommit,
  stripReportMarker,
  taskPullRequests,
  verdictLabel,
  verdictTone
} from '../reviews'
import { personForHandle } from '../repositories/parse'
import { store, timeAgo } from '../store'
import AgentPanel from './AgentPanel.vue'
import FindingsSelector from './FindingsSelector.vue'

// The task's pull-request mode: for each PR the task is linked to, the review
// queue's information for that PR (readiness, reviewed commit, per-step
// verdicts) read from the user-global store the review skills write to. A PR the
// store has no reports for still shows its link, with a note instead of steps.
// The agent panel below them works the pull requests through an agent.

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

// The person carrying a GitHub login as an alias, or null when nobody does.
function personFor(login) {
  return personForHandle(store.people, login)
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
    <div v-if="loading && !queue.prs.length" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load the review queue for this task.</p>
      <button class="btn" @click="load()">Retry</button>
    </div>

    <template v-else>
      <section v-for="{ pr, row } in items" :key="`${pr.owner}/${pr.repo}#${pr.number}`" class="panel task-item-panel">
        <div class="panel-head task-item-head">
          <h2 class="task-item-title">
            <a
              :href="row?.url || pr.url"
              target="_blank"
              rel="noopener"
              :title="[row?.title, readinessTitle(row)].filter(Boolean).join(' — ')"
            >
              <span v-if="row" aria-hidden="true">{{ READINESS_LIGHTS[row.readiness] }}</span>
              {{ row ? `${row.repository}#${row.number}` : `${pr.owner}/${pr.repo}#${pr.number}` }}
            </a>
            <span v-if="row?.draft" class="badge st-draft">draft</span>
            <span v-if="row?.title" class="faint task-item-name" :title="row.title">{{ row.title }}</span>
          </h2>
          <button class="btn sm ghost" :disabled="loading" title="Re-read the store and GitHub" @click="load(true)">
            Refresh
          </button>
        </div>

        <template v-if="row">
          <div class="task-item-meta">
            <span v-if="row.author">
              by
              <router-link v-if="personFor(row.author)" :to="`/person/${personFor(row.author).id}`">{{
                row.author
              }}</router-link>
              <template v-else>{{ row.author }}</template>
            </span>
            <span v-if="row.created_at"
              >opened <span class="mono">{{ timeAgo(row.created_at) }}</span></span
            >
            <span v-if="row.last_comment_at">
              last comment <span class="mono">{{ timeAgo(row.last_comment_at) }}</span>
            </span>
            <span v-if="row.head_commit">
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
              <template v-if="row.steps?.[column.key]">
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
          />
        </template>

        <p v-else class="faint" style="margin: 0">
          No review reports for this pull request yet. Run <code>/review-pr-full</code> on it to fill the queue.
        </p>
      </section>

      <div v-if="!items.length" class="empty">This task is not linked to a pull request.</div>
    </template>

    <!-- The interface for interacting with the pull requests: the task's agent
         panel, whose prompt buttons include the configured PR prompts. It stays
         available while the review queue loads or when it cannot be read, so the
         pull requests can still be worked on through an agent. -->
    <AgentPanel :task="task" :harnesses="harnesses" @changed="emit('changed')" />

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
