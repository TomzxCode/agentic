<script setup>
import { statusLabel } from '../store'
import StatusIcon from './StatusIcon.vue'

// A reference to a task, rendered as a chip with the task's status icon and
// title. Used wherever a task is linked from another entity (a person, a
// repository item) so those references look the same everywhere.
defineProps({
  task: { type: Object, required: true }
})
</script>

<template>
  <router-link :to="`/task/${task.id}`" class="btn sm ghost">
    <StatusIcon :status="task.status" :label="statusLabel(task.status)" />
    <span class="task-link-title">{{ task.title }}</span>
  </router-link>
</template>
