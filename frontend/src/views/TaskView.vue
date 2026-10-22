<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, openTaskStream } from '../api'
import { store } from '../store'
import ContextPanel from '../components/ContextPanel.vue'
import NotesPanel from '../components/NotesPanel.vue'
import ItemsPanel from '../components/ItemsPanel.vue'
import ChangesPanel from '../components/ChangesPanel.vue'
import WorktreesPanel from '../components/WorktreesPanel.vue'
import DependenciesSelect from '../components/DependenciesSelect.vue'
import AgentPanel from '../components/AgentPanel.vue'
import SessionsPanel from '../components/SessionsPanel.vue'
import TimelinePanel from '../components/TimelinePanel.vue'
import SessionLinks from '../components/SessionLinks.vue'
import TaskReviewPanel from '../components/TaskReviewPanel.vue'
import TaskIssuePanel from '../components/TaskIssuePanel.vue'
import EditableText from '../components/EditableText.vue'
import DeadlinePicker from '../components/DeadlinePicker.vue'
import WaitingOnSelect from '../components/WaitingOnSelect.vue'
import SearchSelect from '../components/SearchSelect.vue'
import RepositorySelect from '../components/RepositorySelect.vue'
import PeopleSelect from '../components/PeopleSelect.vue'
import TagInput from '../components/TagInput.vue'
import StatusIcon from '../components/StatusIcon.vue'
import PriorityIcon from '../components/PriorityIcon.vue'
import { taskIssues, taskPullRequests } from '../reviews'

const props = defineProps({ id: { type: String, required: true } })
const emit = defineEmits(['changed'])
const route = useRoute()
const router = useRouter()

const task = ref(null)
const loading = ref(true)
const notFound = ref(false)
// The view mode: the task's own content, or the review queue's row for each
// pull request the task links. It is held in the URL (`?view=pr`) so a link can
// open a task straight in PR mode, as the review queue's task icon does.
const mode = ref('default')
// The description's edit action lives in its panel head, so the head hides it
// while the field is open (a second click would reopen and drop the draft).
const editingDescription = ref(false)
// Picking a repository is only needed when the task does not name exactly one.
const showCreateIssue = ref(false)
const creatingIssue = ref(false)
let closeStream = null

// The pull requests the task is linked to, so PR mode is offered only then.
const linkedPrs = computed(() => taskPullRequests(task.value))
// The GitHub issues the task is linked to, for the issue mode.
const linkedIssues = computed(() => taskIssues(task.value))

// The view modes the switch offers, in order. Each names the title it shows
// when it is available and the hint it shows when it is not.
const MODES = [
  { value: 'default', label: 'Default', title: 'Show the task' },
  {
    value: 'issue',
    label: 'Issue',
    title: 'Show the linked issues and work them through an agent',
    disabledTitle: 'This task is not linked to an issue'
  },
  {
    value: 'pr',
    label: 'PR',
    title: 'Show the pull request review queue for this task',
    disabledTitle: 'This task is not linked to a pull request'
  }
]

function modeAvailable(value) {
  if (value === 'pr') return linkedPrs.value.length > 0
  if (value === 'issue') return linkedIssues.value.length > 0
  return true
}

function modeTitle(entry) {
  return modeAvailable(entry.value) ? entry.title : entry.disabledTitle
}

// Adopt the URL's view (`?view=pr` or `?view=issue`), falling back to the
// default view when the query names a mode the task cannot offer.
function applyViewQuery() {
  const wanted = route.query.view
  mode.value = (wanted === 'pr' || wanted === 'issue') && modeAvailable(wanted) ? wanted : 'default'
}

// Switch view and keep the URL in step, so the mode can be linked to and the
// back button restores it.
function setMode(next) {
  if (!modeAvailable(next)) return
  mode.value = next
  const query = { ...route.query }
  if (next === 'default') delete query.view
  else query.view = next
  router.replace({ query })
}

// Creating a GitHub issue needs a registered repository with a GitHub remote.
const githubRepos = computed(() => store.repositories.filter((r) => (r.remote_url || '').includes('github.com')))
// The task's own GitHub repositories, in the order the task lists them.
const taskGithubRepos = computed(() =>
  (task.value?.repository_ids || []).map((id) => githubRepos.value.find((r) => r.id === id)).filter(Boolean)
)
// What the picker offers: the task's own repositories when it has any, else all
// registered GitHub repositories.
const issueRepos = computed(() => (taskGithubRepos.value.length ? taskGithubRepos.value : githubRepos.value))
const issueRepoOptions = computed(() => issueRepos.value.map((r) => ({ value: r.id, label: r.name })))

// Template refs so the command palette can jump straight to a field.
const titleRef = ref(null)
const descriptionRef = ref(null)
const statusRef = ref(null)
const priorityRef = ref(null)
const deadlineRef = ref(null)
const waitingRef = ref(null)
const snoozeRef = ref(null)
const repositoryRef = ref(null)
const peopleRef = ref(null)
const requesterRef = ref(null)
const dependenciesRef = ref(null)
const tagRef = ref(null)

// The most recent link set on the task, from a run or a recorded session, so the
// header offers the newest way to reopen where the work happened.
const latestLinks = computed(() => {
  const sources = [...(task.value?.runs || []), ...(task.value?.sessions || [])]
    .filter((item) => item.links?.length)
    .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
  return sources[0]?.links || []
})

const STATUS_OPTIONS = [
  { value: 'open', label: 'open', icon: StatusIcon, iconProps: { status: 'open', label: 'open' } },
  {
    value: 'in_progress',
    label: 'in progress',
    icon: StatusIcon,
    iconProps: { status: 'in_progress', label: 'in progress' }
  },
  { value: 'blocked', label: 'blocked', icon: StatusIcon, iconProps: { status: 'blocked', label: 'blocked' } },
  { value: 'done', label: 'done', icon: StatusIcon, iconProps: { status: 'done', label: 'done' } },
  { value: 'archived', label: 'archived', icon: StatusIcon, iconProps: { status: 'archived', label: 'archived' } }
]
const PRIORITY_OPTIONS = [
  { value: 0, label: 'low', icon: PriorityIcon, iconProps: { priority: 0, label: 'low' } },
  { value: 1, label: 'medium', icon: PriorityIcon, iconProps: { priority: 1, label: 'medium' } },
  { value: 2, label: 'high', icon: PriorityIcon, iconProps: { priority: 2, label: 'high' } },
  { value: 3, label: 'urgent', icon: PriorityIcon, iconProps: { priority: 3, label: 'urgent' } }
]
async function load() {
  try {
    task.value = await api.tasks.get(props.id)
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

function subscribe() {
  closeStream?.()
  closeStream = openTaskStream(props.id, (ev) => {
    if (ev.kind !== 'task') return
    load()
    // The timeline links item events to the item's view, so keep the store's
    // items fresh when the task's associations change.
    if (ev.action === 'items_changed') store.loadItems().catch(() => {})
  })
}

// Inline "edit online": each property saves on change, no form.
async function update(field, value) {
  if (field === 'title' && !String(value).trim()) {
    store.notify('Title cannot be empty', true)
    await load()
    return
  }
  try {
    await api.tasks.update(props.id, { [field]: value })
    await load()
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
    await load()
  }
}

async function setRepositories(ids) {
  await update('repository_ids', ids)
}

async function copyId() {
  try {
    await navigator.clipboard.writeText(task.value.id)
    store.notify('Copied task id')
  } catch {
    store.notify('Copy failed', true)
  }
}

async function removeTask() {
  if (!confirm('Delete this task? This cannot be undone.')) return
  await api.tasks.remove(props.id)
  router.push('/')
}

// Create the issue in a named repository, using the task's title and
// description, then link it back so it shows in the task's Items panel.
async function createIssue(repositoryId) {
  if (creatingIssue.value) return
  creatingIssue.value = true
  try {
    const issue = await api.github.createIssue({
      repository_id: repositoryId,
      title: task.value.title,
      body: task.value.description || ''
    })
    showCreateIssue.value = false
    store.notify(`Created GitHub issue #${issue.number}`)
    await api.tasks.associate(props.id, { item: { url: issue.url } })
    await load()
    store.loadItems().catch(() => {})
    emit('changed')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    creatingIssue.value = false
  }
}

// One linked repository creates straight away; zero or several ask which one.
function startCreateIssue() {
  if (taskGithubRepos.value.length === 1) {
    createIssue(taskGithubRepos.value[0].id)
    return
  }
  showCreateIssue.value = true
}

function onChanged() {
  load()
  // Auto-populated people may have joined the directory; keep the panel's picker fresh.
  store.loadPeople().catch(() => {})
  // The timeline links item events to the item's view; keep its lookup fresh.
  store.loadItems().catch(() => {})
  emit('changed')
}

// The description's head action: the field itself keeps its own clicks, so this
// is the way into the editor (as with the palette's Description entry).
function editDescription() {
  descriptionRef.value?.activate?.()
}

// Escape blurs the focused field so its own blur handler runs (committing an
// inline edit, adding a typed tag, …) and the field leaves edit mode.
function blurField() {
  const el = document.activeElement
  if (el && el !== document.body && typeof el.blur === 'function') el.blur()
}

onMounted(async () => {
  // The palette uses this to jump to a task field.
  store.focusField = (field) => {
    const target = {
      title: titleRef,
      description: descriptionRef,
      status: statusRef,
      priority: priorityRef,
      deadline: deadlineRef,
      waiting: waitingRef,
      snooze: snoozeRef,
      repository: repositoryRef,
      people: peopleRef,
      requesters: requesterRef,
      dependencies: dependenciesRef,
      tags: tagRef
    }[field]
    target?.value?.activate?.()
  }
  // Focus-hint mode uses the DOM scan in App; nothing to register here.
  await store.loadHarnesses().catch(() => {})
  await store.loadRepositories().catch(() => {})
  await store.loadPeople().catch(() => {})
  // The timeline resolves item events against the store to link them.
  await store.loadItems().catch(() => {})
  await load()
  applyViewQuery()
  subscribe()
})
onUnmounted(() => {
  store.focusField = null
  store.hintMode = false
  closeStream?.()
})
watch(
  () => props.id,
  async (val) => {
    if (!val) return
    loading.value = true
    notFound.value = false
    // A newly opened task starts in its default view, then adopts the URL's.
    mode.value = 'default'
    await load()
    applyViewQuery()
    subscribe()
  }
)
// A task that loses its last linked pull request or issue falls back to the
// default view, so the switch never shows an empty mode.
watch(
  () => linkedPrs.value.length,
  (count) => {
    if (!count && mode.value === 'pr') setMode('default')
  }
)
watch(
  () => linkedIssues.value.length,
  (count) => {
    if (!count && mode.value === 'issue') setMode('default')
  }
)
// The browser's back and forward buttons move between the modes.
watch(
  () => route.query.view,
  () => applyViewQuery()
)
</script>

<template>
  <div v-if="loading" class="empty"><span class="spinner"></span></div>
  <div v-else-if="notFound" class="empty">Task not found. <router-link to="/">Back</router-link></div>
  <div v-else @keydown.esc="blurField">
    <div class="row page-head task-head">
      <div class="grow">
        <EditableText
          ref="titleRef"
          as="h1"
          class="task-title"
          :value="task.title"
          placeholder="Untitled task"
          @save="(value) => update('title', value)"
        />
      </div>
      <div class="row task-head-tools">
        <div class="view-switch" role="group" aria-label="View mode">
          <button
            v-for="entry in MODES"
            :key="entry.value"
            type="button"
            class="view-switch-btn"
            :class="{ active: mode === entry.value }"
            :aria-pressed="mode === entry.value"
            :disabled="!modeAvailable(entry.value)"
            :title="modeTitle(entry)"
            @click="setMode(entry.value)"
          >
            {{ entry.label }}
          </button>
        </div>
      </div>
      <div class="row task-actions">
        <SessionLinks v-if="latestLinks.length" :links="latestLinks" compact />
        <button
          v-if="githubRepos.length"
          class="btn sm ghost"
          :disabled="creatingIssue"
          title="Create a GitHub issue from this task's title and description"
          @click="startCreateIssue"
        >
          <span v-if="creatingIssue" class="spinner"></span>
          {{ creatingIssue ? 'Creating…' : 'Create GitHub issue' }}
        </button>
        <button class="btn sm ghost" :title="`Copy task id: ${task.id}`" @click="copyId">⧉ Copy ID</button>
        <button class="btn sm danger" @click="removeTask">Delete</button>
      </div>
    </div>

    <TaskIssuePanel v-if="mode === 'issue'" :task="task" :harnesses="store.harnesses" @changed="onChanged" />
    <TaskReviewPanel v-else-if="mode === 'pr'" :task="task" :harnesses="store.harnesses" @changed="onChanged" />

    <template v-else>
      <div v-if="showCreateIssue" class="row create-issue-pick">
        <span class="faint">Create the issue in</span>
        <SearchSelect
          variant="inline"
          :model-value="''"
          :options="issueRepoOptions"
          placeholder="+ choose a repository"
          @update:model-value="createIssue"
        />
        <button class="btn sm ghost" @click="showCreateIssue = false">Cancel</button>
      </div>

      <section class="panel properties" aria-label="Task properties">
        <div class="prop">
          <span class="prop-label">Status</span>
          <SearchSelect
            ref="statusRef"
            variant="inline"
            :model-value="task.status"
            :options="STATUS_OPTIONS"
            :sort="false"
            title="Status"
            @update:model-value="(value) => update('status', value)"
          />
        </div>
        <div class="prop">
          <span class="prop-label">Priority</span>
          <SearchSelect
            ref="priorityRef"
            variant="inline"
            :model-value="task.priority"
            :options="PRIORITY_OPTIONS"
            :sort="false"
            title="Priority"
            @update:model-value="(value) => update('priority', Number(value))"
          />
        </div>
        <div class="prop">
          <span class="prop-label">Deadline</span>
          <DeadlinePicker
            ref="deadlineRef"
            :model-value="task.deadline"
            @update:model-value="(value) => update('deadline', value)"
          />
        </div>
        <div class="prop">
          <span class="prop-label">Waiting on</span>
          <WaitingOnSelect
            ref="waitingRef"
            :model-value="task.waiting_on_person_id"
            :name="task.waiting_on_name"
            :follow-up-at="task.follow_up_at"
            @person="(value) => update('waiting_on_person_id', value)"
            @follow-up="(value) => update('follow_up_at', value)"
          />
        </div>
        <div class="prop">
          <span class="prop-label">Snooze</span>
          <DeadlinePicker
            ref="snoozeRef"
            :model-value="task.snoozed_until"
            title="Snoozed until"
            placeholder="Snooze"
            :show-state="false"
            @update:model-value="(value) => update('snoozed_until', value)"
          />
        </div>
        <div class="prop">
          <span class="prop-label">Tags</span>
          <TagInput
            ref="tagRef"
            :model-value="task.tags || []"
            :suggestions="store.tags"
            placeholder="Add a tag…"
            @update:model-value="(value) => update('tags', value)"
          />
        </div>
        <div class="prop">
          <span class="prop-label">People</span>
          <PeopleSelect ref="peopleRef" :task="task" empty-label="None" link-to-detail @changed="onChanged" />
        </div>
        <div class="prop">
          <span class="prop-label">Requested by</span>
          <PeopleSelect
            ref="requesterRef"
            kind="requesters"
            :task="task"
            empty-label="None"
            link-to-detail
            @changed="onChanged"
          />
        </div>
        <div class="prop">
          <span class="prop-label">Repositories</span>
          <RepositorySelect
            ref="repositoryRef"
            :model-value="task.repository_ids"
            :repositories="store.repositories"
            empty-label="None"
            link-to-detail
            @update:model-value="setRepositories"
          />
        </div>
        <DependenciesSelect ref="dependenciesRef" :task="task" link-to-detail @changed="onChanged" />
      </section>

      <!-- The description and the context gathered for it sit side by side: the
         two things to read first when opening a task. -->
      <div class="grid-even">
        <!-- The description is Markdown (a task imported from a GitHub issue keeps
           its body), rendered with the shared renderer like notes and next steps.
           `as="div"`: the renderer emits block elements, which a <p> cannot hold.
           `edit-trigger="external"`: the body may carry its own controls (a
           collapsible <details> section), which a click on the field would
           otherwise steal; the panel head's button opens the editor instead. -->
        <section class="panel">
          <div class="panel-head">
            <h2>Description</h2>
            <button
              v-if="!editingDescription"
              class="btn sm ghost"
              aria-label="Edit the description"
              @click="editDescription"
            >
              ✎ Edit
            </button>
          </div>
          <EditableText
            ref="descriptionRef"
            class="muted task-description"
            as="div"
            multiline
            markdown
            edit-trigger="external"
            :value="task.description"
            placeholder="Add a description… Use @ to mention a person or an item."
            @editing="editingDescription = $event"
            @save="(value) => update('description', value)"
          />
        </section>
        <ContextPanel :task="task" @changed="onChanged" />
      </div>

      <div class="grid-2">
        <div>
          <NotesPanel :task="task" @changed="onChanged" />
          <AgentPanel :task="task" :harnesses="store.harnesses" @changed="onChanged" />
          <SessionsPanel :task="task" @changed="onChanged" />
          <TimelinePanel :events="task.timeline" :task="task" />
        </div>
        <div>
          <WorktreesPanel :task="task" :repositories="store.repositories" @changed="onChanged" />
          <ItemsPanel :task="task" @changed="onChanged" />
          <ChangesPanel :task="task" @changed="onChanged" />
        </div>
      </div>
    </template>
  </div>
</template>
