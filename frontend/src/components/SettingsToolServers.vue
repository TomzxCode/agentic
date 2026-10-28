<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'

// The "Local tools" settings section: how the server runs the ghx and slackx
// helper CLIs, and the base URLs of their web UIs. When a URL is set, GitHub
// and Slack items link into that UI from the item detail page and the item
// lists. The transport decides whether each command line spawns the binary,
// goes to a server you run, or goes to the serve process this server starts and
// manages; it is read per call, so a change applies without a restart. The
// server URL and token only apply to rpc, so they are hidden for the other
// transports. A managed tool's web UI runs on a port this server picks, so its
// URL is shown as a link to open rather than offered as a field, and the port it
// answers on is shown beside it because item links use that URL. Like the other
// sections, the page shell owns the single settings read and this component
// saves each field on blur.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) },
  effective: { type: Object, default: () => ({}) },
  // The managed tools this server runs, with the port each answers on.
  managed: { type: Array, default: () => [] }
})

const emit = defineEmits(['changed'])

// The managed tool's process as the server last reported it: its URL carries
// the port it actually serves on.
function managedStatus(tool) {
  return props.managed.find((status) => status.tool === tool)
}

// The URL a managed tool's web UI is at. The server reports the port the
// process actually bound; a configured URL supplies the host, since the user
// may reach this machine by name from another device. Its own port is ignored:
// it is usually stale once the process has moved to a free one. Nothing is
// guessed when the server has not reported a URL yet.
function webUrl(tool) {
  const key = `${tool}_url`
  const configured =
    store.settings?.[key]?.trim() ||
    props.effective[key]?.trim() ||
    props.overrides[key]?.trim() ||
    props.defaults[key]?.trim()
  const status = managedStatus(tool)
  if (status?.url) {
    if (!configured || !status.port) return status.url
    try {
      const url = new URL(configured)
      url.port = String(status.port)
      return url.toString().replace(/\/$/, '')
    } catch {
      return status.url
    }
  }
  return configured || ''
}

const form = reactive({
  ghx_backend: 'cli',
  ghx_rpc_url: '',
  ghx_rpc_token: '',
  slackx_backend: 'cli',
  slackx_rpc_url: '',
  slackx_rpc_token: '',
  ghx_url: '',
  slackx_url: ''
})
const saving = ref(false)
const saved = ref(false)
let savedTimer

watch(
  () => props.overrides,
  (overrides) => {
    form.ghx_url = overrides.ghx_url ?? ''
    form.slackx_url = overrides.slackx_url ?? ''
    // The transport has no "blank" state, so an unset or blank override shows
    // the environment's default (the page's defaults carry it).
    form.ghx_backend = overrides.ghx_backend || props.defaults.ghx_backend || 'cli'
    form.slackx_backend = overrides.slackx_backend || props.defaults.slackx_backend || 'cli'
    form.ghx_rpc_url = overrides.ghx_rpc_url ?? ''
    form.ghx_rpc_token = overrides.ghx_rpc_token ?? ''
    form.slackx_rpc_url = overrides.slackx_rpc_url ?? ''
    form.slackx_rpc_token = overrides.slackx_rpc_token ?? ''
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

// A managed tool's process is this server's, so restarting it is an action
// rather than a field: it picks up a new binary or the tool's own config
// without restarting Agentic.
const restarting = reactive({ ghx: false, slackx: false })

async function restart(tool) {
  restarting[tool] = true
  try {
    const result = await api.settings.restartTool(tool)
    const where = result.url ? ` on ${result.url}` : ''
    store.notify(
      result.running ? `${tool} restarted${where}` : `${tool} did not start: check that its binary is installed`,
      !result.running
    )
    // A restart can land on a different port, so the page reloads the settings
    // (which carry each managed tool's port) instead of showing a stale one.
    // The store is what item links read, so it reloads too.
    emit('changed')
    await store.loadSettings().catch(() => {})
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    restarting[tool] = false
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Local tools</h2>
      <span v-if="saving" class="faint">saving…</span>
      <span v-else-if="saved" class="faint">saved</span>
    </div>
    <p class="faint" style="margin-top: 0">
      How the server runs ghx and slackx, and the base URLs of their web UIs. A URL makes GitHub and Slack items show a
      link that opens them there; leave it blank to hide that link. A managed tool supplies its own URL, shown as a link
      to open.
    </p>

    <h3 style="margin: 14px 0 6px">ghx (GitHub)</h3>
    <div class="field">
      <label>Transport</label>
      <select v-model="form.ghx_backend" class="select" @change="saveField('ghx_backend')">
        <option value="cli">cli: run the ghx binary per call</option>
        <option value="rpc">rpc: ask a ghx server you run yourself</option>
        <option value="managed">managed: this server runs ghx serve and calls it</option>
      </select>
    </div>
    <p v-if="form.ghx_backend === 'managed'" class="faint" style="margin: 4px 0 0">
      The server starts <code>ghx serve</code> on a free port, listening on all interfaces, and stops it when it stops.
      The JSON-RPC endpoint uses a token the server generates, so there is no server URL or token to set.
      <template v-if="managedStatus('ghx') && !managedStatus('ghx').running">
        It is not running; its next start will serve at <code>{{ webUrl('ghx') }}</code
        >.
      </template>
      <template v-else-if="webUrl('ghx')">
        Its web UI is at <a :href="webUrl('ghx')" target="_blank" rel="noopener">{{ webUrl('ghx') }}</a> while the
        server runs.
      </template>
      <template v-else> Its web UI address is reported once the server starts the process. </template>
      Restart it to pick up a new binary or its own configuration.
    </p>
    <div v-if="form.ghx_backend === 'managed'" style="margin: 8px 0 0">
      <button class="btn sm ghost" :disabled="restarting.ghx" @click="restart('ghx')">
        <span v-if="restarting.ghx" class="spinner" aria-hidden="true"></span>
        Restart ghx serve
      </button>
    </div>
    <div v-if="form.ghx_backend === 'rpc'" class="field">
      <label>ghx rpc server URL</label>
      <input
        v-model="form.ghx_rpc_url"
        class="input"
        :placeholder="defaults.ghx_rpc_url || 'http://127.0.0.1:8090'"
        @blur="saveField('ghx_rpc_url')"
      />
      <p class="faint" style="margin: 4px 0 0">
        The base URL <code>ghx rpc serve</code> listens on; the JSON-RPC endpoint is <code>&lt;url&gt;/rpc</code>. Used
        only when the transport is rpc, and read per call, so changes apply at once.
      </p>
    </div>
    <div v-if="form.ghx_backend === 'rpc'" class="field">
      <label>ghx rpc token</label>
      <input
        v-model="form.ghx_rpc_token"
        class="input"
        autocomplete="off"
        placeholder="only when the server is bound beyond loopback"
        @blur="saveField('ghx_rpc_token')"
      />
    </div>
    <div v-if="form.ghx_backend !== 'managed'" class="field">
      <label>ghx server URL (web UI)</label>
      <input
        v-model="form.ghx_url"
        class="input"
        :placeholder="defaults.ghx_url || 'http://localhost:8080'"
        @blur="saveField('ghx_url')"
      />
      <p class="faint" style="margin: 4px 0 0">
        The UI <code>ghx serve</code> starts (default port 8080). A GitHub issue or pull request opens at
        <code>&lt;url&gt;/#/&lt;owner&gt;/&lt;repo&gt;/&lt;issues|pulls&gt;/&lt;number&gt;</code>.
      </p>
    </div>

    <h3 style="margin: 14px 0 6px">slackx (Slack)</h3>
    <div class="field">
      <label>Transport</label>
      <select v-model="form.slackx_backend" class="select" @change="saveField('slackx_backend')">
        <option value="cli">cli: run the slackx binary per call</option>
        <option value="rpc">rpc: ask a slackx server you run yourself</option>
        <option value="managed">managed: this server runs slackx serve and calls it</option>
      </select>
    </div>
    <p v-if="form.slackx_backend === 'managed'" class="faint" style="margin: 4px 0 0">
      The server starts <code>slackx serve</code> on a free port, listening on all interfaces, and stops it when it
      stops. The JSON-RPC endpoint uses a token the server generates, so there is no server URL or token to set.
      <template v-if="managedStatus('slackx') && !managedStatus('slackx').running">
        It is not running; its next start will serve at <code>{{ webUrl('slackx') }}</code
        >.
      </template>
      <template v-else-if="webUrl('slackx')">
        Its web UI is at <a :href="webUrl('slackx')" target="_blank" rel="noopener">{{ webUrl('slackx') }}</a> while the
        server runs.
      </template>
      <template v-else> Its web UI address is reported once the server starts the process. </template>
      Restart it to pick up a new binary or its own configuration.
    </p>
    <div v-if="form.slackx_backend === 'managed'" style="margin: 8px 0 0">
      <button class="btn sm ghost" :disabled="restarting.slackx" @click="restart('slackx')">
        <span v-if="restarting.slackx" class="spinner" aria-hidden="true"></span>
        Restart slackx serve
      </button>
    </div>
    <div v-if="form.slackx_backend === 'rpc'" class="field">
      <label>slackx rpc server URL</label>
      <input
        v-model="form.slackx_rpc_url"
        class="input"
        :placeholder="defaults.slackx_rpc_url || 'http://127.0.0.1:8280'"
        @blur="saveField('slackx_rpc_url')"
      />
      <p class="faint" style="margin: 4px 0 0">
        The base URL <code>slackx rpc serve</code> listens on; the JSON-RPC endpoint is <code>&lt;url&gt;/rpc</code>.
        Used only when the transport is rpc, and read per call, so changes apply at once.
      </p>
    </div>
    <div v-if="form.slackx_backend === 'rpc'" class="field">
      <label>slackx rpc token</label>
      <input
        v-model="form.slackx_rpc_token"
        class="input"
        autocomplete="off"
        placeholder="only when the server is bound beyond loopback"
        @blur="saveField('slackx_rpc_token')"
      />
    </div>
    <div v-if="form.slackx_backend !== 'managed'" class="field">
      <label>slackx server URL (web UI)</label>
      <input
        v-model="form.slackx_url"
        class="input"
        :placeholder="defaults.slackx_url || 'http://localhost:8280'"
        @blur="saveField('slackx_url')"
      />
      <p class="faint" style="margin: 4px 0 0">
        The UI <code>slackx serve</code> starts (default port 8280). A Slack thread opens at
        <code>&lt;url&gt;/archives/&lt;channel&gt;/p&lt;ts&gt;</code>.
      </p>
    </div>
  </section>
</template>
