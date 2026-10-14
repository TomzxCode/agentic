<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { aliasLabel, SOURCE_ORDER, sourceLabel, store } from '../store'
import EditableText from '../components/EditableText.vue'
import ItemLink from '../components/ItemLink.vue'
import SearchSelect from '../components/SearchSelect.vue'
import TaskLink from '../components/TaskLink.vue'

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
// The person's linked tasks and items, skipping any id that no longer resolves.
const linkedTasks = computed(() => (person.value?.task_ids || []).map((id) => taskById.value[id]).filter(Boolean))
const linkedItems = computed(() => (person.value?.item_ids || []).map((id) => itemById.value[id]).filter(Boolean))

// How this person is attached to each linked task: as one of the people the
// task involves, as its requester, or both. The two sets are separate, so a
// task can carry either or both.
const involvedTaskIds = computed(() => new Set(person.value?.involved_task_ids || []))
const requesterTaskIds = computed(() => new Set(person.value?.requester_task_ids || []))

function taskRoles(taskId) {
  const roles = []
  if (involvedTaskIds.value.has(taskId)) roles.push('people')
  if (requesterTaskIds.value.has(taskId)) roles.push('requested by')
  return roles
}

// The person's linked items grouped by source, in display order, so a long list
// is scannable by type.
const itemGroups = computed(() => {
  const groups = new Map()
  for (const item of linkedItems.value) {
    const source = item.source || 'other'
    if (!groups.has(source)) groups.set(source, [])
    groups.get(source).push(item)
  }
  return [...groups.entries()]
    .map(([source, items]) => ({ source, label: sourceLabel(source), items }))
    .sort((a, b) => {
      const ai = SOURCE_ORDER.indexOf(a.source)
      const bi = SOURCE_ORDER.indexOf(b.source)
      const rank = (i) => (i === -1 ? SOURCE_ORDER.length : i)
      return rank(ai) - rank(bi) || a.label.localeCompare(b.label)
    })
})

// Every other person, offered as a merge target.
const mergeTargets = computed(() =>
  store.people.filter((other) => other.id !== props.id).map((other) => ({ value: other.id, label: other.name }))
)

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
          <div v-if="linkedTasks.length" class="field" :style="linkedItems.length ? '' : 'margin-bottom: 0'">
            <label>Tasks</label>
            <div class="row" style="gap: 6px; flex-wrap: wrap">
              <span v-for="task in linkedTasks" :key="task.id" class="task-role">
                <TaskLink :task="task" />
                <span class="role-label">{{ taskRoles(task.id).join(' · ') }}</span>
              </span>
            </div>
          </div>
          <div v-if="linkedItems.length" class="field" style="margin-bottom: 0">
            <label>Items</label>
            <div v-for="group in itemGroups" :key="group.source" style="margin-bottom: 8px">
              <div :class="`src-${group.source}`" style="font-size: 11px; margin-bottom: 4px">
                {{ group.label }} <span class="faint">{{ group.items.length }}</span>
              </div>
              <div class="row" style="gap: 6px; flex-wrap: wrap">
                <ItemLink v-for="item in group.items" :key="item.id" :item="item" :show-source="false" />
              </div>
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
