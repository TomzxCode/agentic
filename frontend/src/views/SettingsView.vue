<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { store } from '../store'
import EntityCard from '../components/EntityCard.vue'
import RepositoryGroupsPanel from '../components/RepositoryGroupsPanel.vue'

const route = useRoute()
const router = useRouter()

const SECTIONS = [
  { id: 'sessions', label: 'Session links' },
  { id: 'harnesses', label: 'Agent harnesses' },
  { id: 'groups', label: 'Repository groups' }
]
const active = ref(SECTIONS.some((s) => s.id === route.query.section) ? route.query.section : SECTIONS[0].id)

function select(id) {
  active.value = id
  router.replace({ query: { section: id } })
}

watch(
  () => route.query.section,
  (section) => {
    if (SECTIONS.some((s) => s.id === section)) active.value = section
  }
)

const harnessDraft = reactive({ name: '', command: '', args: '', description: '', model: '' })
const loading = ref(true)

const fullHarnesses = ref([])
const harnessStatus = ref({})
const resumeDrafts = reactive({})
const modelDrafts = reactive({})

const linkForm = reactive({
  openchamber_url: '',
  openchamber_session_path: '',
  terminal_url_template: '',
  editor_url_template: ''
})
const linkDefaults = ref({})
const savingLinks = ref(false)
const savedLinks = ref(false)
let savedTimer

async function loadRepositories() {
  await store.loadRepositories().catch((e) => store.notify(e.message, true))
}

async function loadHarnesses() {
  const [full, status] = await Promise.all([api.harnesses.full(), api.harnesses.list()])
  fullHarnesses.value = full
  harnessStatus.value = Object.fromEntries(status.map((h) => [h.id, h]))
  for (const h of full) {
    resumeDrafts[h.id] = h.resume_command || ''
    modelDrafts[h.id] = h.model || ''
  }
}

async function loadSettings() {
  const data = await api.settings.get()
  linkDefaults.value = data.defaults
  Object.assign(linkForm, {
    openchamber_url: data.overrides.openchamber_url ?? '',
    openchamber_session_path: data.overrides.openchamber_session_path ?? '',
    terminal_url_template: data.overrides.terminal_url_template ?? '',
    editor_url_template: data.overrides.editor_url_template ?? ''
  })
}

async function load() {
  loading.value = true
  await Promise.all([
    loadRepositories(),
    loadHarnesses().catch((e) => store.notify(e.message, true)),
    loadSettings().catch((e) => store.notify(e.message, true))
  ])
  loading.value = false
}

async function addHarness() {
  if (!harnessDraft.name.trim() || !harnessDraft.command.trim()) return
  try {
    await api.harnesses.create({
      name: harnessDraft.name.trim(),
      command: harnessDraft.command.trim(),
      args: harnessDraft.args.split(/\s+/).filter(Boolean),
      description: harnessDraft.description,
      model: harnessDraft.model.trim() || null
    })
    Object.assign(harnessDraft, { name: '', command: '', args: '', description: '', model: '' })
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

async function saveModel(id) {
  try {
    await api.harnesses.update(id, { model: modelDrafts[id].trim() || null })
    store.notify('Model saved')
    await loadHarnesses()
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function setDefault(id) {
  try {
    await api.harnesses.update(id, { is_default: true })
    await loadHarnesses()
    await store.loadHarnesses().catch(() => {})
    store.notify('Default harness updated')
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function saveLinkField(key) {
  savingLinks.value = true
  try {
    await api.settings.update({ [key]: linkForm[key] })
    savedLinks.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (savedLinks.value = false), 1500)
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

    <div class="settings-layout">
      <nav class="settings-nav">
        <button
          v-for="section in SECTIONS"
          :key="section.id"
          type="button"
          class="settings-nav-item"
          :class="{ active: active === section.id }"
          @click="select(section.id)"
        >
          {{ section.label }}
        </button>
      </nav>

      <div class="settings-content">
        <section v-show="active === 'sessions'" class="panel">
          <div class="panel-head">
            <h2>Session links</h2>
            <span v-if="savingLinks" class="faint">saving…</span>
            <span v-else-if="savedLinks" class="faint">saved</span>
          </div>
          <p class="faint" style="margin-top: 0">
            Where an agent session opens. Saved when you leave a field. Leave a field blank to disable that link.
            Placeholders: <code>{session}</code>, <code>{cwd}</code>, <code>{harness}</code>.
          </p>

          <div class="field">
            <label>OpenChamber base URL</label>
            <input
              v-model="linkForm.openchamber_url"
              class="input"
              placeholder="http://localhost:3001"
              @blur="saveLinkField('openchamber_url')"
            />
            <p class="faint" style="margin: 4px 0 0">
              Web: <code>&lt;base&gt;/?session=&lt;id&gt;</code>. For the native deep link use base
              <code>openchamber://session</code> with path <code>/{session}</code>.
            </p>
          </div>
          <div class="field">
            <label>OpenChamber session path</label>
            <input
              v-model="linkForm.openchamber_session_path"
              class="input"
              :placeholder="linkDefaults.openchamber_session_path"
              @blur="saveLinkField('openchamber_session_path')"
            />
          </div>
          <div class="field">
            <label>Terminal URL template (optional)</label>
            <input
              v-model="linkForm.terminal_url_template"
              class="input"
              placeholder="opencode://session/{session}"
              @blur="saveLinkField('terminal_url_template')"
            />
            <p class="faint" style="margin: 4px 0 0">
              Any URL scheme, or a web terminal such as
              <code>http://localhost:7681/?cwd={cwd}</code>.
            </p>
          </div>
          <div class="field">
            <label>Editor URL template (optional)</label>
            <input
              v-model="linkForm.editor_url_template"
              class="input"
              placeholder="vscode://file{path}"
              @blur="saveLinkField('editor_url_template')"
            />
            <p class="faint" style="margin: 4px 0 0">
              Opens a worktree path in your editor. <code>{path}</code> is the absolute path (it starts with
              <code>/</code>).
            </p>
            <p class="faint" style="margin: 4px 0 0">
              Local: <code>vscode://file{path}</code>, <code>cursor://file{path}</code>, <code>zed://file{path}</code>.
            </p>
            <p class="faint" style="margin: 4px 0 0">
              Remote VS Code over SSH: <code>vscode://vscode-remote/ssh-remote+&lt;host&gt;{path}</code> (host from
              <code>~/.ssh/config</code>; needs the Remote-SSH extension). Add <code>?windowId=_blank</code> to open in
              a new window. code-server: <code>https://&lt;host&gt;:8443/?folder={path}</code>. Tunnel:
              <code>https://vscode.dev/tunnel/&lt;name&gt;{path}</code>.
            </p>
          </div>
        </section>

        <section v-show="active === 'harnesses'" class="panel">
          <div class="panel-head"><h2>Agent harnesses</h2></div>
          <p class="faint" style="margin-top: 0">
            Any ACP-compatible coding agent. OpenCode v2 (<code>opencode2 acp</code>), v1 (<code>opencode acp</code>),
            and pi (<code>pi-acp</code>) are preconfigured. The default harness runs when a task does not pick one; the
            resume command is what "open in terminal" copies.
          </p>
          <EntityCard v-for="h in fullHarnesses" :key="h.id">
            <template #title>
              <span class="title">{{ h.name }}</span>
            </template>
            <template #actions>
              <span v-if="h.is_default" class="badge ok">default</span>
              <span
                class="badge"
                :class="{ ok: harnessStatus[h.id]?.available, danger: !harnessStatus[h.id]?.available }"
              >
                {{ harnessStatus[h.id]?.available ? 'available' : 'missing' }}
              </span>
            </template>
            <div class="faint mono">{{ harnessStatus[h.id]?.detail || h.command }}</div>
            <div class="row" style="margin-top: 8px">
              <input v-model="resumeDrafts[h.id]" class="input grow mono" placeholder="opencode --session {session}" />
              <button class="btn sm" @click="saveResume(h.id)">Save</button>
              <button v-if="!h.is_default" class="btn sm" @click="setDefault(h.id)">Set default</button>
            </div>
            <div class="row" style="margin-top: 8px">
              <input
                v-model="modelDrafts[h.id]"
                class="input grow mono"
                placeholder="model, e.g. zai-coding-plan/glm-5.3 (empty uses the harness default)"
              />
              <button class="btn sm" @click="saveModel(h.id)">Save</button>
            </div>
          </EntityCard>
          <div class="row" style="margin-top: 10px">
            <input v-model="harnessDraft.name" class="input grow" placeholder="Name" />
            <input v-model="harnessDraft.command" class="input grow" placeholder="command (e.g. opencode)" />
          </div>
          <div class="row" style="margin-top: 8px">
            <input v-model="harnessDraft.args" class="input grow" placeholder="args (space separated, e.g. acp)" />
            <input v-model="harnessDraft.model" class="input grow mono" placeholder="model (optional)" />
            <button class="btn primary" @click="addHarness">Add harness</button>
          </div>
        </section>

        <div v-show="active === 'groups'">
          <RepositoryGroupsPanel :repositories="store.repositories" />
        </div>
      </div>
    </div>
  </div>
</template>
