<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { formatDateTime, sourceLabel, store, timeAgo } from '../store'
import { itemAuthor, itemStatus, parseGithubUrl, personLink } from '../repositories/parse'
import { renderMarkdown } from '../markdown'
import { groupReviewFiles, reviewLabel, stripReportMarker } from '../reviews'
import EditableText from '../components/EditableText.vue'
import ItemToolLinks from '../components/ItemToolLinks.vue'
import PullRequestReviewers from '../components/PullRequestReviewers.vue'
import TaskLink from '../components/TaskLink.vue'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()

const item = ref(null)
const loading = ref(true)
const notFound = ref(false)
const refreshing = ref(false)
const resettingTitle = ref(false)
const togglingDone = ref(false)

// The Markdown review reports the review skills wrote for this PR, read from
// the user-global ~/.sdlc store. The list is loaded once; picking a report
// fetches its content.
const reviewFiles = ref([])
const reviewPath = ref(null)
const selectedReview = ref(null)
const reviewContent = ref(null)
const reviewTruncated = ref(false)
const reviewLoading = ref(false)

// The reports of one reviewed commit belong together, so the list is grouped by
// the commit in each report's name.
const reviewGroups = computed(() => groupReviewFiles(reviewFiles.value))
// The selected report's Markdown, without its leading marker comment, rendered
// to HTML.
const reviewHtml = computed(() => renderMarkdown(stripReportMarker(reviewContent.value)))

// A GitHub issue or PR description is Markdown, rendered the same way as a
// review report: raw HTML is allowed by the renderer, then sanitized.
const githubHtml = computed(() => renderMarkdown(item.value?.content))

// Each source gets its own layout: a GitHub issue/PR (state, author, body), a
// Slack thread (a transcript), a plain note, or a fetched link (a Drive doc,
// another URL, a commit, a file). Anything unrecognised falls back to the link
// layout, so a new source still renders.
const variant = computed(() => {
  const source = item.value?.source
  if (source === 'github' || source === 'slack' || source === 'note') return source
  if (source === 'file') return 'path'
  return 'link'
})

const status = computed(() => itemStatus(item.value))
// A note has no source to re-fetch from and no author, so its view offers no
// Refresh and no People field.
const isNote = computed(() => item.value?.source === 'note')
// A local path has no author, so its view offers no People field.
const isPath = computed(() => item.value?.source === 'file')
const itemPath = computed(() => item.value?.metadata_json?.path || '')
const pathKind = computed(() => item.value?.kind || item.value?.metadata_json?.kind || 'path')
// The file preview or directory listing, read from disk when the page opens.
// It is never stored on the item, so it reflects the path as it is now.
const pathPreview = ref(null)
const pathPreviewLoading = ref(false)
const pathPreviewError = ref(null)
const pathSize = computed(() => pathPreview.value?.size ?? item.value?.metadata_json?.size ?? null)
const pathModifiedAt = computed(() => pathPreview.value?.modified_at || item.value?.metadata_json?.modified_at || null)
const pathExists = computed(() =>
  pathPreview.value ? pathPreview.value.exists : item.value?.metadata_json?.exists !== false
)
// A Markdown file is rendered, the same as a GitHub body or a review report.
const pathIsMarkdown = computed(() => /\.(md|markdown|mdx)$/i.test(pathPreview.value?.path || itemPath.value))
const pathPreviewHtml = computed(() => renderMarkdown(pathPreview.value?.content))
// Open the path in a configured editor (e.g. vscode://file/{path}).
const editorUrl = computed(() => {
  const template = store.settings?.editor_url_template
  return itemPath.value && template ? template.replaceAll('{path}', encodeURI(itemPath.value)) : ''
})
const github = computed(() => parseGithubUrl(item.value?.url))
// "issue" or "pull request", the two GitHub kinds, as a readable label.
const githubKind = computed(() => (github.value?.kind === 'pr' ? 'pull request' : 'issue'))
const isPullRequest = computed(() => github.value?.kind === 'pr')
const repoLabel = computed(() =>
  github.value ? `${github.value.owner}/${github.value.repo}` : String(item.value?.external_id || '')
)
const authorHandle = computed(() => itemAuthor(item.value))
// Where the item's GitHub author links: the directory person carrying the login
// as an alias, or the prefilled person-creation page when nobody does yet
// (rendered grey). Null when the item names no author.
const authorLink = computed(() => personLink(store.people, authorHandle.value))
const openedAt = computed(() => item.value?.metadata_json?.created_at || null)
const mergedAt = computed(() => item.value?.metadata_json?.merged_at || null)

const openLabel = computed(
  () =>
    ({
      github: 'Open on GitHub',
      slack: 'Open in Slack',
      gdrive: 'Open in Drive',
      commit: 'Open commit',
      file: 'Open path'
    })[item.value?.source] || 'Open link'
)

function formatBytes(value) {
  if (value === null || value === undefined) return ''
  const units = ['B', 'KB', 'MB', 'GB']
  let size = Number(value)
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(unit ? 1 : 0)} ${units[unit]}`
}

const tasksById = computed(() => Object.fromEntries(store.tasks.map((task) => [task.id, task])))
const linkedTasks = computed(() => (item.value?.task_ids || []).map((id) => tasksById.value[id]).filter(Boolean))
const peopleById = computed(() => Object.fromEntries(store.people.map((person) => [person.id, person])))
const linkedPeople = computed(() => (item.value?.person_ids || []).map((id) => peopleById.value[id]).filter(Boolean))

async function load() {
  loading.value = true
  notFound.value = false
  pathPreview.value = null
  pathPreviewError.value = null
  try {
    item.value = await api.items.get(props.id)
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

// Read the path from disk for display only. Nothing from this response is
// written back to the item.
async function loadPathPreview() {
  if (!isPath.value) return
  pathPreviewLoading.value = true
  pathPreviewError.value = null
  try {
    pathPreview.value = await api.items.pathPreview(props.id)
    if (pathPreview.value.error) pathPreviewError.value = pathPreview.value.error
  } catch (e) {
    pathPreviewError.value = e.message
  } finally {
    pathPreviewLoading.value = false
  }
}

async function saveTitle(value) {
  // An empty title is not a rejection: it asks for the source's own title back.
  const title = String(value || '').trim() ? value : ''
  try {
    await api.items.update(props.id, { title })
    await load()
  } catch (e) {
    store.notify(e.message, true)
    await load()
  }
}

// The title a first fetch would have produced, for an item whose title was edited.
async function resetTitle() {
  if (resettingTitle.value) return
  resettingTitle.value = true
  try {
    await api.items.update(props.id, { title: '' })
    await load()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    resettingTitle.value = false
  }
}

async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    item.value = await api.items.refresh(props.id)
    store.notifyRefresh(item.value)
    await loadPathPreview()
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    refreshing.value = false
  }
}

// Marking a Slack conversation done keeps it done when a reply arrives; the
// page flags the reply instead. Reopening clears the done state.
async function toggleDone() {
  if (togglingDone.value) return
  togglingDone.value = true
  try {
    item.value = await api.items.update(props.id, { done: !item.value.done })
    store.notify(item.value.done ? 'Marked done' : 'Reopened')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    togglingDone.value = false
  }
}

async function loadReviews() {
  reviewFiles.value = []
  reviewPath.value = null
  selectedReview.value = null
  reviewContent.value = null
  reviewTruncated.value = false
  if (!isPullRequest.value) return
  try {
    const data = await api.items.reviews(props.id)
    reviewFiles.value = data.files || []
    reviewPath.value = data.path || null
  } catch {
    return
  }
  // Open the most recent report so the section is useful at a glance.
  if (reviewFiles.value.length) await openReview(reviewFiles.value[0].name)
}

async function openReview(name) {
  if (!name) return
  selectedReview.value = name
  reviewLoading.value = true
  reviewContent.value = null
  reviewTruncated.value = false
  try {
    const data = await api.items.review(props.id, name)
    reviewContent.value = data.content
    reviewTruncated.value = !!data.truncated
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    reviewLoading.value = false
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
  await Promise.all([loadReviews(), loadPathPreview()])
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
            <span v-if="item.done" class="badge ok">done</span>
            <span v-if="item.new_since_done" class="badge warn" title="A message arrived after this was marked done"
              >new messages</span
            >
          </div>
          <EditableText as="h1" class="task-title" :value="item.title" placeholder="Untitled item" @save="saveTitle" />
        </div>
        <div class="row task-actions">
          <a v-if="item.url" class="btn sm ghost" :href="item.url" target="_blank" rel="noopener">{{ openLabel }}</a>
          <a v-if="editorUrl" class="btn sm ghost" :href="editorUrl" target="_blank" rel="noopener">Open in editor</a>
          <ItemToolLinks :item="item" />
          <button
            v-if="variant === 'slack'"
            class="btn sm"
            :class="{ ghost: !item.done }"
            :disabled="togglingDone"
            :title="item.done ? 'Reopen this conversation' : 'Mark this conversation done'"
            @click="toggleDone"
          >
            <span v-if="togglingDone" class="spinner" aria-hidden="true"></span>
            {{ item.done ? 'Reopen' : 'Done' }}
          </button>
          <button
            v-if="item.title_custom"
            class="btn sm ghost"
            :disabled="resettingTitle"
            aria-label="Reset this item's title"
            title="Restore the title derived from the source"
            @click="resetTitle"
          >
            <span v-if="resettingTitle" class="spinner" aria-hidden="true"></span>
            <span v-else aria-hidden="true">↺</span>
            {{ resettingTitle ? 'Resetting…' : 'Reset title' }}
          </button>
          <button
            v-if="!isNote"
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
              <router-link v-if="authorLink" :to="authorLink.path" :class="{ faint: authorLink.missing }">
                @{{ authorHandle }}
              </router-link>
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
        <!-- The PR's reviewers, read live from GitHub. The ones still owing a
             review are listed too, since those are the ones to poke. -->
        <PullRequestReviewers v-if="isPullRequest" :item-id="id" />
        <!-- The description is Markdown, rendered with the shared renderer and
             sanitized before it reaches v-html. -->
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div v-if="item.content" class="md" v-html="githubHtml"></div>
        <div v-else class="faint">No description stored. Use Refresh to fetch it from GitHub.</div>
      </section>

      <!-- Slack thread: the conversation as a transcript. -->
      <section v-else-if="variant === 'slack'" class="panel">
        <div class="panel-head"><h2>Thread</h2></div>
        <p v-if="item.new_since_done" class="faint" style="margin-top: 0">
          A message arrived after this conversation was marked done
          <span v-if="item.latest_message_at">(last message {{ timeAgo(item.latest_message_at) }})</span>.
        </p>
        <div v-if="item.content" class="item-body slack-thread">{{ item.content }}</div>
        <div v-else class="faint">Nothing fetched yet. Use Refresh to pull the thread from Slack.</div>
      </section>

      <!-- A note: its text is the whole item. -->
      <section v-else-if="variant === 'note'" class="panel">
        <div class="panel-head"><h2>Note</h2></div>
        <div class="item-body">{{ item.content || 'Empty note.' }}</div>
      </section>

      <!-- A local path: the file's preview or the directory's listing. -->
      <section v-else-if="variant === 'path'" class="panel">
        <div class="panel-head">
          <h2>{{ pathKind === 'directory' ? 'Directory' : pathKind === 'file' ? 'File' : 'Path' }}</h2>
        </div>
        <p class="faint mono" style="margin-top: 0">{{ itemPath || item.external_id }}</p>
        <div class="row" style="gap: 24px; flex-wrap: wrap; margin-bottom: 12px">
          <div v-if="pathSize !== null" class="field" style="margin-bottom: 0">
            <label>Size</label>
            <div>{{ formatBytes(pathSize) }}</div>
          </div>
          <div v-if="pathModifiedAt" class="field" style="margin-bottom: 0">
            <label>Modified</label>
            <div>{{ formatDateTime(pathModifiedAt) }}</div>
          </div>
        </div>
        <p v-if="!pathExists" class="badge danger" style="margin-bottom: 12px">
          This path no longer exists. Use Refresh to check again.
        </p>
        <div v-if="pathPreviewLoading" class="empty"><span class="spinner"></span></div>
        <p v-else-if="pathPreviewError" class="badge danger">{{ pathPreviewError }}</p>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div v-else-if="pathIsMarkdown && pathPreview?.content" class="md path-markdown" v-html="pathPreviewHtml"></div>
        <div v-else-if="pathPreview?.content" class="item-body path-content">{{ pathPreview.content }}</div>
        <div v-else class="faint">Nothing to preview. Open the path in your editor to inspect it.</div>
        <p class="faint" style="margin-bottom: 0">Preview read live from disk, not stored.</p>
      </section>

      <!-- A fetched link: a Drive doc, another URL, or a commit. -->
      <section v-else class="panel">
        <div class="panel-head">
          <h2>{{ sourceLabel(item.source) }}</h2>
        </div>
        <p v-if="item.url" class="faint" style="word-break: break-all">{{ item.url }}</p>
        <div v-if="item.content" class="item-body">{{ item.content }}</div>
        <div v-else class="faint">Nothing fetched yet. Use Refresh to pull the page.</div>
      </section>

      <!-- Review reports: the Markdown the review skills wrote for this PR,
           read from the user-global ~/.sdlc store and grouped by the commit
           each run reviewed. Rendered as Markdown, with the leading marker
           comment stripped and the HTML sanitized before it reaches v-html. -->
      <section v-if="isPullRequest && reviewFiles.length" class="panel">
        <div class="panel-head">
          <h2>Review reports</h2>
          <span class="faint">{{ reviewFiles.length }}</span>
        </div>
        <p v-if="reviewPath" class="faint review-path">{{ reviewPath }}</p>
        <div v-for="group in reviewGroups" :key="group.commit || 'none'" class="review-group">
          <div class="review-group-head">
            <span class="review-commit mono">{{ group.commit || 'No commit' }}</span>
            <span class="faint">{{ group.files.length }} report{{ group.files.length === 1 ? '' : 's' }}</span>
            <span v-if="group.updated_at" class="faint">· {{ timeAgo(group.updated_at) }}</span>
          </div>
          <div class="row review-tabs">
            <button
              v-for="file in group.files"
              :key="file.name"
              class="btn sm"
              :class="{ ghost: selectedReview !== file.name }"
              :title="file.name"
              @click="openReview(file.name)"
            >
              {{ reviewLabel(file) }}
            </button>
          </div>
        </div>
        <div v-if="reviewLoading" class="empty"><span class="spinner"></span></div>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div v-else-if="reviewContent !== null" class="review-content md" v-html="reviewHtml"></div>
        <div v-if="reviewTruncated" class="faint">Showing the first part of a large report.</div>
      </section>

      <div class="grid-2">
        <section class="panel">
          <div class="panel-head"><h2>Links</h2></div>
          <div class="field" :style="isNote ? { marginBottom: 0 } : null">
            <label>Tasks</label>
            <div v-if="linkedTasks.length" class="row" style="gap: 6px; flex-wrap: wrap">
              <TaskLink v-for="task in linkedTasks" :key="task.id" :task="task" />
            </div>
            <div v-else class="faint">Not linked to a task.</div>
          </div>
          <div v-if="!isNote && !isPath" class="field" style="margin-bottom: 0">
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
          <div v-if="itemPath" class="field">
            <label>Path</label>
            <div class="mono" style="overflow-wrap: anywhere">{{ itemPath }}</div>
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
