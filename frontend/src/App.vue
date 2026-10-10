<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { store, statusClass, timeAgo } from './store'

const route = useRoute()
const router = useRouter()
const search = ref('')
const showNew = ref(false)
const draft = ref({ title: '', description: '', priority: 2 })

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return store.problems
  return store.problems.filter(
    (p) => p.title.toLowerCase().includes(q) || (p.summary || '').toLowerCase().includes(q),
  )
})

async function refresh() {
  store.loading = true
  try {
    await store.loadProblems()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    store.loading = false
  }
}

async function createProblem() {
  if (!draft.value.title.trim()) return
  try {
    const problem = await api.problems.create(draft.value)
    showNew.value = false
    draft.value = { title: '', description: '', priority: 2 }
    await refresh()
    router.push(`/p/${problem.id}`)
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(refresh)
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
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
      </div>
      <div class="grow"></div>
      <router-link to="/" class="btn ghost sm" :class="{ primary: route.name === 'problems' }">Problems</router-link>
      <router-link to="/settings" class="btn ghost sm" :class="{ primary: route.name === 'settings' }">Settings</router-link>
    </header>

    <aside class="sidebar">
      <div class="side-head">
        <input v-model="search" class="input grow" placeholder="Search problems…" />
        <button class="btn primary" @click="showNew = true" title="New problem">+</button>
      </div>
      <div v-if="store.loading && !store.problems.length" class="empty"><span class="spinner"></span></div>
      <div v-else-if="!filtered.length" class="empty">No problems yet.</div>
      <router-link
        v-for="p in filtered"
        :key="p.id"
        :to="`/p/${p.id}`"
        class="problem-card"
        :class="{ active: route.params.id === p.id }"
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
        <h1 style="margin-bottom: 14px">New problem</h1>
        <div class="field">
          <label>Title</label>
          <input v-model="draft.title" class="input" placeholder="What needs to be solved?" @keyup.enter="createProblem" />
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
        <div class="row" style="justify-content: flex-end">
          <button class="btn ghost" @click="showNew = false">Cancel</button>
          <button class="btn primary" :disabled="!draft.title.trim()" @click="createProblem">Create</button>
        </div>
      </div>
    </div>

    <div v-if="store.toast" class="toast" :class="{ err: store.toast.isError }">{{ store.toast.message }}</div>
  </div>
</template>
