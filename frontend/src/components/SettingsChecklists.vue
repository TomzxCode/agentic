<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import {
  CHECKLIST_FIELDS,
  CHECKLIST_PRIORITIES,
  CHECKLIST_STATUSES,
  defaultValues,
  fieldDefinition,
  newRule,
  operatorsFor,
  parseItemsText,
  ruleNeedsValues
} from '../checklists'
import { store } from '../store'
import EntityCard from './EntityCard.vue'
import SearchSelect from './SearchSelect.vue'
import TagInput from './TagInput.vue'

// The "Checklists" settings section: reusable checklists plus the rules that
// decide which tasks receive their items. A template is edited as one draft, so
// only an explicit Save sends a request and a half-built rule is never stored.
const templates = ref([])
const tasks = ref([])
const editing = ref(null)
const busy = ref(false)
let nextKey = 1

const peopleOptions = computed(() => store.people.map((person) => ({ value: person.id, label: person.name })))
const repositoryOptions = computed(() =>
  store.repositories.map((repository) => ({ value: repository.id, label: repository.name }))
)
const taskOptions = computed(() => tasks.value.map((task) => ({ value: task.id, label: task.title })))

function draftFrom(template) {
  return {
    key: nextKey++,
    id: template?.id || '',
    name: template?.name || '',
    description: template?.description || '',
    rules: (template?.rules || []).map((rule) => ({
      field: rule.field,
      op: rule.op,
      values: [...(rule.values || [])]
    })),
    itemsText: (template?.items || []).join('\n'),
    appliedCount: template?.applied_count || 0
  }
}

async function load() {
  await Promise.all([
    api.checklistTemplates.list().then((rows) => (templates.value = rows)),
    api.tasks.list().then((rows) => (tasks.value = rows)),
    store.loadTags().catch(() => {}),
    store.loadPeople().catch(() => {}),
    store.loadRepositories().catch(() => {})
  ]).catch((e) => store.notify(e.message, true))
}

function startNew() {
  editing.value = draftFrom(null)
}

function startEdit(template) {
  editing.value = draftFrom(template)
}

function cancel() {
  editing.value = null
}

function addRule() {
  editing.value.rules.push(newRule())
}

function removeRule(index) {
  editing.value.rules.splice(index, 1)
}

// Changing the field invalidates the operator and the picked values, so reset
// both to that field's first valid operator and a sensible starting value.
function changeField(rule) {
  rule.op = operatorsFor(rule.field)[0].value
  rule.values = defaultValues(rule.field)
}

function changeOperator(rule) {
  if (ruleNeedsValues(rule.field, rule.op) && !rule.values.length) rule.values = defaultValues(rule.field)
}

function valueKind(rule) {
  return fieldDefinition(rule.field).kind
}

function valuesNeeded(rule) {
  return ruleNeedsValues(rule.field, rule.op)
}

function operatorOptions(rule) {
  return operatorsFor(rule.field)
}

function optionSet(kind) {
  if (kind === 'status') return CHECKLIST_STATUSES
  if (kind === 'priority') return CHECKLIST_PRIORITIES
  if (kind === 'people' || kind === 'person') return peopleOptions.value
  if (kind === 'repositories') return repositoryOptions.value
  if (kind === 'tasks') return taskOptions.value
  return []
}

function ruleLabel(rule) {
  const field = fieldDefinition(rule.field).label
  const op = operatorsFor(rule.field).find((entry) => entry.value === rule.op)?.label || rule.op
  if (!ruleNeedsValues(rule.field, rule.op)) return `${field} ${op}`
  const labels = (rule.values || []).map((value) => {
    const kind = fieldDefinition(rule.field).kind
    const option = optionSet(kind).find((entry) => String(entry.value) === String(value))
    return option?.label || value
  })
  return `${field} ${op} ${labels.join(', ') || '(nothing)'}`
}

async function save() {
  const draft = editing.value
  if (!draft || !draft.name.trim()) return
  busy.value = true
  const payload = {
    name: draft.name.trim(),
    description: draft.description.trim(),
    rules: draft.rules.map((rule) => ({
      field: rule.field,
      op: rule.op,
      values: ruleNeedsValues(rule.field, rule.op) ? rule.values : []
    })),
    items: parseItemsText(draft.itemsText)
  }
  try {
    if (draft.id) await api.checklistTemplates.update(draft.id, payload)
    else await api.checklistTemplates.create(payload)
    editing.value = null
    await load()
    store.notify(draft.id ? 'Checklist saved' : 'Checklist added')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function remove(template) {
  if (!confirm('Delete this checklist? Its items are removed from the tasks that received them.')) return
  try {
    await api.checklistTemplates.remove(template.id)
    await load()
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function apply(template) {
  try {
    const result = await api.checklistTemplates.apply(template.id)
    await load()
    store.notify(
      result.applied
        ? `Added items to ${result.applied} task${result.applied === 1 ? '' : 's'}`
        : 'No matching task needed the checklist'
    )
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(load)
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Checklists</h2>
      <button v-if="!editing" class="btn sm" @click="startNew">New checklist</button>
    </div>
    <p class="faint" style="margin-top: 0">
      A checklist applies to the tasks whose properties match all of its rules. Its items are copied onto the task once;
      they stay there, editable, even if the task later stops matching (shown disabled).
    </p>

    <div v-if="editing" class="item checklist-editor">
      <div class="row wrap">
        <div class="field grow">
          <label>Name</label>
          <input v-model="editing.name" class="input" placeholder="Feature release" />
        </div>
        <div class="field grow">
          <label>Description (optional)</label>
          <input v-model="editing.description" class="input" placeholder="What this checklist covers" />
        </div>
      </div>

      <div class="field" style="margin-top: 10px">
        <label>Applies when all of these match</label>
        <div v-if="!editing.rules.length" class="faint" style="font-size: 12px">
          No rules yet. A checklist with no rules applies to no task.
        </div>
        <div v-for="(rule, index) in editing.rules" :key="index" class="row wrap rule-row">
          <select v-model="rule.field" class="select" aria-label="Rule field" @change="changeField(rule)">
            <option v-for="field in CHECKLIST_FIELDS" :key="field.value" :value="field.value">{{ field.label }}</option>
          </select>
          <select v-model="rule.op" class="select" aria-label="Rule operator" @change="changeOperator(rule)">
            <option v-for="operator in operatorOptions(rule)" :key="operator.value" :value="operator.value">
              {{ operator.label }}
            </option>
          </select>

          <template v-if="valuesNeeded(rule)">
            <TagInput
              v-if="valueKind(rule) === 'tags'"
              :model-value="rule.values"
              :suggestions="store.tags"
              placeholder="Add tags…"
              @update:model-value="(value) => (rule.values = value)"
            />
            <SearchSelect
              v-else
              class="grow"
              multiple
              :model-value="rule.values"
              :options="optionSet(valueKind(rule))"
              :placeholder="valueKind(rule) === 'tasks' ? 'Choose tasks…' : 'Choose…'"
              @update:model-value="(value) => (rule.values = value)"
            />
          </template>
          <span v-else class="faint" style="font-size: 12px">No value needed</span>

          <button class="btn sm danger" title="Remove this rule" @click="removeRule(index)">✕</button>
        </div>
        <button class="btn sm ghost" style="margin-top: 6px" @click="addRule">Add rule</button>
      </div>

      <div class="field" style="margin-top: 10px">
        <label>Items, one per line</label>
        <textarea
          v-model="editing.itemsText"
          class="textarea"
          rows="5"
          placeholder="Announce the feature is available&#10;Write user documentation"
        ></textarea>
      </div>

      <div class="row" style="justify-content: flex-end; margin-top: 10px">
        <button class="btn ghost" @click="cancel">Cancel</button>
        <button class="btn primary" :disabled="busy || !editing.name.trim()" @click="save">
          <span v-if="busy" class="spinner"></span> Save
        </button>
      </div>
    </div>

    <EntityCard v-for="template in templates" :key="template.id">
      <template #title>
        <span class="title">{{ template.name }}</span>
      </template>
      <template #actions>
        <span class="badge">{{ template.items.length }} item{{ template.items.length === 1 ? '' : 's' }}</span>
        <span class="badge" :title="'Tasks this checklist has been applied to'"
          >{{ template.applied_count }} applied</span
        >
        <button class="btn sm" @click="apply(template)">Apply now</button>
        <button class="btn sm" @click="startEdit(template)">Edit</button>
        <button class="btn sm danger" @click="remove(template)">Remove</button>
      </template>
      <div v-if="template.description" class="faint">{{ template.description }}</div>
      <div v-if="template.rules.length" class="checklist-rules">
        <span v-for="(rule, index) in template.rules" :key="index" class="chip">{{ ruleLabel(rule) }}</span>
      </div>
      <div v-else class="faint">No rules, so this checklist applies to no task.</div>
      <template #meta>
        <div class="faint">{{ template.items.join(' · ') || 'No items yet' }}</div>
      </template>
    </EntityCard>

    <div v-if="!templates.length && !editing" class="faint">No checklists yet.</div>
  </section>
</template>

<style scoped>
.rule-row {
  gap: 6px;
  align-items: center;
  margin-top: 6px;
  flex-wrap: wrap;
}
.rule-row .select {
  width: auto;
  min-width: 130px;
}
.checklist-rules {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}
.checklist-editor .field {
  margin: 0;
}
</style>
