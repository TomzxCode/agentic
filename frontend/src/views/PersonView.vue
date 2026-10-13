<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { aliasLabel, store } from '../store'
import EditableText from '../components/EditableText.vue'
import SearchSelect from '../components/SearchSelect.vue'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()

const person = ref(null)
const items = ref([])
const loading = ref(true)
const notFound = ref(false)
const newAlias = ref('')

const itemById = computed(() => Object.fromEntries(items.value.map((item) => [item.id, item])))
const taskById = computed(() => Object.fromEntries(store.tasks.map((task) => [task.id, task])))
const aliases = computed(() => person.value?.aliases || [])
// Every other person, offered as a merge target.
const mergeTargets = computed(() =>
  store.people.filter((other) => other.id !== props.id).map((other) => ({ value: other.id, label: other.name }))
)

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

// Rename the person, or change their aliases or notes.
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

async function addAlias() {
  const value = newAlias.value.trim()
  if (!value) return
  if (aliases.value.some((alias) => alias.toLowerCase() === value.toLowerCase())) {
    newAlias.value = ''
    return
  }
  newAlias.value = ''
  await save('aliases', [...aliases.value, value])
}

async function removeAlias(value) {
  await save(
    'aliases',
    aliases.value.filter((alias) => alias !== value)
  )
}

// Fold this person into another: their aliases and links move to the target,
// then this person is deleted. Destructive, so it is confirmed first.
async function mergeInto(targetId) {
  if (!targetId) return
  const into = store.people.find((other) => other.id === targetId)
  const target = into?.name || targetId
  const linked = (person.value?.task_ids?.length || 0) + (person.value?.item_ids?.length || 0)
  if (
    !confirm(
      `Merge ${person.value.name} into ${target}? Their aliases and ${linked} link(s) move to ${target}, and ${person.value.name} is deleted.`
    )
  )
    return
  try {
    await api.people.merge(targetId, props.id)
    await store.loadPeople()
    store.notify(`Merged ${person.value.name} into ${target}`)
    router.push(`/person/${targetId}`)
  } catch (e) {
    store.notify(e.message, true)
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
        <div v-if="!aliases.length" class="faint" style="margin-bottom: 12px">No aliases yet.</div>
        <div v-else class="row" style="gap: 6px; flex-wrap: wrap; margin-bottom: 12px">
          <span v-for="alias in aliases" :key="alias" class="chip">
            {{ aliasLabel(alias) }}
            <button class="chip-x" title="Remove" @click="removeAlias(alias)">✕</button>
          </span>
        </div>
        <div class="row" style="gap: 8px; flex-wrap: wrap">
          <input v-model="newAlias" class="input grow" placeholder="Add a handle or email…" @keyup.enter="addAlias" />
          <button class="btn" :disabled="!newAlias.trim()" @click="addAlias">Add</button>
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

      <section v-if="mergeTargets.length" class="panel">
        <div class="panel-head">
          <h2>Merge</h2>
        </div>
        <div class="faint" style="margin-bottom: 12px">
          Move this person's aliases, tasks, and items into another person, then delete this one.
        </div>
        <SearchSelect
          placeholder="Merge into…"
          title="Merge this person into another"
          :model-value="''"
          :options="mergeTargets"
          @update:model-value="mergeInto"
        />
      </section>
    </template>
  </div>
</template>
