<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { renderMarkdown } from '../markdown'
import { STATE_LABELS, itemState, parseGithubUrl, personLink } from '../repositories/parse'
import { store, timeAgo } from '../store'
import { ghxItemUrl } from '../toolLinks'
import PullRequestReviewers from './PullRequestReviewers.vue'

// The detail of one GitHub issue or pull request, read fresh from GitHub and
// falling back to the stored item while the read is in flight or when GitHub
// cannot be reached. Both the task view's issue mode and its PR mode show this
// as the top panel of each linked item, so what the issue or pull request is
// (its state, author, labels, and description) reads the same in both.

const props = defineProps({
  // The item's GitHub URL, which names its kind (issue or pull request).
  url: { type: String, required: true },
  // The stored source item, used as the fallback while the read is in flight.
  item: { type: Object, default: null },
  // Whether to render the description. A host with its own panes (the PR view)
  // shows the body only on its description pane.
  showBody: { type: Boolean, default: true },
  // Whether to render the pull request's reviewers. They belong with the
  // description, so a host with panes shows them only on that pane.
  showReviewers: { type: Boolean, default: true }
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

// The same issue or PR in the local ghx UI, when one is configured.
const ghxLink = computed(() => ghxItemUrl({ url: entry.value.url }, store.settings?.ghx_url))

// The state badge: its label and class, or null when no state is known.
const status = computed(() =>
  entry.value.state ? { label: STATE_LABELS[entry.value.state], className: `st-${entry.value.state}` } : null
)

// Where the item's author links: the person carrying the login as an alias, or
// the prefilled person-creation page when nobody does yet (rendered grey).
const authorLink = computed(() => personLink(store.people, entry.value.author))

const bodyHtml = computed(() => renderMarkdown(entry.value.body))

// The reviewer read costs one `gh` call, so it starts the first time the host
// shows the reviewers and stays loaded when the host switches to another pane.
const reviewersMounted = ref(false)
watch(
  () => props.showReviewers,
  (shown) => {
    if (shown) reviewersMounted.value = true
  },
  { immediate: true }
)

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
           button), grouped with the links out so the actions sit together at
           the end of the row instead of spreading across it. -->
      <div class="task-item-actions">
        <slot name="head" />
        <a class="btn sm ghost" :href="entry.url" target="_blank" rel="noopener">Open on GitHub</a>
        <a v-if="ghxLink" class="btn sm ghost" :href="ghxLink" target="_blank" rel="noopener" title="Open in ghx">
          Open in ghx
        </a>
      </div>
    </div>

    <!-- Host tabs (the PR view's Description / Review / Reports panes), at the
         top of the item so they are the first control after its title. -->
    <slot name="tabs" />

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

    <!-- A pull request's reviewers sit right under its author line, since they
         are the people the PR is waiting on. A host with panes (the PR view)
         keeps them on its description pane with the body. -->
    <PullRequestReviewers
      v-if="kind === 'pr' && reviewersMounted"
      v-show="showReviewers"
      :url="entry.url"
      :title="entry.title"
    />

    <p v-if="error" class="faint" style="margin: 8px 0 0">
      Could not read the {{ kindLabel }} from GitHub; showing the stored copy.
    </p>

    <!-- The body is Markdown, rendered with the shared renderer and sanitized
         before it reaches v-html. -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div v-if="showBody && entry.body" class="md task-item-body" v-html="bodyHtml"></div>
    <p v-else-if="showBody && !loading" class="faint" style="margin: 8px 0 0">
      No description stored. Refresh the item or open it on GitHub.
    </p>

    <!-- Host content that follows the description (the review queue's row for a
         pull request). -->
    <slot />
  </section>
</template>
