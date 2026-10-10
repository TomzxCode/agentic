<script setup>
import { reactive, ref } from 'vue'
import { api } from '../api'
import { store, timeAgo } from '../store'

const props = defineProps({ problem: { type: Object, required: true }, repositories: { type: Array, default: () => [] } })
const emit = defineEmits(['changed'])
const busy = ref(false)
const draft = reactive({ repository_id: '', branch: '', base: '' })

async function create() {
  busy.value = true
  try {
    const body = {}
    if (draft.repository_id) body.repository_id = draft.repository_id
    if (draft.branch) body.branch = draft.branch
    if (draft.base) body.base = draft.base
    await api.worktrees.create(props.problem.id, body)
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
    await api.worktrees.remove(props.problem.id, id)
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  }
}

function copy(path) {
  navigator.clipboard?.writeText(path)
  store.notify('Path copied')
}
</script>

<template>
  <section class="panel">
    <div class="panel-head"><h2>Worktrees <span class="faint">{{ problem.worktrees?.length || 0 }}</span></h2></div>

    <div v-if="!problem.worktrees?.length" class="faint" style="margin-bottom: 12px">
      No worktrees. Create one to give an agent an isolated checkout for this problem.
    </div>

    <div v-for="w in problem.worktrees" :key="w.id" class="item">
      <div class="item-top">
        <span class="badge" :class="{ ok: w.status === 'active', danger: w.status === 'removed' }">{{ w.status }}</span>
        <span class="mono grow" style="overflow: hidden; text-overflow: ellipsis">{{ w.branch }}</span>
        <button class="btn sm ghost" title="Copy path" @click="copy(w.path)">⧉</button>
        <button v-if="w.status === 'active'" class="btn sm danger" @click="remove(w.id)">Remove</button>
      </div>
      <div class="faint mono" style="margin-top: 4px">{{ w.path }}</div>
      <div class="faint">created {{ timeAgo(w.created_at) }}</div>
    </div>

    <div v-if="!problem.repository_id && !problem.worktrees?.length" class="field" style="margin-top: 8px">
      <label>Repository</label>
      <select v-model="draft.repository_id" class="select">
        <option value="">Select a repository…</option>
        <option v-for="r in repositories" :key="r.id" :value="r.id">{{ r.name }} ({{ r.path }})</option>
      </select>
    </div>

    <div class="row" style="margin-top: 10px">
      <input v-model="draft.branch" class="input grow" placeholder="branch (optional, auto-named)" />
      <input v-model="draft.base" class="input grow" placeholder="base (optional)" />
      <button class="btn primary" :disabled="busy || (!problem.repository_id && !draft.repository_id)" @click="create">
        <span v-if="busy" class="spinner"></span> New worktree
      </button>
    </div>
    <p v-if="!problem.repository_id && !repositories.length" class="faint" style="margin-top: 8px">
      Add a <router-link to="/settings">repository</router-link> first.
    </p>
  </section>
</template>
