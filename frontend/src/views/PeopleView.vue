<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { store } from '../store'
import EditableText from '../components/EditableText.vue'

const router = useRouter()

const people = ref([])
const items = ref([])
const loading = ref(true)
const search = ref('')
const newName = ref('')
const busy = ref(false)

const itemById = computed(() => Object.fromEntries(items.value.map((item) => [item.id, item])))
const taskById = computed(() => Object.fromEntries(store.tasks.map((task) => [task.id, task])))

const visible = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return people.value
  return people.value.filter(
    (person) =>
      person.name.toLowerCase().includes(q) ||
      (person.handle || '').toLowerCase().includes(q) ||
      (person.email || '').toLowerCase().includes(q)
  )
})

function taskTitle(id) {
  return taskById.value[id]?.title || id
}

function itemTitle(id) {
  const item = itemById.value[id]
  return item ? item.title || item.url || id : id
}

async function load() {
  loading.value = true
  try {
    const list = await api.people.list()
    people.value = await Promise.all(list.map((person) => api.people.get(person.id)))
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function create() {
  const name = newName.value.trim()
  if (!name) return
  busy.value = true
  try {
    await store.createPerson(name)
    newName.value = ''
    await load()
    store.notify('Person added')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function rename(person, name) {
  if (!name.trim()) {
    await load()
    return
  }
  try {
    await api.people.update(person.id, { name })
    await store.loadPeople()
    await load()
  } catch (e) {
    store.notify(e.message, true)
    await load()
  }
}

async function remove(person) {
  const linked = (person.task_ids?.length || 0) + (person.item_ids?.length || 0)
  const message = linked
    ? `Delete ${person.name}? They will be unlinked from ${linked} task(s)/item(s).`
    : `Delete ${person.name}?`
  if (!confirm(message)) return
  try {
    await api.people.remove(person.id)
    await store.loadPeople()
    await load()
    store.notify('Person deleted')
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(async () => {
  await store.loadTasks().catch(() => {})
  await store.loadPeople().catch(() => {})
  try {
    items.value = await api.items.list()
  } catch (e) {
    store.notify(e.message, true)
  }
  await load()
})
</script>

<template>
  <div>
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 12px">
      <h1>People</h1>
      <span class="faint">{{ visible.length }} of {{ people.length }}</span>
    </div>

    <div class="row" style="margin-bottom: 12px">
      <input v-model="search" class="input grow" placeholder="Search name, handle, or email…" />
    </div>

    <div class="row" style="gap: 8px; margin-bottom: 16px; flex-wrap: wrap">
      <input v-model="newName" class="input grow" placeholder="Add a person by name…" @keyup.enter="create" />
      <button class="btn primary" :disabled="busy || !newName.trim()" @click="create">Add</button>
    </div>

    <div v-if="loading" class="empty"><span class="spinner"></span></div>
    <div v-else-if="!visible.length" class="empty">No people.</div>
    <div v-else>
      <div v-for="person in visible" :key="person.id" class="item">
        <div class="item-top">
          <EditableText
            class="title"
            :value="person.name"
            placeholder="Unnamed person"
            @save="(value) => rename(person, value)"
          />
          <span class="faint">tasks:{{ person.task_ids?.length || 0 }} items:{{ person.item_ids?.length || 0 }}</span>
          <button class="btn sm danger" title="Delete" @click="remove(person)">✕</button>
        </div>
        <div v-if="person.email || person.handle" class="faint">
          <span v-if="person.handle">@{{ person.handle }}</span>
          <span v-if="person.handle && person.email"> · </span>
          <span v-if="person.email">{{ person.email }}</span>
        </div>
        <div v-if="person.notes" class="content">{{ person.notes }}</div>
        <div class="row" style="margin-top: 6px; gap: 6px; flex-wrap: wrap">
          <span v-if="!person.task_ids?.length && !person.item_ids?.length" class="faint">
            not linked to anything
          </span>
          <button
            v-for="taskId in person.task_ids"
            :key="`t-${taskId}`"
            class="btn sm ghost"
            @click="router.push(`/task/${taskId}`)"
          >
            {{ taskTitle(taskId) }}
          </button>
          <button
            v-for="itemId in person.item_ids"
            :key="`i-${itemId}`"
            class="btn sm ghost"
            @click="router.push('/items')"
          >
            {{ itemTitle(itemId) }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
