<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { store, statusClass, timeAgo } from './store'

const route = useRoute()
const router = useRouter()
const search = ref('')
const showNew = ref(false)
const sidebarOpen = ref(false)
const draft = ref({ title: '', description: '', priority: 2, group_id: '' })

// Close the mobile drawer when navigating.
watch(() => route.fullPath, () => (sidebarOpen.value = false))


const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return store.tasks
  return store.tasks.filter(
    (p) => p.title.toLowerCase().includes(q) || (p.summary || '').toLowerCase().includes(q),
  )
})

async function refresh() {
  store.loading = true
  try {
    await store.loadTasks()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    store.loading = false
  }
}

async function createTask() {
  if (!draft.value.title.trim()) return
  try {
    const task = await api.tasks.create({ ...draft.value, group_id: draft.value.group_id || null })
    showNew.value = false
    draft.value = { title: '', description: '', priority: 2, group_id: '' }
    await refresh()
    router.push(`/task/${task.id}`)
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(async () => {
  await refresh()
  await store.loadGroups().catch(() => {})
})
</script>

<template>
  <div class="app" :class="{ 'sidebar-open': sidebarOpen }">
    <header class="topbar">
      <button class="btn ghost menu-btn" aria-label="Toggle task list" @click="sidebarOpen = !sidebarOpen">
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none" />
        </svg>
      </button>
      <router-link to="/" class="brand">
        <svg viewBox="0 0 512 512" aria-hidden="true">
          <path d="M160 168 L256 128 L352 168 M160 168 L160 288 L256 344 L352 288 L352 168 M160 288 L256 248 L352 288"
                stroke="#6ee7b7" stroke-width="16" fill="none" stroke-linecap="round" />
          <g fill="#6ee7b7">
            <circle cx="256" cy="128" r="26" /><circle cx="160" cy="168" r="18" />
            <circle cx="352" cy="168" r="18" /><circle cx="256" cy="248" r="20" />
            <circle cx="160" cy="288" r="18" /><circle cx="352" cy="288" r="18" />
            <circle cx="256" cy="344" r="26" />
          </g>
        </svg>
        <span>Agentic</span>
      </router-link>
      <div class="grow"></div>
      <router-link to="/" class="btn ghost sm nav-tasks" :class="{ primary: route.name === 'tasks' }">Tasks</router-link>
      <router-link to="/settings" class="btn ghost sm" :class="{ primary: route.name === 'settings' }">Settings</router-link>
      <button class="btn primary mobile-only" title="New task" aria-label="New task" @click="showNew = true">+</button>
    </header>

    <div v-if="sidebarOpen" class="sidebar-backdrop" @click="sidebarOpen = false"></div>

    <aside class="sidebar">
      <div class="side-head">
        <input v-model="search" class="input grow" placeholder="Search tasks…" />
        <button class="btn primary" @click="showNew = true" title="New task">+</button>
      </div>
      <div v-if="store.loading && !store.tasks.length" class="empty"><span class="spinner"></span></div>
      <div v-else-if="!filtered.length" class="empty">No tasks yet.</div>
      <router-link
        v-for="p in filtered"
        :key="p.id"
        :to="`/task/${p.id}`"
        class="task-card"
        :class="{ active: route.params.id === p.id }"
        @click="sidebarOpen = false"
      >
        <span class="t">{{ p.title }}</span>
        <span class="s">{{ p.summary || p.description || 'No summary yet' }}</span>
        <span class="meta">
          <span :class="statusClass(p.status)">{{ p.status.replace('_', ' ') }}</span>
          <span v-if="p.next_steps?.length" class="badge">{{ p.next_steps.filter((s) => !s.done).length }} steps</span>
          <span class="faint">{{ timeAgo(p.updated_at) }}</span>
        </span>
      </router-link>
    </aside>

    <main class="main">
      <router-view :key="route.fullPath" @changed="refresh" />
    </main>

    <div v-if="showNew" class="modal-backdrop" @click.self="showNew = false">
      <div class="modal">
        <h1 style="margin-bottom: 14px">New task</h1>
        <div class="field">
          <label>Title</label>
          <input v-model="draft.title" class="input" placeholder="What needs to be solved?" @keyup.enter="createTask" />
        </div>
        <div class="field">
          <label>Description</label>
          <textarea v-model="draft.description" class="textarea" placeholder="Context, links, anything…"></textarea>
        </div>
        <div class="field">
          <label>Priority</label>
          <select v-model.number="draft.priority" class="select">
            <option :value="0">Low</option>
            <option :value="1">Medium</option>
            <option :value="2">High</option>
            <option :value="3">Urgent</option>
          </select>
        </div>
        <div class="field">
          <label>Repository group (optional)</label>
          <select v-model="draft.group_id" class="select">
            <option value="">None</option>
            <option v-for="group in store.groups" :key="group.id" :value="group.id">{{ group.name }}</option>
          </select>
        </div>
        <div class="row" style="justify-content: flex-end">
          <button class="btn ghost" @click="showNew = false">Cancel</button>
          <button class="btn primary" :disabled="!draft.title.trim()" @click="createTask">Create</button>
        </div>
      </div>
    </div>

    <div v-if="store.toast" class="toast" :class="{ err: store.toast.isError }">{{ store.toast.message }}</div>
  </div>
</template>
