<script setup>
import { computed, ref } from 'vue'
import { api } from '../api'
import { store, timeAgo } from '../store'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const refreshing = ref(false)
const summarizing = ref(false)

// A task imported from Slack can be re-named and re-summarized with an agent,
// which is also the recovery path when the import run failed or was interrupted.
const hasSlackItem = computed(() => (props.task.associations || []).some((a) => a.item?.source === 'slack'))

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
    <p v-else class="muted" style="margin: 0">
      No context yet. Add the relevant Slack/GitHub/Drive links, then hit <strong>Refresh with agent</strong> so an
      agent writes a current summary and proposes checklist items.
    </p>
  </section>
</template>
