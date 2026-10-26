<script setup>
import { computed, ref } from 'vue'
import { api } from '../api'
import { store, timeAgo } from '../store'
import EditableText from './EditableText.vue'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const refreshing = ref(false)
const summarizing = ref(false)

// An empty list means the task has no next steps defined, which we surface
// prominently so the user notices it and can refresh the context.
const hasNextSteps = computed(() => (props.task.next_steps || []).length > 0)

// Steps are stored one per entry, but the field's value is Markdown (as with
// notes): one task-list item per step, so the display renders a checkbox per
// step and `[x]` carries the done flag. Saving reads that syntax back.
const stepsText = computed(() =>
  (props.task.next_steps || []).map((s) => `- [${s.done ? 'x' : ' '}] ${s.text}`).join('\n')
)

// A task imported from Slack can be re-named and re-summarized with an agent,
// which is also the recovery path when the import run failed or was interrupted.
const hasSlackItem = computed(() => (props.task.associations || []).some((a) => a.item?.source === 'slack'))

const TASK_ITEM = /^\s*[-*+]\s+\[([ xX])\]\s*(.*)$/
const BULLET = /^\s*[-*+]\s+(.*)$/

async function saveNextSteps(value) {
  const steps = value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const task = TASK_ITEM.exec(line)
      if (task) return { text: task[2].trim(), done: task[1].toLowerCase() === 'x' }
      const bullet = BULLET.exec(line)
      return { text: (bullet ? bullet[1] : line).trim(), done: false }
    })
    .filter((step) => step.text)
  await api.tasks.update(props.task.id, { next_steps: steps })
  emit('changed')
}

// Ticking a rendered checkbox flips that step's done flag. The index comes from
// the box order, which matches the step order the field was built from.
async function onFieldClick(event) {
  const box = event.target?.closest?.('input.task-list-item-checkbox')
  if (!box) return
  const index = [...event.currentTarget.querySelectorAll('input.task-list-item-checkbox')].indexOf(box)
  if (index < 0) return
  await toggleStep(index)
}

async function toggleStep(index) {
  const steps = (props.task.next_steps || []).map((s, i) => (i === index ? { ...s, done: !s.done } : s))
  await api.tasks.update(props.task.id, { next_steps: steps })
  emit('changed')
}

async function refresh() {
  refreshing.value = true
  try {
    await api.runs.refreshContext(props.task.id)
    store.notify('Agent is reading the task and its items…')
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    setTimeout(() => (refreshing.value = false), 1500)
  }
}

async function summarize() {
  summarizing.value = true
  try {
    await api.runs.refreshSummary(props.task.id)
    store.notify('Agent is naming the task and summarizing the Slack thread…')
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    setTimeout(() => (summarizing.value = false), 1500)
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>
        Context <span v-if="task.context_updated_at" class="faint">updated {{ timeAgo(task.context_updated_at) }}</span>
        <span v-if="!hasNextSteps" class="badge warn" title="This task has no next steps defined">no next steps</span>
      </h2>
      <button class="btn sm" :disabled="refreshing" @click="refresh">
        <span v-if="refreshing" class="spinner"></span>
        <span v-else>↻</span> Refresh with agent
      </button>
      <button v-if="hasSlackItem" class="btn sm" :disabled="summarizing" @click="summarize">
        <span v-if="summarizing" class="spinner"></span>
        <span v-else>↻</span> Name &amp; summarize
      </button>
    </div>

    <p v-if="task.summary" class="summary">{{ task.summary }}</p>
    <p v-else class="muted" style="margin: 0 0 12px">
      No context yet. Add the relevant Slack/GitHub/Drive links, then hit <strong>Refresh with agent</strong> so an
      agent writes a current summary and next steps.
    </p>

    <h3 style="margin: 14px 0 6px">Next steps</h3>
    <EditableText
      class="next-steps"
      multiline
      markdown
      task-lists
      as="div"
      :value="stepsText"
      placeholder="No next steps yet. Click to write some, or hit Refresh with agent. Use @ to mention a person, an item, or a date."
      @click="onFieldClick"
      @save="saveNextSteps"
    />
  </section>
</template>
