<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { store } from '../store'

// The "Session links" settings section: where an agent session opens. The page
// shell owns the single settings read and hands the raw overrides/defaults
// down; this component seeds its own editable copy and saves each field on blur.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) }
})

const form = reactive({
  openchamber_url: '',
  openchamber_session_path: '',
  terminal_url_template: '',
  editor_url_template: ''
})
const saving = ref(false)
const saved = ref(false)
let savedTimer

watch(
  () => props.overrides,
  (overrides) => {
    form.openchamber_url = overrides.openchamber_url ?? ''
    form.openchamber_session_path = overrides.openchamber_session_path ?? ''
    form.terminal_url_template = overrides.terminal_url_template ?? ''
    form.editor_url_template = overrides.editor_url_template ?? ''
  },
  { immediate: true }
)

async function saveField(key) {
  saving.value = true
  try {
    await api.settings.update({ [key]: form[key] })
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
      <h2>Session links</h2>
      <span v-if="saving" class="faint">saving…</span>
      <span v-else-if="saved" class="faint">saved</span>
    </div>
    <p class="faint" style="margin-top: 0">
      Where an agent session opens. Saved when you leave a field. Leave a field blank to disable that link.
      Placeholders: <code>{session}</code>, <code>{cwd}</code>, <code>{harness}</code>.
    </p>

    <div class="field">
      <label>OpenChamber base URL</label>
      <input
        v-model="form.openchamber_url"
        class="input"
        placeholder="http://localhost:3001"
        @blur="saveField('openchamber_url')"
      />
      <p class="faint" style="margin: 4px 0 0">
        Web: <code>&lt;base&gt;/?session=&lt;id&gt;</code>. For the native deep link use base
        <code>openchamber://session</code> with path <code>/{session}</code>.
      </p>
    </div>
    <div class="field">
      <label>OpenChamber session path</label>
      <input
        v-model="form.openchamber_session_path"
        class="input"
        :placeholder="defaults.openchamber_session_path"
        @blur="saveField('openchamber_session_path')"
      />
    </div>
    <div class="field">
      <label>Terminal URL template (optional)</label>
      <input
        v-model="form.terminal_url_template"
        class="input"
        placeholder="opencode://session/{session}"
        @blur="saveField('terminal_url_template')"
      />
      <p class="faint" style="margin: 4px 0 0">
        Any URL scheme, or a web terminal such as
        <code>http://localhost:7681/?cwd={cwd}</code>.
      </p>
    </div>
    <div class="field">
      <label>Editor URL template (optional)</label>
      <input
        v-model="form.editor_url_template"
        class="input"
        placeholder="vscode://file{path}"
        @blur="saveField('editor_url_template')"
      />
      <p class="faint" style="margin: 4px 0 0">
        Opens a worktree path in your editor. <code>{path}</code> is the absolute path (it starts with <code>/</code>).
      </p>
      <p class="faint" style="margin: 4px 0 0">
        Local: <code>vscode://file{path}</code>, <code>cursor://file{path}</code>, <code>zed://file{path}</code>.
      </p>
      <p class="faint" style="margin: 4px 0 0">
        Remote VS Code over SSH: <code>vscode://vscode-remote/ssh-remote+&lt;host&gt;{path}</code> (host from
        <code>~/.ssh/config</code>; needs the Remote-SSH extension). Add <code>?windowId=_blank</code> to open in a new
        window. code-server: <code>https://&lt;host&gt;:8443/?folder={path}</code>. Tunnel:
        <code>https://vscode.dev/tunnel/&lt;name&gt;{path}</code>.
      </p>
    </div>
  </section>
</template>
