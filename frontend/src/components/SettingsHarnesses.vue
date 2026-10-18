<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { store } from '../store'
import EntityCard from './EntityCard.vue'

// The "Agent harnesses" settings section. Self-contained: it owns its own list,
// status, and per-harness drafts, and talks to the harness API directly so the
// page shell only has to render it.
const harnessDraft = reactive({ name: '', command: '', args: '', description: '', model: '' })

const fullHarnesses = ref([])
const harnessStatus = ref({})
const resumeDrafts = reactive({})
const modelDrafts = reactive({})

async function loadHarnesses() {
  const [full, status] = await Promise.all([api.harnesses.full(), api.harnesses.list()])
  fullHarnesses.value = full
  harnessStatus.value = Object.fromEntries(status.map((h) => [h.id, h]))
  for (const h of full) {
    resumeDrafts[h.id] = h.resume_command || ''
    modelDrafts[h.id] = h.model || ''
  }
}

// What a run uses while the field is blank: the model the harness's own config
// file names (the server reads it), or the example when none is known.
function modelPlaceholder(harness) {
  return harness.default_model
    ? `${harness.default_model} (harness default)`
    : 'model, e.g. provider/model (empty uses the harness default)'
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

onMounted(() => loadHarnesses().catch((e) => store.notify(e.message, true)))
</script>

<template>
  <section class="panel">
    <div class="panel-head"><h2>Agent harnesses</h2></div>
    <p class="faint" style="margin-top: 0">
      Any ACP-compatible coding agent. OpenCode v2 (<code>opencode2 acp</code>), v1 (<code>opencode acp</code>), and pi
      (<code>pi-acp</code>) are preconfigured. The default harness runs when a task does not pick one; the resume
      command is what "open in terminal" copies.
    </p>
    <EntityCard v-for="h in fullHarnesses" :key="h.id">
      <template #title>
        <span class="title">{{ h.name }}</span>
      </template>
      <template #actions>
        <span v-if="h.is_default" class="badge ok">default</span>
        <span class="badge" :class="{ ok: harnessStatus[h.id]?.available, danger: !harnessStatus[h.id]?.available }">
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
        <input v-model="modelDrafts[h.id]" class="input grow mono" :placeholder="modelPlaceholder(h)" />
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
</template>
