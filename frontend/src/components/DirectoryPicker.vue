<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

const props = defineProps({
  startPath: { type: String, default: '' },
  // Absolute paths already registered as repositories.
  existing: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'add'])

const listing = ref(null)
const loading = ref(false)
const error = ref('')
const hidden = ref(false)
const selected = ref(new Set())
const manual = ref('')

const existingSet = computed(() => new Set(props.existing))
const selectedCount = computed(() => selected.value.size)
const addedHere = computed(
  () => (listing.value?.entries || []).filter((e) => isAdded(e.path)).length,
)
const currentAdded = computed(() => isAdded(listing.value?.path))
const currentLabel = computed(() =>
  currentAdded.value ? '✓ added' : isSelected(listing.value?.path) ? '✓ Select this folder' : 'Select this folder',
)

function isAdded(path) {
  return !!path && existingSet.value.has(path)
}

function isSelected(path) {
  return selected.value.has(path)
}

async function load(path) {
  loading.value = true
  error.value = ''
  try {
    listing.value = await api.fs.list(path || undefined, hidden.value)
    manual.value = listing.value.path
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function toggle(path) {
  if (isAdded(path)) return
  const next = new Set(selected.value)
  next.has(path) ? next.delete(path) : next.add(path)
  selected.value = next
}

function addSelected() {
  emit(
    'add',
    [...selected.value].filter((path) => !isAdded(path)),
  )
}

async function toggleHidden() {
  hidden.value = !hidden.value
  await load(listing.value?.path)
}

function submitManual() {
  if (manual.value.trim()) load(manual.value.trim())
}

onMounted(() => load(props.startPath || undefined))
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal picker">
      <div class="row" style="justify-content: space-between; align-items: center">
        <h1>Choose repository folders</h1>
        <button class="btn sm ghost" @click="emit('close')">✕</button>
      </div>
      <p class="faint" style="margin: 6px 0 10px">
        Browsing the server. Tick one or more folders that are git repositories, then add them.
        Folders already added are marked and cannot be selected again.
      </p>

      <div class="row" style="margin-bottom: 8px">
        <input
          v-model="manual"
          class="input grow mono"
          placeholder="/path/to/folder"
          @keyup.enter="submitManual"
        />
        <button class="btn" @click="submitManual">Go</button>
      </div>

      <div class="row" style="margin-bottom: 8px">
        <button class="btn sm" :disabled="!listing?.parent" @click="load(listing.parent)">↑ Up</button>
        <button
          class="btn sm"
          :class="{ primary: !currentAdded && listing?.is_git && isSelected(listing?.path) }"
          :disabled="!listing?.is_git || currentAdded"
          :title="currentAdded ? 'Already added' : listing?.is_git ? listing.path : 'Current folder is not a git repository'"
          @click="toggle(listing.path)"
        >
          {{ currentLabel }}
        </button>
        <label class="row faint" style="gap: 6px; cursor: pointer">
          <input type="checkbox" :checked="hidden" @change="toggleHidden" /> show hidden
        </label>
        <div class="grow"></div>
        <span v-if="addedHere" class="faint">{{ addedHere }} already added</span>
        <span class="faint">{{ selectedCount }} selected</span>
      </div>

      <div v-if="error" class="badge danger" style="margin-bottom: 8px">{{ error }}</div>

      <div class="picker-list">
        <div v-if="loading" class="empty"><span class="spinner"></span></div>
        <div v-else-if="!listing?.entries.length" class="empty">No sub-folders.</div>
        <template v-else>
          <div
            v-for="entry in listing.entries"
            :key="entry.path"
            class="picker-row"
            :class="{ added: isAdded(entry.path) }"
          >
            <input
              type="checkbox"
              :checked="isSelected(entry.path)"
              :disabled="isAdded(entry.path)"
              :title="isAdded(entry.path) ? 'Already added' : ''"
              @click.stop
              @change="toggle(entry.path)"
            />
            <span class="picker-name" @click="load(entry.path)">{{ entry.name }}</span>
            <span v-if="isAdded(entry.path)" class="badge ok">added</span>
            <span v-else-if="entry.is_git" class="badge run">git</span>
            <button class="btn sm ghost" title="Open" @click="load(entry.path)">open ›</button>
          </div>
        </template>
      </div>

      <div class="row" style="justify-content: flex-end; margin-top: 12px">
        <button class="btn ghost" @click="emit('close')">Cancel</button>
        <button class="btn primary" :disabled="!selectedCount" @click="addSelected">
          Add {{ selectedCount || '' }} folder{{ selectedCount === 1 ? '' : 's' }}
        </button>
      </div>
    </div>
  </div>
</template>
