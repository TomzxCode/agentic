<script setup>
import { computed, reactive, ref } from 'vue'
import { api } from '../api'
import { changeCreateBody, changeReferencesItem, isPullRequestItem } from '../changes'
import { sourceLabel, store, timeAgo } from '../store'
import ItemCard from './ItemCard.vue'

const props = defineProps({ task: { type: Object, required: true } })
const emit = defineEmits(['changed'])
const expanded = ref({})
const busy = ref(false)

// No type field: the backend infers the source from the URL/content.
const draft = reactive({ url: '', title: '', content: '', note: '', showContent: false })

// Notes have their own section under Context (NotesPanel), so the Items panel
// only groups the external sources.
const grouped = computed(() => {
  const groups = {}
  for (const assoc of props.task.associations || []) {
    if (assoc.item.source === 'note') continue
    ;(groups[assoc.item.source] ||= []).push(assoc)
  }
  return groups
})

const changes = computed(() => props.task.changes || [])

// Notes are shown in their own section, so the Items panel counts only the
// external sources it lists.
const itemCount = computed(() => (props.task.associations || []).filter((a) => a.item.source !== 'note').length)

// The external URL of a linked item, so its actions can open the reference.
// Notes have none, and an item that was never given a link has none either.
function itemUrl(item) {
  return item?.url || null
}

// Offer to record a change for a linked PR that no change references yet.
function needsChange(item) {
  return isPullRequestItem(item) && !changes.value.some((change) => changeReferencesItem(change, item))
}

async function recordChange(item) {
  try {
    // A merged PR already landed: the change opens accepted, dated to the merge.
    await api.changes.create(changeCreateBody(props.task.id, item))
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

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
    const updated = await api.items.refresh(itemId)
    store.notifyRefresh(updated)
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

// A Slack conversation can be marked done from the task page too. A reply
// that arrives later is flagged but leaves the conversation done.
async function toggleDone(item) {
  try {
    const updated = await api.items.update(item.id, { done: !item.done })
    Object.assign(item, updated)
    store.notify(updated.done ? 'Marked done' : 'Reopened')
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
        Items <span class="faint">{{ itemCount }}</span>
      </h2>
    </div>

    <div style="border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 12px">
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

    <div v-if="!itemCount" class="faint" style="margin-bottom: 12px">
      Nothing associated yet. Paste a Slack thread, GitHub issue/PR, or Drive link.
    </div>

    <div v-for="(items, source) in grouped" :key="source" style="margin-bottom: 12px">
      <h3 :class="`src-${source}`" style="margin-bottom: 6px">{{ sourceLabel(source) }}</h3>
      <ItemCard
        v-for="assoc in items"
        :key="assoc.id"
        :item="assoc.item"
        :to="`/items/${assoc.item.id}`"
        :expanded="!!expanded[assoc.item.id]"
        :show-source="false"
      >
        <template #note>
          <div v-if="assoc.note" class="faint" style="margin-top: 4px">{{ assoc.note }}</div>
        </template>
        <template #actions>
          <button
            v-if="assoc.item.source === 'slack'"
            class="btn sm"
            :class="{ ghost: !assoc.item.done }"
            :title="assoc.item.done ? 'Reopen this conversation' : 'Mark this conversation done'"
            @click="toggleDone(assoc.item)"
          >
            {{ assoc.item.done ? 'Reopen' : 'Done' }}
          </button>
          <button
            v-if="needsChange(assoc.item)"
            class="btn sm"
            title="Record a change for this PR"
            @click="recordChange(assoc.item)"
          >
            Record change
          </button>
          <a
            v-if="itemUrl(assoc.item)"
            class="btn sm ghost"
            :href="itemUrl(assoc.item)"
            target="_blank"
            rel="noopener"
            title="Open link"
            aria-label="Open link"
            >↗</a
          >
          <button class="btn sm ghost" title="Refresh" @click="refreshItem(assoc.item.id)">↻</button>
          <button class="btn sm ghost" title="Expand" @click="toggle(assoc.item.id)">
            {{ expanded[assoc.item.id] ? '▾' : '▸' }}
          </button>
          <button class="btn sm danger" title="Remove" @click="remove(assoc.item.id)">✕</button>
        </template>
        <template #meta>
          <div class="faint" style="margin-top: 4px">
            added {{ timeAgo(assoc.created_at) }}
            <span v-if="assoc.item.fetched_at"> · fetched {{ timeAgo(assoc.item.fetched_at) }}</span>
          </div>
        </template>
      </ItemCard>
    </div>
  </section>
</template>
