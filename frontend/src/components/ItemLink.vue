<script setup>
import { computed } from 'vue'
import { itemStatus } from '../repositories'
import { sourceLabel } from '../store'

// A reference to a SourceItem, rendered as a chip that opens the item's view.
// The leading indicator is source-aware: a GitHub item shows its state
// (open/closed/merged/draft), a Slack item shows a speech emoji, and any other
// source shows its badge when showSource is on.
const props = defineProps({
  item: { type: Object, required: true },
  showSource: { type: Boolean, default: true }
})

const status = computed(() => (props.item.source === 'github' ? itemStatus(props.item) : null))
const isSlack = computed(() => props.item.source === 'slack')
const showBadge = computed(() => props.showSource && !status.value && !isSlack.value)
</script>

<template>
  <router-link :to="`/items/${item.id}`" class="btn sm ghost">
    <span v-if="status" class="badge" :class="status.className">{{ status.label }}</span>
    <span v-else-if="isSlack" class="item-emoji" title="Slack thread" aria-hidden="true">💬</span>
    <span v-else-if="showBadge" class="badge chip-source" :class="`src-${item.source}`">
      {{ sourceLabel(item.source) }}
    </span>
    {{ item.title || item.url }}
  </router-link>
</template>
