<script setup>
import FindingsSelector from './FindingsSelector.vue'

// The review queue's Share action: the same findings selection as the task
// view's PR mode, opened as a modal over a PR row. Importing a task for the PR
// is reported so the row can show the new task link.

defineProps({
  repository: { type: String, required: true },
  number: { type: Number, required: true },
  url: { type: String, default: '' },
  taskId: { type: String, default: null },
  taskLabel: { type: String, default: '' }
})
const emit = defineEmits(['close', 'shared', 'imported'])

// A sent selection closes the modal, whether it opened over a row or a panel.
function onShared(payload) {
  emit('shared', payload)
  emit('close')
}
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal share-findings">
      <div class="row" style="justify-content: space-between; align-items: baseline">
        <h2 style="margin: 0">
          Share review findings <span class="faint review-modal-path">{{ repository }}#{{ number }}</span>
        </h2>
        <button class="btn sm ghost" aria-label="Close" @click="emit('close')">Close</button>
      </div>

      <FindingsSelector
        :repository="repository"
        :number="number"
        :url="url"
        :task-id="taskId"
        :task-label="taskLabel"
        @shared="onShared"
        @imported="(task) => emit('imported', task)"
      />
    </div>
  </div>
</template>
