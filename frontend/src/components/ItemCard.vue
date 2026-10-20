<script setup>
import { computed } from 'vue'
import { prStatus, sourceLabel, timeAgo } from '../store'
import EntityCard from './EntityCard.vue'

// A single SourceItem (a Slack thread, GitHub issue/PR, Drive doc, URL, or
// note) rendered as a card. The task page's Items panel, the Resources page,
// and the repository detail view all use it, so an item looks the same wherever
// it appears.
const props = defineProps({
  item: { type: Object, required: true },
  // The body is clamped to a few lines unless expanded.
  expanded: { type: Boolean, default: true },
  // The source badge in the header. Hide it when a group header already names
  // the source.
  showSource: { type: Boolean, default: true },
  // The kind and GitHub state line under the header.
  showStatus: { type: Boolean, default: true },
  showContent: { type: Boolean, default: true },
  showTimes: { type: Boolean, default: true },
  selectable: { type: Boolean, default: false },
  selected: { type: Boolean, default: false },
  // When set, the title opens the item's own view instead of its external URL,
  // so a list of the user's items stays in the app. A row with no stored item
  // (a live-only GitHub row) passes nothing and keeps the external link.
  to: { type: String, default: null }
})

const kind = computed(() => String(props.item.kind || '').replace('_', ' '))

// A Slack thread marked done keeps its done state when a reply arrives; the
// badge says there is something new to read without reopening it.
const newSinceDone = computed(() => {
  if (!props.item.new_since_done) return null
  const since = props.item.latest_message_at ? ` (last message ${timeAgo(props.item.latest_message_at)})` : ''
  return `New messages since this was marked done${since}`
})
</script>

<template>
  <EntityCard :selectable="selectable" :selected="selected">
    <template #lead>
      <slot name="lead">
        <span v-if="showSource" class="badge chip-source" :class="`src-${item.source}`">
          {{ sourceLabel(item.source) }}
        </span>
      </slot>
    </template>

    <template #title>
      <router-link v-if="to" :to="to" class="title">{{ item.title || item.url }}</router-link>
      <a v-else-if="item.url" :href="item.url" target="_blank" class="title">{{ item.title || item.url }}</a>
      <span v-else class="title">{{ item.title }}</span>
    </template>

    <template #actions><slot name="actions" /></template>

    <div v-if="showStatus && (item.kind || prStatus(item) || item.done)" class="row" style="gap: 6px; margin-top: 2px">
      <span v-if="item.kind" class="faint">{{ kind }}</span>
      <span v-if="prStatus(item)" class="badge" :class="prStatus(item).className">{{ prStatus(item).label }}</span>
      <span v-if="item.done" class="badge ok">done</span>
      <span v-if="newSinceDone" class="badge warn" :title="newSinceDone">new messages</span>
    </div>

    <slot name="note" />

    <div v-if="showContent && item.content" class="content" :class="{ clamp: !expanded }">{{ item.content }}</div>

    <slot />

    <template #meta>
      <slot name="meta">
        <div v-if="showTimes" class="faint" style="margin-top: 4px">
          added {{ timeAgo(item.created_at) }}
          <span v-if="item.fetched_at"> · fetched {{ timeAgo(item.fetched_at) }}</span>
        </div>
      </slot>
    </template>
  </EntityCard>
</template>
