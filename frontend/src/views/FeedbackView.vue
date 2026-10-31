<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import {
  DECISIONS,
  FEEDBACK_GROUPINGS,
  decisionColor,
  feedbackCounts,
  feedbackSearchBlob,
  groupFeedback,
  orderedSections,
  recommendationColor,
  slugify,
  threadUrl
} from '../feedback'
import { renderMarkdown } from '../markdown'
import { store, timeAgo } from '../store'

// The PR-feedback queue: one card per reviewer comment the
// handle-pr-reviewer-feedback skill analyzed, read from the user-global ~/.sdlc
// store, where a decision is recorded back into the analysis file's frontmatter.
// A decision left without an executed_at is what the skill picks up and runs.

// The grouping and sort are per-device view preferences, remembered in
// localStorage like the tasks page's grouping.
const GROUP_KEY = 'agentic.feedbackGroup'
const SORT_KEY = 'agentic.feedbackSort'

function readStored(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback
  } catch {
    // Storage can be blocked (private mode); fall back to the default.
    return fallback
  }
}

const items = ref([])
const root = ref(null)
const loading = ref(true)
const error = ref(false)
// The feedback id whose decision is being saved, so its buttons disable.
const saving = ref('')

const search = ref('')
const stateFilter = ref('active')
const repoFilter = ref('')
const statusFilter = ref('')
const recFilter = ref('')
const execFilter = ref('')
const selectedAuthors = ref([])
const groupBy = ref(readStored(GROUP_KEY, 'pr'))
const sortBy = ref(readStored(SORT_KEY, 'date-desc'))
// The group the sidebar picked (a pull request under the default grouping).
// Selecting one narrows the list to its items; selecting it again clears it.
const selectedGroup = ref('')

watch(groupBy, (value) => {
  // A group key belongs to one grouping (a PR number is not an author), so the
  // sidebar selection cannot carry over.
  selectedGroup.value = ''
  try {
    localStorage.setItem(GROUP_KEY, value)
  } catch {
    // Not fatal: the choice still applies for this session.
  }
})
watch(sortBy, (value) => {
  try {
    localStorage.setItem(SORT_KEY, value)
  } catch {
    // Not fatal: the choice still applies for this session.
  }
})

async function load(refresh = false) {
  loading.value = true
  error.value = false
  try {
    const payload = await api.feedback.list({ refresh })
    items.value = payload.items || []
    root.value = payload.root || null
    // The nav badge counts the comments still awaiting a decision.
    store.setNavBadge('feedback', feedbackCounts(items.value).pending)
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

// Every item carries the text its card is searched by, computed once per load
// rather than on every keystroke.
const searchBlobs = computed(() => new Map(items.value.map((item) => [item.feedback_id, feedbackSearchBlob(item)])))

const repos = computed(() => [...new Set(items.value.map((item) => item.repo).filter(Boolean))].sort())

const authorCounts = computed(() => {
  const counts = {}
  for (const item of items.value) {
    if (item.author) counts[item.author] = (counts[item.author] || 0) + 1
  }
  return counts
})

function matchesFilters(item) {
  if (
    search.value.trim() &&
    !(searchBlobs.value.get(item.feedback_id) || '').includes(search.value.trim().toLowerCase())
  )
    return false
  if (stateFilter.value === 'active' && item.state === 'closed') return false
  if (stateFilter.value === 'closed' && item.state !== 'closed') return false
  if (repoFilter.value && item.repo !== repoFilter.value) return false
  if (selectedAuthors.value.length && !selectedAuthors.value.includes(item.author)) return false
  if (statusFilter.value && item.status !== statusFilter.value) return false
  if (recFilter.value && item.recommendation !== recFilter.value) return false
  if (execFilter.value && item.run_state !== execFilter.value) return false
  return true
}

const filtered = computed(() => items.value.filter(matchesFilters))
const visible = computed(() => {
  if (!selectedGroup.value) return filtered.value
  const grouping = FEEDBACK_GROUPINGS[groupBy.value] || FEEDBACK_GROUPINGS.pr
  return filtered.value.filter((item) => (grouping.key(item) || '(none)') === selectedGroup.value)
})
const counts = computed(() => feedbackCounts(visible.value))
// The sidebar lists every group the filters leave, so another group is always
// one click away, while the list itself shows only the selected group.
const groups = computed(() => groupFeedback(filtered.value, groupBy.value, sortBy.value))
const shownGroups = computed(() =>
  selectedGroup.value ? groups.value.filter((group) => group.key === selectedGroup.value) : groups.value
)

// A group can disappear when another filter narrows the items, so drop a
// selection that no longer names a group rather than leave an empty list.
watch(groups, (value) => {
  if (selectedGroup.value && !value.some((group) => group.key === selectedGroup.value)) selectedGroup.value = ''
})

const summary = computed(() => {
  const total = visible.value.length
  return `${total} item${total === 1 ? '' : 's'} · ${counts.value.pending} pending`
})

const filterSummary = computed(() => {
  if (selectedAuthors.value.length === 0) return 'All authors'
  if (selectedAuthors.value.length === 1) return selectedAuthors.value[0]
  return `${selectedAuthors.value.length} authors`
})

function toggleAuthor(author) {
  const next = selectedAuthors.value.slice()
  const index = next.indexOf(author)
  if (index < 0) next.push(author)
  else next.splice(index, 1)
  selectedAuthors.value = next
}

function selectAllAuthors(names) {
  selectedAuthors.value = [...names]
}

// Picking a group narrows the list; picking it again goes back to everything.
function toggleGroup(key) {
  selectedGroup.value = selectedGroup.value === key ? '' : key
}

async function setDecision(item, value) {
  const decision = value === 'pending' ? null : value
  saving.value = item.feedback_id
  try {
    const saved = await api.feedback.setDecision(item.feedback_id, decision)
    Object.assign(item, saved)
    store.setNavBadge('feedback', feedbackCounts(items.value).pending)
    store.notify(decision ? `${item.feedback_id} → ${decision}` : `${item.feedback_id} reset`)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    saving.value = ''
  }
}

async function copyReply(item) {
  const text = item.sections?.['Suggested reply']
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    store.notify('Reply copied')
  } catch {
    store.notify('Copy failed', true)
  }
}

function isActive(item, value) {
  return (item.decision || 'pending') === value
}

function runLabel(item) {
  return item.run_state === 'executed' ? 'executed' : item.run_state === 'awaiting' ? 'awaiting run' : ''
}

onMounted(load)
</script>

<template>
  <div class="feedback-page">
    <div class="row feedback-head">
      <h1>PR feedback</h1>
      <span v-if="!loading && !error" class="faint">{{ summary }}</span>
      <span class="grow"></span>
      <button
        class="btn sm ghost"
        :disabled="loading"
        title="Re-read the store and each PR's state"
        @click="load(true)"
      >
        <span v-if="loading" class="spinner" aria-hidden="true"></span>
        Refresh
      </button>
    </div>
    <p v-if="root" class="faint feedback-root">Analysis read from {{ root }}</p>

    <div v-if="loading && !items.length" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load the PR feedback store.</p>
      <button class="btn" @click="load()">Retry</button>
    </div>

    <template v-else>
      <div class="feedback-stats">
        <div class="stat">
          <span class="n">{{ counts.pending }}</span
          ><span class="l">pending</span>
        </div>
        <div class="stat implement">
          <span class="n">{{ counts.implement }}</span
          ><span class="l">implement</span>
        </div>
        <div class="stat decline">
          <span class="n">{{ counts.decline }}</span
          ><span class="l">decline</span>
        </div>
        <div class="stat defer">
          <span class="n">{{ counts.defer }}</span
          ><span class="l">defer</span>
        </div>
        <div class="stat torun">
          <span class="n">{{ counts.to_run }}</span
          ><span class="l">to run</span>
        </div>
      </div>

      <div class="feedback-controls">
        <input v-model="search" class="input" type="search" placeholder="Search title, author, repo, id…" />
        <button
          v-if="selectedGroup"
          type="button"
          class="btn sm ghost feedback-scope"
          :title="`Show every ${FEEDBACK_GROUPINGS[groupBy]?.title.toLowerCase() || 'item'}`"
          @click="selectedGroup = ''"
        >
          Showing {{ selectedGroup }}. Show all
        </button>
        <select v-model="stateFilter" class="select" title="Filter by PR state">
          <option value="active">Active PRs</option>
          <option value="all">All PRs</option>
          <option value="closed">Closed PRs</option>
        </select>
        <select v-model="repoFilter" class="select">
          <option value="">All repos</option>
          <option v-for="repo in repos" :key="repo" :value="repo">{{ repo }}</option>
        </select>
        <details class="filter-menu">
          <summary>{{ filterSummary }}</summary>
          <div class="filter-menu-body">
            <div class="menu-actions">
              <button type="button" class="menu-link" @click="selectAllAuthors(Object.keys(authorCounts))">
                Select all
              </button>
              <button type="button" class="menu-link" @click="selectedAuthors = []">Clear</button>
            </div>
            <label v-for="(count, author) in authorCounts" :key="author" class="menu-item">
              <input type="checkbox" :checked="selectedAuthors.includes(author)" @change="toggleAuthor(author)" />
              <span>{{ author }}</span
              ><span class="menu-count">{{ count }}</span>
            </label>
          </div>
        </details>
        <select v-model="statusFilter" class="select">
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="implement">Implement</option>
          <option value="decline">Decline</option>
          <option value="defer">Defer</option>
        </select>
        <select v-model="recFilter" class="select">
          <option value="">All recommendations</option>
          <option value="implement">implement</option>
          <option value="reject">reject</option>
          <option value="clarify">clarify</option>
          <option value="no-action">no-action</option>
        </select>
        <select v-model="execFilter" class="select" title="Filter by execution state">
          <option value="">Any execution</option>
          <option value="awaiting">Awaiting run</option>
          <option value="executed">Executed</option>
        </select>
        <select v-model="groupBy" class="select" title="Group feedback into sections by">
          <option value="pr">Group: pull request</option>
          <option value="repo">Group: repository</option>
          <option value="author">Group: author</option>
          <option value="recommendation">Group: recommendation</option>
          <option value="status">Group: status</option>
          <option value="kind">Group: type</option>
        </select>
        <select v-model="sortBy" class="select" title="Sort items within each group">
          <option value="date-desc">Sort: newest first</option>
          <option value="date-asc">Sort: oldest first</option>
          <option value="title">Sort: title</option>
          <option value="confidence">Sort: confidence</option>
          <option value="recommendation">Sort: recommendation</option>
          <option value="author">Sort: author</option>
        </select>
      </div>

      <div v-if="!items.length" class="empty">
        No reviewer feedback in the store yet. Run <code>/handle-pr-reviewer-feedback</code> on a PR you authored to
        fill it.
      </div>

      <div v-else class="feedback-layout">
        <aside class="feedback-nav">
          <div class="sidebar-title">{{ FEEDBACK_GROUPINGS[groupBy]?.title || 'Groups' }}</div>
          <button
            type="button"
            class="nav-item"
            :class="{ active: !selectedGroup }"
            :aria-pressed="!selectedGroup"
            @click="selectedGroup = ''"
          >
            <span class="nav-label">All items</span>
            <span class="nav-count">{{ filtered.length }}</span>
          </button>
          <button
            v-for="group in groups"
            :key="group.key"
            type="button"
            class="nav-item"
            :class="{ active: selectedGroup === group.key }"
            :aria-pressed="selectedGroup === group.key"
            :title="`Show only ${group.label}`"
            @click="toggleGroup(group.key)"
          >
            <span class="nav-label">{{ group.label }}</span>
            <span class="nav-count">{{ group.items.length }}</span>
          </button>
        </aside>

        <main class="feedback-list">
          <p v-if="!visible.length" class="empty">No items match the current filters.</p>

          <section v-for="group in shownGroups" :key="group.key" class="feedback-group">
            <div :id="slugify(group.key)" class="group-head">
              <a v-if="group.url" :href="group.url" target="_blank" rel="noopener">{{ group.label }}</a>
              <span v-else>{{ group.label }}</span>
              <span class="faint">
                {{ group.items.length }} item{{ group.items.length === 1 ? '' : 's' }}
                <template v-if="group.pending"> · {{ group.pending }} pending</template>
              </span>
            </div>

            <article
              v-for="item in group.items"
              :key="item.feedback_id"
              class="feedback-card"
              :class="{ pending: item.status === 'pending' }"
              :style="{
                '--rec-color': recommendationColor(item.recommendation),
                '--decision-color': decisionColor(item.decision || 'pending')
              }"
            >
              <div class="card-rail"></div>
              <div class="card-main">
                <div class="card-top">
                  <div class="pills">
                    <span class="pill rec">{{ item.recommendation || 'n/a' }}</span>
                    <span class="pill">{{ item.confidence || '?' }} confidence</span>
                    <span class="pill">{{ item.kind || 'comment' }}</span>
                    <span v-if="item.state === 'closed'" class="pill closed">closed</span>
                    <span
                      class="pill decision"
                      :class="item.status"
                      :style="{ '--c': decisionColor(item.decision || 'pending') }"
                    >
                      {{ item.status }}
                    </span>
                    <span v-if="item.run_state !== 'none'" class="pill run" :class="item.run_state">{{
                      runLabel(item)
                    }}</span>
                  </div>
                  <div class="card-when faint">
                    <span :title="item.created_at">{{ timeAgo(item.created_at) }}</span>
                    <span v-if="!(item.created_at || '').slice(0, 10)" class="faint">—</span>
                  </div>
                </div>

                <h3 class="card-title">{{ item.title }}</h3>
                <div class="card-meta">
                  <a v-if="item.pr_url" :href="item.pr_url" target="_blank" rel="noopener"
                    >{{ item.repo }}#{{ item.pr }}</a
                  >
                  <span v-else>{{ item.repo }}#{{ item.pr }}</span>
                  <span>·</span><span>{{ item.author }}</span> <span>·</span
                  ><span class="mono">{{ item.feedback_id }}</span>
                </div>

                <div class="card-actions">
                  <button
                    v-for="action in DECISIONS"
                    :key="action.value"
                    class="btn sm"
                    :class="[action.value, { active: isActive(item, action.value) }]"
                    :disabled="saving === item.feedback_id"
                    @click="setDecision(item, action.value)"
                  >
                    {{ action.label }}
                  </button>
                  <button
                    class="btn sm pending"
                    :class="{ active: isActive(item, 'pending') }"
                    :disabled="saving === item.feedback_id"
                    @click="setDecision(item, 'pending')"
                  >
                    Reset
                  </button>
                  <span class="grow"></span>
                  <a v-if="threadUrl(item)" class="btn sm ghost" :href="threadUrl(item)" target="_blank" rel="noopener"
                    >Thread</a
                  >
                  <a v-if="item.pr_url" class="btn sm ghost" :href="item.pr_url" target="_blank" rel="noopener">PR</a>
                </div>

                <details
                  v-for="(section, index) in orderedSections(item)"
                  :key="section.name"
                  class="feedback-section"
                  :open="index === 0"
                >
                  <summary>
                    {{ section.name }}
                    <button
                      v-if="section.name === 'Suggested reply'"
                      type="button"
                      class="btn sm ghost reply-copy"
                      @click.prevent.stop="copyReply(item)"
                    >
                      copy
                    </button>
                  </summary>
                  <!-- eslint-disable-next-line vue/no-v-html -->
                  <div class="md feedback-section-body" v-html="renderMarkdown(section.body)"></div>
                </details>
              </div>
            </article>
          </section>
        </main>
      </div>
    </template>
  </div>
</template>
