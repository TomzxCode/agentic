<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { store, statusLabel, taskHasPerson, taskHasTag } from '../store'
import { api } from '../api'
import TagInput from '../components/TagInput.vue'
import TaskCard from '../components/TaskCard.vue'

// A task matches when it carries the active tag filter and is linked to the
// active person filter, if either is set.
const matchesFilter = (p) =>
  (!store.tagFilter || taskHasTag(p, store.tagFilter)) && (!store.personFilter || taskHasPerson(p, store.personFilter))

const counts = computed(() => {
  const c = { open: 0, in_progress: 0, blocked: 0, done: 0, archived: 0 }
  for (const p of store.tasks.filter(matchesFilter)) c[p.status] = (c[p.status] || 0) + 1
  return c
})

// The tasks shown in the selectable list. The default view is the work still
// in flight (not done or archived); a status badge at the top narrows it to a
// single status instead. Tag and person filters apply on top of either.
const visible = computed(() => {
  const byStatus = (p) =>
    store.statusFilter ? p.status === store.statusFilter : p.status !== 'done' && p.status !== 'archived'
  return store.tasks.filter(byStatus).filter(matchesFilter)
})

// People linked to at least one in-flight task, with how many each has. Each
// button narrows the page to the tasks linked to that person.
const peopleFilters = computed(() => {
  const byPerson = {}
  for (const p of store.tasks) {
    if (p.status === 'done' || p.status === 'archived') continue
    for (const id of p.person_ids || []) byPerson[id] = (byPerson[id] || 0) + 1
  }
  return store.people
    .filter((person) => byPerson[person.id])
    .map((person) => ({ id: person.id, name: person.name, count: byPerson[person.id] }))
})

const personFilterName = computed(() => store.people.find((person) => person.id === store.personFilter)?.name || '')

// Deadlines coming up: in-flight tasks whose deadline falls within the selected
// window, soonest first. Overdue deadlines always qualify (they are <= the
// window) and sort to the top, which is where they belong.
const deadlineWindow = ref(7)
const upcomingDeadlines = computed(() => {
  const cutoff = Date.now() + deadlineWindow.value * 86400000
  return store.tasks
    .filter((p) => p.deadline && p.status !== 'done' && p.status !== 'archived')
    .filter((p) => new Date(p.deadline).getTime() <= cutoff)
    .filter(matchesFilter)
    .sort((a, b) => new Date(a.deadline) - new Date(b.deadline))
})

const STATUS_VALUES = ['open', 'in_progress', 'blocked', 'done', 'archived']

// The status badges at the top double as filters: click one to show only the
// tasks in that status, click it again to return to the in-flight list.
const STATUS_BADGES = [
  { value: 'open', tone: '' },
  { value: 'in_progress', tone: 'run' },
  { value: 'blocked', tone: 'warn' },
  { value: 'done', tone: 'ok' }
]

// Change a task's status straight from its row.
async function changeStatus(task, status) {
  if (status === task.status) return
  const previous = task.status
  task.status = status
  try {
    await api.tasks.update(task.id, { status })
  } catch (e) {
    task.status = previous
    store.notify(e.message, true)
  }
}

// --- Bulk edit -------------------------------------------------------------

const selected = ref([])
const bulkStatus = ref('')
const addTags = ref([])
const removeTags = ref([])
const applying = ref(false)

const selectedSet = computed(() => new Set(selected.value))
const allSelected = computed(() => visible.value.length > 0 && selected.value.length === visible.value.length)
const canApply = computed(
  () => selected.value.length > 0 && (bulkStatus.value || addTags.value.length || removeTags.value.length)
)

function resetBulk() {
  selected.value = []
  bulkStatus.value = ''
  addTags.value = []
  removeTags.value = []
}

// Changing a filter hides some rows; drop any selection that goes with them
// so a bulk edit only ever touches what is on screen.
watch(() => [store.tagFilter, store.personFilter, store.statusFilter], resetBulk)

function toggle(id) {
  selected.value = selectedSet.value.has(id) ? selected.value.filter((x) => x !== id) : [...selected.value, id]
}

function toggleAll() {
  selected.value = allSelected.value ? [] : visible.value.map((p) => p.id)
}

async function applyBulk() {
  if (!canApply.value || applying.value) return
  applying.value = true
  try {
    const body = { ids: selected.value }
    if (bulkStatus.value) body.status = bulkStatus.value
    if (addTags.value.length) body.add_tags = addTags.value
    if (removeTags.value.length) body.remove_tags = removeTags.value
    const result = await api.tasks.bulkUpdate(body)
    await store.loadTasks()
    const n = result?.updated?.length ?? selected.value.length
    store.notify(`Updated ${n} task${n === 1 ? '' : 's'}`)
    resetBulk()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    applying.value = false
  }
}

onMounted(() => {
  store.loadTasks()
  store.loadPeople().catch(() => {})
})
</script>

<template>
  <div>
    <h1 style="margin-bottom: 16px">Tasks in flight</h1>

    <div v-if="store.tags.length" class="tag-filters" aria-label="Filter by tag">
      <button
        class="tag-filter"
        :class="{ active: !store.tagFilter }"
        type="button"
        title="Show every task"
        @click="store.tagFilter = ''"
      >
        All
      </button>
      <button
        v-for="tag in store.tags"
        :key="tag.name"
        class="tag-filter"
        :class="{ active: store.tagFilter === tag.name }"
        type="button"
        :title="`Show tasks tagged ${tag.name}`"
        @click="store.toggleTagFilter(tag.name)"
      >
        {{ tag.name }} <span class="count">{{ tag.count }}</span>
      </button>
    </div>

    <div v-if="peopleFilters.length" class="tag-filters" aria-label="Filter by person">
      <button
        class="tag-filter"
        :class="{ active: !store.personFilter }"
        type="button"
        title="Show tasks for anyone"
        @click="store.personFilter = ''"
      >
        Anyone
      </button>
      <button
        v-for="person in peopleFilters"
        :key="person.id"
        class="tag-filter"
        :class="{ active: store.personFilter === person.id }"
        type="button"
        :title="`Show tasks linked to ${person.name}`"
        @click="store.togglePersonFilter(person.id)"
      >
        {{ person.name }} <span class="count">{{ person.count }}</span>
      </button>
    </div>

    <div class="row" style="gap: 10px; margin-bottom: 20px" role="group" aria-label="Filter by status">
      <button
        v-for="badge in STATUS_BADGES"
        :key="badge.value"
        type="button"
        class="badge status-badge"
        :class="[badge.tone, { active: store.statusFilter === badge.value }]"
        :aria-pressed="store.statusFilter === badge.value"
        :title="
          store.statusFilter === badge.value
            ? 'Show every task in flight'
            : `Show only ${statusLabel(badge.value).toLowerCase()} tasks`
        "
        @click="store.toggleStatusFilter(badge.value)"
      >
        {{ statusLabel(badge.value) }} {{ counts[badge.value] }}
      </button>
    </div>

    <section
      v-if="upcomingDeadlines.length && !store.statusFilter"
      class="panel deadline-panel"
      aria-label="Upcoming deadlines"
    >
      <div class="panel-head">
        <h2>Upcoming deadlines</h2>
        <label class="faint deadline-window">
          Within
          <select v-model.number="deadlineWindow" class="select deadline-window-select" aria-label="Deadline window">
            <option :value="1">1 day</option>
            <option :value="3">3 days</option>
            <option :value="7">7 days</option>
            <option :value="14">14 days</option>
            <option :value="30">30 days</option>
          </select>
        </label>
      </div>
      <TaskCard
        v-for="p in upcomingDeadlines"
        :key="p.id"
        class="deadline-row"
        :task="p"
        :show-status="false"
        :show-priority="false"
        :show-people="false"
        :show-deadline-time="true"
        :show-age="false"
        :show-next-step="false"
        :show-tags="false"
      />
    </section>

    <div v-if="visible.length && selected.length" class="panel bulk-bar" aria-label="Bulk edit">
      <div class="row" style="gap: 10px">
        <label class="bulk-count">
          <input type="checkbox" :checked="allSelected" aria-label="Select every shown task" @change="toggleAll" />
          {{ selected.length }} selected
        </label>
        <select v-model="bulkStatus" class="select bulk-status" aria-label="Set status">
          <option value="">Set status…</option>
          <option v-for="s in STATUS_VALUES" :key="s" :value="s">{{ statusLabel(s) }}</option>
        </select>
        <TagInput v-model="addTags" :suggestions="store.tags" :suggestion-limit="0" placeholder="Add tags…" />
        <TagInput v-model="removeTags" :suggestions="store.tags" :suggestion-limit="0" placeholder="Remove tags…" />
        <button class="btn primary sm" type="button" :disabled="!canApply || applying" @click="applyBulk">
          {{ applying ? 'Applying…' : 'Apply' }}
        </button>
        <button
          class="btn sm ghost"
          type="button"
          :disabled="!selected.length && !bulkStatus && !addTags.length && !removeTags.length"
          @click="resetBulk"
        >
          Clear
        </button>
      </div>
    </div>

    <section v-if="visible.length" class="panel">
      <TaskCard
        v-for="p in visible"
        :key="p.id"
        :task="p"
        :people="store.people"
        selectable
        :selected="selectedSet.has(p.id)"
        @toggle="toggle"
        @change-status="changeStatus"
      />
    </section>

    <section v-else class="panel">
      <template v-if="store.statusFilter">
        <h2 style="margin-bottom: 8px">No {{ statusLabel(store.statusFilter).toLowerCase() }} tasks</h2>
        <p class="muted">
          No task is currently {{ statusLabel(store.statusFilter).toLowerCase() }}.
          <button class="btn sm ghost" @click="store.statusFilter = ''">Clear filter</button>
        </p>
      </template>
      <template v-else-if="store.tagFilter">
        <h2 style="margin-bottom: 8px">Nothing tagged "{{ store.tagFilter }}"</h2>
        <p class="muted">
          No in-flight task carries this tag.
          <button class="btn sm ghost" @click="store.tagFilter = ''">Clear filter</button>
        </p>
      </template>
      <template v-else-if="store.personFilter">
        <h2 style="margin-bottom: 8px">Nothing linked to "{{ personFilterName || 'this person' }}"</h2>
        <p class="muted">
          No in-flight task is linked to this person.
          <button class="btn sm ghost" @click="store.personFilter = ''">Clear filter</button>
        </p>
      </template>
      <template v-else>
        <h2 style="margin-bottom: 8px">Get started</h2>
        <ol class="muted" style="padding-left: 18px; line-height: 1.9">
          <li>Create a task (the <strong>+</strong> in the sidebar).</li>
          <li>Associate the relevant Slack thread, GitHub issue/PR, or Drive doc.</li>
          <li>Add a repository in <router-link to="/settings">Settings</router-link>, then spin up a worktree.</li>
          <li>Hit <strong>Refresh with agent</strong> to get a current summary and next steps.</li>
          <li>Run an agent to make progress; the transcript streams live.</li>
        </ol>
      </template>
    </section>
  </div>
</template>
