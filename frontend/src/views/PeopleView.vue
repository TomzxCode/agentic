<script setup>
import { computed, onMounted, ref } from 'vue'
import { store } from '../store'

const people = ref([])
const loading = ref(true)
const search = ref('')
const newName = ref('')
const busy = ref(false)

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

async function load() {
  loading.value = true
  try {
    await store.loadPeople()
    people.value = store.people
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

onMounted(load)
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
          <router-link class="title" :to="`/person/${person.id}`">{{ person.name }}</router-link>
          <span class="faint">tasks:{{ person.task_count || 0 }} items:{{ person.item_count || 0 }}</span>
        </div>
        <div v-if="person.handle || person.email" class="faint">
          <span v-if="person.handle">@{{ person.handle }}</span>
          <span v-if="person.handle && person.email"> · </span>
          <span v-if="person.email">{{ person.email }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
