<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'

const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) }
})

const form = reactive({
  slack_user_id: '',
  slack_bot_token: '',
  slack_events_user_id: '',
  slack_events_channel: '',
  slack_notify_user_id: ''
})
const saving = ref(false)
const saved = ref(false)
const testing = ref(false)
const testResult = ref('')
let savedTimer

watch(
  () => props.overrides,
  (overrides) => {
    form.slack_user_id = overrides.slack_user_id ?? ''
    form.slack_bot_token = overrides.slack_bot_token ?? ''
    form.slack_events_user_id = overrides.slack_events_user_id ?? ''
    form.slack_events_channel = overrides.slack_events_channel ?? ''
    form.slack_notify_user_id = overrides.slack_notify_user_id ?? ''
  },
  { immediate: true }
)

async function saveField(key) {
  saving.value = true
  try {
    await api.settings.update({ [key]: form[key] })
    await store.loadSettings().catch(() => {})
    saved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = false), 1500)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    saving.value = false
  }
}

async function sendTest() {
  testing.value = true
  testResult.value = ''
  try {
    const result = await api.slack.test({
      slack_user_id: form.slack_user_id || undefined,
      slack_events_user_id: form.slack_events_user_id || undefined,
      slack_events_channel: form.slack_events_channel || undefined,
      slack_notify_user_id: form.slack_notify_user_id || undefined
    })
    testResult.value = `Sent (ts ${result.ts || 'n/a'})`
    store.notify('Test notification sent')
  } catch (e) {
    testResult.value = e.message
    store.notify(e.message, true)
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Slack events</h2>
      <span v-if="saving" class="faint">saving…</span>
      <span v-else-if="saved" class="faint">saved</span>
    </div>
    <p class="faint" style="margin-top: 0">
      Where events sent through Slack are delivered. Leave a field blank to fall back to the next one, or pass a
      recipient on each call. The Slack token itself is configured through the environment.
    </p>

    <div class="field">
      <label>Slack user id</label>
      <input v-model="form.slack_user_id" class="input" placeholder="U0123ABCDEF" @blur="saveField('slack_user_id')" />
    </div>
    <div class="field">
      <label>Slack bot token</label>
      <input
        v-model="form.slack_bot_token"
        class="input"
        autocomplete="off"
        placeholder="xoxb-..."
        @blur="saveField('slack_bot_token')"
      />
      <p class="faint" style="margin: 4px 0 0">
        Posts notifications as a bot instead of as you. Leave blank to use your Slack token.
      </p>
    </div>
    <div class="field">
      <label>Slack events user id</label>
      <input
        v-model="form.slack_events_user_id"
        class="input"
        placeholder="U0123ABCDEF"
        @blur="saveField('slack_events_user_id')"
      />
    </div>
    <div class="field">
      <label>Slack events channel</label>
      <input
        v-model="form.slack_events_channel"
        class="input"
        placeholder="#events or C0123ABCDEF"
        @blur="saveField('slack_events_channel')"
      />
    </div>
    <div class="field">
      <label>Slack notify user id</label>
      <input
        v-model="form.slack_notify_user_id"
        class="input"
        placeholder="U0123ABCDEF"
        @blur="saveField('slack_notify_user_id')"
      />
    </div>

    <div class="row" style="margin-top: 12px; gap: 8px; align-items: center">
      <button class="btn" :disabled="testing" @click="sendTest">
        <span v-if="testing" class="spinner" aria-hidden="true"></span>
        {{ testing ? 'Sending…' : 'Send test notification' }}
      </button>
      <span v-if="testResult" class="faint">{{ testResult }}</span>
    </div>
  </section>
</template>
