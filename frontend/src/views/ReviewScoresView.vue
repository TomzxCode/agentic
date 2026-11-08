<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'
import SearchSelect from '../components/SearchSelect.vue'
import ReviewScoreChart from '../components/ReviewScoreChart.vue'
import {
  authorOptions,
  dailyRubricSeries,
  dayLabel,
  filterRuns,
  formatScore,
  repositoryOptions,
  RUBRIC_GROUPS,
  runsSummary,
  scoreTone
} from '../reviewScores'

// The review scores: one line chart per rubric, showing the 0-1 score each
// review step recorded over time. The filters and the daily means are computed
// from the runs the API returns, so the store is read once per page load.

const report = ref({ root: null, rubrics: [], runs: [] })
const loading = ref(true)
const error = ref(false)

// The selected repositories and authors are per-device view preferences, like
// the review queue's filters, so leaving and returning keeps them.
const FILTERS_KEY = 'agentic.reviewScoreFilters'

function readStoredFilters() {
  const defaults = { repositories: [], authors: [] }
  try {
    const stored = JSON.parse(localStorage.getItem(FILTERS_KEY) || 'null')
    if (!stored || typeof stored !== 'object') return defaults
    return {
      repositories: Array.isArray(stored.repositories) ? stored.repositories.map(String) : [],
      authors: Array.isArray(stored.authors) ? stored.authors.map(String) : []
    }
  } catch {
    // Storage can be blocked (private mode), and a stored value can be corrupt.
    return defaults
  }
}

const storedFilters = readStoredFilters()
const repositoryFilter = ref(storedFilters.repositories)
const authorFilter = ref(storedFilters.authors)

watch(
  [repositoryFilter, authorFilter],
  () => {
    try {
      localStorage.setItem(
        FILTERS_KEY,
        JSON.stringify({ repositories: repositoryFilter.value, authors: authorFilter.value })
      )
    } catch {
      // Not fatal: the filters still apply for this session.
    }
  },
  { deep: true }
)

const runs = computed(() => report.value.runs || [])

// The options stay the whole store, so choosing one repository does not make
// the author list look like it lost everyone else.
const repositories = computed(() => repositoryOptions(runs.value))
const authors = computed(() => authorOptions(runs.value))
const repositoryChoices = computed(() =>
  repositories.value.map((entry) => ({ value: entry.value, label: `${entry.value} (${entry.count})` }))
)
const authorChoices = computed(() =>
  authors.value.map((entry) => ({ value: entry.value, label: `${entry.value} (${entry.count})` }))
)

const filteredRuns = computed(() =>
  filterRuns(runs.value, { repositories: repositoryFilter.value, authors: authorFilter.value })
)
const summary = computed(() => runsSummary(filteredRuns.value))
const series = computed(() => dailyRubricSeries(filteredRuns.value))
const groups = computed(() =>
  RUBRIC_GROUPS.map((group) => ({
    group,
    series: series.value.filter((entry) => entry.group === group && entry.points.length)
  })).filter((entry) => entry.series.length)
)
const scoredRubrics = computed(() => series.value.filter((entry) => entry.points.length).length)

function latestPoint(entry) {
  return entry.points[entry.points.length - 1] || null
}

function filterTitle(kind) {
  return kind === 'repositories' ? 'Filter by one or more repositories' : 'Filter by one or more authors'
}

function clearFilters() {
  repositoryFilter.value = []
  authorFilter.value = []
}

async function load() {
  loading.value = true
  error.value = false
  try {
    report.value = await api.reviews.scores()
    // Drop a selected repository or author the refreshed store no longer
    // carries, so a control never filters on something it cannot show.
    const knownRepositories = new Set(repositories.value.map((entry) => entry.value.toLowerCase()))
    repositoryFilter.value = repositoryFilter.value.filter((value) =>
      knownRepositories.has(String(value).toLowerCase())
    )
    const knownAuthors = new Set(authors.value.map((entry) => entry.value.toLowerCase()))
    authorFilter.value = authorFilter.value.filter((value) => knownAuthors.has(String(value).toLowerCase()))
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="review-scores">
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 4px">
      <h1>Review scores</h1>
      <span class="row" style="gap: 8px; align-items: center">
        <span v-if="!loading && !error && summary.reviews" class="faint">
          {{ summary.reviews }} scored review{{ summary.reviews === 1 ? '' : 's' }} · {{ scoredRubrics }} rubric{{
            scoredRubrics === 1 ? '' : 's'
          }}
        </span>
        <button class="btn sm ghost" :disabled="loading" title="Re-read the review store" @click="load">
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          Refresh
        </button>
      </span>
    </div>
    <p class="faint review-scores-intro">
      Each review step records how well a pull request addresses its concern, from 0 (not addressed, or a blocking
      problem) to 1 (fully addressed). The charts average those scores per day.
    </p>
    <p v-if="report.root" class="faint review-root">Reports read from {{ report.root }}</p>

    <div v-if="!loading && !error && runs.length" class="review-filters">
      <SearchSelect
        v-model="repositoryFilter"
        class="review-repository-select"
        multiple
        bulk-actions
        :sort="false"
        :options="repositoryChoices"
        placeholder="All repositories"
        :title="filterTitle('repositories')"
      />
      <SearchSelect
        v-model="authorFilter"
        class="review-author-select"
        multiple
        bulk-actions
        :sort="false"
        :options="authorChoices"
        placeholder="All authors"
        :title="filterTitle('authors')"
      />
      <button v-if="repositoryFilter.length || authorFilter.length" class="btn sm ghost" @click="clearFilters">
        Clear filters
      </button>
    </div>

    <div v-if="loading && !runs.length" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not load the review scores.</p>
      <button class="btn" @click="load">Retry</button>
    </div>

    <div v-else-if="!runs.length" class="empty">
      No review scores yet. Each review step writes a 0-1 score into its report marker, so run
      <code>/review-pr-full</code> on a pull request to start the record.
    </div>

    <div v-else-if="!filteredRuns.length" class="empty">
      <p v-if="repositoryFilter.length && authorFilter.length">
        No scores match {{ repositoryFilter.join(', ') }} by {{ authorFilter.join(', ') }}.
      </p>
      <p v-else-if="repositoryFilter.length">No scores in {{ repositoryFilter.join(', ') }}.</p>
      <p v-else>No scores by {{ authorFilter.join(', ') }}.</p>
      <button class="btn sm ghost" @click="clearFilters">Clear filters</button>
    </div>

    <template v-else>
      <p class="faint review-scores-intro">
        {{ summary.reviews }} review{{ summary.reviews === 1 ? '' : 's' }} averaging {{ formatScore(summary.mean)
        }}<template v-if="summary.first && summary.last">
          · {{ dayLabel(summary.first, true) }} to {{ dayLabel(summary.last, true) }}</template
        >
      </p>

      <section v-for="group in groups" :key="group.group">
        <h2 class="group-head">{{ group.group }}</h2>
        <div class="score-grid">
          <article v-for="entry in group.series" :key="entry.step" class="panel score-card">
            <div class="score-card-head">
              <h3>{{ entry.label }}</h3>
              <span class="badge" :class="scoreTone(entry.mean)">{{ formatScore(entry.mean) }}</span>
            </div>
            <p class="faint score-card-description">{{ entry.description }}</p>
            <ReviewScoreChart :series="entry" />
            <p class="faint score-card-foot">
              {{ entry.count }} review{{ entry.count === 1 ? '' : 's' }}
              <template v-if="latestPoint(entry)">
                · latest {{ formatScore(latestPoint(entry).mean) }} on
                {{ dayLabel(latestPoint(entry).date, true) }}
              </template>
            </p>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>
