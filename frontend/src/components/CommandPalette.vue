<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

const props = defineProps({ items: { type: Array, required: true } })
const emit = defineEmits(['close', 'select'])

const GROUP_ORDER = ['Actions', 'Navigation', 'Tasks']

const query = ref('')
const highlighted = ref(0)
const input = ref(null)

// Rank matches: substring first (earlier = better), then subsequence.
function score(label, q) {
  if (!q) return 0
  const text = label.toLowerCase()
  const index = text.indexOf(q)
  if (index !== -1) return 1000 - index
  let matched = 0
  for (const char of text) {
    if (char === q[matched]) matched += 1
    if (matched === q.length) return 100
  }
  return -1
}

// Bucket matches by group, preserving a fixed section order. Each item carries
// its position in the flat order so keyboard navigation spans the sections.
const grouped = computed(() => {
  const q = query.value.trim().toLowerCase()
  const matched = props.items
    .map((item) => ({ item, s: score(item.label, q) }))
    .filter((entry) => entry.s >= 0)
    .sort((a, b) => b.s - a.s)
    .map((entry) => entry.item)

  const buckets = new Map()
  for (const item of matched) {
    const group = item.group || 'Other'
    if (!buckets.has(group)) buckets.set(group, [])
    buckets.get(group).push(item)
  }
  const order = [
    ...GROUP_ORDER.filter((group) => buckets.has(group)),
    ...[...buckets.keys()].filter((group) => !GROUP_ORDER.includes(group)),
  ]
  let index = 0
  return order.map((group) => ({ group, items: buckets.get(group).map((item) => ({ item, index: index++ })) }))
})

const results = computed(() => grouped.value.flatMap((section) => section.items.map((entry) => entry.item)))

function choose(item) {
  if (!item) return
  emit('select', item)
  emit('close')
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    emit('close')
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    highlighted.value = Math.min(highlighted.value + 1, results.value.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlighted.value = Math.max(highlighted.value - 1, 0)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    choose(results.value[highlighted.value])
  }
}

watch(query, () => (highlighted.value = 0))
onMounted(() => nextTick(() => input.value?.focus()))
</script>

<template>
  <div class="palette-backdrop" @click.self="emit('close')">
    <div class="palette">
      <input
        ref="input"
        v-model="query"
        class="palette-input"
        placeholder="Search tasks and actions…"
        @keydown="onKeydown"
      />
      <div class="palette-list">
        <div v-if="!results.length" class="palette-empty faint">No matches</div>
        <div
          v-for="(section, sectionIndex) in grouped"
          :key="section.group"
          class="palette-group"
          :class="{ divided: sectionIndex > 0 }"
        >
          <div class="palette-group-title">{{ section.group }}</div>
          <button
            v-for="entry in section.items"
            :key="entry.item.id"
            type="button"
            class="palette-item"
            :class="{ active: entry.index === highlighted }"
            @mouseenter="highlighted = entry.index"
            @click="choose(entry.item)"
          >
            <span class="grow">{{ entry.item.label }}</span>
            <span v-if="entry.item.hint" class="faint">{{ entry.item.hint }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
