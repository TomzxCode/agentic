<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { parseGithubUrl } from '../repositories/parse'
import { store } from '../store'
import { taskIssues } from '../reviews'
import AgentPanel from './AgentPanel.vue'
import GithubItemPanel from './GithubItemPanel.vue'

// The task's issue mode: for each GitHub issue the task links (or a single issue
// given by `url`), its current detail (read fresh from GitHub, falling back to
// the stored item) and the Agent panel, so the issue can be worked on through an
// agent instead of the GitHub UI. `task` is optional: a standalone issue view
// has no task, and offers to create one so the agent can run.

const props = defineProps({
  task: { type: Object, default: null },
  harnesses: { type: Array, default: () => [] },
  // A single issue URL to render on its own, without a task association.
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

// The GitHub issues to render: the task's linked issues, or the single issue
// named by `url` when this panel is used as a standalone view.
const issues = computed(() => {
  if (props.url) {
    const parsed = parseGithubUrl(props.url)
    if (!parsed || parsed.kind !== 'issue') return []
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
  return props.task ? taskIssues(props.task) : []
})
</script>

<template>
  <div class="task-issues">
    <GithubItemPanel v-for="issue in issues" :key="issue.url" :url="issue.url" :item="issue.item" />

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
