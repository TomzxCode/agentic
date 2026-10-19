<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import { STATE_LABELS, itemState, personForHandle } from '../repositories/parse'
import { taskIssues } from '../reviews'
import { store, timeAgo } from '../store'
import AgentPanel from './AgentPanel.vue'

// The task's issue mode: for each GitHub issue the task links, its current
// detail (read fresh from GitHub, falling back to the stored item) and the Agent
// panel, so the issue can be worked on through an agent instead of the GitHub UI.

const props = defineProps({
  task: { type: Object, required: true },
  harnesses: { type: Array, default: () => [] }
})
const emit = defineEmits(['changed'])

// The GitHub issues the task links, from its associated items.
const issues = computed(() => taskIssues(props.task))
// A signature of the linked issues, so the panel refetches when the links change.
const signature = computed(() => issues.value.map((issue) => issue.url).join('|'))
// Per issue URL: the fresh GitHub read, or the fact that it could not be read.
const remote = ref({})

// Each linked issue with the fields the panel shows, preferring the fresh
// GitHub read and falling back to the stored item while it is in flight or when
// GitHub cannot be reached.
const entries = computed(() =>
  issues.value.map((issue) => {
    const read = remote.value[issue.url] || {}
    const data = read.data || null
    const item = issue.item || {}
    const meta = item.metadata_json || {}
    return {
      ...issue,
      loading: Boolean(read.loading),
      error: Boolean(read.error),
      number: data?.number ?? issue.number,
      title: data?.title || item.title || '',
      url: data?.url || issue.url,
      author: data?.author || meta.author || '',
      labels: data?.labels || [],
      body: data?.body || item.content || '',
      state: itemState({ metadata_json: { state: data?.state || meta.state } }),
      created_at: meta.created_at || null
    }
  })
)

function statusOf(entry) {
  return entry.state ? { label: STATE_LABELS[entry.state], className: `st-${entry.state}` } : null
}

// The person carrying a GitHub login as an alias, or null when nobody does.
function personFor(handle) {
  return personForHandle(store.people, handle)
}

function bodyHtml(entry) {
  return renderMarkdown(entry.body)
}

async function load() {
  const next = {}
  for (const issue of issues.value) next[issue.url] = { loading: true }
  remote.value = next
  await Promise.all(
    issues.value.map(async (issue) => {
      try {
        const data = await api.github.issue(issue.url)
        remote.value = { ...remote.value, [issue.url]: { data } }
      } catch {
        remote.value = { ...remote.value, [issue.url]: { error: true } }
      }
    })
  )
}

onMounted(load)
watch(signature, () => load())
</script>

<template>
  <div class="task-issues">
    <section v-for="entry in entries" :key="entry.url" class="panel task-item-panel">
      <div class="panel-head task-item-head">
        <h2 class="task-item-title">
          <span v-if="entry.loading" class="spinner" aria-hidden="true"></span>
          <a :href="entry.url" target="_blank" rel="noopener">
            {{ entry.owner }}/{{ entry.repo }}#{{ entry.number }}
          </a>
          <span v-if="statusOf(entry)" class="badge" :class="statusOf(entry).className">{{
            statusOf(entry).label
          }}</span>
          <span v-if="entry.title" class="faint task-item-name" :title="entry.title">{{ entry.title }}</span>
        </h2>
        <a class="btn sm ghost" :href="entry.url" target="_blank" rel="noopener">Open on GitHub</a>
      </div>

      <div class="task-item-meta">
        <span v-if="entry.author">
          by
          <router-link v-if="personFor(entry.author)" :to="`/person/${personFor(entry.author).id}`">{{
            entry.author
          }}</router-link>
          <template v-else>{{ entry.author }}</template>
        </span>
        <span v-if="entry.created_at"
          >opened <span class="mono">{{ timeAgo(entry.created_at) }}</span></span
        >
        <span v-for="label in entry.labels" :key="label" class="badge">{{ label }}</span>
      </div>

      <p v-if="entry.error" class="faint" style="margin: 8px 0 0">
        Could not read the issue from GitHub; showing the stored copy.
      </p>

      <!-- The body is Markdown, rendered with the shared renderer and sanitized
           before it reaches v-html. -->
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div v-if="entry.body" class="md task-issue-body" v-html="bodyHtml(entry)"></div>
      <p v-else-if="!entry.loading" class="faint" style="margin: 8px 0 0">
        No description stored. Refresh the item or open the issue on GitHub.
      </p>
    </section>

    <div v-if="!entries.length" class="empty">This task is not linked to an issue.</div>

    <!-- The interface for interacting with the issue: the task's agent panel,
         whose prompt buttons include the configured issue prompts. -->
    <AgentPanel :task="task" :harnesses="harnesses" @changed="emit('changed')" />
  </div>
</template>
