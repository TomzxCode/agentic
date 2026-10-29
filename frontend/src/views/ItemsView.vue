<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { SOURCE_ORDER, sourceLabel, store, statusLabel } from '../store'
import ItemCard from '../components/ItemCard.vue'
import ItemToolLinks from '../components/ItemToolLinks.vue'
import SearchSelect from '../components/SearchSelect.vue'
import StatusIcon from '../components/StatusIcon.vue'
import TaskLink from '../components/TaskLink.vue'

const items = ref([])
const loading = ref(true)
const search = ref('')
const sourceFilter = ref('')
const expanded = ref({})
// Chosen task per item in the "link to a task" picker (reset after linking).
const linkChoice = ref({})
// Chosen person per item in the "link a person" picker (reset after linking).
const personChoice = ref({})

const peopleById = computed(() => Object.fromEntries(store.people.map((person) => [person.id, person])))

const counts = computed(() => {
  const result = {}
  for (const item of items.value) result[item.source] = (result[item.source] || 0) + 1
  return result
})

const sources = computed(() =>
  [...Object.keys(counts.value)].sort((a, b) => SOURCE_ORDER.indexOf(a) - SOURCE_ORDER.indexOf(b) || a.localeCompare(b))
)

const visible = computed(() => {
  const q = search.value.trim().toLowerCase()
  return items.value.filter((item) => {
    if (sourceFilter.value && item.source !== sourceFilter.value) return false
    if (!q) return true
    return (
      item.title.toLowerCase().includes(q) ||
      (item.url || '').toLowerCase().includes(q) ||
      (item.metadata_json?.path || '').toLowerCase().includes(q) ||
      (item.content || '').toLowerCase().includes(q)
    )
  })
})

function linkedTasks(item) {
  return (item.task_ids || []).map((id) => store.tasks.find((task) => task.id === id)).filter(Boolean)
}

// Tasks this item is not yet linked to, as SearchSelect options with a status icon.
function linkableTasks(item) {
  const linked = new Set(item.task_ids || [])
  return store.tasks
    .filter((task) => !linked.has(task.id))
    .map((task) => ({
      value: task.id,
      label: task.title,
      icon: StatusIcon,
      iconProps: { status: task.status, label: statusLabel(task.status) }
    }))
}

async function linkTask(item, taskId) {
  linkChoice.value[item.id] = ''
  if (!taskId) return
  try {
    await api.tasks.associate(taskId, { item_id: item.id })
    item.task_ids = [...(item.task_ids || []), taskId]
    store.notify('Linked to task')
  } catch (e) {
    store.notify(e.message, true)
  }
}

function itemPeople(item) {
  return (item.person_ids || []).map((id) => peopleById.value[id]).filter(Boolean)
}

// A note is plain text kept with a task: it has no source to re-fetch and no
// author, so the list offers it no refresh and no person linker.
function isNote(item) {
  return item.source === 'note'
}

// A local path has no author, so it offers no person linker.
function isPath(item) {
  return item.source === 'file'
}

function linkablePeople(item) {
  const linked = new Set(item.person_ids || [])
  return store.people
    .filter((person) => !linked.has(person.id))
    .map((person) => ({ value: person.id, label: person.name }))
}

async function linkPerson(item, personId) {
  personChoice.value[item.id] = ''
  if (!personId) return
  try {
    await api.people.linkItem(item.id, { person_id: personId })
    item.person_ids = [...(item.person_ids || []), personId]
    store.notify('Person linked')
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function unlinkPerson(item, personId) {
  try {
    await api.people.unlinkItem(item.id, personId)
    item.person_ids = (item.person_ids || []).filter((id) => id !== personId)
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function load() {
  loading.value = true
  try {
    items.value = await api.items.list()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function refresh(item) {
  try {
    const updated = await api.items.refresh(item.id)
    Object.assign(item, updated)
    store.notifyRefresh(updated)
  } catch (e) {
    store.notify(e.message, true)
  }
}

// A Slack conversation can be marked done and reopened. A reply that arrives
// while it is done is flagged by the API but does not change the done state.
async function toggleDone(item) {
  try {
    const updated = await api.items.update(item.id, { done: !item.done })
    Object.assign(item, updated)
    store.notify(updated.done ? 'Marked done' : 'Reopened')
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function remove(item) {
  const linked = linkedTasks(item).length
  const message = linked
    ? `Delete this ${sourceLabel(item.source)} item? It will also be unlinked from ${linked} task(s).`
    : `Delete this ${sourceLabel(item.source)} item?`
  if (!confirm(message)) return
  try {
    await api.items.remove(item.id)
    items.value = items.value.filter((entry) => entry.id !== item.id)
    store.notify('Item deleted')
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(async () => {
  await store.loadTasks().catch(() => {})
  await store.loadPeople().catch(() => {})
  await load()
})
</script>

<template>
  <div>
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 12px">
      <h1>Resources</h1>
      <span class="faint">{{ visible.length }} of {{ items.length }}</span>
    </div>

    <div class="row" style="margin-bottom: 12px">
      <input v-model="search" class="input grow" placeholder="Search title, link, path, or content…" />
    </div>

    <div class="row" style="margin-bottom: 16px">
      <button class="btn sm" :class="{ primary: !sourceFilter }" @click="sourceFilter = ''">
        All {{ items.length }}
      </button>
      <button
        v-for="source in sources"
        :key="source"
        class="btn sm"
        :class="{ primary: sourceFilter === source }"
        @click="sourceFilter = source"
      >
        {{ sourceLabel(source) }} {{ counts[source] }}
      </button>
    </div>

    <div v-if="loading" class="empty"><span class="spinner"></span></div>
    <div v-else-if="!visible.length" class="empty">No resources.</div>
    <div v-else>
      <ItemCard
        v-for="item in visible"
        :key="item.id"
        :item="item"
        :to="`/items/${item.id}`"
        :expanded="!!expanded[item.id]"
      >
        <template #actions>
          <button
            v-if="item.source === 'slack'"
            class="btn sm"
            :class="{ ghost: !item.done }"
            :title="item.done ? 'Reopen this conversation' : 'Mark this conversation done'"
            @click="toggleDone(item)"
          >
            {{ item.done ? 'Reopen' : 'Done' }}
          </button>
          <ItemToolLinks :item="item" compact />
          <button v-if="!isNote(item)" class="btn sm ghost" title="Refresh" @click="refresh(item)">↻</button>
          <button class="btn sm ghost" title="Expand" @click="expanded[item.id] = !expanded[item.id]">
            {{ expanded[item.id] ? '▾' : '▸' }}
          </button>
          <button class="btn sm danger" title="Delete" @click="remove(item)">✕</button>
        </template>
        <div class="row" style="margin-top: 6px; gap: 6px">
          <span v-if="!linkedTasks(item).length" class="faint">not linked to a task</span>
          <TaskLink v-for="task in linkedTasks(item)" :key="task.id" :task="task" />
          <SearchSelect
            v-if="linkableTasks(item).length"
            variant="inline"
            placeholder="+ Link task"
            title="Link this item to a task"
            :model-value="linkChoice[item.id] || ''"
            :options="linkableTasks(item)"
            @update:model-value="(value) => linkTask(item, value)"
          />
        </div>
        <div v-if="!isNote(item) && !isPath(item)" class="row" style="margin-top: 6px; gap: 6px; flex-wrap: wrap">
          <span v-for="person in itemPeople(item)" :key="person.id" class="chip">
            {{ person.name }}
            <button class="chip-x" title="Unlink person" @click="unlinkPerson(item, person.id)">✕</button>
          </span>
          <SearchSelect
            v-if="linkablePeople(item).length"
            variant="inline"
            placeholder="+ Link person"
            title="Link a person to this item"
            :model-value="personChoice[item.id] || ''"
            :options="linkablePeople(item)"
            @update:model-value="(value) => linkPerson(item, value)"
          />
        </div>
      </ItemCard>
    </div>
  </div>
</template>
