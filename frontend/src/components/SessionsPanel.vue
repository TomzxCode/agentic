<script setup>
// Agent sessions recorded against a task: a run's session plus any attached by
// hand (for example one opened in OpenChamber). Each row carries the links that
// reopen it and a resume command.
import { api } from '../api'
import { store, timeAgo } from '../store'
import EntityCard from './EntityCard.vue'
import SessionLinks from './SessionLinks.vue'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['changed'])

async function remove(id) {
  if (!confirm('Remove this session from the task? The session itself is untouched.')) return
  try {
    await api.sessions.remove(props.task.id, id)
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>
        Sessions <span class="faint">{{ task.sessions?.length || 0 }}</span>
      </h2>
    </div>

    <div v-if="!task.sessions?.length" class="faint" style="margin-bottom: 12px">
      No sessions recorded. Attach one with
      <code class="cmd">agentic session add {{ task.id }} &lt;session-id&gt;</code>.
    </div>

    <EntityCard v-for="session in task.sessions" :key="session.id">
      <template #title>
        <span class="title">{{ session.label || session.session_id }}</span>
      </template>
      <template #title-extra>
        <span v-if="session.harness_id" class="chip">{{ session.harness_id }}</span>
      </template>
      <template #actions>
        <button class="btn sm danger" title="Remove from task" @click="remove(session.id)">Remove</button>
      </template>
      <SessionLinks v-if="session.links?.length" :links="session.links" />
      <template #meta>
        <div class="faint mono" style="margin-top: 4px">{{ session.session_id }}</div>
        <div v-if="session.cwd" class="faint mono">{{ session.cwd }}</div>
        <div class="faint">created {{ timeAgo(session.created_at) }}</div>
      </template>
    </EntityCard>
  </section>
</template>
