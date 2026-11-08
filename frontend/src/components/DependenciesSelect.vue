<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { statusLabel, store } from '../store'
import SearchSelect from './SearchSelect.vue'
import StatusIcon from './StatusIcon.vue'

// The links around a task, shown inline in the task header next to the
// repository and people selectors: the tasks that must come first, the tasks
// that follow, the tasks merely related to it, and its parents and children.
// Each can be linked and unlinked from here; the before/after pairs form the
// graph the Graph page draws, a related pair reads the same from both tasks,
// and the parent/child links form a separate hierarchy. Each group's picker
// keeps its linked tasks listed and ticked, so a link can also be removed from
// the list itself. Every chip shows the linked task's current status, so a
// prerequisite still open is visible without opening it.
const props = defineProps({
  task: { type: Object, required: true },
  // When true, each linked task's title links to its detail page.
  linkToDetail: { type: Boolean, default: false }
})
const emit = defineEmits(['changed'])

const deps = ref({ before: [], after: [], related: [], parents: [], children: [] })

const GROUPS = ['before', 'after', 'related', 'parents', 'children']

// The ids each group's picker shows as chosen. They change on the pick itself,
// not on the next server response, so a task just linked stays listed (ticked)
// in the drawer and can be tapped again to unlink it.
const selected = ref({ before: [], after: [], related: [], parents: [], children: [] })

// Every response carries all sides; fill in any the caller omitted so the lists
// render regardless of API shape.
function normalize(payload) {
  return { before: [], after: [], related: [], parents: [], children: [], ...payload }
}

// Take both the chip lists and the pickers from a full server response (the
// first load and a task change), where nothing is pending locally.
function applyDeps(payload) {
  deps.value = normalize(payload)
  const next = { before: [], after: [], related: [], parents: [], children: [] }
  for (const group of GROUPS) next[group] = deps.value[group].map((task) => task.id)
  selected.value = next
}
const allTasks = ref([])
const busy = ref(false)
const beforeSelect = ref(null)

const linkedIds = computed(() => {
  const ids = new Set()
  for (const group of GROUPS) {
    for (const task of deps.value[group]) ids.add(task.id)
    for (const id of selected.value[group]) ids.add(id)
  }
  return ids
})

// Each picker's options: every task not linked anywhere, plus the tasks already
// in this group, so the drawer keeps them on screen to unlink from there.
const groupOptions = computed(() => {
  const options = {}
  for (const group of GROUPS) {
    const keep = new Set([...selected.value[group], ...deps.value[group].map((task) => task.id)])
    // Linked tasks are carried over when the task list leaves them out (an
    // archived task, say), so they still appear and can be unticked.
    const tasks = new Map(allTasks.value.map((task) => [task.id, task]))
    for (const task of deps.value[group]) if (!tasks.has(task.id)) tasks.set(task.id, task)
    options[group] = [...tasks.values()]
      .filter((task) => task.id !== props.task.id && (!linkedIds.value.has(task.id) || keep.has(task.id)))
      .map((task) => ({ value: task.id, label: task.title }))
  }
  return options
})

async function load() {
  try {
    const [dependencies, tasks] = await Promise.all([api.tasks.dependencies(props.task.id), api.tasks.list()])
    applyDeps(dependencies)
    allTasks.value = tasks
  } catch (e) {
    store.notify(e.message, true)
  }
}
onMounted(load)
watch(() => props.task.id, load)

async function link(relatedId, relation) {
  if (!relatedId) return false
  busy.value = true
  try {
    deps.value = normalize(await api.tasks.addDependency(props.task.id, { related_id: relatedId, relation }))
    emit('changed')
    return true
  } catch (e) {
    store.notify(e.message, true)
    return false
  } finally {
    busy.value = false
  }
}

async function unlink(relatedId, relation) {
  busy.value = true
  const group = groupFor(relation)
  try {
    await api.tasks.removeDependency(props.task.id, relatedId, relation)
    deps.value = {
      ...deps.value,
      [group]: deps.value[group].filter((linked) => linked.id !== relatedId)
    }
    selected.value = {
      ...selected.value,
      [group]: selected.value[group].filter((id) => id !== relatedId)
    }
    emit('changed')
    return true
  } catch (e) {
    store.notify(e.message, true)
    return false
  } finally {
    busy.value = false
  }
}

// The picker state key for an API relation: parents/children are plural there.
function groupFor(relation) {
  if (relation === 'parent') return 'parents'
  if (relation === 'child') return 'children'
  return relation
}

// Diff a picker's chosen ids against what it showed before, so a tick links and
// an untick unlinks. Requests run one after another, in pick order. The group
// names the picker state, the relation names the API link (`parents`/`parent`).
let queue = Promise.resolve()
function syncSelection(group, ids, relation = group) {
  const next = (ids || []).map(String)
  const prev = [...selected.value[group]]
  selected.value = { ...selected.value, [group]: next }
  const added = next.filter((id) => !prev.includes(id))
  const removed = prev.filter((id) => !next.includes(id))
  queue = queue.then(async () => {
    let ok = true
    for (const id of added) ok = (await link(id, relation)) && ok
    for (const id of removed) ok = (await unlink(id, relation)) && ok
    // A failed request leaves nothing to trust in the optimistic state.
    if (!ok) await load()
  })
}

// Let a parent (e.g. the command palette) open the "link a task" dropdown.
defineExpose({ activate: () => beforeSelect.value?.activate?.() })
</script>

<template>
  <div class="dep-select">
    <div class="dep-group">
      <span class="dep-label">before</span>
      <div class="dep-chips">
        <span v-for="linked in deps.before" :key="`b-${linked.id}`" class="chip">
          <StatusIcon :status="linked.status" :label="statusLabel(linked.status)" />
          <RouterLink v-if="linkToDetail" :to="`/task/${linked.id}`">{{ linked.title }}</RouterLink>
          <template v-else>{{ linked.title }}</template>
          <button type="button" class="chip-x" title="Unlink" :disabled="busy" @click="unlink(linked.id, 'before')">
            ×
          </button>
        </span>
        <SearchSelect
          ref="beforeSelect"
          variant="inline"
          multiple
          bulk-actions
          :summary="false"
          :model-value="selected.before"
          :options="groupOptions.before"
          placeholder="+ Link task"
          title="Link a task that must be done before this one"
          @update:model-value="(ids) => syncSelection('before', ids)"
        />
      </div>
    </div>

    <div class="dep-group">
      <span class="dep-label">after</span>
      <div class="dep-chips">
        <span v-for="linked in deps.after" :key="`a-${linked.id}`" class="chip">
          <StatusIcon :status="linked.status" :label="statusLabel(linked.status)" />
          <RouterLink v-if="linkToDetail" :to="`/task/${linked.id}`">{{ linked.title }}</RouterLink>
          <template v-else>{{ linked.title }}</template>
          <button type="button" class="chip-x" title="Unlink" :disabled="busy" @click="unlink(linked.id, 'after')">
            ×
          </button>
        </span>
        <SearchSelect
          variant="inline"
          multiple
          bulk-actions
          :summary="false"
          :model-value="selected.after"
          :options="groupOptions.after"
          placeholder="+ Link task"
          title="Link a task that follows this one"
          @update:model-value="(ids) => syncSelection('after', ids)"
        />
      </div>
    </div>

    <div class="dep-group">
      <span class="dep-label">related</span>
      <div class="dep-chips">
        <span v-for="linked in deps.related" :key="`r-${linked.id}`" class="chip">
          <StatusIcon :status="linked.status" :label="statusLabel(linked.status)" />
          <RouterLink v-if="linkToDetail" :to="`/task/${linked.id}`">{{ linked.title }}</RouterLink>
          <template v-else>{{ linked.title }}</template>
          <button type="button" class="chip-x" title="Unlink" :disabled="busy" @click="unlink(linked.id, 'related')">
            ×
          </button>
        </span>
        <SearchSelect
          variant="inline"
          multiple
          bulk-actions
          :summary="false"
          :model-value="selected.related"
          :options="groupOptions.related"
          placeholder="+ Link task"
          title="Link a task related to this one, in either direction"
          @update:model-value="(ids) => syncSelection('related', ids)"
        />
      </div>
    </div>

    <div class="dep-group">
      <span class="dep-label">parents</span>
      <div class="dep-chips">
        <span v-for="linked in deps.parents" :key="`p-${linked.id}`" class="chip">
          <StatusIcon :status="linked.status" :label="statusLabel(linked.status)" />
          <RouterLink v-if="linkToDetail" :to="`/task/${linked.id}`">{{ linked.title }}</RouterLink>
          <template v-else>{{ linked.title }}</template>
          <button type="button" class="chip-x" title="Unlink" :disabled="busy" @click="unlink(linked.id, 'parent')">
            ×
          </button>
        </span>
        <SearchSelect
          variant="inline"
          multiple
          bulk-actions
          :summary="false"
          :model-value="selected.parents"
          :options="groupOptions.parents"
          placeholder="+ Link task"
          title="Link a task this one is a child of"
          @update:model-value="(ids) => syncSelection('parents', ids, 'parent')"
        />
      </div>
    </div>

    <div class="dep-group">
      <span class="dep-label">children</span>
      <div class="dep-chips">
        <span v-for="linked in deps.children" :key="`c-${linked.id}`" class="chip">
          <StatusIcon :status="linked.status" :label="statusLabel(linked.status)" />
          <RouterLink v-if="linkToDetail" :to="`/task/${linked.id}`">{{ linked.title }}</RouterLink>
          <template v-else>{{ linked.title }}</template>
          <button type="button" class="chip-x" title="Unlink" :disabled="busy" @click="unlink(linked.id, 'child')">
            ×
          </button>
        </span>
        <SearchSelect
          variant="inline"
          multiple
          bulk-actions
          :summary="false"
          :model-value="selected.children"
          :options="groupOptions.children"
          placeholder="+ Link task"
          title="Link a task that is a child of this one"
          @update:model-value="(ids) => syncSelection('children', ids, 'child')"
        />
      </div>
    </div>
  </div>
</template>
