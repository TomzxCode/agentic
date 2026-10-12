<script setup>
import { computed, reactive, ref } from 'vue'
import { api } from '../api'
import { store } from '../store'
import SearchSelect from './SearchSelect.vue'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const busy = ref(false)
const newName = ref('')

const linkedIds = computed(() => new Set((props.task.people || []).map((person) => person.id)))

// People in the directory who are not already on the task.
const linkable = computed(() =>
  store.people
    .filter((person) => !linkedIds.value.has(person.id))
    .map((person) => ({ value: person.id, label: person.name }))
)

const draft = reactive({ choice: '' })

async function linkExisting(personId) {
  draft.choice = ''
  if (!personId) return
  await link({ person_id: personId })
}

async function createAndLink() {
  const name = newName.value.trim()
  if (!name) return
  newName.value = ''
  await link({ name })
}

async function link(body) {
  busy.value = true
  try {
    await api.people.linkTask(props.task.id, body)
    await store.loadPeople()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function remove(person) {
  try {
    await api.people.unlinkTask(props.task.id, person.id)
    await store.loadPeople()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>
        People <span class="faint">{{ task.people?.length || 0 }}</span>
      </h2>
    </div>

    <div v-if="!task.people?.length" class="faint" style="margin-bottom: 12px">
      Nobody associated yet. Link a person from the directory or add a new one.
    </div>

    <div v-else class="row" style="gap: 6px; flex-wrap: wrap; margin-bottom: 12px">
      <span v-for="person in task.people" :key="person.id" class="chip">
        {{ person.name }}
        <button class="chip-x" title="Remove" @click="remove(person)">✕</button>
      </span>
    </div>

    <div style="border-top: 1px solid var(--border); padding-top: 12px">
      <div class="row" style="gap: 8px; flex-wrap: wrap">
        <SearchSelect
          v-if="linkable.length"
          variant="inline"
          class="grow"
          placeholder="＋ Link a person…"
          title="Link a person to this task"
          :model-value="draft.choice"
          :options="linkable"
          @update:model-value="linkExisting"
        />
        <input v-model="newName" class="input grow" placeholder="New person name…" @keyup.enter="createAndLink" />
        <button class="btn" :disabled="busy || !newName.trim()" @click="createAndLink">Add</button>
      </div>
    </div>
  </section>
</template>
