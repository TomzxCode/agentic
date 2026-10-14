<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api'
import { store } from '../store'
import SearchSelect from './SearchSelect.vue'

// The before/after links around a task, shown inline in the task header next to
// the repository and people selectors: the tasks that must come first, and the
// tasks that follow. Both sides can be linked and unlinked from here, and the
// whole set forms the graph the Graph page draws.
const props = defineProps({
  task: { type: Object, required: true },
  // When true, each linked task's title links to its detail page.
  linkToDetail: { type: Boolean, default: false }
})
const emit = defineEmits(['changed'])

const deps = ref({ before: [], after: [] })
const allTasks = ref([])
const busy = ref(false)
const beforeSelect = ref(null)

const linkedIds = computed(() => new Set([...deps.value.before, ...deps.value.after].map((task) => task.id)))

// Tasks that can still be linked: not this one, not already linked either way.
const candidates = computed(() =>
  allTasks.value
    .filter((task) => task.id !== props.task.id && !linkedIds.value.has(task.id))
    .map((task) => ({ value: task.id, label: task.title }))
)

async function load() {
  try {
    const [dependencies, tasks] = await Promise.all([api.tasks.dependencies(props.task.id), api.tasks.list()])
    deps.value = dependencies
    allTasks.value = tasks
  } catch (e) {
    store.notify(e.message, true)
  }
}
onMounted(load)
watch(() => props.task.id, load)

async function link(relatedId, relation) {
  if (!relatedId) return
  busy.value = true
  try {
    deps.value = await api.tasks.addDependency(props.task.id, { related_id: relatedId, relation })
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function unlink(relatedId) {
  busy.value = true
  try {
    await api.tasks.removeDependency(props.task.id, relatedId)
    await load()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

// Let a parent (e.g. the command palette) open the "link a task" dropdown.
defineExpose({ activate: () => beforeSelect.value?.activate?.() })
</script>

<template>
  <div class="dep-select">
    <div class="dep-group">
      <span class="dep-label">before</span>
      <div class="dep-chips">
        <span v-for="linked in deps.before" :key="`b-${linked.id}`" class="chip">
          <RouterLink v-if="linkToDetail" :to="`/task/${linked.id}`">{{ linked.title }}</RouterLink>
          <template v-else>{{ linked.title }}</template>
          <button type="button" class="chip-x" title="Unlink" :disabled="busy" @click="unlink(linked.id)">×</button>
        </span>
        <SearchSelect
          ref="beforeSelect"
          variant="inline"
          keep-open
          :model-value="''"
          :options="candidates"
          placeholder="＋ link…"
          title="Link a task that must be done before this one"
          @update:model-value="(id) => link(id, 'before')"
        />
      </div>
    </div>

    <div class="dep-group">
      <span class="dep-label">after</span>
      <div class="dep-chips">
        <span v-for="linked in deps.after" :key="`a-${linked.id}`" class="chip">
          <RouterLink v-if="linkToDetail" :to="`/task/${linked.id}`">{{ linked.title }}</RouterLink>
          <template v-else>{{ linked.title }}</template>
          <button type="button" class="chip-x" title="Unlink" :disabled="busy" @click="unlink(linked.id)">×</button>
        </span>
        <SearchSelect
          variant="inline"
          keep-open
          :model-value="''"
          :options="candidates"
          placeholder="＋ link…"
          title="Link a task that follows this one"
          @update:model-value="(id) => link(id, 'after')"
        />
      </div>
    </div>
  </div>
</template>
