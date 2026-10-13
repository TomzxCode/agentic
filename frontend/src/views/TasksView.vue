<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { deadlineInfo, formatDeadline, store, statusLabel, taskHasPerson, taskHasTag, timeAgo } from '../store'
import { api } from '../api'
import TagInput from '../components/TagInput.vue'
import SearchSelect from '../components/SearchSelect.vue'
import StatusIcon from '../components/StatusIcon.vue'
import PriorityIcon from '../components/PriorityIcon.vue'

// A task matches when it carries the active tag filter and is linked to the
// active person filter, if either is set.
const matchesFilter = (p) =>
  (!store.tagFilter || taskHasTag(p, store.tagFilter)) && (!store.personFilter || taskHasPerson(p, store.personFilter))

// Row timestamps: how long the task has existed and how long since it last
// changed. The two collapse to one when they describe the same moment (a task
// that has not been touched since it was created).
function taskAge(p) {
  const created = timeAgo(p.created_at)
  const updated = timeAgo(p.updated_at)
  if (created && updated && created !== updated) return `created ${created} · updated ${updated}`
  if (created) return `created ${created}`
  return updated ? `updated ${updated}` : ''
}

const counts = computed(() => {
  const c = { open: 0, in_progress: 0, blocked: 0, done: 0, archived: 0 }
  for (const p of store.tasks.filter(matchesFilter)) c[p.status] = (c[p.status] || 0) + 1
  return c
})

// Every task still in flight and matching the active filters. This is the
// page's default view: a selectable list you can edit in bulk.
const inFlight = computed(() =>
  store.tasks.filter((p) => p.status !== 'done' && p.status !== 'archived').filter(matchesFilter)
)

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

const peopleById = computed(() => Object.fromEntries(store.people.map((person) => [person.id, person])))

// People linked to a task, in link order, skipping any id that no longer
// resolves to a person in the directory.
function taskPeople(task) {
  return (task.person_ids || []).map((id) => peopleById.value[id]).filter(Boolean)
}

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

// 0 = low, 1 = medium, 2 = high, 3 = urgent. Used as the priority icon's label.
const PRIORITY_NAMES = { 0: 'low', 1: 'medium', 2: 'high', 3: 'urgent' }
const priorityLabel = (priority) => `Priority: ${PRIORITY_NAMES[Number(priority)] || 'medium'}`

// The status picker shown on each row, the same icon-only control the sidebar uses.
const statusOptions = STATUS_VALUES.map((value) => ({
  value,
  label: statusLabel(value),
  icon: StatusIcon,
  iconProps: { status: value, label: statusLabel(value) }
}))

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
const allSelected = computed(() => inFlight.value.length > 0 && selected.value.length === inFlight.value.length)
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
watch(() => [store.tagFilter, store.personFilter], resetBulk)

function toggle(id) {
  selected.value = selectedSet.value.has(id) ? selected.value.filter((x) => x !== id) : [...selected.value, id]
}

function toggleAll() {
  selected.value = allSelected.value ? [] : inFlight.value.map((p) => p.id)
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

    <div class="row" style="gap: 10px; margin-bottom: 20px">
      <span class="badge">Open {{ counts.open }}</span>
      <span class="badge run">In progress {{ counts.in_progress }}</span>
      <span class="badge warn">Blocked {{ counts.blocked }}</span>
      <span class="badge ok">Done {{ counts.done }}</span>
    </div>

    <section v-if="upcomingDeadlines.length" class="panel deadline-panel" aria-label="Upcoming deadlines">
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
      <div v-for="p in upcomingDeadlines" :key="p.id" class="item deadline-row">
        <div class="item-body">
          <div class="item-top">
            <span class="badge" :class="deadlineInfo(p.deadline).tone">{{ deadlineInfo(p.deadline).label }}</span>
            <router-link :to="`/task/${p.id}`" class="title">{{ p.title }}</router-link>
            <span class="faint">{{ formatDeadline(p.deadline) }}</span>
          </div>
        </div>
      </div>
    </section>

    <div v-if="inFlight.length && selected.length" class="panel bulk-bar" aria-label="Bulk edit">
      <div class="row" style="gap: 10px">
        <label class="bulk-count">
          <input type="checkbox" :checked="allSelected" aria-label="Select every task in flight" @change="toggleAll" />
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

    <section v-if="inFlight.length" class="panel">
      <div v-for="p in inFlight" :key="p.id" class="item select-item" :class="{ selected: selectedSet.has(p.id) }">
        <input
          type="checkbox"
          class="row-check"
          :checked="selectedSet.has(p.id)"
          :aria-label="`Select ${p.title}`"
          @change="toggle(p.id)"
        />
        <div class="item-body">
          <div class="item-top">
            <SearchSelect
              class="task-status-select"
              variant="icon"
              :model-value="p.status"
              :options="statusOptions"
              :sort="false"
              title="Change status"
              @update:model-value="(value) => changeStatus(p, value)"
            />
            <PriorityIcon :priority="p.priority" :label="priorityLabel(p.priority)" />
            <div class="title-group">
              <router-link :to="`/task/${p.id}`" class="title">{{ p.title }}</router-link>
              <button
                v-for="person in taskPeople(p)"
                :key="person.id"
                type="button"
                class="person-chip"
                :class="{ active: store.personFilter === person.id }"
                :title="`Filter by ${person.name}`"
                @click="store.togglePersonFilter(person.id)"
              >
                {{ person.name }}
              </button>
            </div>
            <span
              v-if="p.deadline"
              class="badge"
              :class="deadlineInfo(p.deadline).tone"
              :title="`Deadline: ${formatDeadline(p.deadline)}`"
              >{{ deadlineInfo(p.deadline).label }}</span
            >
            <span class="faint">{{ taskAge(p) }}</span>
          </div>
          <div v-if="p.next_steps?.filter((s) => !s.done).length" class="faint" style="margin-top: 6px">
            Next: {{ p.next_steps.find((s) => !s.done).text }}
          </div>
          <div v-if="p.tags?.length" class="task-tags" style="margin-top: 6px">
            <button
              v-for="tag in p.tags"
              :key="tag"
              type="button"
              class="tag-chip"
              :class="{ active: store.tagFilter === tag }"
              :title="`Filter by ${tag}`"
              @click="store.toggleTagFilter(tag)"
            >
              {{ tag }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <section v-else class="panel">
      <template v-if="store.tagFilter">
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
