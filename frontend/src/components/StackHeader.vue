<script setup>
// The Stack page head: title and the History / shortcuts controls.
defineProps({
  showHistory: { type: Boolean, default: false }
})
const emit = defineEmits(['toggle-history', 'toggle-help'])
</script>

<template>
  <div class="row page-head" style="margin-bottom: 14px">
    <h1 class="grow">Stack</h1>
    <div class="row stack-head-actions">
      <button class="btn sm ghost" :class="{ active: showHistory }" @click="emit('toggle-history')">History</button>
      <button class="btn sm ghost" title="Keyboard shortcuts (?)" @click="emit('toggle-help')">?</button>
    </div>
  </div>
</template>
