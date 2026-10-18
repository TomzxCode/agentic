<script setup>
import { ref, watch } from 'vue'
import { api } from '../api'
import { DEFAULT_AGENT_PROMPTS, PROMPT_KINDS, parseAgentPrompts } from '../prompts'
import { store } from '../store'

// The "Agent prompts" settings section: user-defined buttons for the agent
// panel, edited as a list and saved as one JSON string. The page shell supplies
// the raw overrides/defaults; this component seeds its drafts from them.
const props = defineProps({
  overrides: { type: Object, default: () => ({}) },
  defaults: { type: Object, default: () => ({}) }
})

const drafts = ref([])
const saving = ref(false)
const saved = ref(false)
let savedTimer
let seq = 0

// A row keyed by a stable id, so removing one row never reuses another's input.
function draft(prompt) {
  seq += 1
  return { id: seq, kind: prompt.kind, label: prompt.label, template: prompt.template }
}

watch(
  () => props.overrides.agent_prompts ?? props.defaults.agent_prompts,
  (raw) => {
    drafts.value = parseAgentPrompts(raw).map(draft)
  },
  { immediate: true }
)

// Save every prompt edit at once: the list is small and stored as one JSON
// string, so there is no per-row request to track. A row with an empty template
// is still being added, so it is left out until it is filled in.
async function save() {
  const prompts = drafts.value
    .filter((prompt) => prompt.template.trim())
    .map((prompt) => ({ kind: prompt.kind, label: prompt.label, template: prompt.template.trim() }))
  saving.value = true
  try {
    await api.settings.update({ agent_prompts: JSON.stringify(prompts) })
    saved.value = true
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => (saved.value = false), 1500)
    await store.loadSettings().catch(() => {})
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    saving.value = false
  }
}

function add() {
  drafts.value.push(draft({ kind: 'issue', label: '', template: '' }))
}

function remove(index) {
  drafts.value.splice(index, 1)
  save()
}

function reset() {
  drafts.value = DEFAULT_AGENT_PROMPTS.map(draft)
  save()
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Agent prompts</h2>
      <span v-if="saving" class="faint">saving…</span>
      <span v-else-if="saved" class="faint">saved</span>
    </div>
    <p class="faint" style="margin-top: 0">
      Buttons shown in the agent panel. Each appears when a task has exactly one associated item of its kind.
      Placeholders: <code>{owner}</code>, <code>{repository}</code>, <code>{number}</code>.
    </p>
    <div v-for="(p, index) in drafts" :key="p.id" class="row" style="margin-top: 8px">
      <select v-model="p.kind" class="select" style="width: auto" aria-label="Item kind" @change="save">
        <option v-for="kind in PROMPT_KINDS" :key="kind.value" :value="kind.value">{{ kind.label }}</option>
      </select>
      <input v-model="p.label" class="input" style="width: 150px" placeholder="Label" @blur="save" />
      <input
        v-model="p.template"
        class="input grow mono"
        placeholder="$review-pr-full {number} {owner}/{repository}"
        @blur="save"
      />
      <button class="btn sm danger" title="Remove" @click="remove(index)">✕</button>
    </div>
    <p v-if="!drafts.length" class="faint" style="margin-top: 8px">No prompts; the agent panel shows no buttons.</p>
    <div class="row" style="margin-top: 10px">
      <button class="btn" @click="add">Add prompt</button>
      <button class="btn ghost" @click="reset">Reset to defaults</button>
    </div>
  </section>
</template>
