<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { store } from '../store'

defineProps({ repositories: { type: Array, default: () => [] } })
const emit = defineEmits(['changed'])

const draft = reactive({ name: '', description: '', repository_ids: [] })
const editingId = ref('')
const editDraft = reactive({ name: '', description: '', repository_ids: [] })
const busy = ref(false)

function toggle(list, id) {
  const index = list.indexOf(id)
  index === -1 ? list.push(id) : list.splice(index, 1)
}

async function load() {
  await store.loadGroups().catch((e) => store.notify(e.message, true))
}

async function create() {
  if (!draft.name.trim()) return
  busy.value = true
  try {
    await api.groups.create({ ...draft, repository_ids: [...draft.repository_ids] })
    draft.name = draft.description = ''
    draft.repository_ids = []
    await load()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

function startEdit(group) {
  editingId.value = group.id
  editDraft.name = group.name
  editDraft.description = group.description
  editDraft.repository_ids = [...group.repository_ids]
}

async function saveEdit(id) {
  try {
    await api.groups.update(id, { ...editDraft, repository_ids: [...editDraft.repository_ids] })
    editingId.value = ''
    await load()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function remove(id) {
  if (!confirm('Delete this group? Tasks using it keep working, just without a group.')) return
  await api.groups.remove(id)
  await load()
  emit('changed')
}

function repoName(id) {
  return store.repositories.find((r) => r.id === id)?.name || id
}

onMounted(load)
</script>

<template>
  <section class="panel">
    <div class="panel-head"><h2>Repository groups</h2></div>
    <p class="faint" style="margin-top: 0">
      Name a set of repositories. Pick a group on a task so the agent knows those checkouts may
      hold information relevant to it.
    </p>

    <div v-for="group in store.groups" :key="group.id" class="item">
      <template v-if="editingId !== group.id">
        <div class="item-top">
          <span class="title">{{ group.name }}</span>
          <span class="badge">{{ group.repository_ids.length }} repo{{ group.repository_ids.length === 1 ? '' : 's' }}</span>
          <button class="btn sm" @click="startEdit(group)">Edit</button>
          <button class="btn sm danger" @click="remove(group.id)">Remove</button>
        </div>
        <div v-if="group.description" class="faint">{{ group.description }}</div>
        <div class="faint mono">
          {{ group.repository_ids.map(repoName).join(' · ') || 'no repositories yet' }}
        </div>
      </template>

      <template v-else>
        <div class="field"><label>Name</label><input v-model="editDraft.name" class="input" /></div>
        <div class="field"><label>Description</label><input v-model="editDraft.description" class="input" /></div>
        <div class="field">
          <label>Repositories</label>
          <div v-if="!repositories.length" class="faint">Add repositories first.</div>
          <label v-for="repo in repositories" :key="repo.id" class="repo-check">
            <input
              type="checkbox"
              :checked="editDraft.repository_ids.includes(repo.id)"
              @change="toggle(editDraft.repository_ids, repo.id)"
            />
            <span>{{ repo.name }}</span>
          </label>
        </div>
        <div class="row" style="justify-content: flex-end">
          <button class="btn ghost" @click="editingId = ''">Cancel</button>
          <button class="btn primary" @click="saveEdit(group.id)">Save</button>
        </div>
      </template>
    </div>
    <div v-if="!store.groups.length" class="faint" style="margin-bottom: 12px">No groups yet.</div>

    <div style="border-top: 1px solid var(--border); padding-top: 12px; margin-top: 4px">
      <div class="row">
        <input v-model="draft.name" class="input grow" placeholder="Group name (e.g. Checkout frontend)" />
        <input v-model="draft.description" class="input grow" placeholder="Description (optional)" />
      </div>
      <div class="field" style="margin-top: 8px">
        <label>Repositories</label>
        <div v-if="!repositories.length" class="faint">Add repositories above first.</div>
        <label v-for="repo in repositories" :key="repo.id" class="repo-check">
          <input
            type="checkbox"
            :checked="draft.repository_ids.includes(repo.id)"
            @change="toggle(draft.repository_ids, repo.id)"
          />
          <span>{{ repo.name }}</span>
          <span class="faint mono">{{ repo.path }}</span>
        </label>
      </div>
      <div class="row" style="justify-content: flex-end">
        <button class="btn primary" :disabled="busy || !draft.name.trim()" @click="create">
          <span v-if="busy" class="spinner"></span> Add group
        </button>
      </div>
    </div>
  </section>
</template>
