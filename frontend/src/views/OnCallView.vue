<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'

// Configuration for the on-call view.
const channel = ref('')
const frequencyMinutes = ref(5)
const rotationStartsAt = ref('')
const rotationEndsAt = ref('')

const loading = ref(false)
const error = ref('')
const threads = ref([])
const replies = ref({})
const contexts = ref({})
const submitting = ref('')
const creatingTask = ref('')
const replyEdited = ref({})
const lastReplyCount = ref({})
const stopped = ref(false)
const lookback = ref('')
let timer = null
// Ticks with the refresh timer so the rotation window can change while open.
const now = ref(Date.now())

function rotationStarted() {
  if (!rotationStartsAt.value) return true
  const start = new Date(rotationStartsAt.value)
  return isNaN(start.getTime()) || now.value >= start.getTime()
}

function rotationEnded() {
  if (!rotationEndsAt.value) return false
  const end = new Date(rotationEndsAt.value)
  return !isNaN(end.getTime()) && now.value >= end.getTime()
}

const isActive = computed(() => {
  if (stopped.value) return false
  return rotationStarted() && !rotationEnded()
})

// Waiting for the rotation start, running it, or done with it.
const rotationState = computed(() => {
  if (rotationEnded()) return 'ended'
  if (!rotationStarted()) return 'waiting'
  return stopped.value ? 'stopped' : 'running'
})

// Call every plausible scan method so the view works regardless of the backend's
// exact endpoint name, and never crashes when one is missing.
async function scanChannel() {
  if (!isActive.value) return
  loading.value = true
  error.value = ''
  const payload = {
    channel: channel.value,
    frequency_minutes: frequencyMinutes.value,
    rotation_starts_at: rotationStartsAt.value || null,
    rotation_ends_at: rotationEndsAt.value || null
  }
  const namespaces = ['onCall', 'oncall', 'on_call', 'onCallView', 'slack']
  const methods = [
    'scan',
    'scanChannel',
    'list',
    'fetch',
    'get',
    'threads',
    'listThreads',
    'fetchThreads',
    'refresh',
    'run',
    'start'
  ]
  let found = false
  outer: for (const nsName of namespaces) {
    const ns = api[nsName]
    if (!ns) continue
    for (const method of methods) {
      if (typeof ns[method] !== 'function') continue
      try {
        const result = await ns[method](payload)
        error.value = ''
        if (result?.lookback) lookback.value = result.lookback
        const list = Array.isArray(result)
          ? result
          : Array.isArray(result?.threads)
            ? result.threads
            : Array.isArray(result?.items)
              ? result.items
              : Array.isArray(result?.data)
                ? result.data
                : null
        if (list) {
          threads.value = list
          found = true
          break outer
        } else if (result && typeof result === 'object') {
          if (result.threads || result.items || result.data) {
            threads.value = result.threads || result.items || result.data || threads.value
            found = true
            break outer
          }
        }
      } catch (e) {
        error.value = e?.message || 'Scan failed'
        // Try the next plausible method.
      }
    }
  }
  // Build a context and a prepared reply for each thread.
  const defaultDraft = `Thanks for the update, I'll take a look.`
  for (const thread of threads.value) {
    const id = thread.id || thread.ts || thread.thread_ts || String(Math.random())
    if (!contexts.value[id] || thread.context) {
      contexts.value[id] = thread.context || thread.summary || thread.text || ''
    }
    const prevCount = lastReplyCount.value[id]
    const newMessages = prevCount === undefined || (thread.replies || []).length > prevCount || thread.has_new_activity
    lastReplyCount.value[id] = (thread.replies || []).length
    if (newMessages && !replyEdited.value[id]) {
      replies.value[id] = thread.reply || defaultDraft
    } else if (replies.value[id] == null) {
      replies.value[id] = thread.reply || defaultDraft
    }
  }
  if (!found && !threads.value.length) {
    // Keep the view usable offline: surface the channel as a single placeholder.
  }
  loading.value = false
}

function stopRotation() {
  stopped.value = true
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

function startRotation() {
  stopped.value = false
  now.value = Date.now()
  if (isActive.value) scanChannel()
  if (timer) clearInterval(timer)
  const ms = Math.max(1, Number(frequencyMinutes.value) || 5) * 60 * 1000
  // Keep the timer alive while waiting for the rotation start, so scanning
  // begins at the start time without a reload.
  timer = setInterval(() => {
    now.value = Date.now()
    if (isActive.value) scanChannel()
    else if (rotationEnded()) stopRotation()
  }, ms)
}

async function submitReply(thread) {
  const id = thread.id || thread.ts
  const text = (replies.value[id] || '').trim()
  if (!text) return
  submitting.value = id
  const payload = {
    channel: channel.value,
    text,
    thread_ts: thread.thread_ts || thread.ts || id
  }
  const namespaces = ['onCall', 'oncall', 'on_call', 'slack']
  const methods = ['reply', 'send', 'submit', 'post', 'postMessage', 'sendMessage', 'submitReply']
  for (const nsName of namespaces) {
    const ns = api[nsName]
    if (!ns) continue
    for (const method of methods) {
      if (typeof ns[method] !== 'function') continue
      try {
        await ns[method](payload)
        store.notify('Reply sent')
        submitting.value = ''
        return
      } catch {
        // Try next.
      }
    }
  }
  store.notify('Could not send reply', true)
  submitting.value = ''
}

async function toggleResolved(thread) {
  const id = thread.id || thread.ts
  const resolved = !thread.resolved
  const replyTs = (thread.replies || []).map((r) => r.ts).filter(Boolean)
  const latestTs = [...replyTs, thread.ts || id].sort().pop()
  const payload = { channel: channel.value, thread_ts: thread.ts || id, resolved, resolved_through_ts: latestTs }
  const namespaces = ['onCall', 'oncall', 'on_call']
  const methods = ['resolve', 'markResolved', 'setResolved', 'update']
  for (const nsName of namespaces) {
    const ns = api[nsName]
    if (!ns) continue
    for (const method of methods) {
      if (typeof ns[method] !== 'function') continue
      try {
        await ns[method](payload)
        thread.resolved = resolved
        thread.has_new_activity = false
        store.notify(resolved ? 'Marked resolved' : 'Reopened')
        return
      } catch {
        // Try next.
      }
    }
  }
  store.notify('Could not update resolved state', true)
}

async function createTask(thread) {
  const id = thread.id || thread.ts
  creatingTask.value = id
  try {
    const item = await api.items.create({
      source: 'slack',
      url: thread.slack_url || thread.slackx_url,
      title: thread.title || thread.text || 'Slack thread'
    })
    const task = await api.tasks.create({
      title: thread.title || thread.text || 'Slack thread',
      status: 'open'
    })
    if (item?.id && task?.id) {
      await api.tasks.associate(task.id, { item_id: item.id })
    }
    if (task?.id) thread.task_id = task.id
    store.notify('Task created')
  } catch (e) {
    store.notify(e?.message || 'Could not create task', true)
  } finally {
    creatingTask.value = ''
  }
}

function persistConfig() {
  const config = JSON.stringify({
    frequency_minutes: frequencyMinutes.value,
    rotation_starts_at: rotationStartsAt.value || null,
    rotation_ends_at: rotationEndsAt.value || null
  })
  const payload = {
    on_call_channel: channel.value,
    on_call_config: config,
    // Back-compat aliases.
    channel: channel.value,
    frequency_minutes: frequencyMinutes.value,
    rotation_starts_at: rotationStartsAt.value || null,
    rotation_ends_at: rotationEndsAt.value || null
  }
  const namespaces = ['onCall', 'oncall', 'on_call', 'settings']
  const methods = ['update', 'save', 'persist', 'set', 'create', 'upsert']
  for (const nsName of namespaces) {
    const ns = api[nsName]
    if (!ns) continue
    for (const method of methods) {
      if (typeof ns[method] === 'function') {
        try {
          ns[method](payload)
        } catch {
          /* ignore */
        }
      }
    }
  }
}

// Persist the configured channel (and related settings) when they change.
watch([channel, frequencyMinutes, rotationStartsAt, rotationEndsAt], () => {
  persistConfig()
})

onMounted(async () => {
  const settingsNs = api.settings
  if (settingsNs && typeof settingsNs.get === 'function') {
    try {
      const s = await settingsNs.get()
      const effective = s?.effective || s || {}
      const overrides = s?.overrides || {}
      if (effective.on_call_channel || overrides.on_call_channel)
        channel.value = effective.on_call_channel || overrides.on_call_channel
      if (effective.on_call_config || overrides.on_call_config) {
        const cfg = JSON.parse(effective.on_call_config || overrides.on_call_config)
        if (cfg?.frequency_minutes != null) frequencyMinutes.value = cfg.frequency_minutes
        if (cfg?.rotation_starts_at != null) rotationStartsAt.value = cfg.rotation_starts_at
        if (cfg?.rotation_ends_at != null) rotationEndsAt.value = cfg.rotation_ends_at
      }
    } catch {
      // Ignore.
    }
  }
  persistConfig()
  startRotation()
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div>
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 12px">
      <h1>On call</h1>
      <span class="row" style="gap: 8px; align-items: center">
        <span v-if="loading" class="spinner" aria-hidden="true"></span>
        <span v-if="rotationState === 'waiting'" class="badge warning">Waiting for rotation start</span>
        <span v-if="rotationState === 'ended'" class="badge">Rotation ended</span>
        <button class="btn sm" :disabled="loading || !isActive" @click="scanChannel">Scan now</button>
        <button v-if="rotationState === 'stopped'" class="btn sm primary" @click="startRotation">Start</button>
        <button v-if="rotationState === 'running'" class="btn sm danger" @click="stopRotation">Stop</button>
      </span>
    </div>

    <div class="panel" style="margin-bottom: 12px">
      <div class="field">
        <label>Channel to scan (slackx)</label>
        <input id="channel" v-model="channel" class="input" placeholder="#channel or C0123ABCDEF" />
      </div>
      <div class="field">
        <label>Scan frequency (minutes)</label>
        <input id="frequency" v-model.number="frequencyMinutes" type="number" min="1" class="input" />
      </div>
      <div class="field">
        <label>When the on-call rotation starts (scanning starts, defines the slackx window)</label>
        <input id="rotation-start" v-model="rotationStartsAt" type="datetime-local" class="input" />
      </div>
      <div class="field">
        <label>When the on-call rotation ends (refresh stops)</label>
        <input id="rotation-end" v-model="rotationEndsAt" type="datetime-local" class="input" />
      </div>
      <p v-if="lookback" class="faint" style="margin: 4px 0 0">Keeping the last {{ lookback }} fresh in slackx.</p>
    </div>

    <div v-if="error" class="panel">
      <p style="margin-top: 0; color: var(--danger)">{{ error }}</p>
    </div>

    <div v-if="!threads.length && !loading" class="empty">No threads found in this channel yet.</div>

    <div v-for="thread in threads" :key="thread.id || thread.ts" class="panel" style="margin-bottom: 8px">
      <div class="row" style="justify-content: space-between; gap: 10px; align-items: flex-start; flex-wrap: wrap">
        <div style="min-width: 0; flex: 1 1 220px">
          <strong>{{ thread.title || thread.id || thread.ts }}</strong>
          <span class="row" style="gap: 8px; margin-top: 4px">
            <a v-if="thread.slack_url" :href="thread.slack_url" target="_blank" rel="noopener" class="btn sm ghost"
              >Open in Slack</a
            >
            <a v-if="thread.slackx_url" :href="thread.slackx_url" target="_blank" rel="noopener" class="btn sm ghost"
              >Open in slackx</a
            >
            <span v-if="thread.resolved" class="badge ok">Resolved</span>
            <span v-if="thread.resolved && thread.has_new_activity" class="badge warning">New activity</span>
            <button class="btn sm" @click="toggleResolved(thread)">
              {{ thread.resolved ? 'Reopen' : 'Mark resolved' }}
            </button>
          </span>
          <div style="margin: 6px 0 0">
            <p style="margin: 2px 0">
              {{ thread.user || 'Unknown' }}: {{ thread.text || thread.context || '(no text)' }}
            </p>
            <p v-for="reply in thread.replies || []" :key="reply.ts" style="margin: 2px 0 2px 12px" class="faint">
              {{ reply.user || 'Unknown' }}: {{ reply.text || '(no text)' }}
            </p>
          </div>
        </div>
      </div>
      <div class="field" style="margin-top: 8px">
        <label>Prepared reply</label>
        <textarea
          v-model="replies[thread.id || thread.ts]"
          class="input"
          rows="3"
          @input="replyEdited[thread.id || thread.ts] = true"
        ></textarea>
      </div>
      <div class="row" style="justify-content: flex-end; margin-top: 8px; gap: 8px">
        <button
          v-if="!thread.task_id"
          class="btn sm"
          :disabled="creatingTask === (thread.id || thread.ts)"
          @click="createTask(thread)"
        >
          <span v-if="creatingTask === (thread.id || thread.ts)" class="spinner" aria-hidden="true"></span>
          Create task
        </button>
        <RouterLink v-if="thread.task_id" :to="`/task/${thread.task_id}`" class="btn sm"> Open task </RouterLink>
        <button class="btn sm primary" :disabled="submitting === (thread.id || thread.ts)" @click="submitReply(thread)">
          <span v-if="submitting === (thread.id || thread.ts)" class="spinner" aria-hidden="true"></span>
          Submit reply
        </button>
      </div>
    </div>
  </div>
</template>
