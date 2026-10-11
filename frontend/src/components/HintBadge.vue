<script setup>
import { store } from '../store'

defineProps({ hint: { type: String, required: true } })
</script>

<template>
  <span v-if="store.hintMode" class="hint-badge">{{ hint }}</span>
</template>
