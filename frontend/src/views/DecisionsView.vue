<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import {
  DECISION_BUCKETS,
  bucketColor,
  cellDecisions,
  decisionCounts,
  decisionMatrix,
  filterDecisions,
  groupDecisions,
  nameSlug,
  pctColor,
  shiftDays
} from '../decisions'
import { store } from '../store'

// The colleague-decisions page: every decision the extract-colleague-decisions
// skill recorded in the notes tree, read through /api/decisions. Decisions are
// grouped by their author, by who supported them, or by who opposed them, with
// a support/opposition matrix over the same rows.

const data = ref(null)
const loading = ref(true)
const error = ref(false)

// The active view is a per-device view preference, remembered in localStorage
// like the feedback page's grouping. The matrix's support/oppose mode is not
// stored: it is a look at the same rows, not the page's main choice.
const VIEW_KEY = 'agentic.decisionsView'
const VIEWS = ['authors', 'supporters', 'opponents', 'matrix']
function readStored(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback
  } catch {
    // Storage can be blocked (private mode); fall back to the default.
    return fallback
  }
}

const stored = readStored(VIEW_KEY, 'authors')
const view = ref(VIEWS.includes(stored) ? stored : 'authors')
const matrixMode = ref('support')
const cell = ref(null)

const search = ref('')
const from = ref('')
const to = ref('')
const preset = ref('')
const buckets = ref([])
// Set while a preset fills both dates, so the range watcher does not wipe the
// preset it just applied.
let applyingPreset = false

watch(view, (value) => {
  try {
    localStorage.setItem(VIEW_KEY, value)
  } catch {
    // Not fatal: the choice still applies for this session.
  }
})

const decisions = computed(() => data.value?.decisions || [])

// The search and date filters run first, so the status chips can count what is
// in range; the bucket filter then narrows the list and the matrix.
const base = computed(() => filterDecisions(decisions.value, { q: search.value, from: from.value, to: to.value }))
const visible = computed(() => filterDecisions(base.value, { buckets: buckets.value }))
const counts = computed(() => decisionCounts(visible.value))
const baseCounts = computed(() => decisionCounts(base.value))

const bucketChips = computed(() => {
  const found = new Set([...DECISION_BUCKETS, ...Object.keys(baseCounts.value.buckets)])
  return [...found].map((bucket) => ({
    bucket,
    count: baseCounts.value.buckets[bucket] || 0,
    active: buckets.value.includes(bucket),
    color: bucketColor(bucket)
  }))
})

const groups = computed(() => {
  if (view.value === 'authors') return groupDecisions(visible.value, 'author')
  if (view.value === 'supporters') return groupDecisions(visible.value, 'supported_by')
  if (view.value === 'opponents') return groupDecisions(visible.value, 'opposed_by')
  return []
})

// The sidebar always names all three sets of people, so a click can switch to
// the matching view even while another one is showing.
const navGroups = computed(() => [
  { id: 'authors', title: 'Authors', target: 'authors', groups: groupDecisions(visible.value, 'author') },
  {
    id: 'supporters',
    title: 'Supporters',
    target: 'supporters',
    groups: groupDecisions(visible.value, 'supported_by')
  },
  { id: 'opponents', title: 'Opponents', target: 'opponents', groups: groupDecisions(visible.value, 'opposed_by') }
])

const matrix = computed(() => decisionMatrix(visible.value, matrixMode.value))
const detail = computed(() => (cell.value ? cellDecisions(visible.value, cell.value, matrixMode.value) : []))

const rangeStart = computed(() => data.value?.range?.start || '')
const rangeEnd = computed(() => data.value?.range?.end || '')

const summary = computed(() => {
  const parts = [
    `${counts.value.total} decision${counts.value.total === 1 ? '' : 's'}`,
    `${counts.value.people} ${counts.value.people === 1 ? 'person' : 'people'}`,
    `${counts.value.supporters} ${counts.value.supporters === 1 ? 'supporter' : 'supporters'}`,
    `${counts.value.opponents} ${counts.value.opponents === 1 ? 'opponent' : 'opponents'}`
  ]
  if (data.value?.range) parts.push(`${data.value.range.start} to ${data.value.range.end}`)
  return parts.join(' · ')
})

const generated = computed(() => {
  const value = data.value?.generated_at
  if (!value) return ''
  const moment = new Date(value)
  return Number.isNaN(moment.getTime()) ? value : moment.toLocaleString()
})

const headline = (author) => data.value?.headlines?.[author] || ''

async function load() {
  loading.value = true
  error.value = false
  try {
    data.value = await api.decisions.list()
  } catch (e) {
    error.value = true
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

function setView(next) {
  if (!VIEWS.includes(next)) return
  view.value = next
  cell.value = null
}

function clearDates() {
  from.value = ''
  to.value = ''
  preset.value = ''
}

// A date range entered backwards is read the way the reader meant it.
watch([from, to], () => {
  if (applyingPreset) {
    applyingPreset = false
    return
  }
  if (from.value && to.value && from.value > to.value) {
    const earlier = to.value
    to.value = from.value
    from.value = earlier
  }
  preset.value = ''
})

function applyPreset(days) {
  if (!rangeEnd.value) return
  applyingPreset = true
  from.value = shiftDays(rangeEnd.value, -(Number(days) - 1))
  to.value = rangeEnd.value
  preset.value = String(days)
}

function toggleBucket(bucket) {
  buckets.value = buckets.value.includes(bucket)
    ? buckets.value.filter((entry) => entry !== bucket)
    : [...buckets.value, bucket]
}

function toggleCell(author, person, diagonal) {
  const current = cell.value
  const same =
    current && current.author === author && current.diagonal === diagonal && (diagonal || current.person === person)
  cell.value = same ? null : { author, person, diagonal }
}

function selectedCell(cellValue) {
  const current = cell.value
  if (!current || current.author !== cellValue.author) return false
  if (cellValue.diagonal) return Boolean(current.diagonal)
  return !current.diagonal && current.person === cellValue.person
}

async function jump(target, name) {
  setView(target)
  await nextTick()
  const section = document.getElementById(nameSlug(name))
  if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

onMounted(load)
</script>

<template>
  <div class="decisions-page">
    <div class="row decisions-head">
      <h1>Colleague decisions</h1>
      <span v-if="!loading && !error" class="faint">{{ summary }}</span>
      <span class="grow"></span>
      <button class="btn sm ghost" :disabled="loading" title="Re-read the notes tree" @click="load">
        <span v-if="loading" class="spinner" aria-hidden="true"></span>
        Refresh
      </button>
    </div>
    <p v-if="data?.root" class="faint decisions-root">Reports read from {{ data.root }} · generated {{ generated }}</p>

    <div v-if="loading && !decisions.length" class="empty"><span class="spinner" aria-hidden="true"></span></div>

    <div v-else-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">Could not read the colleague-decisions reports.</p>
      <button class="btn" @click="load">Retry</button>
    </div>

    <template v-else>
      <div class="decisions-stats">
        <div class="stat">
          <span class="n">{{ counts.total }}</span
          ><span class="l">decisions</span>
        </div>
        <div class="stat">
          <span class="n">{{ counts.people }}</span
          ><span class="l">people</span>
        </div>
        <div class="stat yes">
          <span class="n">{{ counts.supporters }}</span
          ><span class="l">supporters</span>
        </div>
        <div class="stat no">
          <span class="n">{{ counts.opponents }}</span
          ><span class="l">opponents</span>
        </div>
        <div class="stat">
          <span class="n">{{ data?.reports || 0 }}</span
          ><span class="l">reports</span>
        </div>
      </div>

      <div class="decisions-controls">
        <input
          v-model="search"
          class="input"
          type="search"
          placeholder="Search text, person, supporter, date, status…"
        />
        <input v-model="from" class="input date" type="date" :min="rangeStart" :max="rangeEnd" aria-label="From date" />
        <input v-model="to" class="input date" type="date" :min="rangeStart" :max="rangeEnd" aria-label="To date" />
        <button type="button" class="btn sm ghost" :disabled="!from && !to" @click="clearDates">All dates</button>
        <div class="decisions-presets">
          <button
            v-for="days in [7, 30, 90]"
            :key="days"
            type="button"
            class="preset"
            :class="{ active: preset === String(days) }"
            :aria-pressed="preset === String(days)"
            :disabled="!rangeEnd"
            @click="applyPreset(days)"
          >
            Last {{ days }}d
          </button>
        </div>
      </div>

      <div class="decisions-controls decisions-status">
        <span class="faint">Status</span>
        <button
          v-for="chip in bucketChips"
          :key="chip.bucket"
          type="button"
          class="status-chip"
          :class="{ active: chip.active }"
          :aria-pressed="chip.active"
          :style="{ '--bucket-color': chip.color }"
          @click="toggleBucket(chip.bucket)"
        >
          {{ chip.bucket }}<span class="cnt">{{ chip.count }}</span>
        </button>
        <button v-if="buckets.length" type="button" class="status-chip clear" @click="buckets = []">All</button>
      </div>

      <div class="decisions-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          :aria-selected="view === 'authors'"
          :class="{ active: view === 'authors' }"
          @click="setView('authors')"
        >
          By author
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="view === 'supporters'"
          :class="{ active: view === 'supporters' }"
          @click="setView('supporters')"
        >
          By supporter
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="view === 'opponents'"
          :class="{ active: view === 'opponents' }"
          @click="setView('opponents')"
        >
          By opponent
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="view === 'matrix'"
          :class="{ active: view === 'matrix' }"
          @click="setView('matrix')"
        >
          Matrix
        </button>
      </div>

      <div v-if="!decisions.length" class="empty">
        <template v-if="data?.root">
          No decisions reports found under <code>{{ data.root }}</code
          >. Run <code>/extract-colleague-decisions</code> to write one under <code>decisions/YYYY/MM/DD.md</code>.
        </template>
        <template v-else>
          No notes directory found. Set <code>AGENTIC_NOTES_DIR</code> (or <code>NOTES_DIR</code>) to the notes root
          that holds the <code>decisions/</code> reports.
        </template>
      </div>

      <div v-else-if="view === 'matrix'" class="decisions-matrix">
        <div class="decisions-tabs matrix-mode">
          <button
            type="button"
            :class="{ active: matrixMode === 'support' }"
            :aria-pressed="matrixMode === 'support'"
            @click="matrixMode = 'support'"
          >
            Support
          </button>
          <button
            type="button"
            :class="{ active: matrixMode === 'oppose' }"
            :aria-pressed="matrixMode === 'oppose'"
            @click="matrixMode = 'oppose'"
          >
            Oppose
          </button>
        </div>
        <p v-if="!matrix.authors.length" class="empty">No decisions match the current filters.</p>
        <template v-else>
          <div class="matrix-wrap">
            <table>
              <thead>
                <tr>
                  <th class="row">Author \ {{ matrix.pct === 'Opposed' ? 'Opponent' : 'Supporter' }}</th>
                  <th v-for="person in matrix.people" :key="person">{{ person }}</th>
                  <th>{{ matrix.pct }}</th>
                  <th>Received</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in matrix.rows" :key="row.author">
                  <th class="row">{{ row.author }}</th>
                  <td
                    v-for="entry in row.cells"
                    :key="entry.person"
                    :class="{
                      diag: entry.diagonal,
                      zero: !entry.count && !entry.diagonal,
                      clickable: Boolean(entry.count || entry.diagonal),
                      selected: selectedCell({ author: row.author, person: entry.person, diagonal: entry.diagonal })
                    }"
                    :title="
                      entry.diagonal
                        ? `Decisions made by ${row.author}`
                        : `${entry.count} of ${row.total} decisions ${matrix.verb} ${entry.person} (${entry.pct}%)`
                    "
                    :tabindex="entry.count || entry.diagonal ? 0 : undefined"
                    @click="toggleCell(row.author, entry.person, entry.diagonal)"
                    @keydown.enter.prevent="toggleCell(row.author, entry.person, entry.diagonal)"
                    @keydown.space.prevent="toggleCell(row.author, entry.person, entry.diagonal)"
                  >
                    <template v-if="entry.diagonal">
                      <span class="n">{{ entry.count }}</span>
                    </template>
                    <template v-else-if="entry.count">
                      <span class="n">{{ entry.count }}</span
                      ><span class="sub">{{ entry.pct }}%</span>
                    </template>
                    <template v-else>·</template>
                  </td>
                  <td
                    class="pct"
                    :style="{ '--cell-color': pctColor(row.pct) }"
                    :title="`${row.pct}% of ${row.author}'s decisions have at least one ${matrix.noun}`"
                  >
                    <span class="n">{{ row.pct }}%</span>
                  </td>
                  <td>
                    <span class="n">{{ row.received }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="faint decisions-legend">
            Rows are decision authors, columns are {{ matrix.noun }}s. The diagonal is the decisions made; an
            off-diagonal cell is the decisions by the row's author {{ matrix.verb }} the column's {{ matrix.noun }}, as
            a count and as a share of that author's decisions. {{ matrix.pct }} is the share of the author's decisions
            with at least one {{ matrix.noun }}; Received is the total. Click a cell to list its decisions.
          </p>

          <div v-if="cell" class="cell-detail">
            <div class="cell-detail-head">
              <h3>
                <template v-if="cell.diagonal">
                  {{ cell.author }}: {{ detail.length }} decision{{ detail.length === 1 ? '' : 's' }} made
                </template>
                <template v-else>
                  {{ cell.author }} {{ matrix.verb }} {{ cell.person }}: {{ detail.length }} decision{{
                    detail.length === 1 ? '' : 's'
                  }}
                </template>
              </h3>
              <button type="button" class="btn sm ghost" @click="cell = null">Clear</button>
            </div>
            <p v-if="!detail.length" class="empty">No decisions for this combination under the current filter.</p>
            <article
              v-for="decision in detail"
              :key="decision.date + decision.author + decision.text"
              class="decision-card"
              :style="{ '--bucket-color': bucketColor(decision.bucket) }"
            >
              <div class="decision-top">
                <span class="bucket">{{ decision.bucket }}</span>
                <span class="faint">{{ decision.date }}</span>
              </div>
              <p class="decision-text">{{ decision.text }}</p>
              <div v-if="decision.supported_by.length" class="relation yes">
                <span class="relation-label">Supported by</span>
                <span v-for="name in decision.supported_by" :key="name" class="person-chip">{{ name }}</span>
              </div>
              <div v-if="decision.opposed_by.length" class="relation no">
                <span class="relation-label">Opposed by</span>
                <span v-for="name in decision.opposed_by" :key="name" class="person-chip">{{ name }}</span>
              </div>
            </article>
          </div>
        </template>
      </div>

      <div v-else class="decisions-layout">
        <aside class="decisions-nav">
          <div v-for="group in navGroups" :key="group.id" class="nav-group">
            <template v-if="group.groups.length">
              <div class="sidebar-title">{{ group.title }}</div>
              <a
                v-for="person in group.groups"
                :key="person.name"
                class="nav-item"
                href="#"
                @click.prevent="jump(group.target, person.name)"
              >
                <span class="nav-label">{{ person.name }}</span>
                <span class="nav-count">{{ person.items.length }}</span>
              </a>
            </template>
          </div>
        </aside>

        <main class="decisions-list">
          <p v-if="!groups.length" class="empty">No decisions match the current filters.</p>
          <section v-for="group in groups" :id="nameSlug(group.name)" :key="group.name" class="decisions-group">
            <div class="group-head">
              <h2>{{ group.name }}</h2>
              <span class="faint">
                <template v-if="view === 'authors'">
                  {{ group.items.length }} item{{ group.items.length === 1 ? '' : 's' }}
                </template>
                <template v-else-if="view === 'supporters'">
                  backed {{ group.items.length }} decision{{ group.items.length === 1 ? '' : 's' }}
                </template>
                <template v-else>
                  opposed {{ group.items.length }} decision{{ group.items.length === 1 ? '' : 's' }}
                </template>
              </span>
            </div>
            <p v-if="view === 'authors' && headline(group.name)" class="decisions-headline">
              {{ headline(group.name) }}
            </p>

            <article
              v-for="decision in group.items"
              :key="decision.date + decision.author + decision.text"
              class="decision-card"
              :style="{ '--bucket-color': bucketColor(decision.bucket) }"
            >
              <div class="decision-top">
                <span class="bucket">{{ decision.bucket }}</span>
                <span v-if="view !== 'authors'" class="person-chip author">{{ decision.author }}</span>
                <span class="faint">{{ decision.date }}</span>
                <span class="grow"></span>
                <a v-if="decision.permalink" :href="decision.permalink" target="_blank" rel="noopener">Open in Slack</a>
              </div>
              <p class="decision-text">{{ decision.text }}</p>
              <div v-if="decision.supported_by.length" class="relation yes">
                <span class="relation-label">Supported by</span>
                <span v-for="name in decision.supported_by" :key="name" class="person-chip">{{ name }}</span>
              </div>
              <div v-if="decision.opposed_by.length" class="relation no">
                <span class="relation-label">Opposed by</span>
                <span v-for="name in decision.opposed_by" :key="name" class="person-chip">{{ name }}</span>
              </div>
            </article>
          </section>
        </main>
      </div>

      <footer class="decisions-footer">
        <template v-if="data?.not_heard?.length">
          <div class="faint">Not heard from</div>
          <p class="not-heard">{{ data.not_heard.join(', ') }}</p>
        </template>
        <div v-for="(note, index) in data?.cross_cutting || []" :key="index" class="cross-cutting">
          <div class="faint">Cross-cutting</div>
          <p>{{ note }}</p>
        </div>
      </footer>
    </template>
  </div>
</template>
