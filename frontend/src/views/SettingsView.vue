<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { DEFAULT_AGENT_PROMPTS, PROMPT_KINDS, parseAgentPrompts } from '../prompts'
import { store, timeAgo } from '../store'
import EntityCard from '../components/EntityCard.vue'
import RepositoryGroupsPanel from '../components/RepositoryGroupsPanel.vue'

const route = useRoute()
const router = useRouter()

const SECTIONS = [
  { id: 'sessions', label: 'Session links' },
  { id: 'harnesses', label: 'Agent harnesses' },
  { id: 'prompts', label: 'Agent prompts' },
  { id: 'refresh', label: 'Refresh' },
  { id: 'groups', label: 'Repository groups' }
]
const active = ref(SECTIONS.some((s) => s.id === route.query.section) ? route.query.section : SECTIONS[0].id)

function select(id) {
  active.value = id
  router.replace({ query: { section: id } })
  if (id === 'refresh') {
    previewAllRefresh()
    loadRefreshStatus()
  }
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

const refreshForm = reactive({ slack_refresh_policy: '', github_refresh_policy: '' })
const refreshDefaults = ref({})
const refreshPreviews = reactive({ slack_refresh_policy: null, github_refresh_policy: null })
const refreshStatus = ref({})
const savingRefresh = ref('')
const savedRefresh = ref('')
// Per source, so refreshing one does not block the other.
const forcingRefresh = reactive({ slack: false, github: false })
let savedRefreshTimer
const previewTimers = {}

// User-defined agent prompts (Settings → Agent prompts), edited as a list and
// saved as one JSON string, so the agent panel reads them from settings.
const promptDrafts = ref([])
const promptSaving = ref(false)
const promptSaved = ref(false)
let savedPromptTimer
let promptSeq = 0

// A row keyed by a stable id, so removing one row never reuses another's input.
function promptDraft(prompt) {
  promptSeq += 1
  return { id: promptSeq, kind: prompt.kind, label: prompt.label, template: prompt.template }
}

// Slack threads and GitHub issues/PRs refresh on their own schedules.
const REFRESH_FIELDS = [
  { key: 'slack_refresh_policy', label: 'Slack threads', source: 'slack' },
  { key: 'github_refresh_policy', label: 'GitHub issues/PRs', source: 'github' }
]

function formatDuration(seconds) {
  if (seconds == null) return 'never'
  for (const [label, size] of [
    ['w', 604800],
    ['d', 86400],
    ['h', 3600],
    ['m', 60],
    ['s', 1]
  ]) {
    if (seconds >= size && seconds % size === 0) return `${seconds / size}${label}`
  }
  return `${seconds}s`
}

// Explain a policy as age bands, using the server's parser so the preview and
// the saved behavior never disagree. Best effort: a backend without the
// endpoint simply shows no preview.
async function previewRefresh(key) {
  if (typeof api.settings.previewRefreshPolicy !== 'function') return
  try {
    refreshPreviews[key] = await api.settings.previewRefreshPolicy(refreshForm[key])
  } catch (e) {
    refreshPreviews[key] = { valid: false, error: e.message }
  }
}

function previewAllRefresh() {
  return Promise.all(REFRESH_FIELDS.map((field) => previewRefresh(field.key)))
}

// When the background job last ran for each source. Best effort: a backend
// without the endpoint simply shows no status.
async function loadRefreshStatus() {
  if (typeof api.settings.refreshStatus !== 'function') return
  try {
    refreshStatus.value = (await api.settings.refreshStatus()).sources || {}
  } catch {
    // Leave the last known status; a failed read should not block the settings.
  }
}

// Re-fetch every item of one source now, ignoring its policy.
async function forceRefresh(source) {
  if (forcingRefresh[source]) return
  forcingRefresh[source] = true
  try {
    const report = await api.items.refreshSource(source)
    const label = REFRESH_FIELDS.find((field) => field.source === source)?.label || source
    const summary = `${report.refreshed} refreshed${report.failed ? `, ${report.failed} failed` : ''}`
    store.notify(`${label}: ${summary}`, report.failed > 0)
    await loadRefreshStatus()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    forcingRefresh[source] = false
  }
}

function onRefreshInput(key) {
  clearTimeout(previewTimers[key])
  previewTimers[key] = setTimeout(() => previewRefresh(key), 300)
}

async function saveRefresh(key) {
  savingRefresh.value = key
  try {
    await api.settings.update({ [key]: refreshForm[key] })
    savedRefresh.value = key
    clearTimeout(savedRefreshTimer)
    savedRefreshTimer = setTimeout(() => (savedRefresh.value = ''), 1500)
    await previewRefresh(key)
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    savingRefresh.value = ''
  }
}

// Save every prompt edit at once: the list is small and stored as one JSON
// string, so there is no per-row request to track. A row with an empty template
// is still being added, so it is left out until it is filled in.
async function savePrompts() {
  const prompts = promptDrafts.value
    .filter((prompt) => prompt.template.trim())
    .map((prompt) => ({ kind: prompt.kind, label: prompt.label, template: prompt.template.trim() }))
  promptSaving.value = true
  try {
    await api.settings.update({ agent_prompts: JSON.stringify(prompts) })
    promptSaved.value = true
    clearTimeout(savedPromptTimer)
    savedPromptTimer = setTimeout(() => (promptSaved.value = false), 1500)
    await store.loadSettings().catch(() => {})
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    promptSaving.value = false
  }
}

function addPrompt() {
  promptDrafts.value.push(promptDraft({ kind: 'issue', label: '', template: '' }))
}

function removePrompt(index) {
  promptDrafts.value.splice(index, 1)
  savePrompts()
}

function resetPrompts() {
  promptDrafts.value = DEFAULT_AGENT_PROMPTS.map(promptDraft)
  savePrompts()
}

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
  refreshDefaults.value = data.defaults
  refreshForm.slack_refresh_policy = data.overrides.slack_refresh_policy ?? ''
  refreshForm.github_refresh_policy = data.overrides.github_refresh_policy ?? ''
  promptDrafts.value = parseAgentPrompts(data.overrides.agent_prompts ?? data.defaults.agent_prompts).map(promptDraft)
  if (active.value === 'refresh') await previewAllRefresh()
}

async function load() {
  loading.value = true
  await Promise.all([
    loadRepositories(),
    loadHarnesses().catch((e) => store.notify(e.message, true)),
    loadSettings().catch((e) => store.notify(e.message, true)),
    loadRefreshStatus()
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

        <section v-show="active === 'prompts'" class="panel">
          <div class="panel-head">
            <h2>Agent prompts</h2>
            <span v-if="promptSaving" class="faint">saving…</span>
            <span v-else-if="promptSaved" class="faint">saved</span>
          </div>
          <p class="faint" style="margin-top: 0">
            Buttons shown in the agent panel. Each appears when a task has exactly one associated item of its kind.
            Placeholders: <code>{owner}</code>, <code>{repository}</code>, <code>{number}</code>.
          </p>
          <div v-for="(p, index) in promptDrafts" :key="p.id" class="row" style="margin-top: 8px">
            <select v-model="p.kind" class="select" style="width: auto" aria-label="Item kind" @change="savePrompts">
              <option v-for="kind in PROMPT_KINDS" :key="kind.value" :value="kind.value">{{ kind.label }}</option>
            </select>
            <input v-model="p.label" class="input" style="width: 150px" placeholder="Label" @blur="savePrompts" />
            <input
              v-model="p.template"
              class="input grow mono"
              placeholder="$review-pr-full {number} {owner}/{repository}"
              @blur="savePrompts"
            />
            <button class="btn sm danger" title="Remove" @click="removePrompt(index)">✕</button>
          </div>
          <p v-if="!promptDrafts.length" class="faint" style="margin-top: 8px">
            No prompts; the agent panel shows no buttons.
          </p>
          <div class="row" style="margin-top: 10px">
            <button class="btn" @click="addPrompt">Add prompt</button>
            <button class="btn ghost" @click="resetPrompts">Reset to defaults</button>
          </div>
        </section>

        <section v-show="active === 'refresh'" class="panel">
          <div class="panel-head">
            <h2>Refresh</h2>
          </div>
          <p class="faint" style="margin-top: 0">
            How often to re-fetch Slack threads (slackx) and GitHub issues/PRs (ghx). Age bands pair an upper age with a
            refresh interval. Each field saves when you leave it; leave one blank to stop refreshing that source.
          </p>
          <div v-for="field in REFRESH_FIELDS" :key="field.key" class="field">
            <label>
              {{ field.label }}
              <span v-if="savingRefresh === field.key" class="faint">saving…</span>
              <span v-else-if="savedRefresh === field.key" class="faint">saved</span>
            </label>
            <div class="row">
              <input
                v-model="refreshForm[field.key]"
                class="input mono grow"
                :placeholder="refreshDefaults[field.key] || '1d=1h,7d=6h,30d=1d,*=7d'"
                @input="onRefreshInput(field.key)"
                @blur="saveRefresh(field.key)"
              />
              <button class="btn sm" :disabled="forcingRefresh[field.source]" @click="forceRefresh(field.source)">
                <span v-if="forcingRefresh[field.source]" class="spinner" aria-hidden="true"></span>
                Force refresh
              </button>
            </div>
            <p class="faint" style="margin: 4px 0 0">
              <code>1d=1h,7d=6h,30d=1d,*=7d</code>: hourly while under a day old, every 6h under a week, daily under 30
              days, weekly after. Omit the <code>*</code> band (or use <code>*=never</code>) to stop refreshing an item
              once it outgrows the last band.
            </p>
            <p class="faint" style="margin: 4px 0 0">
              Last run:
              <template v-if="refreshStatus[field.source]?.last_run_at">
                {{ timeAgo(refreshStatus[field.source].last_run_at) }} ·
                {{ refreshStatus[field.source].refreshed }} refreshed
                <span v-if="refreshStatus[field.source].failed" style="color: var(--danger)">
                  · {{ refreshStatus[field.source].failed }} failed
                </span>
                <span v-if="refreshStatus[field.source].origin === 'manual'"> · forced</span>
              </template>
              <template v-else>never</template>
            </p>
            <p v-if="refreshStatus[field.source]?.error" style="margin: 4px 0 0; color: var(--danger)">
              {{ refreshStatus[field.source].error }}
            </p>
            <div v-if="refreshPreviews[field.key]">
              <p v-if="!refreshPreviews[field.key].valid" style="color: var(--danger); margin: 0">
                {{ refreshPreviews[field.key].error }}
              </p>
              <template v-else-if="refreshPreviews[field.key].enabled">
                <div
                  v-for="(tier, index) in refreshPreviews[field.key].tiers"
                  :key="index"
                  class="row"
                  style="gap: 8px"
                >
                  <span class="faint" style="min-width: 140px"
                    >newer than {{ formatDuration(tier.max_age_seconds) }}</span
                  >
                  <span v-if="tier.interval_seconds != null">every {{ formatDuration(tier.interval_seconds) }}</span>
                  <span v-else class="faint">never</span>
                </div>
                <div class="row" style="gap: 8px">
                  <span class="faint" style="min-width: 140px">older than that</span>
                  <span v-if="refreshPreviews[field.key].fallback_seconds != null">
                    every {{ formatDuration(refreshPreviews[field.key].fallback_seconds) }}
                  </span>
                  <span v-else class="faint">never</span>
                </div>
              </template>
              <p v-else class="faint" style="margin: 0">No automatic refresh.</p>
            </div>
          </div>
        </section>

        <div v-show="active === 'groups'">
          <RepositoryGroupsPanel :repositories="store.repositories" />
        </div>
      </div>
    </div>
  </div>
</template>
