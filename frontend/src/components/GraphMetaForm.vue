<script setup>
import { computed, ref, watch } from 'vue'
import { nextRuns, scheduleError } from '../cron'
import { formatDateTime } from '../store'

// One graph's settings form (not its definition): name, description, the cron
// that fires it, and whether it is enabled. The "new graph" panel and each
// row's settings form are separate instances, so drafts never bleed into each
// other, like the scheduled-task forms.
const props = defineProps({
  modelValue: { type: Object, required: true },
  heading: { type: String, required: true },
  submitLabel: { type: String, required: true },
  saving: { type: Boolean, default: false },
  idPrefix: { type: String, required: true }
})
const emit = defineEmits(['update:modelValue', 'save', 'cancel'])

function field(key) {
  return computed({
    get: () => props.modelValue[key],
    set: (value) => emit('update:modelValue', { ...props.modelValue, [key]: value })
  })
}
const name = field('name')
const description = field('description')
const schedule = field('schedule')
const timezone = field('timezone')
const enabled = field('enabled')

// The same live cron preview the scheduled-task form shows.
const preview = ref([])
const previewError = ref('')
const previewTimezone = ref('')
const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone

function refreshPreview() {
  const expression = (props.modelValue.schedule || '').trim()
  const zone = (props.modelValue.timezone || '').trim() || browserTimezone
  previewTimezone.value = zone
  const invalid = scheduleError(expression)
  if (invalid) {
    preview.value = []
    previewError.value = invalid
    return
  }
  try {
    preview.value = nextRuns(expression, zone, 5)
    previewError.value = ''
  } catch {
    preview.value = []
    previewError.value = `'${zone}' is not a known timezone`
  }
}

watch([() => props.modelValue.schedule, () => props.modelValue.timezone], refreshPreview, { immediate: true })
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
      <label :for="`${idPrefix}-schedule`">Schedule (cron, optional)</label>
      <input
        :id="`${idPrefix}-schedule`"
        v-model="schedule"
        class="input grow"
        placeholder="0 9 * * *"
        :style="{ fontFamily: 'var(--mono)' }"
      />
      <p class="faint" style="margin: 4px 0 0">
        Leave empty to run only by hand. Examples: <code>0 9 * * *</code> daily at 09:00 ·
        <code>*/15 * * * *</code> every 15 minutes.
      </p>
    </div>
    <div class="field">
      <label :for="`${idPrefix}-timezone`">Timezone</label>
      <input :id="`${idPrefix}-timezone`" v-model="timezone" class="input grow" :placeholder="browserTimezone" />
      <p class="faint" style="margin: 4px 0 0">Cron times are read in this timezone.</p>
    </div>
    <div v-if="preview.length" class="graphs-next" style="margin-bottom: 12px">
      <span class="faint">Next 5 runs in {{ previewTimezone }}</span>
      <ul>
        <li v-for="t in preview" :key="t">{{ formatDateTime(t, previewTimezone) }}</li>
      </ul>
    </div>
    <p v-else-if="previewError" class="faint" style="margin: 0 0 12px; color: var(--danger)">
      {{ previewError }}
    </p>
    <div class="row" style="justify-content: space-between; margin-top: 8px">
      <label class="row" style="gap: 6px; align-items: center">
        <input v-model="enabled" type="checkbox" />
        <span>Enabled</span>
      </label>
      <button class="btn primary" :disabled="saving" @click="emit('save')">{{ submitLabel }}</button>
    </div>
  </div>
</template>

<style scoped>
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
</style>
