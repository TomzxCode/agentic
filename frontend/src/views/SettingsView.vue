<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { store } from '../store'

const repoDraft = reactive({ path: '' })
const harnessDraft = reactive({ name: '', command: '', args: '', description: '' })
const loading = ref(true)

async function load() {
  loading.value = true
  await Promise.all([
    store.loadRepositories().catch((e) => store.notify(e.message, true)),
    store.loadHarnesses().catch((e) => store.notify(e.message, true)),
  ])
  loading.value = false
}

async function addRepo() {
  if (!repoDraft.path.trim()) return
  try {
    await api.repositories.create({ path: repoDraft.path.trim() })
    repoDraft.path = ''
    await store.loadRepositories()
  } catch (e) {
    store.notify(e.message, true)
  }
}

async function removeRepo(id) {
  if (!confirm('Remove this repository from Agentic? (No files are deleted.)')) return
  await api.repositories.remove(id)
  await store.loadRepositories()
}

async function addHarness() {
  if (!harnessDraft.name.trim() || !harnessDraft.command.trim()) return
  try {
    await api.harnesses.create({
      name: harnessDraft.name.trim(),
      command: harnessDraft.command.trim(),
      args: harnessDraft.args.split(/\s+/).filter(Boolean),
      description: harnessDraft.description,
    })
    Object.assign(harnessDraft, { name: '', command: '', args: '', description: '' })
    await store.loadHarnesses()
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(load)
</script>

<template>
  <div>
    <h1 style="margin-bottom: 16px">Settings</h1>

    <section class="panel">
      <div class="panel-head"><h2>Repositories</h2></div>
      <p class="faint" style="margin-top: 0">Local git checkouts that problems can create isolated worktrees from.</p>
      <div v-for="r in store.repositories" :key="r.id" class="item">
        <div class="item-top">
          <span class="title">{{ r.name }}</span>
          <span v-if="r.default_branch" class="badge">{{ r.default_branch }}</span>
          <button class="btn sm danger" @click="removeRepo(r.id)">Remove</button>
        </div>
        <div class="faint mono">{{ r.path }}</div>
        <div v-if="r.remote_url" class="faint">{{ r.remote_url }}</div>
      </div>
      <div class="row" style="margin-top: 10px">
        <input v-model="repoDraft.path" class="input grow" placeholder="/absolute/path/to/git/repo" @keyup.enter="addRepo" />
        <button class="btn primary" @click="addRepo">Add repository</button>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head"><h2>Agent harnesses</h2></div>
      <p class="faint" style="margin-top: 0">
        Any ACP-compatible coding agent. OpenCode (`opencode acp`) and pi (`pi-acp`) are preconfigured.
      </p>
      <div v-for="h in store.harnesses" :key="h.id" class="item">
        <div class="item-top">
          <span class="title">{{ h.name }}</span>
          <span class="badge" :class="{ ok: h.available, danger: !h.available }">
            {{ h.available ? 'available' : 'missing' }}
          </span>
        </div>
        <div class="faint mono">{{ h.detail || h.id }}</div>
      </div>
      <div class="row" style="margin-top: 10px">
        <input v-model="harnessDraft.name" class="input grow" placeholder="Name" />
        <input v-model="harnessDraft.command" class="input grow" placeholder="command (e.g. opencode)" />
      </div>
      <div class="row" style="margin-top: 8px">
        <input v-model="harnessDraft.args" class="input grow" placeholder="args (space separated, e.g. acp)" />
        <button class="btn primary" @click="addHarness">Add harness</button>
      </div>
    </section>
  </div>
</template>
