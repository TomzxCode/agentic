<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { changeCreateBody } from '../changes'
import { store } from '../store'
import ReviewPeople from '../components/ReviewPeople.vue'
import TaskLink from '../components/TaskLink.vue'

// Ask the shell to reload tasks/tags so the sidebar reflects an action.
const emit = defineEmits(['changed'])

const loading = ref(true)
const error = ref(false)
// The id of the action in flight, so its button shows a spinner and the rest
// of the inbox is not clicked twice.
const busy = ref('')
// The reviewer whose Slack poke is in flight.
const poking = ref(null)

// The section each suggestion kind belongs to, in the order they are shown. The
// API returns them already ordered by kind, so a stable grouping keeps that.
// An unreviewed pull request is split by whether anyone was asked to review it:
// with requested reviewers it can be poked, and with none there is nobody to
// poke, so it is offered separately to find a reviewer.
const SECTIONS = {
  review_pr_past_slo: 'Reviews past SLO',
  poke_pr_no_reviews: 'Poke reviewers',
  find_pr_reviewer: 'Find a reviewer',
  close_task_finished_items: 'Close finished tasks',
  record_change_merged_pr: 'Record changes',
  remove_worktree_done_task: 'Clean up worktrees'
}
const SECTION_ORDER = [
  'review_pr_past_slo',
  'poke_pr_no_reviews',
  'find_pr_reviewer',
  'close_task_finished_items',
  'record_change_merged_pr',
  'remove_worktree_done_task'
]

const suggestions = computed(() => store.inbox)

const sections = computed(() =>
  SECTION_ORDER.map((kind) => ({
    kind,
    label: SECTIONS[kind],
    items: suggestions.value.filter((suggestion) => suggestion.kind === kind)
  })).filter((section) => section.items.length)
)

// The task a suggestion is about, falling back to the copy the API returned
// when the task is not in the store.
function taskFor(suggestion) {
  return (
    store.tasks.find((task) => task.id === suggestion.task_id) || {
      id: suggestion.task_id,
      title: suggestion.task_title,
      status: suggestion.task_status,
      tags: []
    }
  )
}

async function load() {
  loading.value = true
  error.value = false
  try {
    await store.loadTasks()
    // Recording a change reads the item's merge time, so the items are needed.
    await store.loadItems().catch(() => {})
    await store.loadInbox()
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function runAction(suggestion, action) {
  if (busy.value) return
  busy.value = action.id
  try {
    if (action.kind === 'set_task_status') {
      await api.tasks.update(action.task_id, { status: action.status })
      const task = store.tasks.find((entry) => entry.id === action.task_id)
      if (task) task.status = action.status
      store.notify('Task closed')
    } else if (action.kind === 'create_change') {
      await recordChange(suggestion, action)
      store.notify('Change recorded')
    } else if (action.kind === 'remove_worktree') {
      await api.worktrees.remove(action.task_id, action.worktree_id)
      store.notify('Worktree removed')
    }
    emit('changed')
    await store.loadInbox()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = ''
  }
}

// The app's own PR page for a suggestion that names a pull request, so the row
// opens in the app rather than on GitHub. A suggestion without a repository or
// number keeps its external link.
function pullTarget(suggestion) {
  const [owner, repo] = String(suggestion.repository || '').split('/')
  if (!owner || !repo || !suggestion.number) return null
  return `/pr/${owner}/${repo}/${suggestion.number}`
}

// The requested reviewers of a suggestion as the reviewer rows the PR page
// shows: the My PRs read knows no review state, but each was asked, so they
// render as requested and awaiting review, exactly as the item page's live
// GitHub read does for a pending request.
function reviewerRows(suggestion) {
  return (suggestion.reviewers || []).map((login) => ({ login, state: 'PENDING', requested: true }))
}

// Poke one requested reviewer of a pull request on Slack, the same message the
// PR page sends, and report who was reached or why it could not go.
async function pokeReviewer(suggestion, reviewer) {
  if (poking.value) return
  poking.value = reviewer.login
  try {
    const report = await api.myPulls.poke({
      repository: suggestion.repository,
      number: suggestion.number,
      title: suggestion.title,
      url: suggestion.url,
      logins: [reviewer.login]
    })
    const sent = report.poked[0]
    if (sent) store.notify(`Poked ${sent.name || `@${reviewer.login}`} on Slack`)
    else store.notify(report.failed[0]?.reason || 'The poke could not be sent.', true)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    poking.value = null
  }
}

// Record a change for a merged PR, the same way the repository page does: a
// merge time fetched before the PR merged is refreshed once so the change dates
// to the merge, falling back to now when GitHub still reports none.
async function recordChange(suggestion, action) {
  const item = store.items.find((entry) => entry.id === action.item_id)
  if (!item) {
    store.notify('That pull request is no longer in the resources list.', true)
    return
  }
  let mergedAt = item.metadata_json?.merged_at
  if (!mergedAt) {
    const refreshed = await api.items.refresh(item.id)
    if (refreshed) {
      mergedAt = refreshed.metadata_json?.merged_at
      Object.assign(item, refreshed)
    }
  }
  await api.changes.create(changeCreateBody(action.task_id, item, mergedAt || new Date().toISOString()))
}

onMounted(load)
</script>

<template>
  <div>
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 12px">
      <h1>Inbox</h1>
      <span class="row" style="gap: 8px; align-items: center">
        <span class="faint"> {{ suggestions.length }} suggestion{{ suggestions.length === 1 ? '' : 's' }} </span>
        <button class="btn sm ghost" :disabled="loading" @click="load">
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          Refresh
        </button>
      </span>
    </div>

    <div v-if="loading && !suggestions.length" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load the inbox.</p>
      <button class="btn" @click="load">Retry</button>
    </div>

    <div v-else-if="!suggestions.length" class="empty">Inbox zero. Nothing needs a decision right now.</div>

    <template v-else>
      <section v-for="section in sections" :key="section.kind">
        <h2 class="group-head">
          {{ section.label }} <span class="faint">{{ section.items.length }}</span>
        </h2>
        <div v-for="suggestion in section.items" :key="suggestion.id" class="panel inbox-item">
          <div class="row" style="justify-content: space-between; gap: 10px; align-items: flex-start; flex-wrap: wrap">
            <div style="min-width: 0; flex: 1 1 220px">
              <TaskLink v-if="suggestion.task_id" :task="taskFor(suggestion)" />
              <template v-else>
                <router-link v-if="pullTarget(suggestion)" :to="pullTarget(suggestion)">
                  {{ suggestion.title || `${suggestion.repository}#${suggestion.number}` }}
                </router-link>
                <a v-else :href="suggestion.url" target="_blank" rel="noopener">
                  {{ suggestion.title || `${suggestion.repository}#${suggestion.number}` }}
                </a>
                <span v-if="suggestion.title && suggestion.repository" class="faint mono" style="margin-left: 6px">
                  {{ suggestion.repository }}#{{ suggestion.number }}
                </span>
              </template>
              <p class="faint" style="margin: 6px 0 0">{{ suggestion.reason }}</p>
              <!-- The requested reviewers, with their own poke actions, the
                   same rows the PR page shows. -->
              <div
                v-if="suggestion.kind === 'poke_pr_no_reviews' && reviewerRows(suggestion).length"
                style="margin-top: 10px"
              >
                <ReviewPeople
                  :reviewers="reviewerRows(suggestion)"
                  :poking="poking"
                  @poke="(reviewer) => pokeReviewer(suggestion, reviewer)"
                />
              </div>
            </div>
            <span class="row" style="gap: 6px; flex-wrap: wrap">
              <template v-for="action in suggestion.actions" :key="action.id">
                <router-link v-if="action.kind === 'open_pr'" class="btn sm primary" :to="pullTarget(suggestion)">
                  {{ action.label }}
                </router-link>
                <a
                  v-else-if="action.kind === 'open_url'"
                  class="btn sm primary"
                  :href="action.url"
                  target="_blank"
                  rel="noopener"
                >
                  {{ action.label }}
                </a>
                <button v-else class="btn sm primary" :disabled="!!busy" @click="runAction(suggestion, action)">
                  <span v-if="busy === action.id" class="spinner" aria-hidden="true"></span>
                  {{ action.label }}
                </button>
              </template>
            </span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>
