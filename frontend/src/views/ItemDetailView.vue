<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { sourceLabel, store, timeAgo } from '../store'
import { itemAuthor, itemStatus, parseGithubUrl, personForHandle } from '../repositories'
import EditableText from '../components/EditableText.vue'
import TaskLink from '../components/TaskLink.vue'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()

const item = ref(null)
const loading = ref(true)
const notFound = ref(false)
const refreshing = ref(false)

// Each source gets its own layout: a GitHub issue/PR (state, author, body), a
// Slack thread (a transcript), a plain note, or a fetched link (a Drive doc,
// another URL, a commit, a file). Anything unrecognised falls back to the link
// layout, so a new source still renders.
const variant = computed(() => {
  const source = item.value?.source
  if (source === 'github' || source === 'slack' || source === 'note') return source
  return 'link'
})

const status = computed(() => itemStatus(item.value))
const github = computed(() => parseGithubUrl(item.value?.url))
// "issue" or "pull request", the two GitHub kinds, as a readable label.
const githubKind = computed(() => (github.value?.kind === 'pr' ? 'pull request' : 'issue'))
const repoLabel = computed(() =>
  github.value ? `${github.value.owner}/${github.value.repo}` : String(item.value?.external_id || '')
)
const authorHandle = computed(() => itemAuthor(item.value))
// The directory person behind the item's GitHub author, when one carries the
// login as an alias; null leaves the handle unlinked.
const authorPerson = computed(() => personForHandle(store.people, authorHandle.value))
const openedAt = computed(() => item.value?.metadata_json?.created_at || null)
const mergedAt = computed(() => item.value?.metadata_json?.merged_at || null)

const openLabel = computed(
  () =>
    ({
      github: 'Open on GitHub',
      slack: 'Open in Slack',
      gdrive: 'Open in Drive',
      commit: 'Open commit',
      file: 'Open file'
    })[item.value?.source] || 'Open link'
)

const tasksById = computed(() => Object.fromEntries(store.tasks.map((task) => [task.id, task])))
const linkedTasks = computed(() => (item.value?.task_ids || []).map((id) => tasksById.value[id]).filter(Boolean))
const peopleById = computed(() => Object.fromEntries(store.people.map((person) => [person.id, person])))
const linkedPeople = computed(() => (item.value?.person_ids || []).map((id) => peopleById.value[id]).filter(Boolean))

function formatDateTime(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric' })
}

async function load() {
  loading.value = true
  notFound.value = false
  try {
    item.value = await api.items.get(props.id)
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

async function saveTitle(value) {
  if (!String(value || '').trim()) {
    await load()
    return
  }
  try {
    await api.items.update(props.id, { title: value })
    await load()
  } catch (e) {
    store.notify(e.message, true)
    await load()
  }
}

async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    item.value = await api.items.refresh(props.id)
    store.notify('Refreshed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    refreshing.value = false
  }
}

async function remove() {
  const linked = linkedTasks.value.length
  const message = linked
    ? `Delete this ${sourceLabel(item.value.source)} item? It will also be unlinked from ${linked} task(s).`
    : `Delete this ${sourceLabel(item.value.source)} item?`
  if (!confirm(message)) return
  try {
    await api.items.remove(props.id)
    store.notify('Item deleted')
    router.push('/items')
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(async () => {
  await Promise.all([store.loadTasks().catch(() => {}), store.loadPeople().catch(() => {})])
  await load()
})
</script>

<template>
  <div>
    <router-link class="btn sm ghost" to="/items" style="margin-bottom: 12px">← Resources</router-link>

    <div v-if="loading" class="empty"><span class="spinner"></span></div>
    <div v-else-if="notFound" class="empty">
      Item not found.
      <router-link to="/items">Back to resources</router-link>
    </div>

    <template v-else>
      <div class="row page-head task-head">
        <div class="grow">
          <div class="row" style="gap: 6px; align-items: center; flex-wrap: wrap">
            <span class="badge chip-source" :class="`src-${item.source}`">{{ sourceLabel(item.source) }}</span>
            <template v-if="variant === 'github'">
              <span class="badge">{{ githubKind }}</span>
              <span v-if="github?.number" class="faint">#{{ github.number }}</span>
            </template>
            <span v-else-if="item.kind" class="badge">{{ String(item.kind).replace('_', ' ') }}</span>
            <span v-if="status" class="badge" :class="status.className">{{ status.label }}</span>
          </div>
          <EditableText as="h1" class="task-title" :value="item.title" placeholder="Untitled item" @save="saveTitle" />
        </div>
        <div class="row task-actions">
          <a v-if="item.url" class="btn sm ghost" :href="item.url" target="_blank" rel="noopener">{{ openLabel }}</a>
          <button
            class="btn sm ghost"
            :disabled="refreshing"
            aria-label="Refresh this item"
            title="Re-fetch the item from its source"
            @click="refresh"
          >
            <span v-if="refreshing" class="spinner" aria-hidden="true"></span>
            <span v-else aria-hidden="true">↻</span>
            {{ refreshing ? 'Refreshing…' : 'Refresh' }}
          </button>
          <button class="btn sm danger" aria-label="Delete this item" @click="remove">Delete</button>
        </div>
      </div>

      <!-- GitHub issue or pull request: its metadata and body. -->
      <section v-if="variant === 'github'" class="panel">
        <div class="panel-head">
          <h2>{{ githubKind === 'pull request' ? 'Pull request' : 'Issue' }}</h2>
        </div>
        <div class="row" style="gap: 24px; flex-wrap: wrap; margin-bottom: 12px">
          <div v-if="repoLabel" class="field" style="margin-bottom: 0">
            <label>Repository</label>
            <div>{{ repoLabel }}</div>
          </div>
          <div class="field" style="margin-bottom: 0">
            <label>Author</label>
            <div>
              <router-link v-if="authorPerson" :to="`/person/${authorPerson.id}`"> @{{ authorHandle }} </router-link>
              <span v-else-if="authorHandle">@{{ authorHandle }}</span>
              <span v-else class="faint">unknown</span>
            </div>
          </div>
          <div v-if="status" class="field" style="margin-bottom: 0">
            <label>State</label>
            <div>{{ status.label }}</div>
          </div>
          <div v-if="openedAt" class="field" style="margin-bottom: 0">
            <label>Opened</label>
            <div>{{ formatDateTime(openedAt) }}</div>
          </div>
          <div v-if="mergedAt" class="field" style="margin-bottom: 0">
            <label>Merged</label>
            <div>{{ formatDateTime(mergedAt) }}</div>
          </div>
        </div>
        <div v-if="item.content" class="item-body">{{ item.content }}</div>
        <div v-else class="faint">No description stored. Use Refresh to fetch it from GitHub.</div>
      </section>

      <!-- Slack thread: the conversation as a transcript. -->
      <section v-else-if="variant === 'slack'" class="panel">
        <div class="panel-head"><h2>Thread</h2></div>
        <div v-if="item.content" class="item-body slack-thread">{{ item.content }}</div>
        <div v-else class="faint">Nothing fetched yet. Use Refresh to pull the thread from Slack.</div>
      </section>

      <!-- A note: its text is the whole item. -->
      <section v-else-if="variant === 'note'" class="panel">
        <div class="panel-head"><h2>Note</h2></div>
        <div class="item-body">{{ item.content || 'Empty note.' }}</div>
      </section>

      <!-- A fetched link: a Drive doc, another URL, a commit, or a file. -->
      <section v-else class="panel">
        <div class="panel-head">
          <h2>{{ sourceLabel(item.source) }}</h2>
        </div>
        <p v-if="item.url" class="faint" style="word-break: break-all">{{ item.url }}</p>
        <div v-if="item.content" class="item-body">{{ item.content }}</div>
        <div v-else class="faint">Nothing fetched yet. Use Refresh to pull the page.</div>
      </section>

      <div class="grid-2">
        <section class="panel">
          <div class="panel-head"><h2>Links</h2></div>
          <div class="field">
            <label>Tasks</label>
            <div v-if="linkedTasks.length" class="row" style="gap: 6px; flex-wrap: wrap">
              <TaskLink v-for="task in linkedTasks" :key="task.id" :task="task" />
            </div>
            <div v-else class="faint">Not linked to a task.</div>
          </div>
          <div class="field" style="margin-bottom: 0">
            <label>People</label>
            <div v-if="linkedPeople.length" class="row" style="gap: 6px; flex-wrap: wrap">
              <router-link v-for="person in linkedPeople" :key="person.id" class="chip" :to="`/person/${person.id}`">
                {{ person.name }}
              </router-link>
            </div>
            <div v-else class="faint">No people linked.</div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head"><h2>Details</h2></div>
          <div class="field">
            <label>Source</label>
            <div>{{ sourceLabel(item.source) }}</div>
          </div>
          <div v-if="item.kind" class="field">
            <label>Kind</label>
            <div>{{ String(item.kind).replace('_', ' ') }}</div>
          </div>
          <div v-if="item.external_id" class="field">
            <label>External id</label>
            <div style="overflow-wrap: anywhere">{{ item.external_id }}</div>
          </div>
          <div class="field">
            <label>Added</label>
            <div>{{ formatDateTime(item.created_at) }}</div>
          </div>
          <div v-if="item.fetched_at" class="field">
            <label>Fetched</label>
            <div>{{ timeAgo(item.fetched_at) }}</div>
          </div>
          <div class="field" style="margin-bottom: 0">
            <label>Updated</label>
            <div>{{ timeAgo(item.updated_at) }}</div>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>
