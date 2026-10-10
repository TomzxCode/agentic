<script setup>
import { timeAgo } from '../store'

defineProps({ events: { type: Array, default: () => [] } })
</script>

<template>
  <section class="panel">
    <div class="panel-head"><h2>Timeline</h2></div>
    <div v-if="!events.length" class="faint">Nothing yet.</div>
    <ul class="timeline">
      <li v-for="e in events" :key="e.id">
        <span class="dot"></span>
        <span class="grow">
          {{ e.message || e.type }}
          <span class="faint"> · {{ e.type }}</span>
        </span>
        <span class="when">{{ timeAgo(e.created_at) }}</span>
      </li>
    </ul>
  </section>
</template>
