<script setup>
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { store } from '../store'
import SearchSelect from './SearchSelect.vue'

const props = defineProps({
  task: { type: Object, required: true },
  // Which link set to render: the people the task involves, or the people who
  // requested it. Both are people from the same directory, linked to the task.
  kind: { type: String, default: 'people' }, // people | requesters
  emptyLabel: { type: String, default: 'no people' },
  // When true, each linked person's name links to their detail page.
  linkToDetail: { type: Boolean, default: false }
})
const emit = defineEmits(['changed'])

const busy = ref(false)
const select = ref(null)

const isRequesters = computed(() => props.kind === 'requesters')
const linked = computed(() => (isRequesters.value ? props.task.requesters : props.task.people) || [])
const linkedIds = computed(() => new Set(linked.value.map((person) => person.id)))

// People named by the task's items (an issue/PR author, a commenter) who are
// not linked yet; one click links them. Only the involved-people set offers
// these suggestions, since a requester is not implied by an item.
const suggested = computed(() =>
  isRequesters.value ? [] : (props.task.suggested_people || []).filter((person) => !linkedIds.value.has(person.id))
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
    if (isRequesters.value) {
      await api.people.linkRequester(props.task.id, { person_id: personId })
    } else {
      await api.people.linkTask(props.task.id, { person_id: personId })
    }
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
    if (isRequesters.value) {
      await api.people.unlinkRequester(props.task.id, person.id)
    } else {
      await api.people.unlinkTask(props.task.id, person.id)
    }
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
      + {{ person.name }}
    </button>
    <SearchSelect
      v-if="linkable.length"
      ref="select"
      variant="inline"
      keep-open
      :model-value="''"
      :options="linkable"
      :placeholder="isRequesters ? '+ Link requester' : '+ Link person'"
      :title="isRequesters ? 'Link a person who requested this task' : 'Link a person to this task'"
      @update:model-value="link"
    />
    <span v-if="!linked.length && !suggested.length && !linkable.length" class="faint">{{ emptyLabel }}</span>
  </div>
</template>
