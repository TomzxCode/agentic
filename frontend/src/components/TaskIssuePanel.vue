<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { parseGithubUrl } from '../repositories/parse'
import { store } from '../store'
import { taskIssues } from '../reviews'
import AgentPanel from './AgentPanel.vue'
import GithubItemPanel from './GithubItemPanel.vue'
import TaskGithubLinks from './TaskGithubLinks.vue'

// The task's issue mode: for each GitHub issue the task links (or a single issue
// given by `url`), its current detail (read fresh from GitHub, falling back to
// the stored item) and the Agent panel, so the issue can be worked on through an
// agent instead of the GitHub UI. `task` is optional: a standalone issue view
// has no task, and offers to create one so the agent can run.

const props = defineProps({
  task: { type: Object, default: null },
  harnesses: { type: Array, default: () => [] },
  // A single issue URL to render on its own, without a task association.
  url: { type: String, default: '' },
  // The item selected in the linked-items list, named by its key. Empty falls
  // back to the first linked issue.
  selected: { type: String, default: '' }
})
const emit = defineEmits(['changed'])
const route = useRoute()
const router = useRouter()

const resolvedTask = ref(props.task)
watch(
  () => props.task,
  (value) => {
    resolvedTask.value = value
  }
)

// Even without a linked task, the agent panel can offer its prompt buttons and
// build context from the issue's coordinates, creating a task on the first run.
const agentTask = computed(() => {
  if (resolvedTask.value) return resolvedTask.value
  const tracked = (store.items || []).find((item) => item.url === props.url)
  const parsed = parseGithubUrl(props.url)
  let item = tracked
  if (!item) {
    item = { source: 'github', kind: 'issue', url: props.url, title: '', metadata_json: {} }
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

// A standalone view may open an issue that is already linked to a task: adopt
// that task so the agent panel works without creating a duplicate. The full
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

// The GitHub issues the task links, each with the current state the links
// endpoint read. A standalone view (`url`) has no list, because it renders one
// issue on its own.
const linked = computed(() => (props.task ? taskIssues(props.task) : []))

// The task's GitHub links, read in one request so the list can show each
// issue's current state without a request per item.
const summaries = ref({ issues: [], pulls: [] })

async function loadLinks() {
  if (!resolvedTask.value?.id || props.url) {
    summaries.value = { issues: [], pulls: [] }
    return
  }
  try {
    summaries.value = await api.github.taskLinks(resolvedTask.value.id)
  } catch {
    // The list still renders from the stored items below; a failed read must
    // not hide the issues the task links.
    summaries.value = { issues: [], pulls: [] }
  }
}

onMounted(loadLinks)
watch(
  () => [resolvedTask.value?.id, props.url],
  () => {
    loadLinks()
  }
)

// The issues to render: the single issue named by `url` when this panel is
// used as a standalone view, or the task's linked issues with their state.
const issues = computed(() => {
  if (props.url) {
    const parsed = parseGithubUrl(props.url)
    if (!parsed || parsed.kind !== 'issue') return []
    const tracked = (store.items || []).find((item) => item.url === props.url)
    return [
      {
        key: `${parsed.owner}/${parsed.repo}/${parsed.number}`,
        owner: parsed.owner,
        repo: parsed.repo,
        number: Number(parsed.number),
        url: props.url,
        item: tracked || null,
        item_id: tracked?.id,
        state: tracked?.metadata_json?.state || ''
      }
    ]
  }
  return linked.value.map((issue) => {
    const summary = (summaries.value.issues || []).find(
      (entry) =>
        Number(entry.number) === Number(issue.number) &&
        String(entry.url || '').toLowerCase() === String(issue.url || '').toLowerCase()
    )
    return {
      ...issue,
      key: `${issue.owner}/${issue.repo}/${issue.number}`,
      title: summary?.title || issue.item?.title || '',
      state: summary?.state || issue.item?.metadata_json?.state || ''
    }
  })
})

// The issue the panel renders. A task that links one issue shows it straight
// away; one that links several shows only the list until the user picks a row
// (or the URL names one), so opening the mode does not land on the first issue.
const selectedKey = computed(() => {
  if (props.selected && issues.value.some((issue) => issue.key === props.selected)) return props.selected
  return issues.value.length === 1 ? issues.value[0].key : ''
})

const current = computed(() => issues.value.find((issue) => issue.key === selectedKey.value) || null)

// Return to the list from an open issue, keeping the mode in the URL.
function clearSelection() {
  const query = { ...route.query }
  delete query.item
  router.push({ query })
}
</script>

<template>
  <div class="task-issues">
    <TaskGithubLinks
      v-if="!props.url && issues.length > 1 && !current"
      kind="issue"
      :items="issues"
      :selected="selectedKey"
    />

    <div v-if="!props.url && issues.length > 1 && current" class="task-link-back">
      <button class="btn sm ghost" @click="clearSelection">← All issues</button>
    </div>

    <GithubItemPanel v-if="current" :key="current.key" :url="current.url" :item="current.item" />

    <div v-if="!issues.length" class="empty">This task is not linked to an issue.</div>

    <!-- The interface for interacting with the issue: the task's agent panel,
         whose prompt buttons include the configured issue prompts. -->
    <AgentPanel
      :task="agentTask"
      :github-url="props.url"
      :harnesses="harnesses"
      context-kind="issue"
      @changed="emit('changed')"
      @task-created="adoptTask"
    />
  </div>
</template>
