<script setup>
import { computed, ref, useId } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  // Existing tags to offer as quick picks; accepts ["name"] or [{ name, count }].
  suggestions: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'Add a tag…' },
  // Cap the number of quick-pick chips shown.
  suggestionLimit: { type: Number, default: 6 }
})
const emit = defineEmits(['update:modelValue'])

const draft = ref('')
const input = ref(null)

const tags = computed(() => props.modelValue || [])
const suggestionNames = computed(() =>
  props.suggestions.map((s) => (typeof s === 'string' ? s : s.name)).filter(Boolean)
)
// Every existing tag not yet applied feeds the datalist; the quick-pick chips
// show only the first few so the control stays compact.
const available = computed(() => suggestionNames.value.filter((name) => !tags.value.includes(name)))
const remaining = computed(() => available.value.slice(0, props.suggestionLimit))

function add(name) {
  const value = String(name ?? draft.value ?? '').trim()
  draft.value = ''
  if (!value || tags.value.includes(value)) return
  emit('update:modelValue', [...tags.value, value])
}

function remove(name) {
  emit(
    'update:modelValue',
    tags.value.filter((tag) => tag !== name)
  )
}

function onKeydown(event) {
  if (event.key === 'Enter' || event.key === ',') {
    event.preventDefault()
    add()
  } else if (event.key === 'Backspace' && !draft.value && tags.value.length) {
    remove(tags.value[tags.value.length - 1])
  }
}

// Let a parent (e.g. the command palette) jump straight into adding a tag.
defineExpose({ activate: () => input.value?.focus() })

const listId = `tag-suggestions-${useId()}`
</script>

<template>
  <div class="tag-input">
    <span v-for="tag in tags" :key="tag" class="chip">
      {{ tag }}
      <button class="chip-x" type="button" :aria-label="`Remove tag ${tag}`" @click="remove(tag)">×</button>
    </span>
    <input
      ref="input"
      v-model="draft"
      class="tag-entry"
      :placeholder="tags.length ? 'Add…' : placeholder"
      :list="available.length ? listId : undefined"
      @keydown="onKeydown"
      @blur="draft.trim() && add()"
    />
    <datalist :id="listId">
      <option v-for="name in available" :key="name" :value="name" />
    </datalist>
    <button
      v-for="name in remaining"
      :key="name"
      type="button"
      class="chip chip-add"
      :title="`Add tag ${name}`"
      @click="add(name)"
    >
      + {{ name }}
    </button>
  </div>
</template>
