<script setup>
import { computed } from 'vue'
import { deadlineInfo, formatDeadline, priorityLabel as priorityName, statusLabel, store, timeAgo } from '../store'
import EntityCard from './EntityCard.vue'
import PriorityIcon from './PriorityIcon.vue'
import SearchSelect from './SearchSelect.vue'
import StatusIcon from './StatusIcon.vue'

// A single Task rendered as a card: an inline status picker and priority icon, a
// title linking to the task, the people linked to it, its deadline and age, its
// next step, and its tags. The tasks page (and its deadlines section) use it so
// a task row looks the same wherever it appears.
//
// Person and tag chips act on the shared filters in the store, the same way the
// tasks page's filter rows do.
const props = defineProps({
  task: { type: Object, required: true },
  // The people directory, used to resolve the task's person ids to names.
  people: { type: Array, default: () => [] },
  selectable: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  showStatus: { type: Boolean, default: true },
  showPriority: { type: Boolean, default: true },
  showPeople: { type: Boolean, default: true },
  showDeadline: { type: Boolean, default: true },
  // The exact deadline time, shown after the state badge (the deadlines list).
  showDeadlineTime: { type: Boolean, default: false },
  showAge: { type: Boolean, default: true },
  showNextStep: { type: Boolean, default: true },
  showTags: { type: Boolean, default: true }
})

defineEmits(['change-status', 'toggle'])

const STATUS_VALUES = ['open', 'in_progress', 'blocked', 'done', 'archived']
const statusOptions = STATUS_VALUES.map((value) => ({
  value,
  label: statusLabel(value),
  icon: StatusIcon,
  iconProps: { status: value, label: statusLabel(value) }
}))

// 0 = low, 1 = medium, 2 = high, 3 = urgent.
const priorityLabel = computed(() => `Priority: ${priorityName(props.task.priority)}`)

const peopleById = computed(() => Object.fromEntries(props.people.map((person) => [person.id, person])))
const linkedPeople = computed(() => (props.task.person_ids || []).map((id) => peopleById.value[id]).filter(Boolean))

const deadline = computed(() => deadlineInfo(props.task.deadline))
const nextStep = computed(() => (props.task.next_steps || []).find((step) => !step.done))

// How long the task has existed and since it last changed; the two collapse to
// one when they describe the same moment.
const age = computed(() => {
  const created = timeAgo(props.task.created_at)
  const updated = timeAgo(props.task.updated_at)
  if (created && updated && created !== updated) return `created ${created} · updated ${updated}`
  if (created) return `created ${created}`
  return updated ? `updated ${updated}` : ''
})
</script>

<template>
  <EntityCard :selectable="selectable" :selected="selected">
    <template #select>
      <input
        type="checkbox"
        class="row-check"
        :checked="selected"
        :aria-label="`Select ${task.title}`"
        @change="$emit('toggle', task.id)"
      />
    </template>

    <template #lead>
      <SearchSelect
        v-if="showStatus"
        class="task-status-select"
        variant="icon"
        :model-value="task.status"
        :options="statusOptions"
        :sort="false"
        title="Change status"
        @update:model-value="(value) => $emit('change-status', task, value)"
      />
      <PriorityIcon v-if="showPriority" :priority="task.priority" :label="priorityLabel" />
    </template>

    <template #title>
      <router-link :to="`/task/${task.id}`" class="title">{{ task.title }}</router-link>
    </template>

    <template #title-extra>
      <template v-if="showPeople">
        <button
          v-for="person in linkedPeople"
          :key="person.id"
          type="button"
          class="person-chip"
          :class="{ active: store.personFilter === person.id }"
          :title="`Filter by ${person.name}`"
          @click="store.togglePersonFilter(person.id)"
        >
          {{ person.name }}
        </button>
      </template>
    </template>

    <template #actions>
      <span
        v-if="showDeadline && deadline"
        class="badge"
        :class="deadline.tone"
        :title="`Deadline: ${formatDeadline(task.deadline)}`"
      >
        {{ deadline.label }}
      </span>
      <span v-if="showDeadlineTime" class="faint">{{ formatDeadline(task.deadline) }}</span>
      <slot name="actions" />
      <span v-if="showAge && age" class="faint">{{ age }}</span>
    </template>

    <div v-if="showNextStep && nextStep" class="faint" style="margin-top: 6px">Next: {{ nextStep.text }}</div>

    <div v-if="showTags && task.tags?.length" class="task-tags" style="margin-top: 6px">
      <button
        v-for="tag in task.tags"
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
  </EntityCard>
</template>
