<script setup>
import { computed } from 'vue'
import { taskIssues } from '../reviews'
import AgentPanel from './AgentPanel.vue'
import GithubItemPanel from './GithubItemPanel.vue'

// The task's issue mode: for each GitHub issue the task links, its current
// detail (read fresh from GitHub, falling back to the stored item) and the Agent
// panel, so the issue can be worked on through an agent instead of the GitHub UI.

const props = defineProps({
  task: { type: Object, required: true },
  harnesses: { type: Array, default: () => [] }
})
const emit = defineEmits(['changed'])

// The GitHub issues the task links, from its associated items.
const issues = computed(() => taskIssues(props.task))
</script>

<template>
  <div class="task-issues">
    <GithubItemPanel v-for="issue in issues" :key="issue.url" :url="issue.url" :item="issue.item" />

    <div v-if="!issues.length" class="empty">This task is not linked to an issue.</div>

    <!-- The interface for interacting with the issue: the task's agent panel,
         whose prompt buttons include the configured issue prompts. -->
    <AgentPanel :task="task" :harnesses="harnesses" context-kind="issue" @changed="emit('changed')" />
  </div>
</template>
