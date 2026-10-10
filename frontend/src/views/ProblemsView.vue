<script setup>
import { computed, onMounted } from 'vue'
import { store, statusClass, timeAgo } from '../store'

const counts = computed(() => {
  const c = { open: 0, in_progress: 0, blocked: 0, done: 0, archived: 0 }
  for (const p of store.problems) c[p.status] = (c[p.status] || 0) + 1
  return c
})

const focus = computed(() =>
  store.problems
    .filter((p) => p.status !== 'done' && p.status !== 'archived')
    .sort((a, b) => {
      const av = (a.next_steps || []).filter((s) => !s.done).length
      const bv = (b.next_steps || []).filter((s) => !s.done).length
      return b.priority - a.priority || bv - av
    })
    .slice(0, 8),
)

onMounted(() => store.loadProblems())
</script>

<template>
  <div>
    <h1 style="margin-bottom: 16px">Problems in flight</h1>

    <div class="row" style="gap: 10px; margin-bottom: 20px">
      <span class="badge">Open {{ counts.open }}</span>
      <span class="badge run">In progress {{ counts.in_progress }}</span>
      <span class="badge warn">Blocked {{ counts.blocked }}</span>
      <span class="badge ok">Done {{ counts.done }}</span>
    </div>

    <section class="panel" v-if="focus.length">
      <div class="panel-head"><h2>Focus</h2></div>
      <router-link
        v-for="p in focus"
        :key="p.id"
        :to="`/p/${p.id}`"
        class="item"
        style="display: block"
      >
        <div class="item-top">
          <span :class="statusClass(p.status)">{{ p.status.replace('_', ' ') }}</span>
          <span class="title">{{ p.title }}</span>
          <span class="faint">{{ timeAgo(p.updated_at) }}</span>
        </div>
        <div v-if="p.summary" class="content clamp">{{ p.summary }}</div>
        <div v-if="p.next_steps?.filter((s) => !s.done).length" class="faint" style="margin-top: 6px">
          Next: {{ p.next_steps.find((s) => !s.done).text }}
        </div>
      </router-link>
    </section>

    <section class="panel" v-else>
      <h2 style="margin-bottom: 8px">Get started</h2>
      <ol class="muted" style="padding-left: 18px; line-height: 1.9">
        <li>Create a problem (the <strong>+</strong> in the sidebar).</li>
        <li>Associate the relevant Slack thread, GitHub issue/PR, or Drive doc.</li>
        <li>Add a repository in <router-link to="/settings">Settings</router-link>, then spin up a worktree.</li>
        <li>Hit <strong>Refresh with agent</strong> to get a current summary and next steps.</li>
        <li>Run an agent to make progress; the transcript streams live.</li>
      </ol>
    </section>
  </div>
</template>
