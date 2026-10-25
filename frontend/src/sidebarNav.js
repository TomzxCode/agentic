// The sidebar's bottom nav: which page icons exist, which are shown, and in
// what order. A per-device preference (localStorage), like the sidebar width,
// so it never touches the server's settings table. The state is module-level
// because the shell renders the nav while the Settings section edits it, and
// both must see the same choice without a reload.
import { computed, reactive } from 'vue'

// The pages a user can show in the nav, in their default order. `routeNames`
// are the route names that light the icon, so a detail route keeps its list
// icon lit (a person page lights People, a repository page lights Repositories).
export const SIDEBAR_NAV_ITEMS = [
  { id: 'stack', label: 'Stack', to: '/stack', icon: 'stack', routeNames: ['stack'] },
  { id: 'tasks', label: 'Tasks', to: '/', icon: 'tasks', routeNames: ['tasks'] },
  { id: 'inbox', label: 'Inbox', to: '/inbox', icon: 'inbox', routeNames: ['inbox'], badge: 'inbox' },
  { id: 'reviews', label: 'Review queue', to: '/reviews', icon: 'reviews', routeNames: ['reviews'] },
  { id: 'my-pulls', label: 'My PRs', to: '/my-pulls', icon: 'pulls', routeNames: ['my-pulls'] },
  { id: 'feedback', label: 'PR feedback', to: '/feedback', icon: 'feedback', routeNames: ['feedback'] },
  { id: 'decisions', label: 'Decisions', to: '/decisions', icon: 'decisions', routeNames: ['decisions'] },
  { id: 'gantt', label: 'Gantt', to: '/gantt', icon: 'gantt', routeNames: ['gantt'] },
  { id: 'graph', label: 'Graph', to: '/graph', icon: 'graph', routeNames: ['graph'] },
  { id: 'events', label: 'Events', to: '/events', icon: 'events', routeNames: ['events'] },
  { id: 'metrics', label: 'Metrics', to: '/metrics', icon: 'metrics', routeNames: ['metrics'] },
  { id: 'items', label: 'Items', to: '/items', icon: 'items', routeNames: ['items'] },
  { id: 'people', label: 'People', to: '/people', icon: 'people', routeNames: ['people', 'person', 'person-new'] },
  {
    id: 'repositories',
    label: 'Repositories',
    to: '/repositories',
    icon: 'repositories',
    routeNames: ['repositories', 'repository']
  },
  { id: 'schedules', label: 'Scheduled tasks', to: '/schedules', icon: 'schedule', routeNames: ['schedules'] },
  { id: 'graphs', label: 'Execution graphs', to: '/graphs', icon: 'graphs', routeNames: ['graphs'] },
  { id: 'on-call', label: 'On call', to: '/on-call', icon: 'slack', routeNames: ['on-call', 'oncall'] },
  { id: 'settings', label: 'Settings', to: '/settings', icon: 'settings', routeNames: ['settings'] }
]

const STORAGE_KEY = 'agentic.sidebarNav'
const DEFAULT_ORDER = SIDEBAR_NAV_ITEMS.map((item) => item.id)
const KNOWN_IDS = new Set(DEFAULT_ORDER)

const state = reactive({ order: [...DEFAULT_ORDER], hidden: [] })

// Fold whatever was stored onto the current item set: drop ids we no longer
// know, drop duplicates, and append any item added to the code since the choice
// was saved, so a new page shows up instead of being lost.
export function normalizeSidebarNav(stored) {
  const order = []
  const seen = new Set()
  const storedOrder = Array.isArray(stored && stored.order) ? stored.order : []
  for (const id of storedOrder) {
    if (KNOWN_IDS.has(id) && !seen.has(id)) {
      order.push(id)
      seen.add(id)
    }
  }
  for (const id of DEFAULT_ORDER) if (!seen.has(id)) order.push(id)

  const hidden = []
  const storedHidden = Array.isArray(stored && stored.hidden) ? stored.hidden : []
  for (const id of storedHidden) if (KNOWN_IDS.has(id) && !hidden.includes(id)) hidden.push(id)

  return { order, hidden }
}

function readStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    // Storage can be blocked (private mode) or hold corrupt JSON.
    return null
  }
}

export function loadSidebarNav() {
  const stored = normalizeSidebarNav(readStored())
  state.order = stored.order
  state.hidden = stored.hidden
}

function persist() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ order: state.order, hidden: state.hidden }))
  } catch {
    // Not fatal: the choice still applies for this session.
  }
}

export function setNavHidden(id, hidden) {
  if (!KNOWN_IDS.has(id)) return
  if (hidden) {
    if (!state.hidden.includes(id)) state.hidden = [...state.hidden, id]
  } else {
    state.hidden = state.hidden.filter((entry) => entry !== id)
  }
  persist()
}

// Move an item so it lands at `to`, clamping to the list bounds; a drag uses
// this directly, and the keyboard nudges through `moveNavItem` below.
export function moveNavItemTo(id, to) {
  const from = state.order.indexOf(id)
  if (from === -1) return
  const target = Math.max(0, Math.min(state.order.length - 1, to))
  if (target === from) return
  const order = [...state.order]
  order.splice(from, 1)
  order.splice(target, 0, id)
  state.order = order
  persist()
}

// Move an item one slot up (delta -1) or down (delta +1); a no-op at the ends.
export function moveNavItem(id, delta) {
  const from = state.order.indexOf(id)
  if (from === -1) return
  moveNavItemTo(id, from + delta)
}

export function resetSidebarNav() {
  state.order = [...DEFAULT_ORDER]
  state.hidden = []
  persist()
}

// Every item in configured order, each carrying its hidden flag.
export const sidebarNavList = computed(() =>
  state.order.map((id) => ({ ...SIDEBAR_NAV_ITEMS.find((item) => item.id === id), hidden: state.hidden.includes(id) }))
)

// What the shell renders: the items the user has not hidden.
export const visibleSidebarNav = computed(() => sidebarNavList.value.filter((item) => !item.hidden))

// How many columns the nav grid uses: six at most, so the items fill two even
// rows, and fewer when the user hides items so the remaining icons do not shrink
// into a corner.
export const sidebarNavColumns = computed(() => Math.max(1, Math.min(6, visibleSidebarNav.value.length)))

// True when the choice differs from the default order or visibility, so the
// Settings section can offer a reset only when there is something to reset.
export const sidebarNavCustomized = computed(
  () => state.hidden.length > 0 || state.order.some((id, index) => id !== DEFAULT_ORDER[index])
)
