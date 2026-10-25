<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { parseRemote } from '../repositories/parse'
import { store } from '../store'
import TaskReviewPanel from '../components/TaskReviewPanel.vue'

const route = useRoute()
const owner = computed(() => route.params.owner)
const repo = computed(() => route.params.repo)
const number = computed(() => route.params.number)
const url = computed(() => `https://github.com/${owner.value}/${repo.value}/pull/${number.value}`)

const repository = computed(() => {
  const wanted = `${owner.value}/${repo.value}`.toLowerCase()
  return (
    (store.repositories || []).find((entry) => {
      const remote = parseRemote(entry.remote_url)
      return remote && `${remote.owner}/${remote.repo}`.toLowerCase() === wanted
    }) || null
  )
})
const backLink = computed(() => (repository.value ? `/repositories/${repository.value.id}` : '/repositories'))

onMounted(async () => {
  await store.loadHarnesses().catch(() => {})
  await store.loadRepositories().catch(() => {})
  await store.loadTasks().catch(() => {})
  await store.loadItems().catch(() => {})
  await store.loadPeople().catch(() => {})
})
</script>

<template>
  <div>
    <div class="faint" style="margin-bottom: 12px">
      <router-link to="/repositories">Repositories</router-link>
      <template v-if="repository">
        / <router-link :to="backLink">{{ repository.name }}</router-link></template
      >
      <template v-else> / {{ owner }}/{{ repo }}</template>
      / Pull request #{{ number }}
    </div>
    <TaskReviewPanel :url="url" :harnesses="store.harnesses" />
  </div>
</template>
