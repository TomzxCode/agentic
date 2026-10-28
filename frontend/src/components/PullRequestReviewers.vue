<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
import { store } from '../store'
import ReviewPeople from './ReviewPeople.vue'

// The reviewers of a pull request, read live from GitHub, with the Slack poke
// that asks one for a review. The item page addresses the stored item; the
// standalone pull request view has no item, so it passes the URL instead.
const props = defineProps({
  itemId: { type: String, default: '' },
  url: { type: String, default: '' },
  title: { type: String, default: '' }
})

const reviewers = ref([])
const error = ref(null)
const loading = ref(false)
const poking = ref(null)

async function load() {
  reviewers.value = []
  error.value = null
  loading.value = true
  try {
    const data = props.itemId ? await api.items.reviewers(props.itemId) : await api.github.pullReviewers(props.url)
    reviewers.value = data.reviewers || []
    error.value = data.error || null
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// The emoji itself is the action; the toast reports who the message reached, or
// why it could not go.
async function poke(reviewer) {
  if (poking.value) return
  poking.value = reviewer.login
  try {
    const sent = props.itemId
      ? await api.items.poke(props.itemId, reviewer.login)
      : await api.github.pokePull({ url: props.url, title: props.title, login: reviewer.login })
    store.notify(`Poked ${sent.name || `@${reviewer.login}`} on Slack`)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    poking.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="field">
    <label>Reviewers</label>
    <div v-if="loading" class="empty"><span class="spinner"></span></div>
    <p v-else-if="error" class="faint" style="margin: 0">{{ error }}</p>
    <p v-else-if="!reviewers.length" class="faint" style="margin: 0">No reviewers yet.</p>
    <ReviewPeople v-else :reviewers="reviewers" :poking="poking" @poke="poke" />
  </div>
</template>
