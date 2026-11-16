<script setup>
import { ref, watch } from 'vue'

// The confirmation both the review queue and the PR view use before approving
// a pull request: approving is a GitHub write, so it takes one deliberate step
// and can carry a review comment.
const props = defineProps({
  // The pull request to approve, with repository, number, and title; null keeps
  // the dialog closed.
  target: { type: Object, default: null },
  approving: { type: Boolean, default: false }
})
const emit = defineEmits(['confirm', 'cancel'])

const body = ref('')

watch(
  () => props.target,
  () => {
    body.value = ''
  }
)

function cancel() {
  if (!props.approving) emit('cancel')
}
</script>

<template>
  <div v-if="target" class="modal-backdrop" @click.self="cancel">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="pull-approve-title">
      <h2 id="pull-approve-title" style="margin-top: 0">Approve pull request</h2>
      <p>
        Approve <strong>{{ target.repository }}#{{ target.number }}</strong> on GitHub?
        <span v-if="target.title" class="faint">{{ target.title }}</span>
      </p>
      <p class="faint">
        This submits an approving review as you. It does not merge the pull request, and GitHub may still ask for
        another required review.
      </p>
      <label class="pr-action-form">
        <span class="faint">Review comment (optional)</span>
        <textarea v-model="body" class="textarea" rows="3" placeholder="Leave a comment with the approval" />
      </label>
      <div class="row" style="justify-content: flex-end; gap: 8px">
        <button class="btn sm ghost" :disabled="approving" @click="cancel">Cancel</button>
        <button class="btn sm" :disabled="approving" @click="emit('confirm', body)">
          <span v-if="approving" class="spinner" aria-hidden="true"></span>
          Approve
        </button>
      </div>
    </div>
  </div>
</template>
