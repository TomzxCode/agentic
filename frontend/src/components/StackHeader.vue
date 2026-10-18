<script setup>
// The Stack page head: title and the History / shortcuts / Refresh controls.
defineProps({
  showHistory: { type: Boolean, default: false },
  loading: { type: Boolean, default: false }
})
const emit = defineEmits(['toggle-history', 'toggle-help', 'refresh'])
</script>

<template>
  <div class="row page-head" style="margin-bottom: 14px">
    <h1 class="grow">Stack</h1>
    <button class="btn sm ghost" :class="{ active: showHistory }" @click="emit('toggle-history')">History</button>
    <button class="btn sm ghost" title="Keyboard shortcuts (?)" @click="emit('toggle-help')">?</button>
    <button class="btn sm ghost" @click="emit('refresh')"><span v-if="loading" class="spinner"></span> Refresh</button>
  </div>
</template>
