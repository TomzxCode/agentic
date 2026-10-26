<script setup>
const props = defineProps({
  options: { type: Array, default: () => [] },
  highlighted: { type: Number, default: 0 }
})
const emit = defineEmits(['choose', 'update:highlighted'])

// Consecutive options of the same kind form a group, since the list always
// carries every person before any item.
function startsGroup(index) {
  return index === 0 || props.options[index].kind !== props.options[index - 1].kind
}

function groupLabel(kind) {
  if (kind === 'person') return 'People'
  if (kind === 'date') return 'Dates'
  return 'Items'
}
</script>

<template>
  <!-- mousedown is prevented so clicking an option never blurs the field and
       commits a half-written value before the mention is inserted. -->
  <div class="mention-panel" role="listbox" aria-label="Mention a person, item, or date" @mousedown.prevent>
    <div v-if="!options.length" class="ss-empty faint">No people, items, or dates match</div>
    <template v-for="(option, index) in options" :key="`${option.kind}-${option.id}`">
      <div v-if="startsGroup(index)" class="mention-group" aria-hidden="true">{{ groupLabel(option.kind) }}</div>
      <button
        type="button"
        class="ss-option mention-option"
        :class="{ active: index === highlighted }"
        role="option"
        :aria-selected="index === highlighted"
        @mouseenter="emit('update:highlighted', index)"
        @click="emit('choose', option)"
      >
        <span class="mention-mark" :class="option.kind" aria-hidden="true">{{
          option.kind === 'item' ? '#' : '@'
        }}</span>
        <span class="ss-option-label">{{ option.label }}</span>
        <span v-if="option.detail" class="mention-detail faint">{{ option.detail }}</span>
      </button>
    </template>
  </div>
</template>
