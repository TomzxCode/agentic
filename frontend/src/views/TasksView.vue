<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { store, statusLabel, timeAgo, taskHasTag } from '../store'
import { api } from '../api'
import TagInput from '../components/TagInput.vue'
import StatusIcon from '../components/StatusIcon.vue'

const matchesFilter = (p) => !store.tagFilter || taskHasTag(p, store.tagFilter)

const counts = computed(() => {
  const c = { open: 0, in_progress: 0, blocked: 0, done: 0, archived: 0 }
  for (const p of store.tasks.filter(matchesFilter)) c[p.status] = (c[p.status] || 0) + 1
  return c
})

// Every task still in flight and matching the active tag filter. This is the
// page's default view: a selectable list you can edit in bulk.
const inFlight = computed(() =>
  store.tasks.filter((p) => p.status !== 'done' && p.status !== 'archived').filter(matchesFilter)
)

// --- Bulk edit -------------------------------------------------------------
const STATUS_VALUES = ['open', 'in_progress', 'blocked', 'done', 'archived']

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

// Changing the filter hides some rows; drop any selection that goes with them
// so a bulk edit only ever touches what is on screen.
watch(() => store.tagFilter, resetBulk)

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

onMounted(() => store.loadTasks())
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

    <div class="row" style="gap: 10px; margin-bottom: 20px">
      <span class="badge">Open {{ counts.open }}</span>
      <span class="badge run">In progress {{ counts.in_progress }}</span>
      <span class="badge warn">Blocked {{ counts.blocked }}</span>
      <span class="badge ok">Done {{ counts.done }}</span>
    </div>

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
            <StatusIcon :status="p.status" :label="statusLabel(p.status)" />
            <router-link :to="`/task/${p.id}`" class="title">{{ p.title }}</router-link>
            <span class="faint">{{ timeAgo(p.updated_at) }}</span>
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
