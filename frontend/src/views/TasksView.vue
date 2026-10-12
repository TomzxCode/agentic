<script setup>
import { computed, onMounted } from 'vue'
import { store, statusClass, timeAgo, taskHasTag } from '../store'

const matchesFilter = (p) => !store.tagFilter || taskHasTag(p, store.tagFilter)

const counts = computed(() => {
  const c = { open: 0, in_progress: 0, blocked: 0, done: 0, archived: 0 }
  for (const p of store.tasks.filter(matchesFilter)) c[p.status] = (c[p.status] || 0) + 1
  return c
})

const focus = computed(() =>
  store.tasks
    .filter((p) => p.status !== 'done' && p.status !== 'archived')
    .filter(matchesFilter)
    .sort((a, b) => {
      const av = (a.next_steps || []).filter((s) => !s.done).length
      const bv = (b.next_steps || []).filter((s) => !s.done).length
      return b.priority - a.priority || bv - av
    })
    .slice(0, 8)
)

onMounted(() => store.loadTasks())
</script>

<template>
  <div>
    <h1 style="margin-bottom: 16px">Tasks in flight</h1>

    <div v-if="store.tags.length" class="tag-filters" aria-label="Filter by tag">
      <button
        class="tag-filter"
        :class="{ active: !store.tagFilter }"
        type="button"
        title="Show every task"
        @click="store.tagFilter = ''"
      >
        All
      </button>
      <button
        v-for="tag in store.tags"
        :key="tag.name"
        class="tag-filter"
        :class="{ active: store.tagFilter === tag.name }"
        type="button"
        :title="`Show tasks tagged ${tag.name}`"
        @click="store.toggleTagFilter(tag.name)"
      >
        {{ tag.name }} <span class="count">{{ tag.count }}</span>
      </button>
    </div>

    <div class="row" style="gap: 10px; margin-bottom: 20px">
      <span class="badge">Open {{ counts.open }}</span>
      <span class="badge run">In progress {{ counts.in_progress }}</span>
      <span class="badge warn">Blocked {{ counts.blocked }}</span>
      <span class="badge ok">Done {{ counts.done }}</span>
    </div>

    <section v-if="focus.length" class="panel">
      <div class="panel-head"><h2>Focus</h2></div>
      <router-link v-for="p in focus" :key="p.id" :to="`/task/${p.id}`" class="item" style="display: block">
        <div class="item-top">
          <span :class="statusClass(p.status)">{{ p.status.replace('_', ' ') }}</span>
          <span class="title">{{ p.title }}</span>
          <span class="faint">{{ timeAgo(p.updated_at) }}</span>
        </div>
        <div v-if="p.summary" class="content clamp">{{ p.summary }}</div>
        <div v-if="p.next_steps?.filter((s) => !s.done).length" class="faint" style="margin-top: 6px">
          Next: {{ p.next_steps.find((s) => !s.done).text }}
        </div>
        <div v-if="p.tags?.length" class="task-tags" style="margin-top: 6px">
          <button
            v-for="tag in p.tags"
            :key="tag"
            type="button"
            class="tag-chip"
            :class="{ active: store.tagFilter === tag }"
            :title="`Filter by ${tag}`"
            @click.prevent.stop="store.toggleTagFilter(tag)"
          >
            {{ tag }}
          </button>
        </div>
      </router-link>
    </section>

    <section v-else class="panel">
      <template v-if="store.tagFilter">
        <h2 style="margin-bottom: 8px">Nothing tagged "{{ store.tagFilter }}"</h2>
        <p class="muted">
          No in-flight task carries this tag.
          <button class="btn sm ghost" @click="store.tagFilter = ''">Clear filter</button>
        </p>
      </template>
      <template v-else>
        <h2 style="margin-bottom: 8px">Get started</h2>
        <ol class="muted" style="padding-left: 18px; line-height: 1.9">
          <li>Create a task (the <strong>+</strong> in the sidebar).</li>
          <li>Associate the relevant Slack thread, GitHub issue/PR, or Drive doc.</li>
          <li>Add a repository in <router-link to="/settings">Settings</router-link>, then spin up a worktree.</li>
          <li>Hit <strong>Refresh with agent</strong> to get a current summary and next steps.</li>
          <li>Run an agent to make progress; the transcript streams live.</li>
        </ol>
      </template>
    </section>
  </div>
</template>
