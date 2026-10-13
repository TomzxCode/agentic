<script setup>
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { store } from '../store'
import SearchSelect from './SearchSelect.vue'

const props = defineProps({
  task: { type: Object, required: true },
  emptyLabel: { type: String, default: 'no people' },
  // When true, each linked person's name links to their detail page.
  linkToDetail: { type: Boolean, default: false }
})
const emit = defineEmits(['changed'])

const busy = ref(false)
const select = ref(null)

const linked = computed(() => props.task.people || [])
const linkedIds = computed(() => new Set(linked.value.map((person) => person.id)))

// People named by the task's items (an issue/PR author, a commenter) who are
// not linked yet; one click links them.
const suggested = computed(() =>
  (props.task.suggested_people || []).filter((person) => !linkedIds.value.has(person.id))
)

// People in the directory who are not already on the task.
const linkable = computed(() =>
  store.people
    .filter((person) => !linkedIds.value.has(person.id))
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((person) => ({ value: person.id, label: person.name }))
)

async function link(personId) {
  if (!personId) return
  busy.value = true
  try {
    await api.people.linkTask(props.task.id, { person_id: personId })
    await store.loadPeople()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function remove(person) {
  busy.value = true
  try {
    await api.people.unlinkTask(props.task.id, person.id)
    await store.loadPeople()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

// Let a parent (e.g. the command palette) open the "link a person" dropdown.
defineExpose({ activate: () => select.value?.activate?.() })
</script>

<template>
  <div class="people-select">
    <span v-for="person in linked" :key="person.id" class="chip">
      <RouterLink v-if="linkToDetail" :to="`/person/${person.id}`">{{ person.name }}</RouterLink>
      <template v-else>{{ person.name }}</template>
      <button type="button" class="chip-x" title="Remove" :disabled="busy" @click="remove(person)">×</button>
    </span>
    <button
      v-for="person in suggested"
      :key="person.id"
      type="button"
      class="chip chip-add"
      :disabled="busy"
      title="Link this person to the task"
      @click="link(person.id)"
    >
      ＋ {{ person.name }}
    </button>
    <SearchSelect
      v-if="linkable.length"
      ref="select"
      variant="inline"
      keep-open
      :model-value="''"
      :options="linkable"
      placeholder="＋ Link a person…"
      title="Link a person to this task"
      @update:model-value="link"
    />
    <span v-if="!linked.length && !suggested.length && !linkable.length" class="faint">{{ emptyLabel }}</span>
  </div>
</template>
