<script setup>
import { computed, ref, watch } from 'vue'
import { nextRuns, scheduleError } from '../cron'
import { formatDateTime } from '../store'

// One scheduled-task form. The "new task" panel and each row's edit form are
// separate instances, so every form owns its draft and opening one never
// disturbs what was typed in another.
const props = defineProps({
  modelValue: { type: Object, required: true },
  heading: { type: String, required: true },
  submitLabel: { type: String, required: true },
  saving: { type: Boolean, default: false },
  zones: { type: Array, default: () => [] },
  browserTimezone: { type: String, default: 'UTC' },
  // Distinguishes the ids of the fields when more than one form is open.
  idPrefix: { type: String, required: true }
})
const emit = defineEmits(['update:modelValue', 'save', 'cancel'])

// A writable binding for one field that emits a new draft, since the parent
// holds the draft (it must outlive this component) and props cannot be mutated.
function field(key) {
  return computed({
    get: () => props.modelValue[key],
    set: (value) => emit('update:modelValue', { ...props.modelValue, [key]: value })
  })
}
const name = field('name')
const schedule = field('schedule')
const timezone = field('timezone')
const command = field('command')
const cwd = field('cwd')
const enabled = field('enabled')

// The next occurrences under the schedule field, computed in the browser so the
// preview updates on every keystroke with no request. The server still owns the
// schedule: it decides when a task really runs, using croniter. croner reads the
// same IANA zones and agrees with it for the five-field expressions the form
// accepts, except inside the repeated hour of a daylight-saving fall-back, where
// the two can differ by one run once a year.
const preview = ref([])
const previewError = ref('')
// The zone the cron is read in.
const previewTimezone = ref(props.browserTimezone)
// True when the preview's zone is not the one the browser shows times in.
const zonesDiffer = computed(() => previewTimezone.value !== props.browserTimezone)

// Recompute from the draft expression and zone. Pure and instant, so it runs on
// every keystroke with no debounce.
function refreshPreview() {
  const expression = (props.modelValue.schedule || '').trim()
  const zone = (props.modelValue.timezone || '').trim() || props.browserTimezone
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
      <input :id="`${idPrefix}-name`" v-model="name" class="input grow" placeholder="Nightly backup" />
    </div>
    <div class="field">
      <label :for="`${idPrefix}-schedule`">Schedule (cron: minute hour day month weekday)</label>
      <input
        :id="`${idPrefix}-schedule`"
        v-model="schedule"
        class="input grow"
        placeholder="0 9 * * *"
        :style="{ fontFamily: 'var(--mono)' }"
      />
      <p class="faint" style="margin: 4px 0 0">
        Examples: <code>0 9 * * *</code> daily at 09:00 · <code>*/15 * * * *</code> every 15 minutes ·
        <code>0 18 * * 5</code> Fridays at 18:00
      </p>
    </div>
    <div class="field">
      <label :for="`${idPrefix}-timezone`">Timezone</label>
      <input
        :id="`${idPrefix}-timezone`"
        v-model="timezone"
        class="input grow"
        :list="`${idPrefix}-timezone-options`"
        placeholder="UTC"
      />
      <datalist :id="`${idPrefix}-timezone-options`">
        <option v-for="zone in zones" :key="zone" :value="zone" />
      </datalist>
      <p class="faint" style="margin: 4px 0 0">Cron times are read in this timezone.</p>
    </div>
    <div v-if="preview.length" class="sched-next" style="margin-bottom: 12px">
      <span class="faint">Next 5 runs in {{ previewTimezone || modelValue.timezone }}</span>
      <ul>
        <li v-for="t in preview" :key="t">
          {{ formatDateTime(t, previewTimezone) }}
          <span v-if="zonesDiffer" class="faint">· {{ formatDateTime(t) }} your time</span>
        </li>
      </ul>
    </div>
    <p v-else-if="previewError" class="faint" style="margin: 0 0 12px; color: var(--danger)">
      {{ previewError }}
    </p>
    <div class="field">
      <label :for="`${idPrefix}-command`">Shell command</label>
      <textarea
        :id="`${idPrefix}-command`"
        v-model="command"
        class="textarea grow"
        rows="3"
        placeholder="~/scripts/backup.sh >> /tmp/backup.log 2>&1"
        :style="{ fontFamily: 'var(--mono)' }"
      ></textarea>
    </div>
    <div class="field">
      <label :for="`${idPrefix}-cwd`">Working directory (optional)</label>
      <input :id="`${idPrefix}-cwd`" v-model="cwd" class="input grow" placeholder="/home/me/project" />
    </div>
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
/* The next-runs preview lays the runs out inline, so they read as a row of
   times rather than a bulleted list. Scoped here because this component owns
   the markup. */
.sched-next {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin-top: 4px;
}
.sched-next > span {
  font-size: 12px;
}
.sched-next ul {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.sched-next li {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--muted);
}
</style>
