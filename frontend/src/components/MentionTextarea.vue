<script setup>
import { computed, ref } from 'vue'
import { decodeMentionLinks } from '../mentions'
import { useMentions } from '../composables/useMentions'
import MentionMenu from './MentionMenu.vue'

// A textarea that completes people and items when an @ mention is typed. It
// writes the reference as plain `@name` text, so the editor keeps showing what
// the field stores; the Markdown renderer links it when the value is displayed.
// Every other attribute, such as its class and placeholder, stays on the
// textarea itself.
defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue', 'keydown', 'blur'])

const text = computed({
  // A link saved by an earlier build edits as its plain `@name`.
  get: () => decodeMentionLinks(props.modelValue ?? ''),
  set: (value) => emit('update:modelValue', value)
})
const input = ref(null)
const {
  open: mentionOpen,
  options: mentionOptions,
  highlighted: mentionHighlighted,
  onInput: onMentionInput,
  onClick: onMentionClick,
  onKeydown: onMentionKeydown,
  choose: chooseMention
} = useMentions({ value: text, input })

// The field's own handlers still see every key the picker did not take.
function onKeydown(event) {
  if (onMentionKeydown(event)) return
  emit('keydown', event)
}
</script>

<template>
  <div class="mention-field">
    <textarea
      ref="input"
      v-model="text"
      v-bind="$attrs"
      @input="onMentionInput"
      @click="onMentionClick"
      @keydown="onKeydown"
      @blur="emit('blur', $event)"
    ></textarea>
    <MentionMenu
      v-if="mentionOpen"
      :options="mentionOptions"
      :highlighted="mentionHighlighted"
      @choose="chooseMention"
      @update:highlighted="mentionHighlighted = $event"
    />
  </div>
</template>
