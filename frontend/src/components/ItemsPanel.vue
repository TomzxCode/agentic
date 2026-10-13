<script setup>
import { computed, reactive, ref } from 'vue'
import { api } from '../api'
import { store, timeAgo, prStatus } from '../store'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const expanded = ref({})
const busy = ref(false)

// No type field: the backend infers the source from the URL/content.
const draft = reactive({ url: '', title: '', content: '', note: '', showContent: false })

const grouped = computed(() => {
  const groups = {}
  for (const assoc of props.task.associations || []) {
    ;(groups[assoc.item.source] ||= []).push(assoc)
  }
  return groups
})

function toggle(id) {
  expanded.value[id] = !expanded.value[id]
}

async function addItem() {
  if (!draft.url.trim() && !draft.content.trim() && !draft.title.trim()) return
  busy.value = true
  try {
    await api.tasks.associate(props.task.id, {
      note: draft.note,
      item: {
        url: draft.url || null,
        title: draft.title,
        content: draft.content,
        fetch: !draft.content
      }
    })
    draft.url = draft.title = draft.content = draft.note = ''
    draft.showContent = false
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function remove(itemId) {
  await api.tasks.unassociate(props.task.id, itemId)
  emit('changed')
}

async function refreshItem(itemId) {
  try {
    await api.items.refresh(itemId)
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
        Items <span class="faint">{{ task.associations?.length || 0 }}</span>
      </h2>
    </div>

    <div v-if="!task.associations?.length" class="faint" style="margin-bottom: 12px">
      Nothing associated yet. Paste a Slack thread, GitHub issue/PR, Drive link, or a note.
    </div>

    <div v-for="(items, source) in grouped" :key="source" style="margin-bottom: 12px">
      <h3 :class="`src-${source}`" style="margin-bottom: 6px">{{ source }}</h3>
      <div v-for="assoc in items" :key="assoc.id" class="item">
        <div class="item-top">
          <span class="badge chip-source" :class="`src-${source}`">{{ source }}</span>
          <a v-if="assoc.item.url" :href="assoc.item.url" target="_blank" class="title">{{
            assoc.item.title || assoc.item.url
          }}</a>
          <span v-else class="title">{{ assoc.item.title }}</span>
          <button class="btn sm ghost" title="Refresh" @click="refreshItem(assoc.item.id)">↻</button>
          <button class="btn sm ghost" title="Expand" @click="toggle(assoc.item.id)">
            {{ expanded[assoc.item.id] ? '▾' : '▸' }}
          </button>
          <button class="btn sm danger" title="Remove" @click="remove(assoc.item.id)">✕</button>
        </div>
        <div v-if="assoc.item.kind || prStatus(assoc.item)" class="row" style="gap: 6px; margin-top: 4px">
          <span v-if="assoc.item.kind" class="faint">{{ assoc.item.kind.replace('_', ' ') }}</span>
          <span v-if="prStatus(assoc.item)" class="badge" :class="prStatus(assoc.item).className">
            {{ prStatus(assoc.item).label }}
          </span>
        </div>
        <div v-if="assoc.note" class="faint" style="margin-top: 4px">{{ assoc.note }}</div>
        <div v-if="assoc.item.content" class="content" :class="{ clamp: !expanded[assoc.item.id] }">
          {{ assoc.item.content }}
        </div>
        <div class="faint" style="margin-top: 4px">
          added {{ timeAgo(assoc.created_at) }}
          <span v-if="assoc.item.fetched_at"> · fetched {{ timeAgo(assoc.item.fetched_at) }}</span>
        </div>
      </div>
    </div>

    <div style="border-top: 1px solid var(--border); padding-top: 12px; margin-top: 4px">
      <div class="row">
        <input
          v-model="draft.url"
          class="input grow"
          placeholder="Paste a Slack/GitHub/Drive link, any URL, or just text (type is inferred)"
        />
      </div>
      <div class="row" style="margin-top: 8px">
        <input v-model="draft.title" class="input grow" placeholder="Title (optional)" />
        <input v-model="draft.note" class="input grow" placeholder="Note (optional)" />
        <button class="btn" @click="draft.showContent = !draft.showContent">+ text</button>
        <button class="btn primary" :disabled="busy" @click="addItem">
          <span v-if="busy" class="spinner"></span> Associate
        </button>
      </div>
      <textarea
        v-if="draft.showContent"
        v-model="draft.content"
        class="textarea"
        style="margin-top: 8px"
        placeholder="Paste content to keep with this item (skips fetching)."
      ></textarea>
    </div>
  </section>
</template>
