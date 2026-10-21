<script setup>
// The person a task waits on, plus the date to check back. Choosing a person
// parks the task off the stack (the server marks it blocked); clearing the
// person stops waiting and clears the check-back date.
import { computed } from 'vue'
import { store } from '../store'
import DeadlinePicker from './DeadlinePicker.vue'
import SearchSelect from './SearchSelect.vue'

const props = defineProps({
  modelValue: { type: String, default: null },
  // The resolved name, so a person missing from the loaded directory still reads.
  name: { type: String, default: null },
  followUpAt: { type: String, default: null }
})
const emit = defineEmits(['person', 'follow-up'])

const options = computed(() =>
  store.people
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((person) => ({ value: person.id, label: person.name }))
)

const selectedName = computed(
  () => props.name || store.people.find((person) => person.id === props.modelValue)?.name || props.modelValue
)
</script>

<template>
  <div class="waiting-select">
    <span v-if="modelValue" class="chip">
      {{ selectedName }}
      <button
        type="button"
        class="chip-x"
        title="Stop waiting on this person"
        aria-label="Stop waiting on this person"
        @click="emit('person', null)"
      >
        ×
      </button>
    </span>
    <SearchSelect
      v-else
      variant="inline"
      :model-value="''"
      :options="options"
      placeholder="＋ Waiting on a person…"
      title="Wait on a person"
      @update:model-value="(value) => emit('person', value)"
    />
    <span v-if="modelValue" class="waiting-follow-up">
      <span class="faint">check back</span>
      <DeadlinePicker
        :model-value="followUpAt"
        title="Check back"
        placeholder="set a date"
        :show-state="false"
        @update:model-value="(value) => emit('follow-up', value)"
      />
    </span>
  </div>
</template>
