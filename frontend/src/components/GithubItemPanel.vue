<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import { STATE_LABELS, itemState, parseGithubUrl, personLink } from '../repositories/parse'
import { store, timeAgo } from '../store'

// The detail of one GitHub issue or pull request, read fresh from GitHub and
// falling back to the stored item while the read is in flight or when GitHub
// cannot be reached. Both the task view's issue mode and its PR mode show this
// as the top panel of each linked item, so what the issue or pull request is
// (its state, author, labels, and description) reads the same in both.

const props = defineProps({
  // The item's GitHub URL, which names its kind (issue or pull request).
  url: { type: String, required: true },
  // The stored source item, used as the fallback while the read is in flight.
  item: { type: Object, default: null }
})

const parsed = computed(() => parseGithubUrl(props.url) || {})
// "issue" or "pr", from the URL.
const kind = computed(() => parsed.value.kind || 'issue')
const kindLabel = computed(() => (kind.value === 'pr' ? 'pull request' : 'issue'))

const loading = ref(true)
const error = ref(false)
const data = ref(null)

// The fields the panel shows, preferring the fresh GitHub read and falling back
// to the stored item.
const entry = computed(() => {
  const item = props.item || {}
  const meta = item.metadata_json || {}
  const state = data.value?.state || meta.state
  return {
    owner: parsed.value.owner || '',
    repo: parsed.value.repo || '',
    number: data.value?.number ?? parsed.value.number,
    title: data.value?.title || item.title || '',
    url: data.value?.url || props.url,
    author: data.value?.author || meta.author || '',
    labels: data.value?.labels || [],
    body: data.value?.body || item.content || '',
    state: itemState({
      metadata_json: { state, is_draft: data.value?.is_draft ?? meta.is_draft }
    }),
    created_at: data.value?.created_at || meta.created_at || null
  }
})

// The state badge: its label and class, or null when no state is known.
const status = computed(() =>
  entry.value.state ? { label: STATE_LABELS[entry.value.state], className: `st-${entry.value.state}` } : null
)

// Where the item's author links: the person carrying the login as an alias, or
// the prefilled person-creation page when nobody does yet (rendered grey).
const authorLink = computed(() => personLink(store.people, entry.value.author))

const bodyHtml = computed(() => renderMarkdown(entry.value.body))

async function load() {
  loading.value = true
  error.value = false
  data.value = null
  try {
    data.value = await api.github.issue(props.url)
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => props.url, load)
</script>

<template>
  <section class="panel task-item-panel">
    <div class="panel-head task-item-head">
      <h2 class="task-item-title">
        <span v-if="loading" class="spinner" aria-hidden="true"></span>
        <a :href="entry.url" target="_blank" rel="noopener"> {{ entry.owner }}/{{ entry.repo }}#{{ entry.number }} </a>
        <span v-if="status" class="badge" :class="status.className">{{ status.label }}</span>
        <span v-if="entry.title" class="faint task-item-name" :title="entry.title">{{ entry.title }}</span>
      </h2>
      <!-- Extra head content the host adds (a readiness light, a refresh
           button), ahead of the link out to GitHub. -->
      <slot name="head" />
      <a class="btn sm ghost" :href="entry.url" target="_blank" rel="noopener">Open on GitHub</a>
    </div>

    <div class="task-item-meta">
      <span v-if="entry.author">
        by
        <router-link :to="authorLink.path" :class="{ faint: authorLink.missing }">{{ entry.author }}</router-link>
      </span>
      <span v-if="entry.created_at"
        >opened <span class="mono">{{ timeAgo(entry.created_at) }}</span></span
      >
      <span v-for="label in entry.labels" :key="label" class="badge">{{ label }}</span>
    </div>

    <p v-if="error" class="faint" style="margin: 8px 0 0">
      Could not read the {{ kindLabel }} from GitHub; showing the stored copy.
    </p>

    <!-- The body is Markdown, rendered with the shared renderer and sanitized
         before it reaches v-html. -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div v-if="entry.body" class="md task-item-body" v-html="bodyHtml"></div>
    <p v-else-if="!loading" class="faint" style="margin: 8px 0 0">
      No description stored. Refresh the item or open it on GitHub.
    </p>

    <!-- Host content that follows the description (the review queue's row for a
         pull request). -->
    <slot />
  </section>
</template>
