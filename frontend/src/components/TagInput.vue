<script setup>
import { computed, ref } from 'vue'
import SearchSelect from './SearchSelect.vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  // Existing tags to offer in the picker; accepts ["name"] or [{ name, count }].
  suggestions: { type: Array, default: () => [] },
  placeholder: { type: String, default: '+ add tag' }
})
const emit = defineEmits(['update:modelValue'])

const select = ref(null)

const tags = computed(() => props.modelValue || [])
const suggestionNames = computed(() =>
  props.suggestions.map((s) => (typeof s === 'string' ? s : s.name)).filter(Boolean)
)
// Every existing tag not yet applied feeds the picker, which filters them as the
// user types and also offers to create a tag that does not exist yet.
const addOptions = computed(() =>
  suggestionNames.value.filter((name) => !tags.value.includes(name)).map((name) => ({ value: name, label: name }))
)

function add(name) {
  const value = String(name ?? '').trim()
  if (!value || tags.value.includes(value)) return
  emit('update:modelValue', [...tags.value, value])
}

function remove(name) {
  emit(
    'update:modelValue',
    tags.value.filter((tag) => tag !== name)
  )
}

// Backspace on the picker's empty filter removes the last tag, like an entry
// field would.
function onKeydown(event) {
  const fromFilter = event.target?.classList?.contains('ss-search')
  if (fromFilter && event.key === 'Backspace' && !event.target.value && tags.value.length) {
    remove(tags.value[tags.value.length - 1])
  }
}

// Let a parent (e.g. the command palette) open the tag picker directly.
defineExpose({ activate: () => select.value?.activate?.() })
</script>

<template>
  <div class="tag-input" @keydown="onKeydown">
    <span v-for="tag in tags" :key="tag" class="chip">
      {{ tag }}
      <button class="chip-x" type="button" :aria-label="`Remove tag ${tag}`" @click="remove(tag)">×</button>
    </span>
    <SearchSelect
      ref="select"
      variant="inline"
      keep-open
      creatable
      :model-value="''"
      :options="addOptions"
      :placeholder="placeholder"
      title="Add a tag"
      @update:model-value="add"
    />
  </div>
</template>
