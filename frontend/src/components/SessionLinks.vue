<script setup>
import { store } from '../store'

defineProps({
  links: { type: Array, default: () => [] },
  compact: { type: Boolean, default: false },
})

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    store.notify('Copied to clipboard')
  } catch {
    store.notify('Copy failed', true)
  }
}
</script>

<template>
  <div v-if="links.length" class="session-links" :class="{ compact }">
    <template v-for="link in links" :key="link.id">
      <a
        v-if="link.url"
        :href="link.url"
        target="_blank"
        rel="noopener"
        class="btn sm ghost"
        :title="link.url"
      >↗ {{ link.label }}</a>
      <button
        v-else-if="link.command"
        class="btn sm ghost"
        :title="link.command"
        @click="copy(link.command)"
      >⧉ {{ compact ? 'Resume' : 'Copy resume command' }}</button>
    </template>
    <code v-if="!compact" class="cmd" title="Run this in a terminal">
      <span
        v-for="link in links.filter((l) => l.command)"
        :key="link.id"
      >{{ link.command }}</span>
    </code>
  </div>
</template>
