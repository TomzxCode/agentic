<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { DECISIONS, decisionColor, orderedSections, recommendationColor, threadUrl } from '../feedback'
import { renderMarkdown } from '../markdown'
import { store, timeAgo } from '../store'
import { ghxItemUrl } from '../toolLinks'

// One analyzed reviewer comment: its recommendation, its sections, and the
// Implement / Decline / Defer decision the triage writes back into the analysis
// file. The PR feedback page stacks these under a group heading, and the PR
// view shows the same cards in its Feedback tab, so the decision works the same
// wherever the comment is read.

const props = defineProps({
  item: { type: Object, required: true }
})
const emit = defineEmits(['changed'])

// The decision being saved, so the buttons disable while the write is in flight.
const saving = ref(false)

function isActive(value) {
  return (props.item.decision || 'pending') === value
}

function runLabel() {
  const state = props.item.run_state
  return state === 'executed' ? 'executed' : state === 'awaiting' ? 'awaiting run' : ''
}

// The app's own page for the card's pull request, the card's primary link: the
// same page My PRs and the review queue open. Null when the file names no
// repository or number, since that page could not be built.
function prPath() {
  const item = props.item
  return item.repo && item.pr ? `/pr/${item.repo}/${item.pr}` : null
}

// The pull request's page in the local ghx web UI, when one is configured.
function ghxLink() {
  return ghxItemUrl({ url: props.item.pr_url }, store.settings?.ghx_url)
}

async function setDecision(value) {
  const decision = value === 'pending' ? null : value
  saving.value = true
  try {
    const saved = await api.feedback.setDecision(props.item.feedback_id, decision)
    emit('changed', saved)
    store.notify(decision ? `${saved.feedback_id} → ${decision}` : `${saved.feedback_id} reset`)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    saving.value = false
  }
}

async function copyReply() {
  const text = props.item.sections?.['Suggested reply']
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    store.notify('Reply copied')
  } catch {
    store.notify('Copy failed', true)
  }
}
</script>

<template>
  <article
    class="feedback-card"
    :class="{ pending: item.status === 'pending' }"
    :style="{
      '--rec-color': recommendationColor(item.recommendation),
      '--decision-color': decisionColor(item.decision || 'pending')
    }"
  >
    <div class="card-rail"></div>
    <div class="card-main">
      <div class="card-top">
        <div class="pills">
          <span class="pill rec">{{ item.recommendation || 'n/a' }}</span>
          <span class="pill">{{ item.confidence || '?' }} confidence</span>
          <span class="pill">{{ item.kind || 'comment' }}</span>
          <span v-if="item.state === 'closed'" class="pill closed">closed</span>
          <span
            class="pill decision"
            :class="item.status"
            :style="{ '--c': decisionColor(item.decision || 'pending') }"
          >
            {{ item.status }}
          </span>
          <span v-if="item.run_state !== 'none'" class="pill run" :class="item.run_state">{{ runLabel() }}</span>
        </div>
        <div class="card-when faint">
          <span :title="item.created_at">{{ timeAgo(item.created_at) }}</span>
          <span v-if="!(item.created_at || '').slice(0, 10)" class="faint">—</span>
        </div>
      </div>

      <h3 class="card-title">{{ item.title }}</h3>
      <div class="card-meta">
        <router-link v-if="prPath()" class="feedback-pr-link" :to="prPath()" :title="`Open PR #${item.pr} in the app`"
          >{{ item.repo }}#{{ item.pr }}</router-link
        >
        <span v-else>{{ item.repo }}#{{ item.pr }}</span>
        <a
          v-if="ghxLink()"
          class="feedback-tool-link"
          :href="ghxLink()"
          target="_blank"
          rel="noopener"
          title="Open in ghx"
          >ghx</a
        >
        <a
          v-if="item.pr_url"
          class="feedback-tool-link"
          :href="item.pr_url"
          target="_blank"
          rel="noopener"
          title="Open on GitHub"
          >gh</a
        >
        <span>·</span><span>{{ item.author }}</span> <span>·</span><span class="mono">{{ item.feedback_id }}</span>
      </div>

      <div class="card-actions">
        <button
          v-for="action in DECISIONS"
          :key="action.value"
          class="btn sm"
          :class="[action.value, { active: isActive(action.value) }]"
          :disabled="saving"
          @click="setDecision(action.value)"
        >
          {{ action.label }}
        </button>
        <button
          class="btn sm pending"
          :class="{ active: isActive('pending') }"
          :disabled="saving"
          @click="setDecision('pending')"
        >
          Reset
        </button>
        <span class="grow"></span>
        <a v-if="threadUrl(item)" class="btn sm ghost" :href="threadUrl(item)" target="_blank" rel="noopener">Thread</a>
      </div>

      <details
        v-for="(section, index) in orderedSections(item)"
        :key="section.name"
        class="feedback-section"
        :open="index === 0"
      >
        <summary>
          {{ section.name }}
          <button
            v-if="section.name === 'Suggested reply'"
            type="button"
            class="btn sm ghost reply-copy"
            @click.prevent.stop="copyReply()"
          >
            copy
          </button>
        </summary>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div class="md feedback-section-body" v-html="renderMarkdown(section.body)"></div>
      </details>
    </div>
  </article>
</template>
