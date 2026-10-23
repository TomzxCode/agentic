<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'

// The "Local tools" settings section: how the server runs the ghx and slackx
// helper CLIs, and the base URLs of their web UIs. When a URL is set, GitHub
// and Slack items link into that UI from the item detail page and the item
// lists. The transport decides whether each command line spawns the binary or
// goes to the tool's JSON-RPC server; it is read per call, so a change applies
// without a restart. Like the other sections, the page shell owns the single
// settings read and this component saves each field on blur.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) }
})

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
      link that opens them there; leave it blank to hide that link.
    </p>

    <h3 style="margin: 14px 0 6px">ghx (GitHub)</h3>
    <div class="field">
      <label>Transport</label>
      <select v-model="form.ghx_backend" class="select" @change="saveField('ghx_backend')">
        <option value="cli">cli: run the ghx binary per call</option>
        <option value="rpc">rpc: ask a running ghx JSON-RPC server</option>
        <option value="serve">serve: run ghx serve managed by this server</option>
      </select>
    </div>
    <div class="field">
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
    <div class="field">
      <label>ghx rpc token</label>
      <input
        v-model="form.ghx_rpc_token"
        class="input"
        autocomplete="off"
        placeholder="only when the server is bound beyond loopback"
        @blur="saveField('ghx_rpc_token')"
      />
    </div>
    <div class="field">
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
        <option value="rpc">rpc: ask a running slackx JSON-RPC server</option>
        <option value="serve">serve: run slackx serve managed by this server</option>
      </select>
    </div>
    <div class="field">
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
    <div class="field">
      <label>slackx rpc token</label>
      <input
        v-model="form.slackx_rpc_token"
        class="input"
        autocomplete="off"
        placeholder="only when the server is bound beyond loopback"
        @blur="saveField('slackx_rpc_token')"
      />
    </div>
    <div class="field">
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
