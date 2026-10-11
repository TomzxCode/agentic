<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { store, timeAgo } from '../store'

const router = useRouter()

const SOURCE_LABELS = {
  github: 'GitHub',
  slack: 'Slack',
  gdrive: 'Google Drive',
  url: 'Web',
  note: 'Note',
  commit: 'Commit',
  file: 'File',
}
const SOURCE_ORDER = ['github', 'slack', 'gdrive', 'url', 'note', 'commit', 'file']

const items = ref([])
const loading = ref(true)
const search = ref('')
const sourceFilter = ref('')
const expanded = ref({})

function label(source) {
  return SOURCE_LABELS[source] || source
}

const counts = computed(() => {
  const result = {}
  for (const item of items.value) result[item.source] = (result[item.source] || 0) + 1
  return result
})

const sources = computed(() =>
  [...Object.keys(counts.value)].sort(
    (a, b) => SOURCE_ORDER.indexOf(a) - SOURCE_ORDER.indexOf(b) || a.localeCompare(b),
  ),
)

const visible = computed(() => {
  const q = search.value.trim().toLowerCase()
  return items.value.filter((item) => {
    if (sourceFilter.value && item.source !== sourceFilter.value) return false
    if (!q) return true
    return (
      item.title.toLowerCase().includes(q) ||
      (item.url || '').toLowerCase().includes(q) ||
      (item.content || '').toLowerCase().includes(q)
    )
  })
})

function linkedTasks(item) {
  return (item.task_ids || []).map((id) => store.tasks.find((task) => task.id === id)).filter(Boolean)
}

async function load() {
  loading.value = true
  try {
    items.value = await api.items.list()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function refresh(item) {
  try {
    const updated = await api.items.refresh(item.id)
    Object.assign(item, updated)
    store.notify('Refreshed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(async () => {
  await store.loadTasks().catch(() => {})
  await load()
})
</script>

<template>
  <div>
    <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 12px">
      <h1>Resources</h1>
      <span class="faint">{{ visible.length }} of {{ items.length }}</span>
    </div>

    <div class="row" style="margin-bottom: 12px">
      <input v-model="search" class="input grow" placeholder="Search title, link, or content…" />
    </div>

    <div class="row" style="margin-bottom: 16px">
      <button class="btn sm" :class="{ primary: !sourceFilter }" @click="sourceFilter = ''">
        All {{ items.length }}
      </button>
      <button
        v-for="source in sources"
        :key="source"
        class="btn sm"
        :class="{ primary: sourceFilter === source }"
        @click="sourceFilter = source"
      >
        {{ label(source) }} {{ counts[source] }}
      </button>
    </div>

    <div v-if="loading" class="empty"><span class="spinner"></span></div>
    <div v-else-if="!visible.length" class="empty">No resources.</div>
    <div v-else>
      <div v-for="item in visible" :key="item.id" class="item">
        <div class="item-top">
          <span class="badge chip-source" :class="`src-${item.source}`">{{ label(item.source) }}</span>
          <a v-if="item.url" :href="item.url" target="_blank" class="title">{{ item.title || item.url }}</a>
          <span v-else class="title">{{ item.title }}</span>
          <button class="btn sm ghost" title="Refresh" @click="refresh(item)">↻</button>
          <button class="btn sm ghost" title="Expand" @click="expanded[item.id] = !expanded[item.id]">
            {{ expanded[item.id] ? '▾' : '▸' }}
          </button>
        </div>
        <div v-if="item.kind" class="faint">{{ item.kind.replace('_', ' ') }}</div>
        <div v-if="item.content" class="content" :class="{ clamp: !expanded[item.id] }">{{ item.content }}</div>
        <div class="row" style="margin-top: 6px; gap: 6px">
          <span v-if="!linkedTasks(item).length" class="faint">not linked to a task</span>
          <button
            v-for="task in linkedTasks(item)"
            :key="task.id"
            class="btn sm ghost"
            @click="router.push(`/task/${task.id}`)"
          >
            ↗ {{ task.title }}
          </button>
        </div>
        <div class="faint" style="margin-top: 4px">
          added {{ timeAgo(item.created_at) }}
          <span v-if="item.fetched_at"> · fetched {{ timeAgo(item.fetched_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
