<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from './api'
import { SETTINGS_SECTIONS } from './settings'
import { store, timeAgo, aliasLabel, sourceLabel } from './store'
import SearchSelect from './components/SearchSelect.vue'
import RepositorySelect from './components/RepositorySelect.vue'
import TagInput from './components/TagInput.vue'
import DeadlinePicker from './components/DeadlinePicker.vue'
import StatusIcon from './components/StatusIcon.vue'
import PriorityIcon from './components/PriorityIcon.vue'
import Icon from './components/Icon.vue'
import CommandPalette from './components/CommandPalette.vue'

const route = useRoute()
const router = useRouter()
const showNew = ref(false)
const sidebarOpen = ref(false)
const paletteOpen = ref(false)
const draft = ref({
  title: '',
  description: '',
  status: 'open',
  priority: 2,
  tags: [],
  deadline: null,
  repository_ids: [],
  group_id: '',
  github_url: '',
  slack_url: ''
})

// "Import from GitHub or Slack" state. One field accepts either source.
const importRepo = ref('')
const issues = ref([])
const loadingIssues = ref(false)
const issueFilter = ref('')
const pickedIssue = ref(null)
const importUrl = ref('')
const importKind = ref('') // '' | 'github' | 'slack'
const loadingIssue = ref(false)
// What a GitHub preview auto-filled, so switching source can undo it.
let importPrefill = { title: '', description: '' }

watch(
  () => route.fullPath,
  () => {
    sidebarOpen.value = false
    store.hintMode = false
  }
)

const GITHUB_ISSUE_RE = /github\.com\/[^/\s]+\/[^/\s]+\/(?:issues|pull)\/\d+/i
const SLACK_URL_RE = /https?:\/\/[^./\s]+\.slack\.com\/archives\/[^/\s]+\/p\d+/i

const githubRepos = computed(() => store.repositories.filter((r) => (r.remote_url || '').includes('github.com')))

const priorityOptions = [
  { value: 0, label: 'Low', icon: PriorityIcon, iconProps: { priority: 0, label: 'Low' } },
  { value: 1, label: 'Medium', icon: PriorityIcon, iconProps: { priority: 1, label: 'Medium' } },
  { value: 2, label: 'High', icon: PriorityIcon, iconProps: { priority: 2, label: 'High' } },
  { value: 3, label: 'Urgent', icon: PriorityIcon, iconProps: { priority: 3, label: 'Urgent' } }
]
const statusOptions = [
  { value: 'open', label: 'Open', icon: StatusIcon, iconProps: { status: 'open', label: 'Open' } },
  {
    value: 'in_progress',
    label: 'In progress',
    icon: StatusIcon,
    iconProps: { status: 'in_progress', label: 'In progress' }
  },
  { value: 'blocked', label: 'Blocked', icon: StatusIcon, iconProps: { status: 'blocked', label: 'Blocked' } },
  { value: 'done', label: 'Done', icon: StatusIcon, iconProps: { status: 'done', label: 'Done' } },
  { value: 'archived', label: 'Archived', icon: StatusIcon, iconProps: { status: 'archived', label: 'Archived' } }
]
// Repositories of the most recently created task, offered as quick picks.
const lastUsedRepositories = computed(() => {
  const last = [...store.tasks].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0]
  if (!last) return []
  return (last.repository_ids || [])
    .filter((id) => !(draft.value.repository_ids || []).includes(id))
    .map((id) => store.repositories.find((r) => r.id === id))
    .filter(Boolean)
    .sort((a, b) => a.name.localeCompare(b.name))
})
const groupOptions = computed(() => [
  { value: '', label: 'None' },
  ...store.groups.map((g) => ({ value: g.id, label: g.name }))
])
// Picking a group fills the repository list with that group's repositories.
watch(
  () => draft.value.group_id,
  (id) => {
    const group = store.groups.find((g) => g.id === id)
    if (group) draft.value.repository_ids = [...(group.repository_ids || [])]
  }
)
const importRepoOptions = computed(() => githubRepos.value.map((r) => ({ value: r.id, label: r.name })))

// The sidebar is for work in flight: hide done and archived tasks.
const sidebarTasks = computed(() => store.tasks.filter((p) => p.status !== 'done' && p.status !== 'archived'))

// Command palette: navigate anywhere (and a couple of actions) from the keyboard.
const taskFieldItems = computed(() =>
  route.name === 'task'
    ? [
        {
          id: 'field-title',
          label: 'Edit title',
          group: 'This task',
          icon: 'title',
          run: () => store.focusField?.('title')
        },
        {
          id: 'field-description',
          label: 'Edit description',
          group: 'This task',
          icon: 'description',
          run: () => store.focusField?.('description')
        },
        {
          id: 'field-status',
          label: 'Set status',
          group: 'This task',
          icon: 'status',
          run: () => store.focusField?.('status')
        },
        {
          id: 'field-priority',
          label: 'Set priority',
          group: 'This task',
          icon: 'priority',
          run: () => store.focusField?.('priority')
        },
        {
          id: 'field-deadline',
          label: 'Set deadline',
          group: 'This task',
          icon: 'deadline',
          run: () => store.focusField?.('deadline')
        },
        {
          id: 'field-repository',
          label: 'Add repository',
          group: 'This task',
          icon: 'repositories',
          run: () => store.focusField?.('repository')
        },
        {
          id: 'field-people',
          label: 'Link a person',
          group: 'This task',
          icon: 'personPlus',
          run: () => store.focusField?.('people')
        },
        {
          id: 'field-requesters',
          label: 'Link a requester',
          group: 'This task',
          icon: 'personCheck',
          run: () => store.focusField?.('requesters')
        },
        {
          id: 'field-dependencies',
          label: 'Link a dependency',
          group: 'This task',
          icon: 'link',
          run: () => store.focusField?.('dependencies')
        },
        {
          id: 'field-tags',
          label: 'Set tags',
          group: 'This task',
          icon: 'tag',
          run: () => store.focusField?.('tags')
        }
      ]
    : []
)

// One palette entry per tag in use: pick it to filter the task list by that tag.
const tagItems = computed(() =>
  store.tags.map((tag) => ({
    id: `tag-${tag.name}`,
    label: `Filter by tag: ${tag.name}`,
    group: 'Tags',
    icon: 'tag',
    hint: store.tagFilter === tag.name ? 'active' : String(tag.count),
    keywords: tag.name,
    run: () => {
      store.tagFilter = tag.name
      router.push('/')
    }
  }))
)

// One palette entry per person: pick it to open that person's page. Aliases are
// shown as the hint and are searchable, so a handle or email finds the person.
const personItems = computed(() =>
  store.people.map((person) => ({
    id: `person-${person.id}`,
    label: person.name,
    group: 'People',
    icon: 'people',
    hint: (person.aliases || []).map(aliasLabel).join(' · ') || undefined,
    keywords: (person.aliases || []).join(' '),
    run: () => router.push(`/person/${person.id}`)
  }))
)

// One palette entry per resource: pick it to open that item's page. The source
// is shown as the hint and is searchable, so "github" or "slack" narrows the
// list.
const itemItems = computed(() =>
  store.items.map((item) => ({
    id: `item-${item.id}`,
    label: item.title || item.url || 'Untitled item',
    group: 'Items',
    icon: 'items',
    hint: sourceLabel(item.source),
    keywords: [item.source, item.kind, item.url].filter(Boolean).join(' '),
    run: () => router.push(`/items/${item.id}`)
  }))
)

// One palette entry per repository: pick it to open that repository's page. Its
// path and remote are searchable, so a directory or "github" narrows the list.
const repositoryItems = computed(() =>
  store.repositories.map((repository) => ({
    id: `repository-${repository.id}`,
    label: repository.name || repository.path,
    group: 'Repositories',
    icon: 'repositories',
    hint: repository.path,
    keywords: [repository.path, repository.remote_url].filter(Boolean).join(' '),
    run: () => router.push(`/repositories/${repository.id}`)
  }))
)

// One palette entry per Settings section: pick it to open that section. The
// group header names Settings, and "settings" is searchable, so the whole list
// appears under that one word.
const settingsItems = computed(() =>
  SETTINGS_SECTIONS.map((section) => ({
    id: `settings-${section.id}`,
    label: section.label,
    group: 'Settings',
    icon: 'settings',
    keywords: `settings ${section.id}`,
    run: () => router.push({ path: '/settings', query: { section: section.id } })
  }))
)

const paletteItems = computed(() => [
  { id: 'new-task', label: 'New task', hint: '⌘N', group: 'Actions', icon: 'plus', run: () => (showNew.value = true) },
  {
    id: 'focus-hints',
    label: 'Show focus hints',
    hint: 'f',
    group: 'Actions',
    icon: 'keyboard',
    run: () => (store.hintMode = true)
  },
  {
    id: 'toggle-sidebar',
    label: sidebarHidden.value ? 'Show task list' : 'Hide task list',
    hint: '⌘B',
    group: 'Actions',
    icon: 'panel',
    keywords: 'sidebar panel collapse',
    run: toggleSidebar
  },
  ...(store.tagFilter
    ? [
        {
          id: 'clear-tag-filter',
          label: `Clear tag filter: ${store.tagFilter}`,
          group: 'Actions',
          icon: 'close',
          run: () => (store.tagFilter = '')
        }
      ]
    : []),
  ...taskFieldItems.value,
  { id: 'go-tasks', label: 'Go to tasks', group: 'Navigation', icon: 'tasks', run: () => router.push('/') },
  { id: 'go-inbox', label: 'Go to inbox', group: 'Navigation', icon: 'inbox', run: () => router.push('/inbox') },
  { id: 'go-stack', label: 'Go to stack', group: 'Navigation', icon: 'stack', run: () => router.push('/stack') },
  { id: 'go-gantt', label: 'Go to gantt', group: 'Navigation', icon: 'gantt', run: () => router.push('/gantt') },
  { id: 'go-graph', label: 'Go to graph', group: 'Navigation', icon: 'graph', run: () => router.push('/graph') },
  {
    id: 'go-metrics',
    label: 'Go to metrics',
    group: 'Navigation',
    icon: 'metrics',
    run: () => router.push('/metrics')
  },
  {
    id: 'go-items',
    label: 'Go to resources',
    group: 'Navigation',
    icon: 'items',
    run: () => router.push('/items')
  },
  { id: 'go-people', label: 'Go to people', group: 'Navigation', icon: 'people', run: () => router.push('/people') },
  {
    id: 'go-repositories',
    label: 'Go to repositories',
    group: 'Navigation',
    icon: 'repositories',
    run: () => router.push('/repositories')
  },
  {
    id: 'go-settings',
    label: 'Go to settings',
    group: 'Navigation',
    icon: 'settings',
    run: () => router.push('/settings')
  },
  ...tagItems.value,
  ...store.tasks.map((task) => ({
    id: `task-${task.id}`,
    label: task.title,
    group: 'Tasks',
    icon: 'tasks',
    hint: [task.status.replace('_', ' '), ...(task.tags || []).map((tag) => `#${tag}`)].join(' '),
    keywords: (task.tags || []).join(' '),
    run: () => router.push(`/task/${task.id}`)
  })),
  ...itemItems.value,
  ...repositoryItems.value,
  ...settingsItems.value,
  ...personItems.value
])

function runPaletteItem(item) {
  item.run?.()
}

function isTyping(target) {
  return !!target && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)
}

// Focus-hint mode: press f, then the letter over a control, to focus it. The
// targets are scanned from the page so every field/button is covered.
const HINT_SELECTOR = 'a[href], button, input, textarea, select, [tabindex]:not([tabindex="-1"])'
const hintBadges = ref([])
let hintTargets = []
let hintBuffer = ''
let hintCleanup = null

function hintLabelFor(index) {
  const alphabet = 'abcdefghijklmnopqrstuvwxyz'
  if (index < alphabet.length) return alphabet[index]
  const rest = index - alphabet.length
  return alphabet[Math.floor(rest / alphabet.length)] + alphabet[rest % alphabet.length]
}

// Dim the badges whose label does not start with what has been typed so far.
function updateHintMatches() {
  hintTargets.forEach((target, index) => {
    const badge = hintBadges.value[index]
    if (badge) badge.dimmed = hintBuffer !== '' && !target.key.startsWith(hintBuffer)
  })
}

function focusHint(target) {
  target.el.focus()
  store.hintMode = false
}

function positionHints() {
  hintTargets.forEach((target, index) => {
    const badge = hintBadges.value[index]
    if (!badge) return
    const rect = target.el.getBoundingClientRect()
    badge.left = rect.left
    badge.top = rect.top
    badge.hidden = rect.width === 0 && rect.height === 0
  })
}

function stopHints() {
  hintCleanup?.()
  hintCleanup = null
  hintTargets = []
  hintBadges.value = []
  hintBuffer = ''
}

function startHints() {
  stopHints()
  const container = document.querySelector('.main')
  if (!container) return
  const nodes = Array.from(container.querySelectorAll(HINT_SELECTOR)).filter(
    // Skip the agent transcript and controls that opt out (the sidebar toggle).
    (el) => !el.disabled && !el.closest('.transcript') && !el.hasAttribute('data-no-hint')
  )
  hintTargets = nodes.map((el, index) => ({ key: hintLabelFor(index), el }))
  hintBadges.value = hintTargets.map(({ key }) => ({ key, left: 0, top: 0, hidden: false, dimmed: false }))
  positionHints()
  window.addEventListener('scroll', positionHints, true)
  window.addEventListener('resize', positionHints)
  hintCleanup = () => {
    window.removeEventListener('scroll', positionHints, true)
    window.removeEventListener('resize', positionHints)
  }
}

function onGlobalKeydown(event) {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    paletteOpen.value = !paletteOpen.value
    return
  }

  // Cmd/Ctrl+B hides or shows the sidebar (Shift is left to the browser).
  if ((event.metaKey || event.ctrlKey) && !event.shiftKey && event.key.toLowerCase() === 'b') {
    event.preventDefault()
    toggleSidebar()
    return
  }

  // Cmd/Ctrl+N opens the new-task modal (and must beat the browser's own).
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'n') {
    event.preventDefault()
    showNew.value = true
    return
  }

  if (store.hintMode) {
    if (event.key === 'Escape') {
      event.preventDefault()
      store.hintMode = false
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const exact = hintTargets.find((target) => target.key === hintBuffer)
      if (exact) focusHint(exact)
      return
    }
    if (event.key === 'Backspace') {
      event.preventDefault()
      hintBuffer = hintBuffer.slice(0, -1)
      updateHintMatches()
      return
    }
    const char = event.key.toLowerCase()
    if (/^[a-z]$/.test(char)) {
      event.preventDefault()
      const next = hintBuffer + char
      const matches = hintTargets.filter((target) => target.key.startsWith(next))
      if (matches.length === 1) {
        focusHint(matches[0])
      } else {
        hintBuffer = matches.length === 0 ? '' : next
        updateHintMatches()
      }
    }
    return
  }

  if (event.key === 'Escape') {
    if (paletteOpen.value) paletteOpen.value = false
    else if (showNew.value) showNew.value = false
    return
  }

  if (
    event.key.toLowerCase() === 'f' &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.altKey &&
    !isTyping(event.target) &&
    !paletteOpen.value &&
    !showNew.value &&
    document.querySelector('.main')?.querySelector(`:is(${HINT_SELECTOR}):not([data-no-hint])`)
  ) {
    event.preventDefault()
    store.hintMode = true
  }
}

watch(
  () => store.hintMode,
  (on) => (on ? startHints() : stopHints())
)

// Newest issues first (by number), with a text filter.
const sortedIssues = computed(() => {
  const q = issueFilter.value.trim().toLowerCase()
  const list = [...issues.value].sort((a, b) => (b.number ?? 0) - (a.number ?? 0))
  if (!q) return list
  return list.filter((i) => i.title.toLowerCase().includes(q) || String(i.number).includes(q))
})

async function refresh() {
  store.loading = true
  try {
    await store.loadTasks()
    await store.loadTags()
    // The inbox badge in the nav tracks the same state the tasks do.
    await store.loadInbox().catch(() => {})
    // Drop a filter whose tag no longer exists on any task.
    if (store.tagFilter && !store.tags.some((tag) => tag.name === store.tagFilter)) store.tagFilter = ''
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    store.loading = false
  }
}

function resetDraft() {
  draft.value = {
    title: '',
    description: '',
    status: 'open',
    priority: 2,
    tags: [],
    deadline: null,
    repository_ids: [],
    group_id: '',
    github_url: '',
    slack_url: ''
  }
  importRepo.value = ''
  issues.value = []
  issueFilter.value = ''
  pickedIssue.value = null
  importUrl.value = ''
  importKind.value = ''
  importPrefill = { title: '', description: '' }
}

function addRepository(id) {
  if (!id) return
  draft.value.repository_ids = [...draft.value.repository_ids, id]
}

// Change a task's status straight from the sidebar list.
async function changeStatus(task, status) {
  if (status === task.status) return
  const previous = task.status
  task.status = status
  try {
    await api.tasks.update(task.id, { status })
  } catch (e) {
    task.status = previous
    store.notify(e.message, true)
  }
}

// --- Sidebar drawer swipe ---------------------------------------------------
// Below 760px the sidebar is an off-canvas drawer. Swiping right opens it and
// swiping left while it is open closes it. An opening swipe is not restricted to
// the screen edge: Android's own back gesture owns the outer few millimetres of
// the edge and swallows a swipe that starts there, so the gesture starts
// anywhere the page does not already use a sideways drag. Plain touch events,
// never preventDefault, so vertical scrolling is untouched.
const SIDEBAR_LOCK_PX = 12 // horizontal travel that claims the gesture
const SIDEBAR_FLICK_MS = 250 // a quick swipe this short still commits
const SIDEBAR_FLICK_PX = 24
// While a swipe is in flight this is how far the drawer has been dragged
// (0 closed, 1 open). It is null the rest of the time, when CSS owns the
// transform; dragging holds the release back one frame so the transition runs.
const sidebarDrag = ref(null)
const sidebarDragging = ref(false)
const sidebarDragStyle = computed(() =>
  sidebarDrag.value === null ? null : { transform: `translateX(${(sidebarDrag.value - 1) * 100}%)` }
)
let swipe = null
let swipeSeq = 0

// A sideways swipe that starts on a strip that scrolls sideways belongs to that
// strip, and one that starts in a text field belongs to the caret. `.main` is
// the page scroller itself, so it is never treated as a sideways strip.
function gestureIsOwned(target) {
  if (!(target instanceof Element)) return false
  if (target.closest('input, textarea, [contenteditable]')) return true
  for (let node = target; node instanceof Element; node = node.parentElement) {
    if (node.classList.contains('main')) return false
    if (node.scrollWidth > node.clientWidth + 1) return true
  }
  return false
}

function beginSwipe(event) {
  // Only on the mobile layout, one finger, and never under a modal or palette.
  if (window.innerWidth > 760 || event.touches.length !== 1) return
  if (showNew.value || paletteOpen.value) return
  const opening = !sidebarOpen.value
  if (opening && gestureIsOwned(event.target)) return
  const touch = event.touches[0]
  swipe = {
    seq: ++swipeSeq,
    startX: touch.clientX,
    startY: touch.clientY,
    startTime: Date.now(),
    width: Math.max(window.innerWidth, 1),
    opening,
    decided: false,
    dx: 0,
    progress: opening ? 0 : 1
  }
}

function moveSwipe(event) {
  if (!swipe || event.touches.length !== 1) return
  const touch = event.touches[0]
  const dx = touch.clientX - swipe.startX
  const dy = touch.clientY - swipe.startY
  if (!swipe.decided) {
    // Wait until the finger has committed to a horizontal swipe in the useful
    // direction. Touch sampling drifts sideways early on, so one sideways
    // sample must not kill the gesture; only a drag whose sideways travel keeps
    // up with its horizontal travel (a page scroll) is left alone.
    const along = swipe.opening ? dx : -dx
    if (along < SIDEBAR_LOCK_PX || Math.abs(dy) >= along) return
    swipe.decided = true
    sidebarDragging.value = true
  }
  swipe.dx = dx
  const raw = swipe.opening ? dx / swipe.width : 1 + dx / swipe.width
  swipe.progress = Math.min(1, Math.max(0, raw))
  sidebarDrag.value = swipe.progress
}

function endSwipe() {
  if (!swipe) return
  const gesture = swipe
  swipe = null
  if (!gesture.decided) return
  const flick = Date.now() - gesture.startTime < SIDEBAR_FLICK_MS && Math.abs(gesture.dx) >= SIDEBAR_FLICK_PX
  const committed = flick || (gesture.opening ? gesture.progress > 0.5 : gesture.progress < 0.5)
  sidebarOpen.value = gesture.opening ? committed : !committed
  releaseDrawer(gesture.seq)
}

function cancelSwipe() {
  if (!swipe) return
  const seq = swipe.seq
  swipe = null
  releaseDrawer(seq)
}

// Let the drawer render at the released position with the transition back on,
// then hand it back to CSS, so it eases from where the finger let go instead of
// snapping.
function releaseDrawer(seq) {
  sidebarDragging.value = false
  requestAnimationFrame(() => {
    if (swipeSeq === seq) sidebarDrag.value = null
  })
}

// --- Sidebar resize (desktop) ----------------------------------------------
// On desktop the sidebar is a grid column of its own. A handle on its right
// edge drags that column between a floor that keeps the list readable and a
// ceiling that leaves the page usable. Width is a per-device preference, so it
// is kept in localStorage rather than on the server.
const SIDEBAR_DEFAULT_PX = 300
// The floor keeps the Search / New task row and the nav icon row intact.
const SIDEBAR_MIN_PX = 260
const SIDEBAR_MAX_PX = 560
const SIDEBAR_WIDTH_KEY = 'agentic.sidebarWidth'
const SIDEBAR_HIDDEN_KEY = 'agentic.sidebarHidden'
// Above this width the sidebar is a column; at or below it is a drawer.
const DESKTOP_MIN_PX = 760
const sidebarWidth = ref(readStoredWidth())
const sidebarResizing = ref(false)
const sidebarHidden = ref(readStoredNumber(SIDEBAR_HIDDEN_KEY) === 1)

function isDesktop() {
  return window.innerWidth > DESKTOP_MIN_PX
}

function readStoredNumber(key) {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? null : Number(raw)
  } catch {
    // Storage can be blocked (private mode).
    return null
  }
}

function writeStored(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Not fatal: the choice still applies for this session.
  }
}

function readStoredWidth() {
  const stored = readStoredNumber(SIDEBAR_WIDTH_KEY)
  return stored !== null && stored > 0 ? clampSidebarWidth(stored) : SIDEBAR_DEFAULT_PX
}

function clampSidebarWidth(px) {
  return Math.round(Math.min(SIDEBAR_MAX_PX, Math.max(SIDEBAR_MIN_PX, px)))
}

function setSidebarWidth(px, persist = true) {
  sidebarWidth.value = clampSidebarWidth(px)
  if (!persist) return
  writeStored(SIDEBAR_WIDTH_KEY, String(sidebarWidth.value))
}

function setSidebarHidden(hidden) {
  sidebarHidden.value = hidden
  writeStored(SIDEBAR_HIDDEN_KEY, hidden ? '1' : '0')
}

// The menu button toggles the drawer on mobile and reveals the column on
// desktop, where it is only shown while the sidebar is hidden.
function toggleSidebar() {
  if (isDesktop()) setSidebarHidden(!sidebarHidden.value)
  else sidebarOpen.value = !sidebarOpen.value
}

// Whether the task list is on screen, for the toggle's state and label.
function sidebarExpanded() {
  return isDesktop() ? !sidebarHidden.value : sidebarOpen.value
}

function sidebarToggleLabel() {
  return sidebarExpanded() ? 'Hide the task list (⌘B)' : 'Show the task list (⌘B)'
}

let resizeFrom = null

function startResize(event) {
  // Below 760px the sidebar is an off-canvas drawer, not a column to size.
  if (!isDesktop() || event.button > 0) return
  resizeFrom = { x: event.clientX, width: sidebarWidth.value }
  sidebarResizing.value = true
  window.addEventListener('pointermove', moveResize)
  window.addEventListener('pointerup', endResize)
  window.addEventListener('pointercancel', endResize)
  event.preventDefault()
}

function moveResize(event) {
  if (!resizeFrom) return
  // Not persisted until the drag ends, so a drag writes storage once.
  setSidebarWidth(resizeFrom.width + (event.clientX - resizeFrom.x), false)
}

function endResize() {
  if (!resizeFrom) return
  resizeFrom = null
  sidebarResizing.value = false
  window.removeEventListener('pointermove', moveResize)
  window.removeEventListener('pointerup', endResize)
  window.removeEventListener('pointercancel', endResize)
  setSidebarWidth(sidebarWidth.value)
}

function resetSidebarWidth() {
  setSidebarWidth(SIDEBAR_DEFAULT_PX)
}

// The handle is a separator the keyboard can drive: arrows nudge it, Home/End
// jump to the bounds, Enter restores the default.
function onResizerKeydown(event) {
  const step = event.shiftKey ? 40 : 10
  if (event.key === 'ArrowLeft') setSidebarWidth(sidebarWidth.value - step)
  else if (event.key === 'ArrowRight') setSidebarWidth(sidebarWidth.value + step)
  else if (event.key === 'Home') setSidebarWidth(SIDEBAR_MIN_PX)
  else if (event.key === 'End') setSidebarWidth(SIDEBAR_MAX_PX)
  else if (event.key === 'Enter') resetSidebarWidth()
  else return
  event.preventDefault()
}

async function loadIssues() {
  if (!importRepo.value) return
  loadingIssues.value = true
  try {
    issues.value = await api.github.issues({ repository_id: importRepo.value, limit: 25 })
    if (!issues.value.length) store.notify('No open issues in that repository')
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    loadingIssues.value = false
  }
}

// Paste an issue/PR or Slack thread URL into one field; the source is detected.
let urlTimer
function onImportInput() {
  clearTimeout(urlTimer)
  const url = importUrl.value.trim()
  if (!url) {
    resetImport()
    return
  }
  if (SLACK_URL_RE.test(url)) {
    applySlackImport(url)
    return
  }
  if (GITHUB_ISSUE_RE.test(url)) {
    urlTimer = setTimeout(previewFromUrl, 500)
  }
}

async function previewFromUrl() {
  const url = importUrl.value.trim()
  if (!GITHUB_ISSUE_RE.test(url)) return
  loadingIssue.value = true
  try {
    applyIssue(await api.github.issue(url))
  } catch (e) {
    store.notify(e.message, true)
  } finally {
    loadingIssue.value = false
  }
}

function applyIssue(issue) {
  importKind.value = 'github'
  pickedIssue.value = issue.number
  importUrl.value = issue.url || importUrl.value
  draft.value.slack_url = ''
  draft.value.title = issue.title
  draft.value.description = issue.body
  draft.value.github_url = issue.url
  importPrefill = { title: issue.title, description: issue.body }
}

function applySlackImport(url) {
  if (importKind.value === 'github') undoGithubPrefill()
  importKind.value = 'slack'
  pickedIssue.value = null
  draft.value.github_url = ''
  draft.value.slack_url = url
}

// Undo the fields a GitHub preview filled, but only where the user has not edited them.
function undoGithubPrefill() {
  if (draft.value.title === importPrefill.title) draft.value.title = ''
  if (draft.value.description === importPrefill.description) draft.value.description = ''
  importPrefill = { title: '', description: '' }
}

function resetImport() {
  if (importKind.value === 'github') undoGithubPrefill()
  importKind.value = ''
  pickedIssue.value = null
  draft.value.github_url = ''
  draft.value.slack_url = ''
}

function pickIssue(issue) {
  applyIssue(issue)
}

function clearImport() {
  resetImport()
  importUrl.value = ''
}

async function createTask() {
  if (!draft.value.title.trim() && !draft.value.github_url && !draft.value.slack_url.trim()) return
  try {
    const task = await api.tasks.create({
      ...draft.value,
      priority: Number(draft.value.priority),
      repository_ids: [...draft.value.repository_ids],
      group_id: draft.value.group_id || null,
      github_url: draft.value.github_url || null,
      slack_url: draft.value.slack_url.trim() || null
    })
    showNew.value = false
    resetDraft()
    await refresh()
    router.push(`/task/${task.id}`)
  } catch (e) {
    store.notify(e.message, true)
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onGlobalKeydown)
  window.addEventListener('touchstart', beginSwipe)
  window.addEventListener('touchmove', moveSwipe)
  window.addEventListener('touchend', endSwipe)
  window.addEventListener('touchcancel', cancelSwipe)
  await refresh()
  await store.loadGroups().catch(() => {})
  await store.loadRepositories().catch(() => {})
  await store.loadPeople().catch(() => {})
  await store.loadItems().catch(() => {})
  await store.loadSettings().catch(() => {})
})
onUnmounted(() => {
  window.removeEventListener('keydown', onGlobalKeydown)
  window.removeEventListener('touchstart', beginSwipe)
  window.removeEventListener('touchmove', moveSwipe)
  window.removeEventListener('touchend', endSwipe)
  window.removeEventListener('touchcancel', cancelSwipe)
  window.removeEventListener('pointermove', moveResize)
  window.removeEventListener('pointerup', endResize)
  window.removeEventListener('pointercancel', endResize)
  stopHints()
})
</script>

<template>
  <div
    class="app"
    :class="{
      'sidebar-open': sidebarOpen,
      'sidebar-dragging': sidebarDragging,
      'sidebar-resizing': sidebarResizing,
      'sidebar-hidden': sidebarHidden
    }"
    :style="{ '--sidebar-width': `${sidebarWidth}px` }"
  >
    <aside class="sidebar" :style="sidebarDragStyle">
      <div class="side-brand">
        <router-link to="/" class="brand">
          <svg viewBox="0 0 512 512" aria-hidden="true">
            <path
              d="M160 168 L256 128 L352 168 M160 168 L160 288 L256 344 L352 288 L352 168 M160 288 L256 248 L352 288"
              stroke="#6ee7b7"
              stroke-width="16"
              fill="none"
              stroke-linecap="round"
            />
            <g fill="#6ee7b7">
              <circle cx="256" cy="128" r="26" />
              <circle cx="160" cy="168" r="18" />
              <circle cx="352" cy="168" r="18" />
              <circle cx="256" cy="248" r="20" />
              <circle cx="160" cy="288" r="18" />
              <circle cx="352" cy="288" r="18" />
              <circle cx="256" cy="344" r="26" />
            </g>
          </svg>
          <span>Agentic</span>
        </router-link>
        <button class="btn sm sidebar-close" aria-label="Close task list" @click="sidebarOpen = false">
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none" />
          </svg>
        </button>
      </div>
      <div class="side-scroll">
        <div v-if="store.loading && !store.tasks.length" class="empty"><span class="spinner"></span></div>
        <div v-else-if="!sidebarTasks.length" class="empty">
          {{ store.tasks.length ? 'All caught up.' : 'No tasks yet.' }}
        </div>
        <div v-for="p in sidebarTasks" :key="p.id" class="task-card" :class="{ active: route.params.id === p.id }">
          <SearchSelect
            class="task-status-select"
            variant="icon"
            :model-value="p.status"
            :options="statusOptions"
            :sort="false"
            title="Change status"
            @update:model-value="(value) => changeStatus(p, value)"
          />
          <router-link :to="`/task/${p.id}`" class="task-link" @click="sidebarOpen = false">
            <span class="t">{{ p.title }}</span>
            <span v-if="p.next_steps?.length" class="badge steps">{{
              p.next_steps.filter((s) => !s.done).length
            }}</span>
            <span class="faint when">{{ timeAgo(p.updated_at) }}</span>
          </router-link>
        </div>
      </div>

      <nav class="sidebar-nav" aria-label="Primary">
        <div class="sidebar-nav-actions">
          <button
            class="palette-trigger"
            title="Command palette (Ctrl/Cmd+K)"
            aria-label="Open command palette"
            @click="paletteOpen = true"
          >
            <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
              <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2" />
              <path d="M20 20l-3.5-3.5" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            </svg>
            <span class="palette-label">Search</span>
            <kbd class="palette-kbd">⌘K</kbd>
          </button>
          <button class="btn primary new-task" title="New task (Ctrl/Cmd+N)" @click="showNew = true">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
              <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none" />
            </svg>
            New task
          </button>
        </div>
        <div class="sidebar-nav-links">
          <router-link
            to="/"
            class="nav-link"
            :class="{ active: route.name === 'tasks' }"
            title="Tasks"
            aria-label="Tasks"
            @click="sidebarOpen = false"
          >
            <Icon name="tasks" />
          </router-link>
          <router-link
            to="/inbox"
            class="nav-link"
            :class="{ active: route.name === 'inbox' }"
            title="Inbox"
            aria-label="Inbox"
            @click="sidebarOpen = false"
          >
            <Icon name="inbox" />
            <span v-if="store.inboxCount" class="nav-badge" aria-hidden="true">{{ store.inboxCount }}</span>
          </router-link>
          <router-link
            to="/stack"
            class="nav-link"
            :class="{ active: route.name === 'stack' }"
            title="Stack"
            aria-label="Stack"
            @click="sidebarOpen = false"
          >
            <Icon name="stack" />
          </router-link>
          <router-link
            to="/gantt"
            class="nav-link"
            :class="{ active: route.name === 'gantt' }"
            title="Gantt"
            aria-label="Gantt"
            @click="sidebarOpen = false"
          >
            <Icon name="gantt" />
          </router-link>
          <router-link
            to="/graph"
            class="nav-link"
            :class="{ active: route.name === 'graph' }"
            title="Graph"
            aria-label="Graph"
            @click="sidebarOpen = false"
          >
            <Icon name="graph" />
          </router-link>
          <router-link
            to="/metrics"
            class="nav-link"
            :class="{ active: route.name === 'metrics' }"
            title="Metrics"
            aria-label="Metrics"
            @click="sidebarOpen = false"
          >
            <Icon name="metrics" />
          </router-link>
          <router-link
            to="/items"
            class="nav-link"
            :class="{ active: route.name === 'items' }"
            title="Items"
            aria-label="Items"
            @click="sidebarOpen = false"
          >
            <Icon name="items" />
          </router-link>
          <router-link
            to="/people"
            class="nav-link"
            :class="{ active: route.name === 'people' || route.name === 'person' }"
            title="People"
            aria-label="People"
            @click="sidebarOpen = false"
          >
            <Icon name="people" />
          </router-link>
          <router-link
            to="/repositories"
            class="nav-link"
            :class="{ active: route.name === 'repositories' || route.name === 'repository' }"
            title="Repositories"
            aria-label="Repositories"
            @click="sidebarOpen = false"
          >
            <Icon name="repositories" />
          </router-link>
          <router-link
            to="/settings"
            class="nav-link"
            :class="{ active: route.name === 'settings' }"
            title="Settings"
            aria-label="Settings"
            @click="sidebarOpen = false"
          >
            <Icon name="settings" />
          </router-link>
        </div>
      </nav>
      <div
        class="sidebar-resizer"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize task list"
        :aria-valuenow="sidebarWidth"
        :aria-valuemin="SIDEBAR_MIN_PX"
        :aria-valuemax="SIDEBAR_MAX_PX"
        tabindex="0"
        title="Drag to resize, double-click to reset"
        @pointerdown="startResize"
        @keydown="onResizerKeydown"
        @dblclick="resetSidebarWidth"
      ></div>
    </aside>

    <div v-if="sidebarOpen || sidebarDragging" class="sidebar-backdrop" @click="sidebarOpen = false"></div>

    <main class="main">
      <button
        class="btn menu-btn"
        data-no-hint
        :title="sidebarToggleLabel()"
        :aria-label="sidebarToggleLabel()"
        :aria-expanded="sidebarExpanded()"
        @click="toggleSidebar"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <rect x="3" y="4.5" width="18" height="15" rx="2.6" fill="none" stroke="currentColor" stroke-width="1.7" />
          <path d="M9.1 5.4v13.2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" fill="none" />
        </svg>
      </button>
      <router-view :key="route.fullPath" @changed="refresh" />
    </main>

    <div v-if="showNew" class="modal-backdrop" @click.self="showNew = false">
      <div class="modal">
        <h1 style="margin-bottom: 14px">New task</h1>

        <div class="field">
          <label>Import from GitHub or Slack (optional)</label>
          <input
            v-model="importUrl"
            class="input"
            placeholder="Paste an issue, PR, or Slack thread URL…"
            @input="onImportInput"
            @keyup.enter="previewFromUrl"
          />
          <p v-if="loadingIssue" class="faint" style="margin: 6px 0 0"><span class="spinner"></span> Loading issue…</p>
          <p v-else-if="pickedIssue" class="faint" style="margin: 6px 0 0">
            Importing <a :href="draft.github_url" target="_blank">#{{ pickedIssue }}</a>
            <button class="btn sm ghost" @click="clearImport">clear</button>
          </p>
          <p v-else-if="draft.slack_url" class="faint" style="margin: 6px 0 0">
            Importing the Slack thread; an agent names the task and summarizes the discussion.
            <button class="btn sm ghost" @click="clearImport">clear</button>
          </p>

          <details style="margin-top: 8px">
            <summary class="faint" style="cursor: pointer">or pick from a repository</summary>
            <div class="row" style="margin-top: 8px">
              <SearchSelect
                v-model="importRepo"
                class="grow"
                :options="importRepoOptions"
                placeholder="Choose a repository…"
              />
              <button class="btn" :disabled="!importRepo || loadingIssues" @click="loadIssues">
                <span v-if="loadingIssues" class="spinner"></span> Load issues
              </button>
            </div>
            <input
              v-if="issues.length"
              v-model="issueFilter"
              class="input"
              style="margin-top: 8px"
              placeholder="Filter issues…"
            />
            <div v-if="issues.length" class="issue-list">
              <button v-for="issue in sortedIssues" :key="issue.number" class="issue-row" @click="pickIssue(issue)">
                <span class="badge ok">{{ issue.state.toLowerCase() }}</span>
                <span class="grow">#{{ issue.number }} {{ issue.title }}</span>
                <span v-if="issue.author" class="faint">{{ issue.author }}</span>
              </button>
            </div>
            <p v-if="!githubRepos.length" class="faint" style="margin: 6px 0 0">
              No GitHub repositories registered. Add one in <router-link to="/repositories">Repositories</router-link>.
            </p>
          </details>
        </div>

        <div class="field">
          <label>Title</label>
          <input v-model="draft.title" class="input" placeholder="What needs to be solved?" @keyup.enter="createTask" />
        </div>
        <div class="field">
          <label>Description</label>
          <textarea v-model="draft.description" class="textarea" placeholder="Context, links, anything…"></textarea>
        </div>
        <div class="field">
          <label>Status</label>
          <SearchSelect v-model="draft.status" :options="statusOptions" :sort="false" placeholder="Status" />
        </div>
        <div class="field">
          <label>Priority</label>
          <SearchSelect v-model="draft.priority" :options="priorityOptions" :sort="false" placeholder="Priority" />
        </div>
        <div class="field">
          <label>Deadline (optional)</label>
          <DeadlinePicker v-model="draft.deadline" />
        </div>
        <div class="field">
          <label>Tags (optional)</label>
          <TagInput v-model="draft.tags" :suggestions="store.tags" placeholder="Add tags…" />
        </div>
        <div class="field">
          <label>Repository group (optional)</label>
          <SearchSelect v-model="draft.group_id" :options="groupOptions" placeholder="None" />
          <p class="faint" style="margin: 6px 0 0">Picking a group fills in its repositories below.</p>
        </div>
        <div class="field">
          <label>Repositories (optional)</label>
          <RepositorySelect
            v-model="draft.repository_ids"
            :repositories="store.repositories"
            empty-label="none registered"
          />
          <div v-if="lastUsedRepositories.length" class="row" style="margin-top: 6px">
            <span class="faint">last used:</span>
            <button
              v-for="repo in lastUsedRepositories"
              :key="repo.id"
              class="chip chip-add"
              title="Add this repository"
              @click="addRepository(repo.id)"
            >
              + {{ repo.name }}
            </button>
          </div>
        </div>
        <div class="row" style="justify-content: flex-end">
          <button class="btn ghost" @click="showNew = false">Cancel</button>
          <button
            class="btn primary"
            :disabled="!draft.title.trim() && !draft.github_url && !draft.slack_url.trim()"
            @click="createTask"
          >
            Create
          </button>
        </div>
      </div>
    </div>

    <div v-if="store.toast" class="toast" :class="{ err: store.toast.isError }">{{ store.toast.message }}</div>

    <div v-if="store.hintMode" class="hint-banner">
      Type the label over a control to focus it · <span class="mono">Enter</span> to confirm a shorter label ·
      <span class="mono">Backspace</span> to undo · <span class="mono">Esc</span> to exit
    </div>

    <span
      v-for="badge in hintBadges"
      v-show="!badge.hidden"
      :key="badge.key"
      class="hint-badge"
      :class="{ dimmed: badge.dimmed }"
      :style="{ left: badge.left + 'px', top: badge.top + 'px' }"
      >{{ badge.key }}</span
    >

    <CommandPalette v-if="paletteOpen" :items="paletteItems" @select="runPaletteItem" @close="paletteOpen = false" />
  </div>
</template>
