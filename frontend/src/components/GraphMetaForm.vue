<script setup>
import { computed } from 'vue'

// One graph's settings form (not its definition): name and description. A
// schedule is a trigger node in the definition, edited on the canvas, so the
// graph itself carries no trigger settings. The "new graph" panel and each
// row's settings form are separate instances, so drafts never bleed into each
// other, like the scheduled-task forms.
const props = defineProps({
  modelValue: { type: Object, required: true },
  heading: { type: String, required: true },
  submitLabel: { type: String, required: true },
  saving: { type: Boolean, default: false },
  idPrefix: { type: String, required: true }
})
const emit = defineEmits(['update:modelValue', 'save', 'cancel'])

function field(key) {
  return computed({
    get: () => props.modelValue[key],
    set: (value) => emit('update:modelValue', { ...props.modelValue, [key]: value })
  })
}
const name = field('name')
const description = field('description')
</script>

<template>
  <div class="panel">
    <div class="panel-head">
      <h2>{{ heading }}</h2>
      <button class="btn sm ghost" @click="emit('cancel')">Cancel</button>
    </div>
    <div class="field">
      <label :for="`${idPrefix}-name`">Name</label>
      <input :id="`${idPrefix}-name`" v-model="name" class="input grow" placeholder="Nightly triage" />
    </div>
    <div class="field">
      <label :for="`${idPrefix}-description`">Description</label>
      <input
        :id="`${idPrefix}-description`"
        v-model="description"
        class="input grow"
        placeholder="What this graph does"
      />
    </div>
    <div class="row" style="justify-content: flex-end; margin-top: 8px">
      <button class="btn primary" :disabled="saving" @click="emit('save')">{{ submitLabel }}</button>
    </div>
  </div>
</template>
