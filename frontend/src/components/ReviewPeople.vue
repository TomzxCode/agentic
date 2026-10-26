<script setup>
import { computed } from 'vue'
import { personLink } from '../repositories/parse'
import { githubReviewState, orderGithubReviewers } from '../reviews'
import { store, timeAgo } from '../store'

// The reviewers of a pull request, one row each: who they are, their review
// state, and the Slack poke action beside their name. The item page supplies
// GitHub's live reviewer read; the inbox supplies the requested reviewers from
// the My PRs read, marked requested and awaiting review. The parent owns the
// poke call and says whose poke is in flight.
const props = defineProps({
  reviewers: { type: Array, default: () => [] },
  poking: { type: String, default: null }
})
const emit = defineEmits(['poke'])

const rows = computed(() =>
  orderGithubReviewers(props.reviewers).map((review) => ({
    ...review,
    link: personLink(store.people, review.login),
    stateInfo: review.state ? githubReviewState(review.state) : null
  }))
)
</script>

<template>
  <div class="review-people">
    <div v-for="reviewer in rows" :key="reviewer.key" class="review-person">
      <router-link v-if="reviewer.link" :to="reviewer.link.path" :class="{ faint: reviewer.link.missing }"
        >@{{ reviewer.login }}</router-link
      >
      <span v-else class="faint">@{{ reviewer.login }}</span>
      <button
        class="btn sm ghost review-poke"
        :disabled="!!poking"
        :title="`Poke ${reviewer.login} on Slack`"
        :aria-label="`Poke ${reviewer.login} on Slack`"
        @click="emit('poke', reviewer)"
      >
        <span v-if="poking === reviewer.login" class="spinner" aria-hidden="true"></span>
        <span v-else aria-hidden="true">👉</span>
      </button>
      <span v-if="reviewer.stateInfo" class="badge" :class="reviewer.stateInfo.className">{{
        reviewer.stateInfo.label
      }}</span>
      <span v-if="reviewer.submitted_at" class="faint">last review {{ timeAgo(reviewer.submitted_at) }}</span>
      <span v-else-if="reviewer.requested" class="faint">requested</span>
    </div>
  </div>
</template>
