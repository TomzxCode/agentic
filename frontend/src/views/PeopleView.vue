<script setup>
import { computed, onMounted, ref, resolveComponent, shallowRef } from 'vue'
import { aliasLabel, formatDateTime, store } from '../store'
import { api } from '../api'
import GridColumnChooser from '../components/GridColumnChooser.vue'
import PeopleGrid from '../components/PeopleGrid.vue'

const people = ref([])
const loading = ref(true)
const newName = ref('')
const busy = ref(false)
// The names slackx resolved for the Slack user ids carried as aliases, if any.
const slackNames = ref({})
// How many rows the grid currently shows (its filters may hide some).
const shown = ref(null)
// The grid's api, once it reports ready, so the column chooser can read the
// columns and show or hide them.
const gridApi = shallowRef(null)

// The globally registered router-link, handed to the grid so its name cells keep
// internal navigation inside the SPA (and so tests can stub it by name).
const routerLink = resolveComponent('RouterLink')

// The grid rows: each person with the aliases line the grid displays.
const rows = computed(() =>
  people.value.map((person) => ({
    ...person,
    aliases_line: (person.aliases || []).map((alias) => aliasLabel(alias, slackNames.value)).join(' · '),
    created_line: formatDateTime(person.created_at),
    raw: person
  }))
)

async function load() {
  loading.value = true
  try {
    // A Slack user id alias is shown as the name slackx resolves it to; asking
    // for the names is best effort, so a failure leaves the raw ids displayed.
    const [, resolved] = await Promise.all([
      store.loadPeople(),
      api.people.slackAliasNames().catch(() => ({ names: {} }))
    ])
    people.value = store.people
    slackNames.value = resolved.names || {}
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
  <div class="page-fill">
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 12px">
      <h1>People</h1>
      <span class="row" style="gap: 8px; align-items: center; flex-wrap: wrap; justify-content: flex-end">
        <span class="faint">{{ shown ?? people.length }} of {{ people.length }}</span>
        <GridColumnChooser :api="gridApi" storage-key="people" />
      </span>
    </div>

    <div class="row" style="gap: 8px; margin-bottom: 16px; flex-wrap: wrap">
      <input v-model="newName" class="input grow" placeholder="Add a person by name…" @keyup.enter="create" />
      <button class="btn primary" :disabled="busy || !newName.trim()" @click="create">Add</button>
    </div>

    <div v-if="loading" class="empty"><span class="spinner"></span></div>
    <div v-else-if="!people.length" class="empty">No people.</div>
    <PeopleGrid v-else :rows="rows" :router-link="routerLink" @count="shown = $event" @ready="gridApi = $event" />
  </div>
</template>
