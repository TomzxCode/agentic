<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import {
  assignedReviewers,
  CI_LABELS,
  CI_TONES,
  hasIndividualReviewer,
  hasMergeConflicts,
  isReadyToMerge,
  pullStatus,
  pullStatusLabel,
  readyToMergeTitle
} from '../myPulls'
import { STATE_LABELS } from '../repositories/parse'

// The list of GitHub items a task links, shown at the top of the task view's
// Issue and PR modes when there is more than one. Each row names the item and
// its current state, and selecting one navigates to it without leaving the
// task: the query carries the item, so the task page rerenders the panel for
// that item and the back button returns to the previous one.

const props = defineProps({
  // "issue" or "pr".
  kind: { type: String, required: true },
  // The linked items, each carrying a stable `key`, its `number`, `title`, and
  // its current state (an issue's state, a pull request's state and facts).
  items: { type: Array, default: () => [] },
  // The selected item's key, or "" when the panel falls back to the first.
  selected: { type: String, default: '' }
})

const route = useRoute()

const label = computed(() => (props.kind === 'pr' ? 'pull request' : 'issue'))

function target(entry) {
  return { query: { ...route.query, item: entry.key } }
}

function isSelected(entry) {
  return entry.key === props.selected
}

function statusClass(entry) {
  return `st-${pullStatus(entry)}`
}

function issueStateLabel(entry) {
  const state = String(entry.state || '').toLowerCase()
  return STATE_LABELS[state] || ''
}

function reviewersLabel(entry) {
  const waiting = entry.requested_users || []
  if (waiting.length) return `${waiting.length} reviewer${waiting.length === 1 ? '' : 's'}`
  if (hasIndividualReviewer(entry))
    return `${assignedReviewers(entry).length} reviewer${assignedReviewers(entry).length === 1 ? '' : 's'}`
  if ((entry.requested_teams || []).length) return 'team only'
  return 'no reviewers'
}

function reviewersTone(entry) {
  if (hasIndividualReviewer(entry)) return 'ok'
  if ((entry.requested_teams || []).length) return 'warn'
  return ''
}

function reviewersTitle(entry) {
  const waiting = entry.requested_users || []
  if (waiting.length) return `Review requested from ${waiting.join(', ')}`
  const approvers = entry.approvers || []
  if (approvers.length) return `Approved by ${approvers.join(', ')}`
  if ((entry.requested_teams || []).length) {
    return `Only a team is requested (${entry.requested_teams.join(', ')}); no individual reviewer is assigned`
  }
  return 'No reviewer is assigned'
}

function commentsTone(entry) {
  return Number(entry.open_threads) > 0 ? 'warn' : ''
}

function commentsTitle(entry) {
  const open = Number(entry.open_threads) || 0
  return open ? `${open} inline comment${open === 1 ? '' : 's'} still open` : 'No inline comments are open'
}

function conflictsLabel(entry) {
  const value = hasMergeConflicts(entry)
  if (value === null) return 'conflicts ?'
  return value ? 'conflicts' : 'no conflicts'
}

function conflictsTone(entry) {
  const value = hasMergeConflicts(entry)
  if (value === null) return ''
  return value ? 'danger' : 'ok'
}

function conflictsTitle(entry) {
  const value = hasMergeConflicts(entry)
  if (value === null) return 'GitHub has not reported mergeability yet'
  return value ? 'The branches have merge conflicts' : 'No merge conflicts'
}
</script>

<template>
  <nav class="task-link-list" :aria-label="`Linked ${label}s`">
    <router-link
      v-for="entry in items"
      :key="entry.key"
      :to="target(entry)"
      class="task-link"
      :class="{ active: isSelected(entry) }"
      :aria-current="isSelected(entry) ? 'true' : undefined"
    >
      <span class="task-link-number">#{{ entry.number }}</span>
      <span class="task-link-title" :title="entry.title">{{ entry.title || 'Untitled' }}</span>
      <span class="task-link-facts">
        <template v-if="kind === 'pr'">
          <span class="badge" :class="statusClass(entry)">{{ pullStatusLabel(entry) }}</span>
          <span
            class="badge"
            :class="CI_TONES[entry.ci] || ''"
            :title="`Checks: ${CI_LABELS[entry.ci] || 'unknown'}`"
            >{{ CI_LABELS[entry.ci] || 'Unknown' }}</span
          >
          <span class="badge" :class="reviewersTone(entry)" :title="reviewersTitle(entry)">{{
            reviewersLabel(entry)
          }}</span>
          <span
            class="badge"
            :class="commentsTone(entry)"
            :title="commentsTitle(entry)"
            :aria-label="commentsTitle(entry)"
            >{{ entry.open_threads || 0 }} open</span
          >
          <span class="badge" :class="conflictsTone(entry)" :title="conflictsTitle(entry)">{{
            conflictsLabel(entry)
          }}</span>
          <span class="badge" :class="isReadyToMerge(entry) ? 'ok' : ''" :title="readyToMergeTitle(entry)">{{
            isReadyToMerge(entry) ? 'ready' : 'not ready'
          }}</span>
        </template>
        <span v-else-if="issueStateLabel(entry)" class="badge" :class="`st-${String(entry.state).toLowerCase()}`">{{
          issueStateLabel(entry)
        }}</span>
      </span>
    </router-link>
  </nav>
</template>
