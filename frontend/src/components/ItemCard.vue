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
  selected: { type: Boolean, default: false }
})

const kind = computed(() => String(props.item.kind || '').replace('_', ' '))
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
      <a v-if="item.url" :href="item.url" target="_blank" class="title">{{ item.title || item.url }}</a>
      <span v-else class="title">{{ item.title }}</span>
    </template>

    <template #actions><slot name="actions" /></template>

    <div v-if="showStatus && (item.kind || prStatus(item))" class="row" style="gap: 6px; margin-top: 2px">
      <span v-if="item.kind" class="faint">{{ kind }}</span>
      <span v-if="prStatus(item)" class="badge" :class="prStatus(item).className">{{ prStatus(item).label }}</span>
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
