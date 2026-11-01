<script setup>
import { computed } from 'vue'
import { nextRuns, scheduleError } from '../cron'
import { formatDateTime } from '../store'

// One graph's settings form (not its definition): name, description, and its
// triggers. A trigger is one way the graph starts without a manual run; the
// schedule is one trigger type beside the webhook, so the form edits a list
// rather than a single cron field. The "new graph" panel and each row's
// settings form are separate instances, so drafts never bleed into each other,
// like the scheduled-task forms.
const props = defineProps({
  modelValue: { type: Object, required: true },
  heading: { type: String, required: true },
  submitLabel: { type: String, required: true },
  saving: { type: Boolean, default: false },
  idPrefix: { type: String, required: true },
  // The saved graph's id, so a webhook trigger can show its URL. Empty while a
  // new graph is still being created.
  graphId: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'save', 'cancel'])

const TRIGGER_TYPES = [
  { value: 'schedule', label: 'Schedule' },
  { value: 'webhook', label: 'Webhook' }
]

const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone

const name = computed({
  get: () => props.modelValue.name,
  set: (value) => update({ name: value })
})
const description = computed({
  get: () => props.modelValue.description,
  set: (value) => update({ description: value })
})
const triggers = computed(() => props.modelValue.triggers || [])

function update(patch) {
  emit('update:modelValue', { ...props.modelValue, ...patch })
}

function setTriggers(next) {
  update({ triggers: next })
}

function setTrigger(index, patch) {
  setTriggers(triggers.value.map((trigger, position) => (position === index ? { ...trigger, ...patch } : trigger)))
}

function setConfig(index, key, value) {
  const trigger = triggers.value[index]
  setTrigger(index, { config: { ...(trigger.config || {}), [key]: value } })
}

function addTrigger() {
  setTriggers([...triggers.value, { id: '', type: 'schedule', config: { cron: '', timezone: '' }, enabled: true }])
}

function removeTrigger(index) {
  setTriggers(triggers.value.filter((trigger, position) => position !== index))
}

// Switching the type drops the old config, since the keys mean different
// things per type, and seeds the new type's empty shape.
function changeType(index, type) {
  const config = type === 'webhook' ? { secret: '' } : { cron: '', timezone: '' }
  setTrigger(index, { type, config })
}

// The next five runs of every schedule trigger, so each cron can be checked
// where it is typed. The API stays the authority; this is presentation.
const previews = computed(() =>
  triggers.value.map((trigger) => {
    if (trigger.type !== 'schedule') return null
    const expression = (trigger.config?.cron || '').trim()
    const zone = (trigger.config?.timezone || '').trim() || browserTimezone
    if (!expression) return { error: '', runs: [], zone }
    const invalid = scheduleError(expression)
    if (invalid) return { error: invalid, runs: [], zone }
    try {
      return { error: '', runs: nextRuns(expression, zone, 5), zone }
    } catch {
      return { error: `'${zone}' is not a known timezone`, runs: [], zone }
    }
  })
)

function webhookUrl(trigger) {
  if (!props.graphId || !trigger.id) return ''
  return `${window.location.origin}/api/graphs/${props.graphId}/triggers/${trigger.id}/fire`
}
</script>

<template>
  <div class="panel">
    <div class="panel-head">
      <h2>{{ heading }}</h2>
      <button class="btn sm ghost" @click="emit('cancel')">Cancel</button>
    </div>
    <div class="field">
      <label :for="`${idPrefix}-name`">Name</label>
      <input :id="`${idPrefix}-name`" v-model="name" class="input grow" placeholder="Nightly triage" />
    </div>
    <div class="field">
      <label :for="`${idPrefix}-description`">Description</label>
      <input
        :id="`${idPrefix}-description`"
        v-model="description"
        class="input grow"
        placeholder="What this graph does"
      />
    </div>

    <div class="field">
      <span>Triggers</span>
      <p class="faint" style="margin: 4px 0 8px">
        A trigger starts the graph without a manual run; Run is always available. Add none to run only by hand.
      </p>
      <div v-for="(trigger, index) in triggers" :key="trigger.id || index" class="trigger-block">
        <div class="row trigger-head">
          <select
            class="input trigger-type"
            :aria-label="`Trigger ${index + 1} type`"
            :value="trigger.type"
            @change="changeType(index, $event.target.value)"
          >
            <option v-for="type in TRIGGER_TYPES" :key="type.value" :value="type.value">{{ type.label }}</option>
          </select>
          <label class="row" style="gap: 6px; align-items: center">
            <input
              type="checkbox"
              :checked="trigger.enabled"
              :aria-label="`Trigger ${index + 1} enabled`"
              @change="setTrigger(index, { enabled: $event.target.checked })"
            />
            <span>Enabled</span>
          </label>
          <button class="btn sm ghost" :aria-label="`Remove trigger ${index + 1}`" @click="removeTrigger(index)">
            Remove
          </button>
        </div>

        <template v-if="trigger.type === 'schedule'">
          <div class="field">
            <label :for="`${idPrefix}-trigger-${index}-cron`">Cron expression</label>
            <input
              :id="`${idPrefix}-trigger-${index}-cron`"
              :value="trigger.config?.cron || ''"
              class="input grow"
              placeholder="0 9 * * *"
              :style="{ fontFamily: 'var(--mono)' }"
              @input="setConfig(index, 'cron', $event.target.value)"
            />
            <p class="faint" style="margin: 4px 0 0">
              Examples: <code>0 9 * * *</code> daily at 09:00 · <code>*/15 * * * *</code> every 15 minutes.
            </p>
          </div>
          <div class="field">
            <label :for="`${idPrefix}-trigger-${index}-timezone`">Timezone</label>
            <input
              :id="`${idPrefix}-trigger-${index}-timezone`"
              :value="trigger.config?.timezone || ''"
              class="input grow"
              :placeholder="browserTimezone"
              @input="setConfig(index, 'timezone', $event.target.value)"
            />
            <p class="faint" style="margin: 4px 0 0">Cron times are read in this timezone.</p>
          </div>
          <div v-if="previews[index]?.runs.length" class="graphs-next">
            <span class="faint">Next 5 runs in {{ previews[index].zone }}</span>
            <ul>
              <li v-for="t in previews[index].runs" :key="t">{{ formatDateTime(t, previews[index].zone) }}</li>
            </ul>
          </div>
          <p v-else-if="previews[index]?.error" class="faint graphs-next-error">
            {{ previews[index].error }}
          </p>
        </template>

        <template v-else>
          <div class="field">
            <label :for="`${idPrefix}-trigger-${index}-secret`">Secret (optional)</label>
            <input
              :id="`${idPrefix}-trigger-${index}-secret`"
              :value="trigger.config?.secret || ''"
              class="input grow"
              placeholder="Leave empty to accept any caller"
              @input="setConfig(index, 'secret', $event.target.value)"
            />
            <p class="faint" style="margin: 4px 0 0">
              A caller sends it in the <code>X-Trigger-Secret</code> header, so a leaked URL alone cannot start the
              graph.
            </p>
          </div>
          <p v-if="webhookUrl(trigger)" class="faint webhook-url" style="margin: 0">
            POST <code>{{ webhookUrl(trigger) }}</code>
          </p>
          <p v-else class="faint" style="margin: 0">Save the graph to get the URL that fires this trigger.</p>
        </template>
      </div>
      <button class="btn sm" @click="addTrigger">+ Trigger</button>
    </div>

    <div class="row" style="justify-content: flex-end; margin-top: 8px">
      <button class="btn primary" :disabled="saving" @click="emit('save')">{{ submitLabel }}</button>
    </div>
  </div>
</template>

<style scoped>
.trigger-block {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px;
  margin-bottom: 10px;
}
.trigger-head {
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.trigger-type {
  width: auto;
  min-width: 130px;
}
.graphs-next {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 4px;
}
.graphs-next > span {
  font-size: 12px;
}
.graphs-next ul {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.graphs-next li {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--muted);
}
.graphs-next-error {
  margin: 0 0 8px;
  color: var(--danger);
}
.webhook-url code {
  word-break: break-all;
}
</style>
