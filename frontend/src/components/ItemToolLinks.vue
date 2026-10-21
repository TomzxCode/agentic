<script setup>
import { computed } from 'vue'
import { store } from '../store'
import { itemToolLinks } from '../toolLinks'

// The item's links into the local ghx or slackx web UI, shown only when the
// matching server URL is configured. Compact renders the tool name alone, for
// a row of icon-sized row actions.
const props = defineProps({
  item: { type: Object, required: true },
  compact: { type: Boolean, default: false }
})

const links = computed(() => itemToolLinks(props.item, store.settings))
</script>

<template>
  <a
    v-for="link in links"
    :key="link.id"
    class="btn sm ghost"
    :href="link.url"
    target="_blank"
    rel="noopener"
    :title="link.label"
  >
    {{ compact ? link.id : link.label }}
  </a>
</template>
