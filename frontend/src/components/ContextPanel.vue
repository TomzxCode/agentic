<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { store, timeAgo } from '../store'

const props = defineProps({ problem: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const refreshing = ref(false)

async function toggleStep(index) {
  const steps = (props.problem.next_steps || []).map((s, i) =>
    i === index ? { ...s, done: !s.done } : s,
  )
  await api.problems.update(props.problem.id, { next_steps: steps })
  emit('changed')
}

async function refresh() {
  refreshing.value = true
  try {
    await api.runs.refreshContext(props.problem.id)
    store.notify('Agent is reading the problem and its items…')
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    setTimeout(() => (refreshing.value = false), 1500)
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>Context <span v-if="problem.context_updated_at" class="faint">updated {{ timeAgo(problem.context_updated_at) }}</span></h2>
      <button class="btn sm" :disabled="refreshing" @click="refresh">
        <span v-if="refreshing" class="spinner"></span>
        <span v-else>↻</span> Refresh with agent
      </button>
    </div>

    <p v-if="problem.summary" class="summary">{{ problem.summary }}</p>
    <p v-else class="muted" style="margin: 0 0 12px">
      No context yet. Add the relevant Slack/GitHub/Drive links, then hit <strong>Refresh with agent</strong> so an
      agent writes a current summary and next steps.
    </p>

    <h3 style="margin: 14px 0 6px">Next steps</h3>
    <ul v-if="problem.next_steps?.length" class="steps">
      <li v-for="(step, i) in problem.next_steps" :key="i">
        <input type="checkbox" :checked="step.done" @change="toggleStep(i)" />
        <span :class="{ done: step.done }">{{ step.text }}</span>
      </li>
    </ul>
    <p v-else class="faint" style="margin: 0">No next steps yet.</p>
  </section>
</template>
