<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  assignedReviewers,
  attentionState,
  conflictsLabel,
  conflictsTone,
  descriptionLabel,
  descriptionTone,
  descriptionTitle,
  hasIndividualReviewer,
  hasMergeConflicts,
  isReadyToMerge,
  linkedIssueLabel,
  linkedIssueTone,
  linkedIssueTitle,
  pullStatusClass,
  pullStatusLabel,
  readyToMergeTitle,
  reviewLabel,
  reviewTone
} from '../myPulls'
import { personLink, STATE_LABELS } from '../repositories/parse'
import { formatDateTime, store, timeAgo } from '../store'
import PullChecksPopover from './PullChecksPopover.vue'

// The list of GitHub items a task links, shown at the top of the task view's
// Issue and PR modes when there is more than one. Each entry names the item and
// its current state, and selecting one navigates to it without leaving the
// task: the query carries the item, so the task page rerenders the panel for
// that item and the back button returns to the previous one.
//
// Pull requests read as the My PRs table does, because the same facts decide
// whether a pull request is moving: status, review, reviewers, checks, open
// comments, merge conflicts, and merge readiness. Issues keep a compact row.

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
const router = useRouter()

const label = computed(() => (props.kind === 'pr' ? 'pull request' : 'issue'))

function target(entry) {
  return { query: { ...route.query, item: entry.key } }
}

function navigate(entry) {
  router.push(target(entry))
}

function isSelected(entry) {
  return entry.key === props.selected
}

function issueStateLabel(entry) {
  const state = String(entry.state || '').toLowerCase()
  return STATE_LABELS[state] || ''
}

function repositoryName(entry) {
  return entry.repository || `${entry.owner || ''}/${entry.repo || ''}`
}

function reviewers(entry) {
  return assignedReviewers(entry)
}

function reviewerPrefix(entry) {
  return (entry.requested_users || []).length ? 'waiting on ' : 'approved by '
}

function reviewerEmptyLabel(entry) {
  return (entry.requested_teams || []).length ? 'team only' : 'none'
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

function reviewerNeedsPerson(entry) {
  return !hasIndividualReviewer(entry) && (entry.requested_teams || []).length > 0
}

function commentsTitle(entry) {
  const open = Number(entry.open_threads) || 0
  return open ? `${open} inline comment${open === 1 ? '' : 's'} still open` : 'No inline comments are open'
}

function conflictsTitle(entry) {
  const value = hasMergeConflicts(entry)
  if (value === null) return 'GitHub has not reported mergeability yet'
  return value ? 'The branches have merge conflicts' : 'No merge conflicts'
}

function personLinkFor(login) {
  return personLink(store.people, login)
}
</script>

<template>
  <div v-if="kind === 'pr'" class="my-pulls-table-wrap task-link-table-wrap">
    <table class="my-pulls-table task-link-table">
      <thead>
        <tr>
          <th>PR</th>
          <th>Status</th>
          <th>Review</th>
          <th>Reviewers</th>
          <th>Checks</th>
          <th>Comments</th>
          <th>Conflicts</th>
          <th>Issue</th>
          <th>Description</th>
          <th>Ready</th>
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="entry in items"
          :key="entry.key"
          class="task-link-row"
          :class="[`attention-rank-${attentionState(entry).rank}`, { active: isSelected(entry) }]"
          role="link"
          tabindex="0"
          :aria-current="isSelected(entry) ? 'true' : undefined"
          :aria-label="`Open #${entry.number} ${entry.title || ''} in this task`"
          @click="navigate(entry)"
          @keydown.enter="navigate(entry)"
          @keydown.space.prevent="navigate(entry)"
        >
          <td class="my-pulls-pr-cell">
            <span
              class="my-pulls-attention"
              role="img"
              :title="attentionState(entry).label"
              :aria-label="attentionState(entry).label"
            ></span>
            <span class="my-pulls-number">#{{ entry.number }}</span>
            <span class="my-pulls-repository faint" :title="repositoryName(entry)">{{ repositoryName(entry) }}</span>
            <span class="my-pulls-title" :title="entry.title">{{ entry.title || 'Untitled' }}</span>
          </td>
          <td data-label="Status">
            <span class="badge" :class="pullStatusClass(entry)">{{ pullStatusLabel(entry) }}</span>
          </td>
          <td data-label="Review">
            <span class="badge" :class="reviewTone(entry)">{{ reviewLabel(entry) }}</span>
          </td>
          <td class="my-pulls-approvers" data-label="Reviewers" :title="reviewersTitle(entry)">
            <template v-if="reviewers(entry).length">
              <span class="my-pulls-approvers-label faint">{{ reviewerPrefix(entry) }}</span>
              <template v-for="(login, index) in reviewers(entry)" :key="login">
                <span v-if="index" class="faint">, </span>
                <router-link
                  v-if="personLinkFor(login)"
                  :to="personLinkFor(login).path"
                  :class="{ faint: personLinkFor(login).missing }"
                  @click.stop
                  >{{ login }}</router-link
                >
                <span v-else>{{ login }}</span>
              </template>
            </template>
            <span v-else class="faint" :class="{ 'tone-warn': reviewerNeedsPerson(entry) }">{{
              reviewerEmptyLabel(entry)
            }}</span>
          </td>
          <td data-label="Checks" @click.stop>
            <PullChecksPopover :pull="entry" />
          </td>
          <td class="my-pulls-threads" data-label="Comments" :title="commentsTitle(entry)">
            <span :class="{ 'my-pulls-threads-open': entry.open_threads > 0 }">{{ entry.open_threads || 0 }} open</span>
          </td>
          <td data-label="Conflicts" :class="conflictsTone(entry)" :title="conflictsTitle(entry)">
            {{ conflictsLabel(entry) }}
          </td>
          <td data-label="Issue">
            <span class="badge" :class="linkedIssueTone(entry)" :title="linkedIssueTitle(entry)">{{
              linkedIssueLabel(entry)
            }}</span>
          </td>
          <td data-label="Description">
            <span class="badge" :class="descriptionTone(entry)" :title="descriptionTitle(entry)">{{
              descriptionLabel(entry)
            }}</span>
          </td>
          <td data-label="Ready">
            <span class="badge" :class="isReadyToMerge(entry) ? 'ok' : ''" :title="readyToMergeTitle(entry)">{{
              isReadyToMerge(entry) ? 'Yes' : 'No'
            }}</span>
          </td>
          <td class="faint" data-label="Updated">
            <span v-if="entry.updated_at" class="mono" :title="formatDateTime(entry.updated_at)">{{
              timeAgo(entry.updated_at)
            }}</span>
            <span v-else>—</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <nav v-else class="task-link-list" :aria-label="`Linked ${label}s`">
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
        <span v-if="issueStateLabel(entry)" class="badge" :class="`st-${String(entry.state).toLowerCase()}`">{{
          issueStateLabel(entry)
        }}</span>
      </span>
    </router-link>
  </nav>
</template>
