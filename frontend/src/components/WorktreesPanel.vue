<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { store, timeAgo } from '../store'
import SearchSelect from './SearchSelect.vue'

const props = defineProps({ task: { type: Object, required: true }, repositories: { type: Array, default: () => [] } })
const emit = defineEmits(['changed'])
const busy = ref(false)
const draft = reactive({ repository_id: props.task.repository_ids?.[0] || '', branch: '', base: '' })

const repositoryOptions = computed(() => {
  const ids = props.task.repository_ids || []
  const list = ids.length ? props.repositories.filter((r) => ids.includes(r.id)) : props.repositories
  return [{ value: '', label: 'Select a repository…' }, ...list.map((r) => ({ value: r.id, label: r.name }))]
})

async function create() {
  busy.value = true
  try {
    const body = {}
    if (draft.repository_id) body.repository_id = draft.repository_id
    if (draft.branch) body.branch = draft.branch
    if (draft.base) body.base = draft.base
    await api.worktrees.create(props.task.id, body)
    draft.branch = draft.base = ''
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function remove(id) {
  if (!confirm('Remove this worktree? Uncommitted work in it will be lost.')) return
  try {
    await api.worktrees.remove(props.task.id, id)
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

function copy(path) {
  navigator.clipboard?.writeText(path)
  store.notify('Path copied')
}

// Open the worktree in a configured editor (e.g. vscode://file/{path}).
function editorUrl(worktree) {
  const template = store.settings?.editor_url_template
  if (!template) return ''
  return template.replaceAll('{path}', encodeURI(worktree.path))
}

function openEditor(worktree) {
  const url = editorUrl(worktree)
  if (url) window.open(url, '_blank')
}

onMounted(() => {
  if (!Object.keys(store.settings).length) store.loadSettings().catch(() => {})
})
</script>

<template>
  <section class="panel">
    <div class="panel-head"><h2>Worktrees <span class="faint">{{ task.worktrees?.length || 0 }}</span></h2></div>

    <div v-if="!task.worktrees?.length" class="faint" style="margin-bottom: 12px">
      No worktrees. Create one to give an agent an isolated checkout for this task.
    </div>

    <div v-for="w in task.worktrees" :key="w.id" class="item">
      <div class="item-top">
        <span class="badge" :class="{ ok: w.status === 'active', danger: w.status === 'removed' }">{{ w.status }}</span>
        <span class="mono grow" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap">{{ w.branch }}</span>
        <button v-if="w.status === 'active' && editorUrl(w)" class="btn sm ghost" title="Open in editor" @click="openEditor(w)">✎</button>
        <button class="btn sm ghost" title="Copy path" @click="copy(w.path)">⧉</button>
        <button v-if="w.status === 'active'" class="btn sm danger" @click="remove(w.id)">Remove</button>
      </div>
      <div class="faint mono" style="margin-top: 4px">{{ w.path }}</div>
      <div class="faint">created {{ timeAgo(w.created_at) }}</div>
    </div>

    <div v-if="!task.worktrees?.length" class="field" style="margin-top: 8px">
      <label>Repository</label>
      <SearchSelect v-model="draft.repository_id" :options="repositoryOptions" placeholder="Select a repository…" />
    </div>

    <div class="row" style="margin-top: 10px">
      <input v-model="draft.branch" class="input grow" placeholder="branch (optional, auto-named)" />
      <input v-model="draft.base" class="input grow" placeholder="base (optional)" />
      <button class="btn primary" :disabled="busy || (!task.repository_ids?.length && !draft.repository_id)" @click="create">
        <span v-if="busy" class="spinner"></span> New worktree
      </button>
    </div>
    <p v-if="!task.repository_ids?.length && !repositories.length" class="faint" style="margin-top: 8px">
      Add a <router-link to="/settings">repository</router-link> first.
    </p>
  </section>
</template>
