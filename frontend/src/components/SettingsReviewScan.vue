<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store, timeAgo } from '../store'

// The "Review requests" settings section: the background scan that asks GitHub
// which pull requests await a review, and the review SLOs. Which repositories it
// considers is set in the GitHub section. The page shell supplies the raw
// overrides/defaults and whether this section is showing, so the status loads
// when it is opened.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) },
  active: { type: Boolean, default: false }
})

const form = reactive({
  review_slo: '',
  review_nudge_slo: '',
  review_auto_poke: '',
  review_auto_poke_message: '',
  review_poke_message: ''
})
const defaultAutoPokeMessage = ':wave::robot_face: I would love your review on this PR: {link}'
const status = ref(null)
const saving = ref('')
const saved = ref('')
const scanning = ref(false)
let savedTimer

async function load() {
  // Best effort: a backend without the endpoint simply shows no status.
  if (typeof api.reviews?.scan !== 'function') return
  try {
    status.value = await api.reviews.scan()
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function save(key) {
  saving.value = key
  try {
    await api.settings.update({ [key]: form[key] })
    saved.value = key
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = ''), 1500)
    status.value = await api.reviews.scan().catch(() => status.value)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    saving.value = ''
  }
}

// The scan runs in the request, so a big result set can take a moment.
async function scanNow() {
  if (scanning.value || typeof api.reviews?.runScan !== 'function') return
  scanning.value = true
  try {
    status.value = await api.reviews.runScan()
    if (status.value.error) store.notify(status.value.error, true)
    else store.notify(`Scan found ${status.value.found}, kept ${status.value.kept}`)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    scanning.value = false
  }
}

watch(
  () => props.overrides,
  (overrides) => {
    form.review_slo = overrides.review_slo ?? ''
    form.review_nudge_slo = overrides.review_nudge_slo ?? ''
    form.review_auto_poke = overrides.review_auto_poke ?? ''
    form.review_auto_poke_message = overrides.review_auto_poke_message ?? ''
    form.review_poke_message = overrides.review_poke_message ?? ''
  },
  { immediate: true }
)

watch(
  () => props.active,
  (active) => {
    if (active) load()
  }
)

onMounted(load)
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Review requests</h2>
      <button class="btn sm" :disabled="scanning" @click="scanNow">
        <span v-if="scanning" class="spinner" aria-hidden="true"></span>
        Scan now
      </button>
    </div>
    <p class="faint" style="margin-top: 0">
      A background scan asks GitHub which pull requests await your review: those with a review requested from you, and
      the open ones you have already reviewed. They join the
      <router-link to="/reviews">review queue</router-link> even before a review report exists for them. It runs after
      each GitHub cache refresh, through <code>ghx</code>'s cache, so repositories it has never cached are not scanned.
      Which repositories the scan considers is set in the <strong>GitHub</strong> section. The nudge SLO below instead
      reads your own open pull requests, the way the <router-link to="/my-pulls">My PRs</router-link> page does.
    </p>

    <p class="faint">
      Last scan:
      <template v-if="status?.last_run_at">
        {{ timeAgo(status.last_run_at) }} · {{ status.found }} found, {{ status.kept }} kept
        <span v-if="status.origin === 'manual'"> · run by hand</span>
        <span v-else-if="status?.stored"> · {{ status.stored }} in the queue</span>
      </template>
      <template v-else>never</template>
    </p>
    <p v-if="status?.error" style="margin: 4px 0 0; color: var(--danger)">{{ status.error }}</p>

    <div class="field">
      <label>
        Review SLO
        <span v-if="saving === 'review_slo'" class="faint">saving…</span>
        <span v-else-if="saved === 'review_slo'" class="faint">saved</span>
      </label>
      <input
        v-model="form.review_slo"
        class="input mono"
        :placeholder="defaults.review_slo || '1d'"
        @blur="save('review_slo')"
      />
      <p class="faint" style="margin: 4px 0 0">
        How long a pull request may await your review before the inbox flags it, such as <code>8h</code> or
        <code>1d</code>. The wait starts when the scan first sees the pull request waiting. Leave it blank to turn the
        SLO off.
      </p>
    </div>

    <div class="field">
      <label>
        Review nudge SLO
        <span v-if="saving === 'review_nudge_slo'" class="faint">saving…</span>
        <span v-else-if="saved === 'review_nudge_slo'" class="faint">saved</span>
      </label>
      <input
        v-model="form.review_nudge_slo"
        class="input mono"
        :placeholder="defaults.review_nudge_slo || '1d'"
        @blur="save('review_nudge_slo')"
      />
      <p class="faint" style="margin: 4px 0 0">
        How long a pull request of yours may wait without any review from anyone before the inbox offers to poke its
        reviewers, such as <code>1h30m</code> or <code>1d</code>. The wait runs from when the pull request was opened.
        Leave it blank to turn the nudge off.
      </p>
    </div>

    <div class="field">
      <label>
        Review auto-poke
        <span v-if="saving === 'review_auto_poke'" class="faint">saving…</span>
        <span v-else-if="saved === 'review_auto_poke'" class="faint">saved</span>
      </label>
      <input
        v-model="form.review_auto_poke"
        class="input mono"
        :placeholder="defaults.review_auto_poke || '24h,26h,28h'"
        @blur="save('review_auto_poke')"
      />
      <p class="faint" style="margin: 4px 0 0">
        Comma-separated absolute ages at which to DM the requested reviewers of a pull request of yours that nobody has
        reviewed, counted from when it was last marked ready for review (or opened if it never was a draft):
        <code>24h,26h,28h</code> pokes three times. A repeat stays on the SLO's clock, such as <code>24h+1h</code>;
        <code>24h+~1h</code> waits that long after each poke instead. <code>now+1h</code> pokes now and then hourly,
        <code>next+1h</code> waits for the next hourly boundary, and <code>next+~1h</code> waits one interval from now.
        Leave it blank to turn auto-poking off.
      </p>
    </div>

    <div class="field">
      <label>
        Auto-poke message
        <span v-if="saving === 'review_auto_poke_message'" class="faint">saving…</span>
        <span v-else-if="saved === 'review_auto_poke_message'" class="faint">saved</span>
      </label>
      <textarea
        v-model="form.review_auto_poke_message"
        class="textarea mono"
        rows="3"
        :placeholder="defaults.review_auto_poke_message || defaultAutoPokeMessage"
        @blur="save('review_auto_poke_message')"
      ></textarea>
      <p class="faint" style="margin: 4px 0 0">
        The DM the auto-poke sends. Variables: <code>{link}</code> (the pull request as a Slack link),
        <code>{url}</code>, <code>{title}</code>, <code>{slo}</code> (the age that triggered the poke, such as
        <code>1d</code>), and <code>{elapsed}</code> (the pull request's age since it was opened or last marked ready
        for review, such as <code>1d 6h</code>). Leave it blank for the default message.
      </p>
    </div>

    <div class="field">
      <label>
        Poke message
        <span v-if="saving === 'review_poke_message'" class="faint">saving…</span>
        <span v-else-if="saved === 'review_poke_message'" class="faint">saved</span>
      </label>
      <textarea
        v-model="form.review_poke_message"
        class="textarea mono"
        rows="3"
        :placeholder="defaults.review_poke_message || defaultAutoPokeMessage"
        @blur="save('review_poke_message')"
      ></textarea>
      <p class="faint" style="margin: 4px 0 0">
        The DM a manual poke sends. The variables are the same; <code>{slo}</code> is the review nudge SLO and
        <code>{elapsed}</code> is the pull request's age since it was opened or last marked ready for review. Leave it
        blank for the default message.
      </p>
    </div>
  </section>
</template>
