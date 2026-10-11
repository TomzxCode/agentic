<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { store } from '../store'
import DirectoryPicker from '../components/DirectoryPicker.vue'
import RepositoryGroupsPanel from '../components/RepositoryGroupsPanel.vue'

const repoDraft = reactive({ path: '' })
const harnessDraft = reactive({ name: '', command: '', args: '', description: '' })
const loading = ref(true)

const showPicker = ref(false)
const fullHarnesses = ref([])
const harnessStatus = ref({})
const resumeDrafts = reactive({})

const linkForm = reactive({
  openchamber_url: '',
  openchamber_session_path: '',
  terminal_url_template: '',
  editor_url_template: '',
})
const linkDefaults = ref({})
const savingLinks = ref(false)

async function loadRepositories() {
  await store.loadRepositories().catch((e) => store.notify(e.message, true))
}

async function loadHarnesses() {
  const [full, status] = await Promise.all([api.harnesses.full(), api.harnesses.list()])
  fullHarnesses.value = full
  harnessStatus.value = Object.fromEntries(status.map((h) => [h.id, h]))
  for (const h of full) resumeDrafts[h.id] = h.resume_command || ''
}

async function loadSettings() {
  const data = await api.settings.get()
  linkDefaults.value = data.defaults
  Object.assign(linkForm, {
    openchamber_url: data.overrides.openchamber_url ?? '',
    openchamber_session_path: data.overrides.openchamber_session_path ?? '',
    terminal_url_template: data.overrides.terminal_url_template ?? '',
    editor_url_template: data.overrides.editor_url_template ?? '',
  })
}

async function load() {
  loading.value = true
  await Promise.all([
    loadRepositories(),
    loadHarnesses().catch((e) => store.notify(e.message, true)),
    loadSettings().catch((e) => store.notify(e.message, true)),
  ])
  loading.value = false
}

async function addRepo() {
  if (!repoDraft.path.trim()) return
  try {
    await api.repositories.create({ path: repoDraft.path.trim() })
    repoDraft.path = ''
    await loadRepositories()
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function addRepos(paths) {
  if (!paths.length) return
  try {
    const result = await api.repositories.createBulk(paths)
    await loadRepositories()
    showPicker.value = false
    const added = result.added.length
    if (result.errors.length) {
      store.notify(`Added ${added}, ${result.errors.length} skipped (not a git repository)`, true)
    } else {
      store.notify(`Added ${added} repositor${added === 1 ? 'y' : 'ies'}`)
    }
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function removeRepo(id) {
  if (!confirm('Remove this repository from Agentic? (No files are deleted.)')) return
  await api.repositories.remove(id)
  await loadRepositories()
}

async function addHarness() {
  if (!harnessDraft.name.trim() || !harnessDraft.command.trim()) return
  try {
    await api.harnesses.create({
      name: harnessDraft.name.trim(),
      command: harnessDraft.command.trim(),
      args: harnessDraft.args.split(/\s+/).filter(Boolean),
      description: harnessDraft.description,
    })
    Object.assign(harnessDraft, { name: '', command: '', args: '', description: '' })
    await loadHarnesses()
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function saveResume(id) {
  try {
    await api.harnesses.update(id, { resume_command: resumeDrafts[id] })
    store.notify('Resume command saved')
    await loadHarnesses()
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function saveLinks() {
  savingLinks.value = true
  try {
    await api.settings.update({ ...linkForm })
    store.notify('Session link settings saved')
    await loadSettings()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    savingLinks.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 style="margin-bottom: 16px">Settings</h1>

    <section class="panel">
      <div class="panel-head"><h2>Session links</h2></div>
      <p class="faint" style="margin-top: 0">
        Where an agent session opens. Leave a field blank to disable that link. Placeholders:
        <code>{session}</code>, <code>{cwd}</code>, <code>{harness}</code>.
      </p>

      <div class="field">
        <label>OpenChamber base URL</label>
        <input v-model="linkForm.openchamber_url" class="input" placeholder="http://localhost:3001" />
        <p class="faint" style="margin: 4px 0 0">
          Web: <code>&lt;base&gt;/?session=&lt;id&gt;</code>. For the native deep link use base
          <code>openchamber://session</code> with path <code>/{session}</code>.
        </p>
      </div>
      <div class="field">
        <label>OpenChamber session path</label>
        <input v-model="linkForm.openchamber_session_path" class="input" :placeholder="linkDefaults.openchamber_session_path" />
      </div>
      <div class="field">
        <label>Terminal URL template (optional)</label>
        <input v-model="linkForm.terminal_url_template" class="input" placeholder="opencode://session/{session}" />
        <p class="faint" style="margin: 4px 0 0">
          Any URL scheme, or a web terminal such as
          <code>http://localhost:7681/?cwd={cwd}</code>.
        </p>
      </div>
      <div class="field">
        <label>Editor URL template (optional)</label>
        <input v-model="linkForm.editor_url_template" class="input" placeholder="vscode://file{path}" />
        <p class="faint" style="margin: 4px 0 0">
          Opens a worktree path in your editor. <code>{path}</code> is the absolute path (it starts with
          <code>/</code>). Examples: <code>vscode://file{path}</code>, <code>cursor://file{path}</code>,
          <code>zed://file{path}</code>.
        </p>
      </div>
      <div class="row" style="justify-content: flex-end">
        <button class="btn primary" :disabled="savingLinks" @click="saveLinks">
          <span v-if="savingLinks" class="spinner"></span> Save session links
        </button>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head"><h2>Agent harnesses</h2></div>
      <p class="faint" style="margin-top: 0">
        Any ACP-compatible coding agent. OpenCode (<code>opencode acp</code>) and pi (<code>pi-acp</code>) are
        preconfigured. The resume command is what "open in terminal" copies.
      </p>
      <div v-for="h in fullHarnesses" :key="h.id" class="item">
        <div class="item-top">
          <span class="title">{{ h.name }}</span>
          <span class="badge" :class="{ ok: harnessStatus[h.id]?.available, danger: !harnessStatus[h.id]?.available }">
            {{ harnessStatus[h.id]?.available ? 'available' : 'missing' }}
          </span>
        </div>
        <div class="faint mono">{{ harnessStatus[h.id]?.detail || h.command }}</div>
        <div class="row" style="margin-top: 8px">
          <input v-model="resumeDrafts[h.id]" class="input grow mono" placeholder="opencode --session {session}" />
          <button class="btn sm" @click="saveResume(h.id)">Save</button>
        </div>
      </div>
      <div class="row" style="margin-top: 10px">
        <input v-model="harnessDraft.name" class="input grow" placeholder="Name" />
        <input v-model="harnessDraft.command" class="input grow" placeholder="command (e.g. opencode)" />
      </div>
      <div class="row" style="margin-top: 8px">
        <input v-model="harnessDraft.args" class="input grow" placeholder="args (space separated, e.g. acp)" />
        <button class="btn primary" @click="addHarness">Add harness</button>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head"><h2>Repositories</h2></div>
      <p class="faint" style="margin-top: 0">Local git checkouts that tasks can create isolated worktrees from.</p>
      <div v-for="r in store.repositories" :key="r.id" class="item">
        <div class="item-top">
          <span class="title">{{ r.name }}</span>
          <span v-if="r.default_branch" class="badge">{{ r.default_branch }}</span>
          <button class="btn sm danger" @click="removeRepo(r.id)">Remove</button>
        </div>
        <div class="faint mono">{{ r.path }}</div>
        <div v-if="r.remote_url" class="faint">{{ r.remote_url }}</div>
      </div>
      <div class="row" style="margin-top: 10px">
        <input v-model="repoDraft.path" class="input grow" placeholder="/absolute/path/to/git/repo" @keyup.enter="addRepo" />
        <button class="btn" @click="showPicker = true">Browse…</button>
        <button class="btn primary" @click="addRepo">Add repository</button>
      </div>
    </section>

    <DirectoryPicker
      v-if="showPicker"
      :existing="store.repositories.map((r) => r.path)"
      @close="showPicker = false"
      @add="addRepos"
    />

    <RepositoryGroupsPanel :repositories="store.repositories" />
  </div>
</template>
