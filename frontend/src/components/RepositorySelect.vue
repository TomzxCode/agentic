<script setup>
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import SearchSelect from './SearchSelect.vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  repositories: { type: Array, default: () => [] },
  placeholder: { type: String, default: '+ Link repository' },
  emptyLabel: { type: String, default: 'no repositories' },
  // When true, each selected repository's name links to its detail page.
  linkToDetail: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

const select = ref(null)

const ids = computed(() => props.modelValue || [])
const selected = computed(() =>
  ids.value
    .map((id) => props.repositories.find((r) => r.id === id))
    .filter(Boolean)
    .sort((a, b) => a.name.localeCompare(b.name))
)
const addOptions = computed(() =>
  props.repositories
    .filter((r) => !ids.value.includes(r.id))
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((r) => ({ value: r.id, label: r.name }))
)

function add(id) {
  if (!id || ids.value.includes(id)) return
  emit('update:modelValue', [...ids.value, id])
}

function remove(id) {
  emit(
    'update:modelValue',
    ids.value.filter((x) => x !== id)
  )
}

// Let a parent (e.g. the command palette) open the "add repository" dropdown.
defineExpose({ activate: () => select.value?.activate?.() })
</script>

<template>
  <div class="repo-select">
    <span v-for="repo in selected" :key="repo.id" class="chip">
      <RouterLink v-if="linkToDetail" :to="`/repositories/${repo.id}`">{{ repo.name }}</RouterLink>
      <template v-else>{{ repo.name }}</template>
      <button type="button" class="chip-x" title="Remove" @click="remove(repo.id)">×</button>
    </span>
    <SearchSelect
      v-if="addOptions.length"
      ref="select"
      variant="inline"
      keep-open
      :model-value="''"
      :options="addOptions"
      :placeholder="placeholder"
      @update:model-value="add"
    />
    <span v-if="!selected.length && !addOptions.length" class="faint">{{ emptyLabel }}</span>
  </div>
</template>
