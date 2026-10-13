<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { store } from '../store'
import EditableText from '../components/EditableText.vue'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()

const person = ref(null)
const items = ref([])
const loading = ref(true)
const notFound = ref(false)

const itemById = computed(() => Object.fromEntries(items.value.map((item) => [item.id, item])))
const taskById = computed(() => Object.fromEntries(store.tasks.map((task) => [task.id, task])))

function taskTitle(id) {
  return taskById.value[id]?.title || id
}

function itemTitle(id) {
  const item = itemById.value[id]
  return item ? item.title || item.url || id : id
}

async function load() {
  loading.value = true
  try {
    person.value = await api.people.get(props.id)
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

// Rename the person, or change one of their aliases (handle, email) or notes.
async function save(field, value) {
  if (field === 'name' && !String(value).trim()) {
    await load()
    return
  }
  try {
    await api.people.update(props.id, { [field]: value })
    await store.loadPeople()
    await load()
  } catch (e) {
    store.notify(e.message, true)
    await load()
  }
}

async function remove() {
  const linked = (person.value?.task_ids?.length || 0) + (person.value?.item_ids?.length || 0)
  const message = linked
    ? `Delete ${person.value.name}? They will be unlinked from ${linked} task(s)/item(s).`
    : `Delete ${person.value.name}?`
  if (!confirm(message)) return
  try {
    await api.people.remove(props.id)
    await store.loadPeople()
    store.notify('Person deleted')
    router.push('/people')
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(async () => {
  await store.loadTasks().catch(() => {})
  await store.loadPeople().catch(() => {})
  try {
    items.value = await api.items.list()
  } catch (e) {
    store.notify(e.message, true)
  }
  await load()
})
</script>

<template>
  <div>
    <router-link class="btn sm ghost" to="/people" style="margin-bottom: 12px">← People</router-link>

    <div v-if="loading" class="empty"><span class="spinner"></span></div>
    <div v-else-if="notFound" class="empty">
      Person not found.
      <router-link to="/people">Back to people</router-link>
    </div>
    <template v-else>
      <div class="row" style="justify-content: space-between; align-items: baseline; margin-bottom: 12px">
        <h1 style="margin: 0">
          <EditableText
            class="title"
            :value="person.name"
            placeholder="Unnamed person"
            @save="(value) => save('name', value)"
          />
        </h1>
        <button class="btn sm danger" title="Delete" @click="remove">Delete</button>
      </div>

      <section class="panel">
        <div class="panel-head">
          <h2>Aliases</h2>
        </div>
        <div class="field">
          <label>Handle</label>
          <EditableText :value="person.handle || ''" placeholder="No handle" @save="(value) => save('handle', value)" />
        </div>
        <div class="field" style="margin-bottom: 0">
          <label>Email</label>
          <EditableText :value="person.email || ''" placeholder="No email" @save="(value) => save('email', value)" />
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Notes</h2>
        </div>
        <EditableText
          multiline
          :value="person.notes || ''"
          placeholder="No notes"
          @save="(value) => save('notes', value)"
        />
      </section>

      <section class="panel">
        <div class="panel-head">
          <h2>Relationships</h2>
        </div>
        <div v-if="!person.task_ids?.length && !person.item_ids?.length" class="faint">
          Not linked to any task or item.
        </div>
        <template v-else>
          <div v-if="person.task_ids?.length" class="field" :style="person.item_ids?.length ? '' : 'margin-bottom: 0'">
            <label>Tasks</label>
            <div class="row" style="gap: 6px; flex-wrap: wrap">
              <button
                v-for="taskId in person.task_ids"
                :key="`t-${taskId}`"
                class="btn sm ghost"
                @click="router.push(`/task/${taskId}`)"
              >
                {{ taskTitle(taskId) }}
              </button>
            </div>
          </div>
          <div v-if="person.item_ids?.length" class="field" style="margin-bottom: 0">
            <label>Items</label>
            <div class="row" style="gap: 6px; flex-wrap: wrap">
              <button
                v-for="itemId in person.item_ids"
                :key="`i-${itemId}`"
                class="btn sm ghost"
                @click="router.push('/items')"
              >
                {{ itemTitle(itemId) }}
              </button>
            </div>
          </div>
        </template>
      </section>
    </template>
  </div>
</template>
